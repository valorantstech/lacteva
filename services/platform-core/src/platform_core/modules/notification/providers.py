"""Channel provider abstraction (NOT-001).

A provider is the thing that actually hands a rendered message to a channel.
The platform ships ADAPTERS ONLY — a logging adapter (which delegates to the
existing `Notifier` port, preserving that abstraction) and a placeholder
adapter that accepts and records without side effects. Real gateways (market
SMS providers, transactional email) are deployment concerns that implement
this same protocol; no provider-specific code lives in the platform.

Selection is configuration (`LACTEVA_NOTIFICATION_SMS_PROVIDER`,
`LACTEVA_NOTIFICATION_EMAIL_PROVIDER`), and providers can be swapped at
runtime through `register_provider` — the seam deployments and tests use.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from platform_core.core.config import get_settings
from platform_core.infrastructure.notifications import Notification, get_notifier

log = structlog.get_logger("notification.provider")


class ProviderSendError(Exception):
    """Delivery failed and is worth trying again.

    The base class is RETRYABLE, which keeps every pre-MSG-001 raiser
    behaving exactly as it did. Permanence is the special case and has to be
    claimed explicitly — the safe default when a provider says something
    unfamiliar is to try again, not to give up on a farmer's message.
    """


class PermanentSendError(ProviderSendError):
    """Delivery failed and will fail identically forever (MSG-001).

    An invalid phone number, a rejected sender id, a bad credential, a
    malformed request. Retrying these costs money on every attempt, delays
    the queue behind them, and cannot succeed.

    Before MSG-001 the retry engine had no way to be told this: every failure
    was retried to exhaustion, so one mistyped number consumed five gateway
    calls and five backoff windows.
    """


@dataclass(frozen=True)
class OutboundMessage:
    channel: str
    recipient: str
    title: str
    body: str
    language: str
    template_key: str
    notification_id: uuid.UUID

    @property
    def idempotency_key(self) -> str:
        """What the gateway should deduplicate on (MSG-001).

        The notification id, which is stable across every retry of this
        message — so a send that succeeded at the gateway but timed out on
        our side is recognised as a duplicate rather than delivered twice.
        The platform cannot prevent that on its own: only the gateway knows
        it already accepted the message.
        """
        return f"lacteva-{self.notification_id}"


@dataclass(frozen=True)
class DeliveryResult:
    """What a provider reports back (MSG-001).

    `send()` used to return a bare string, which was enough to write in the
    audit trail and not enough to operate: an operator asking "did it
    actually arrive?" had nothing to read, and a provider with a richer
    answer had nowhere to put it.
    """

    #: The gateway's own id. This is what a support conversation quotes.
    provider_message_id: str
    #: accepted | sent | delivered | unknown. Most gateways only ACCEPT
    #: synchronously and confirm delivery later over a webhook the platform
    #: does not yet receive — see MSG-001's technical debt.
    status: str = "accepted"
    #: Provider-specific fields worth keeping: cost, segment count, the
    #: gateway's own status string. Never credentials.
    metadata: dict[str, Any] = field(default_factory=dict)


ACCEPTED = "accepted"
DELIVERED = "delivered"
UNKNOWN = "unknown"


class ChannelProvider(Protocol):
    name: str

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        """Deliver, or raise.

        Raise `PermanentSendError` when a retry cannot help and
        `ProviderSendError` when it can. Getting that distinction wrong is
        the difference between five wasted gateway calls and a message that
        never gets sent.
        """
        ...


def mask_phone(value: str) -> str:
    """A phone number, safe to log (MSG-001).

    `+254700123456` becomes `+2547****3456`: enough to correlate a log line
    with a support conversation, not enough to be a contact list. Applied
    everywhere a recipient is logged, because a log that carries every
    supplier's number is a copy of the directory with weaker access control
    than the database it came from.
    """
    if not value:
        return ""
    if "@" in value:  # an email address
        name, _, domain = value.partition("@")
        head = name[:1]
        return f"{head}{'*' * max(len(name) - 1, 1)}@{domain}"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:5]}{'*' * (len(value) - 9)}{value[-4:]}"


class LoggingProvider:
    """Delegates to the platform `Notifier` port (preserved abstraction) and
    logs the rendered message. The dev/test default."""

    def __init__(self, channel: str):
        self.name = f"logging-{channel}"
        self._channel = channel

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        await get_notifier().send(
            Notification(
                id=message.notification_id,
                channel=self._channel,
                recipient=message.recipient,
                template_key=message.template_key,
                locale=message.language,
                payload={"title": message.title, "body": message.body},
            )
        )
        log.info(
            "notification_dispatched",
            channel=self._channel,
            template=message.template_key,
            recipient=mask_phone(message.recipient),
            language=message.language,
        )
        return DeliveryResult(
            provider_message_id=f"{self.name}:{message.notification_id}", status=ACCEPTED
        )


class PlaceholderProvider:
    """Accepts and records without any side effect — the stand-in until a
    market gateway is configured. Deliveries are marked sent so the pipeline
    is exercised end to end; nothing leaves the platform."""

    def __init__(self, channel: str):
        self.name = f"placeholder-{channel}"
        self._channel = channel

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        log.debug(
            "notification_placeholder",
            channel=self._channel,
            template=message.template_key,
            recipient=mask_phone(message.recipient),
        )
        return DeliveryResult(provider_message_id=f"{self.name}:{uuid.uuid4()}", status=ACCEPTED)


class DryRunProvider:
    """Renders and logs a real message without sending it (MSG-001).

    The difference from `PlaceholderProvider` is intent, and it matters
    operationally: placeholder means "no gateway is configured yet", dry-run
    means "a gateway IS configured and we are deliberately not using it".
    Staging runs in dry-run against production-shaped configuration, so a
    credential or sender-id mistake surfaces before it reaches a farmer.
    """

    def __init__(self, channel: str):
        self.name = f"dry-run-{channel}"
        self._channel = channel

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        log.info(
            "sms_dry_run",
            channel=self._channel,
            template=message.template_key,
            recipient=mask_phone(message.recipient),
            characters=len(message.body),
            segments=_segments(message.body),
        )
        return DeliveryResult(
            provider_message_id=f"{self.name}:{message.notification_id}",
            status=ACCEPTED,
            metadata={"dry_run": True, "segments": _segments(message.body)},
        )


class DisabledProvider:
    """Refuses to send, permanently (MSG-001).

    For a market that is not live, or a suspended gateway. `PermanentSendError`
    rather than silent success on purpose: a notification marked sent that
    was never sent is a lie the platform would then repeat to an operator
    asking why a supplier was not told.
    """

    def __init__(self, channel: str):
        self.name = f"disabled-{channel}"
        self._channel = channel

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        raise PermanentSendError(f"{self._channel} delivery is disabled by configuration")


def _segments(body: str) -> int:
    """SMS segment count — GSM-7 is 160 characters, 153 when concatenated;
    anything outside that alphabet forces UCS-2 at 70/67. Logged because
    segments are what a gateway bills, and a template that quietly crosses a
    boundary doubles the cost of every message it sends."""
    gsm = body.isascii()
    single, multi = (160, 153) if gsm else (70, 67)
    if len(body) <= single:
        return 1
    return -(-len(body) // multi)


class HttpSmsProvider:
    """A generic HTTP SMS gateway (MSG-001).

    **Vendor-neutral by construction.** The platform must not depend on one
    market's gateway — dairy markets differ by country and the same
    deployment may change provider without changing code. So this speaks a
    small, documented JSON contract configured entirely by environment, and
    classifies outcomes by HTTP STATUS, which every gateway agrees on even
    when their payloads do not.

    A gateway whose shape does not fit implements `ChannelProvider` and is
    installed with `register_provider` — that seam already existed and this
    class does not replace it.

    Classification, and the reasoning behind each:

    | Status | Verdict | Why |
    | --- | --- | --- |
    | 2xx | accepted | |
    | 400, 404, 422 | **permanent** | Malformed request or unknown number — identical on retry |
    | 401, 403 | **permanent** | A credential problem is fixed by an operator, not by waiting |
    | 408, 425, 429 | retry | Timeout or throttle; the backoff is exactly right |
    | 5xx | retry | The gateway's problem, not the message's |
    | timeout / network | retry | We cannot know whether it arrived, so we
      assume it did not — the idempotency key stops the double send |
    | unparseable body | accepted, `status=unknown` | A 2xx we cannot read is
      still a 2xx; failing it would resend a message the gateway took |
    """

    #: A retry cannot change the outcome, so do not spend a gateway call on it.
    PERMANENT_STATUSES = frozenset({400, 401, 402, 403, 404, 405, 409, 415, 422})

    def __init__(self, channel: str = "sms") -> None:
        self.name = "http-sms"
        self._channel = channel
        settings = get_settings()
        self._url = settings.sms_api_url
        self._api_key = settings.sms_api_key
        self._sender = settings.sms_sender_id
        self._timeout = settings.sms_timeout_seconds
        if not self._url:
            raise ValueError("LACTEVA_SMS_API_URL must be set when the sms provider is 'http'")

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        import httpx

        payload = {
            "to": message.recipient,
            "from": self._sender,
            "text": message.body,
            # The gateway deduplicates on this. Stable across every retry, so
            # a send that succeeded but timed out on our side is recognised
            # rather than delivered twice — the one double-send the platform
            # cannot prevent by itself.
            "client_reference": message.idempotency_key,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": message.idempotency_key,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            # We do not know whether it arrived. Assume it did not and retry;
            # the idempotency key is what makes that safe.
            raise ProviderSendError(f"gateway timeout after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderSendError(f"gateway unreachable: {type(exc).__name__}") from exc

        if response.status_code in self.PERMANENT_STATUSES:
            raise PermanentSendError(
                f"gateway rejected the message ({response.status_code}): "
                f"{_safe_detail(response.text)}"
            )
        if response.status_code >= 400:
            raise ProviderSendError(
                f"gateway error {response.status_code}: {_safe_detail(response.text)}"
            )

        try:
            body = response.json()
        except ValueError:
            # A 2xx we cannot parse is still a 2xx. Treating it as a failure
            # would resend a message the gateway has already accepted.
            log.warning("sms_unparseable_response", status=response.status_code)
            return DeliveryResult(
                provider_message_id=message.idempotency_key,
                status=UNKNOWN,
                metadata={"unparseable": True, "http_status": response.status_code},
            )
        if not isinstance(body, dict):
            log.warning("sms_unexpected_response_shape", status=response.status_code)
            return DeliveryResult(
                provider_message_id=message.idempotency_key,
                status=UNKNOWN,
                metadata={"http_status": response.status_code},
            )

        return DeliveryResult(
            provider_message_id=str(
                body.get("message_id") or body.get("id") or message.idempotency_key
            ),
            status=str(body.get("status") or ACCEPTED),
            metadata={
                "http_status": response.status_code,
                "segments": _segments(message.body),
                # Whatever the gateway says about cost, which is the number an
                # operator reconciles against an invoice.
                **{k: body[k] for k in ("cost", "currency", "parts") if k in body},
            },
        )


def _safe_detail(text: str) -> str:
    """A gateway error, trimmed and free of anything worth stealing.

    Error bodies echo the request often enough that a raw copy can carry the
    phone number, and occasionally the credential.
    """
    return (text or "")[:200].replace("\n", " ")


_PROVIDERS: dict[str, ChannelProvider] = {}


def register_provider(channel: str, provider: ChannelProvider) -> None:
    """Install a provider for a channel (deployment wiring; tests use it to
    inject failing or recording adapters)."""
    _PROVIDERS[channel] = provider


def reset_providers() -> None:
    _PROVIDERS.clear()


def get_provider(channel: str) -> ChannelProvider:
    if channel not in _PROVIDERS:
        settings = get_settings()
        configured = {
            "sms": settings.notification_sms_provider,
            "email": settings.notification_email_provider,
        }.get(channel, "logging")
        _PROVIDERS[channel] = _build(channel, configured)
    return _PROVIDERS[channel]


def _build(channel: str, configured: str) -> ChannelProvider:
    """Configuration to provider. One place, so a typo is a startup failure
    rather than a message that quietly goes nowhere."""
    builders = {
        "logging": LoggingProvider,
        "placeholder": PlaceholderProvider,
        "dry_run": DryRunProvider,
        "disabled": DisabledProvider,
        "http": HttpSmsProvider,
    }
    builder = builders.get(configured)
    if builder is None:
        raise ValueError(
            f"unknown {channel} provider {configured!r} — expected one of {sorted(builders)}"
        )
    return builder(channel)
