"""Cloudflare Turnstile, verified server-side (WO-103 · LACTEVA-AUTH-003).

The owner asked for "captcha or something" on sign-up. It is there, and on
the forms bots actually attack: accepting an invitation, asking for a
password reset, and signing in once an address or an account has failed
three times in fifteen minutes. Every one is enforced by the API against the
verifier — the widget in the browser is decoration — and with no keys the
check is OFF and the health report says so, never silently.

The verifier here is the fake that answers as Cloudflare's published test
keys do; nothing in this file reaches the network.
"""

import re

import pytest

from platform_core.core import turnstile
from platform_core.core.errors import AppError
from tests.conftest import register_and_login
from tests.test_email_change import _capturing
from tests.test_org_structure import _tenant_admin


async def _invite(client, admin, email):
    capture, restore = _capturing()
    try:
        r = await client.post(
            "/v1/invitations", json={"email": email, "role_name": "DRIVER"}, headers=admin
        )
        assert r.status_code == 201, r.text
    finally:
        restore()
    body = capture.to(email)[-1].body
    return re.search(r"/accept-invitation#code=([A-Za-z0-9_-]+)", body).group(1)


def _on(secret=turnstile.TEST_SECRET_ALWAYS_PASSES) -> turnstile.FakeTurnstileVerifier:
    """Turn Turnstile ON now. The fixtures that build a tenant admin accept an
    invitation themselves, so the switch is thrown after the setup, as an
    operator would configure keys on a running platform."""
    fake = turnstile.FakeTurnstileVerifier(secret)
    turnstile.set_turnstile_verifier(fake)
    return fake


async def test_invitation_acceptance_needs_a_token_when_turnstile_is_on(client):
    _org, admin = await _tenant_admin(client)
    token = await _invite(client, admin, "guarded@kilima.example")
    turnstile_on = _on()
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "guarded-password-11", "full_name": "Guarded"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["title"] == "captcha_required"
    assert "security check" in r.json()["detail"]
    # The invitation is untouched by the refusal: the same code works once
    # the form is completed — and the verifier was asked, with the caller's
    # address.
    r = await client.post(
        "/v1/invitations/accept",
        json={
            "token": token,
            "password": "guarded-password-11",
            "full_name": "Guarded",
            "turnstile_token": "XXXX.DUMMY.TOKEN",
        },
    )
    assert r.status_code == 201, r.text
    assert turnstile_on.calls[-1][0] == "XXXX.DUMMY.TOKEN"


async def test_a_token_cloudflare_rejects_is_refused(client):
    """Cloudflare's always-fail test secret: a token is carried and still
    refused — the widget alone proves nothing, the verifier's answer does."""
    _org, admin = await _tenant_admin(client)
    token = await _invite(client, admin, "rejected@kilima.example")
    _on(turnstile.TEST_SECRET_ALWAYS_FAILS)
    r = await client.post(
        "/v1/invitations/accept",
        json={
            "token": token,
            "password": "rejected-password-11",
            "full_name": "Rejected",
            "turnstile_token": "XXXX.DUMMY.TOKEN",
        },
    )
    assert r.status_code == 400 and r.json()["title"] == "captcha_required"


async def test_the_password_reset_request_needs_a_token_when_turnstile_is_on(client, turnstile_on):
    r = await client.post("/v1/auth/password-reset/request", json={"email": "who@kilima.example"})
    assert r.status_code == 400 and r.json()["title"] == "captcha_required"
    r = await client.post(
        "/v1/auth/password-reset/request",
        json={"email": "who@kilima.example", "turnstile_token": "XXXX.DUMMY.TOKEN"},
    )
    assert r.status_code == 202, r.text


async def test_sign_in_is_challenged_from_the_third_failure(client):
    """Three wrong passwords from one address (or for one account) in
    fifteen minutes, and the next attempt must carry a token — with the
    token it proceeds to the ordinary credential check."""
    await register_and_login(client, "challenged@kilima.example")
    turnstile_on = _on()
    for _ in range(3):
        r = await client.post(
            "/v1/auth/token",
            json={"email": "challenged@kilima.example", "password": "wrong-password-11"},
        )
        assert r.status_code == 401, r.text
    assert turnstile_on.calls == []
    # The fourth attempt without a token is refused BEFORE credentials are
    # looked at — even the right password.
    r = await client.post(
        "/v1/auth/token",
        json={"email": "challenged@kilima.example", "password": "correct-horse-battery"},
    )
    assert r.status_code == 400 and r.json()["title"] == "captcha_required"
    # With a token, the ordinary path: wrong is 401, right is a token pair.
    r = await client.post(
        "/v1/auth/token",
        json={
            "email": "challenged@kilima.example",
            "password": "wrong-password-11",
            "turnstile_token": "XXXX.DUMMY.TOKEN",
        },
    )
    assert r.status_code == 401
    r = await client.post(
        "/v1/auth/token",
        json={
            "email": "challenged@kilima.example",
            "password": "correct-horse-battery",
            "turnstile_token": "XXXX.DUMMY.TOKEN",
        },
    )
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


