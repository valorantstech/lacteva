"""Firebase Cloud Messaging, HTTP v1 (WO-77).

`HttpPushProvider` speaks a vendor-neutral contract — a static bearer key and
a flat body — and FCM speaks neither: it wants a short-lived OAuth2 access
token minted from a service-account key, and a nested envelope whose `data`
values must every one be strings. So this adapter stands BESIDE the generic
one, implements the same `ChannelProvider` protocol, and is chosen with
`LACTEVA_NOTIFICATION_PUSH_PROVIDER=fcm`. Nothing else in the notification
module knows which of the two is installed.

Three properties decide whether this survives a month in production, and each
has a test:

* **One token, not one per message.** The access token is cached and refreshed
  five minutes before it expires, behind a single-flight lock, so four hundred
  bills on the first of the month cost one round trip to Google's token
  endpoint (the same property WO-73 required of the portal's refresh).
* **A dead token is forgotten, not retried.** `UNREGISTERED` — and a 400 that
  names the registration token — raise `DeadTokenError`, on which the service
  drops the device registration. A retry cannot resurrect an uninstalled app,
  and a dead token retried forever hides the live ones behind it.
* **A 401 is a stale access token, once.** Mint a fresh one and retry the
  send exactly once; a second 401 is a credential problem and is permanent.
  `429` and `5xx` are transient and go back to the relay's own retry and
  backoff — there is no second retry mechanism here.

The service-account key is the one real secret of the push channel. It is read
from a file on the host, held in memory as the fields the signer needs, and
never appears in a log line, an error message, a `DeliveryResult` or a
response — nor does the access token, nor a full device token. SEC-003 / F-04.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from platform_core.core.config import get_settings
from platform_core.modules.notification.providers import (
    ACCEPTED,
    DeadTokenError,
    DeliveryResult,
    OutboundMessage,
    PermanentSendError,
    ProviderSendError,
    assert_may_reach_the_network,
)

log = structlog.get_logger(__name__)

#: The only scope this adapter ever asks for.
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
#: Refresh this long before the token's stated expiry. Google issues hour-long
#: tokens; five minutes is wide enough for a slow relay and narrow enough that
#: a token is reused for the whole month-end batch.
REFRESH_MARGIN_SECONDS = 300
#: How long the signed assertion asks to live. Google caps it at one hour.
ASSERTION_LIFETIME_SECONDS = 3600


@dataclass(frozen=True)
class ServiceAccount:
    """The three fields the signer needs, and nothing else from the file."""

    client_email: str
    private_key: str
    token_uri: str
    project_id: str

    @classmethod
    def load(cls, path: str) -> ServiceAccount:
        file = Path(path)
        try:
            data = json.loads(file.read_text())
        except FileNotFoundError as exc:
            raise ValueError(
                f"LACTEVA_NOTIFICATION_FCM_CREDENTIALS_PATH does not exist: {file.name}"
            ) from exc
        except (OSError, ValueError) as exc:
            # Deliberately not the exception text: a JSON error quotes the
            # document, and this document is a private key.
            raise ValueError(
                f"LACTEVA_NOTIFICATION_FCM_CREDENTIALS_PATH could not be read as a "
                f"service-account key: {file.name} ({type(exc).__name__})"
            ) from None
        if not isinstance(data, dict) or data.get("type") != "service_account":
            raise ValueError(
                f"LACTEVA_NOTIFICATION_FCM_CREDENTIALS_PATH is not a service-account key: "
                f"{file.name}"
            )
        missing = [k for k in ("client_email", "private_key", "token_uri") if not data.get(k)]
        if missing:
            raise ValueError(f"service-account key {file.name} is missing {', '.join(missing)}")
        return cls(
            client_email=str(data["client_email"]),
            private_key=str(data["private_key"]),
            token_uri=str(data["token_uri"]),
            project_id=str(data.get("project_id") or ""),
        )

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return f"ServiceAccount(client_email={self.client_email!r})"


class AccessTokenSource:
    """One access token at a time, refreshed early, minted single-flight."""

    def __init__(self, account: ServiceAccount, *, timeout: float) -> None:
        self._account = account
        self._timeout = timeout
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        #: How many times the token endpoint was actually called. Read by the
        #: test that proves four hundred sends cost one token.
        self.mints = 0

    def _fresh(self, now: float) -> bool:
        return self._token is not None and now < self._expires_at - REFRESH_MARGIN_SECONDS

    async def get(self, *, force: bool = False) -> str:
        now = time.time()
        if not force and self._fresh(now):
            return self._token  # type: ignore[return-value]
        async with self._lock:
            # Whoever held the lock may have minted while we waited: the
            # second, third and four-hundredth caller all find it fresh.
            now = time.time()
            if not force and self._fresh(now):
                return self._token  # type: ignore[return-value]
            if force and self._token is not None:
                # A forced refresh is one caller's discovery that the token is
                # stale; the others queued behind it get the new one.
                self._token = None
            self._token, self._expires_at = await self._mint(now)
            return self._token

    async def _mint(self, now: float) -> tuple[str, float]:
        import httpx
        import jwt

        assertion = jwt.encode(
            {
                "iss": self._account.client_email,
                "scope": FCM_SCOPE,
                "aud": self._account.token_uri,
                "iat": int(now),
                "exp": int(now) + ASSERTION_LIFETIME_SECONDS,
            },
            self._account.private_key,
            algorithm="RS256",
        )
        self.mints += 1
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._account.token_uri,
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": assertion,
                    },
                )
        except httpx.TimeoutException as exc:
            raise ProviderSendError(f"fcm token endpoint timeout after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderSendError(
                f"fcm token endpoint unreachable: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 500:
            raise ProviderSendError(f"fcm token endpoint error {response.status_code}")
        if response.status_code >= 400:
            # A refused assertion is a credential problem: the key is revoked,
            # the clock is wrong, the account was deleted. Retrying does not
            # help and the body is not quoted — it can echo the assertion.
            raise PermanentSendError(
                f"fcm token endpoint refused the service account ({response.status_code})"
            )
        try:
            body = response.json()
            token = str(body["access_token"])
            expires_in = float(body.get("expires_in", ASSERTION_LIFETIME_SECONDS))
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderSendError("fcm token endpoint returned no access token") from exc
        log.info("fcm_access_token_minted", expires_in=int(expires_in))
        return token, now + expires_in


class FcmPushProvider:
    """`ChannelProvider` for the push channel over FCM HTTP v1."""

    #: FCM error `status` values (google.rpc.Code) that mean the ADDRESS is dead.
    DEAD_TOKEN_STATUSES = frozenset({"UNREGISTERED", "NOT_FOUND"})
    #: Message rejected as sent; the token may well be fine.
    PERMANENT_STATUSES = frozenset({400, 403, 404})
    #: Transient by FCM's own contract: back off and try again.
    TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(self, channel: str = "push") -> None:
        self.name = "fcm-push"
        self._channel = channel
        settings = get_settings()
        self._project_id = settings.notification_fcm_project_id
        path = settings.notification_fcm_credentials_path
        if not (self._project_id and path):
            raise ValueError(
                "LACTEVA_NOTIFICATION_FCM_PROJECT_ID and "
                "LACTEVA_NOTIFICATION_FCM_CREDENTIALS_PATH must both be set when the push "
                "provider is 'fcm'"
            )
        self._timeout = settings.push_timeout_seconds
        self._account = ServiceAccount.load(path)
        if self._account.project_id and self._account.project_id != self._project_id:
            raise ValueError(
                "LACTEVA_NOTIFICATION_FCM_PROJECT_ID does not match the project the "
                "service-account key belongs to"
            )
        self.tokens = AccessTokenSource(self._account, timeout=self._timeout)
        self._url = FCM_SEND_URL.format(project_id=self._project_id)

    # --- the envelope ---------------------------------------------------------

    @staticmethod
    def envelope(message: OutboundMessage) -> dict[str, Any]:
        """The FCM v1 message. `data` is strings only — asserted, because FCM
        rejects the WHOLE message otherwise and this is the single most common
        way a first FCM integration fails."""
        data = {
            "template": message.template_key,
            "notification_id": str(message.notification_id),
            "channel": message.channel,
        }
        assert_string_data(data)
        return {
            "message": {
                "token": message.recipient,
                "notification": {"title": message.title or "Lacteva", "body": message.body},
                "data": data,
                "android": {
                    "priority": "high",
                    # The channel the app creates on first run; Android shows
                    # its name in system settings (WO-77 Part B).
                    "notification": {"channel_id": "lacteva"},
                },
            }
        }

    # --- send -----------------------------------------------------------------

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        assert_may_reach_the_network(self.name)
        envelope = self.envelope(message)
        response = await self._post(envelope, await self.tokens.get())
        if response.status_code == 401:
            # A stale access token, once. The second 401 is a credential
            # problem and falls through to the permanent branch below.
            response = await self._post(envelope, await self.tokens.get(force=True))
        return self._classify(response, message)

    async def _post(self, envelope: dict[str, Any], access_token: str):
        import httpx

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; UTF-8",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                return await client.post(self._url, json=envelope, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderSendError(f"fcm timeout after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderSendError(f"fcm unreachable: {type(exc).__name__}") from exc

    def _classify(self, response, message: OutboundMessage) -> DeliveryResult:
        status = response.status_code
        if status < 300:
            try:
                name = str(response.json().get("name") or "")
            except (ValueError, AttributeError):
                name = ""
            log.info(
                "push_sent",
                provider=self.name,
                template=message.template_key,
                language=message.language,
            )
            return DeliveryResult(
                provider_message_id=name or message.idempotency_key,
                status=ACCEPTED,
                metadata={"http_status": status},
            )
        code, detail = _error_of(response)
        if status == 404 or code in self.DEAD_TOKEN_STATUSES:
            raise DeadTokenError(f"fcm: registration token is no longer valid ({code or status})")
        if status == 400 and code == "INVALID_ARGUMENT" and "token" in detail.lower():
            # "The registration token is not a valid FCM registration token":
            # FCM's wording for a token that never was, or rotated away.
            raise DeadTokenError("fcm: registration token is not valid (INVALID_ARGUMENT)")
        if status == 401:
            raise PermanentSendError("fcm refused the service account's access token (401)")
        if status in self.PERMANENT_STATUSES:
            raise PermanentSendError(f"fcm rejected the message ({code or status}): {detail}")
        if status in self.TRANSIENT_STATUSES or status >= 500:
            raise ProviderSendError(f"fcm unavailable ({code or status}); will retry")
        raise ProviderSendError(f"fcm unexpected response ({status}); will retry")


def assert_string_data(data: dict[str, Any]) -> None:
    """FCM rejects the WHOLE message if any `data` value is not a string.
    Refused here, before a byte leaves the process, as a permanent failure —
    a retry cannot turn an integer into a string."""
    for key, value in data.items():
        if not isinstance(value, str):
            raise PermanentSendError(f"fcm data value {key!r} is not a string")


def _error_of(response) -> tuple[str, str]:
    """FCM's `error.status` and a trimmed `error.message` — never the whole body,
    which echoes the request and with it the device token."""
    try:
        error = response.json().get("error") or {}
        code = str(error.get("status") or "")
        detail = str(error.get("message") or "")[:160].replace("\n", " ")
        return code, _without_tokens(detail)
    except (ValueError, AttributeError):
        return "", ""


def _without_tokens(text: str) -> str:
    """Strip anything that looks like a registration token from a detail line."""
    return " ".join(part for part in text.split() if len(part) < 40)


__all__ = ["AccessTokenSource", "FcmPushProvider", "ServiceAccount", "assert_string_data"]
