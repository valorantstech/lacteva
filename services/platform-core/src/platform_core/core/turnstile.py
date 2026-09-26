"""Cloudflare Turnstile, verified server-side (WO-103 · LACTEVA-AUTH-003).

The owner asked for "captcha or something" on the sign-up form. The sign-up
form is already bot-proof on its own — nothing proceeds without a
43-character one-time code — so the challenge goes there as asked AND where
bots actually attack: the forms with no secret. On this API that is the
invitation acceptance, the "forgot password" request, and sign-in once an
address or an IP has failed three times in fifteen minutes. The marketing
site's two lead forms are verified by the site's own server route with the
same secret.

Turnstile is free, usually invisible, needs no DNS change, and the widget in
the browser is decoration: the only thing that counts is this module asking
Cloudflare's siteverify API whether the token the browser sent is genuine,
on every protected request.

Keys at runtime: LACTEVA_TURNSTILE_SITE_KEY (public — the browser needs it)
and LACTEVA_TURNSTILE_SECRET_KEY (this module's). With no secret the check is
OFF — the forms work and the `turnstile` health probe says so, loudly, so a
deployment cannot believe it is protected when it is not. Cloudflare's
published test keys (`1x…` always passes, `2x…` always fails) are what
development uses; the test suite installs a fake that answers as those keys
would, so no test reaches the network.
"""

from __future__ import annotations

from typing import Protocol

import httpx
import structlog

from platform_core.core.config import get_settings
from platform_core.core.errors import AppError

log = structlog.get_logger("security.turnstile")

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

#: Cloudflare's published test secrets. Real siteverify honours them exactly
#: like this; the fake below mirrors it so a test never leaves the process.
TEST_SECRET_ALWAYS_PASSES = "1x0000000000000000000000000000000AA"  # noqa: S105 — published test value
TEST_SECRET_ALWAYS_FAILS = "2x0000000000000000000000000000000AA"  # noqa: S105 — published test value
TEST_SECRET_ALREADY_SPENT = "3x0000000000000000000000000000000AA"  # noqa: S105 — published test value
TEST_SITE_KEY_ALWAYS_PASSES = "1x00000000000000000000AA"


class CaptchaRequired(AppError):
    """The request needed a genuine Turnstile token and did not carry one —
    or carried one Cloudflare would not vouch for. 400, not 403: the caller
    is not forbidden, the form has to be completed."""

    status_code = 400
    code = "captcha_required"
    message_key = "error.captcha_required"


class TurnstileVerifier(Protocol):
    @property
    def enabled(self) -> bool: ...

    async def verify(self, token: str, remote_ip: str | None) -> bool: ...


class HttpTurnstileVerifier:
    """The real thing: one POST to siteverify per protected request."""

    def __init__(self, secret: str, *, timeout: float = 5.0):
        self._secret = secret
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._secret)

    async def verify(self, token: str, remote_ip: str | None) -> bool:
        data = {"secret": self._secret, "response": token}
        if remote_ip and remote_ip != "unknown":
            data["remoteip"] = remote_ip
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(SITEVERIFY_URL, data=data)
        except httpx.HTTPError as exc:
            # Fail CLOSED. A challenge that cannot be verified is not a
            # challenge that was passed; the forms this guards are the ones
            # bots attack, and an outage of Cloudflare's verifier is rarer
            # than a bot.
            log.warning("turnstile.siteverify_unreachable", error=str(exc))
            return False
        if response.status_code != 200:
            log.warning("turnstile.siteverify_status", status=response.status_code)
            return False
        body = response.json()
        ok = bool(body.get("success"))
        if not ok:
            log.info("turnstile.rejected", codes=body.get("error-codes", []))
        return ok


class FakeTurnstileVerifier:
    """Answers as Cloudflare's test keys do, without the network. Installed
    by the test suite; also what a developer gets when the secret IS one of
    the published test secrets, so `1x…` in a `.env` behaves the same offline."""

    def __init__(self, secret: str = ""):
        self.secret = secret
        self.calls: list[tuple[str, str | None]] = []

    @property
    def enabled(self) -> bool:
        return bool(self.secret)

    async def verify(self, token: str, remote_ip: str | None) -> bool:
        self.calls.append((token, remote_ip))
        if not token:
            return False
        return self.secret == TEST_SECRET_ALWAYS_PASSES


_verifier: TurnstileVerifier | None = None


def get_turnstile_verifier() -> TurnstileVerifier:
    global _verifier
    if _verifier is None:
        secret = get_settings().turnstile_secret_key
        if secret in (
            TEST_SECRET_ALWAYS_PASSES,
            TEST_SECRET_ALWAYS_FAILS,
            TEST_SECRET_ALREADY_SPENT,
        ):
            _verifier = FakeTurnstileVerifier(secret)
        else:
            _verifier = HttpTurnstileVerifier(secret)
    return _verifier


def set_turnstile_verifier(verifier: TurnstileVerifier | None) -> None:
    """Tests, and only tests."""
    global _verifier
    _verifier = verifier


def turnstile_enabled() -> bool:
    return get_turnstile_verifier().enabled


async def enforce_turnstile(token: str | None, *, remote_ip: str | None, endpoint: str) -> None:
    """Refuse the request unless Cloudflare vouches for `token`. A no-op when
    no secret is configured — the check is OFF, and the health probe says so."""
    verifier = get_turnstile_verifier()
    if not verifier.enabled:
        return
    if not token or not await verifier.verify(token, remote_ip):
        log.info("turnstile.refused", endpoint=endpoint, had_token=bool(token))
        raise CaptchaRequired("complete the security check and try again")