async def test_the_first_sign_in_failures_are_free(client):
    """A person who mistypes twice is not a bot: no token is asked for
    until the third failure, and a fresh account is never challenged."""
    await register_and_login(client, "careful@kilima.example")
    turnstile_on = _on()
    for _ in range(2):
        r = await client.post(
            "/v1/auth/token",
            json={"email": "careful@kilima.example", "password": "wrong-password-11"},
        )
        assert r.status_code == 401
    r = await client.post(
        "/v1/auth/token",
        json={"email": "careful@kilima.example", "password": "correct-horse-battery"},
    )
    assert r.status_code == 200, r.text
    assert turnstile_on.calls == []


async def test_with_no_keys_the_forms_work_and_the_health_report_says_so(client):
    """OFF is a state the operator must SEE. The autouse fixture leaves the
    suite without a secret, as a deployment without keys would be."""
    assert turnstile.turnstile_enabled() is False
    r = await client.post("/v1/auth/password-reset/request", json={"email": "who@kilima.example"})
    assert r.status_code == 202
    from platform_core.core.health_probes import turnstile as probe

    result = await probe()
    assert result.name == "turnstile"
    assert result.status == "warning"
    assert "LACTEVA_TURNSTILE_SECRET_KEY is not set" in result.detail
    assert result.data == {"configured": False}


async def test_the_health_probe_is_healthy_only_with_both_keys(monkeypatch):
    from platform_core.core.config import get_settings
    from platform_core.core.health_probes import turnstile as probe

    turnstile.set_turnstile_verifier(
        turnstile.FakeTurnstileVerifier(turnstile.TEST_SECRET_ALWAYS_PASSES)
    )
    monkeypatch.setattr(get_settings(), "turnstile_site_key", "")
    result = await probe()
    assert result.status == "warning" and "LACTEVA_TURNSTILE_SITE_KEY is not" in result.detail
    monkeypatch.setattr(get_settings(), "turnstile_site_key", turnstile.TEST_SITE_KEY_ALWAYS_PASSES)
    result = await probe()
    assert result.status == "healthy" and result.data == {"configured": True}


def test_cloudflares_test_secrets_never_reach_the_network(monkeypatch):
    """A `.env` carrying a published test secret gets the fake, offline —
    so development and CI behave as production will without a live call."""
    from platform_core.core.config import get_settings

    for secret, expected in (
        (turnstile.TEST_SECRET_ALWAYS_PASSES, turnstile.FakeTurnstileVerifier),
        (turnstile.TEST_SECRET_ALWAYS_FAILS, turnstile.FakeTurnstileVerifier),
        ("0x4AAAAAAA-real-looking-secret", turnstile.HttpTurnstileVerifier),
        ("", turnstile.HttpTurnstileVerifier),
    ):
        turnstile.set_turnstile_verifier(None)
        monkeypatch.setattr(get_settings(), "turnstile_secret_key", secret)
        verifier = turnstile.get_turnstile_verifier()
        assert isinstance(verifier, expected), secret
        assert verifier.enabled is bool(secret)
    turnstile.set_turnstile_verifier(None)


async def test_the_real_verifier_fails_closed(monkeypatch):
    """siteverify unreachable, or answering anything but success, is NOT a
    pass: the forms this guards are the ones bots attack."""
    import httpx

    verifier = turnstile.HttpTurnstileVerifier("0x4AAAAAAA-real-looking-secret", timeout=0.1)

    class Boom:
        def __init__(self, *a, **k): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx, "AsyncClient", Boom)
    assert await verifier.verify("XXXX.DUMMY.TOKEN", "203.0.113.9") is False

    class Says:
        def __init__(self, payload, status=200):
            self._payload, self.status_code = payload, status

        def json(self):
            return self._payload

    class Client:
        answer = Says({"success": False, "error-codes": ["invalid-input-response"]})

        def __init__(self, *a, **k): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data):
            assert url == turnstile.SITEVERIFY_URL
            assert data["response"] == "XXXX.DUMMY.TOKEN" and data["remoteip"] == "203.0.113.9"
            return Client.answer

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    assert await verifier.verify("XXXX.DUMMY.TOKEN", "203.0.113.9") is False
    Client.answer = Says({"success": True})
    assert await verifier.verify("XXXX.DUMMY.TOKEN", "203.0.113.9") is True


def test_captcha_required_is_a_400_with_its_own_code():
    exc = turnstile.CaptchaRequired("x")
    assert isinstance(exc, AppError)
    assert exc.status_code == 400 and exc.code == "captcha_required"


@pytest.mark.parametrize("token", ["", None])
async def test_an_empty_token_is_no_token(client, turnstile_on, token):
    r = await client.post(
        "/v1/auth/password-reset/request",
        json={"email": "who@kilima.example", "turnstile_token": token},
    )
    assert r.status_code == 400 and r.json()["title"] == "captcha_required"
