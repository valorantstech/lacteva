"""Security hardening (SEC-001) — penetration-style suite.

These tests attack the platform rather than exercise it: forged and expired
tokens, retired and future keys, algorithm confusion, privilege escalation,
cross-tenant reach, refresh replay, and abuse budgets. A failure here is a
vulnerability, not a regression in behaviour.

RLS policy EXECUTION is not covered here — SQLite has no row-level security.
Those tests live in `test_rls_postgres.py` and skip without a PostgreSQL
instance; what runs here is the isolation the application itself enforces,
plus proof that the policy set covers every tenant-owned table.
"""

import uuid
from datetime import timedelta

import jwt
import pytest

from platform_core.core.db import utcnow
from tests.conftest import register_and_login
from tests.test_org_structure import _tenant_admin


def _settings():
    from platform_core.core.config import get_settings

    return get_settings()


@pytest.fixture
def key_guard():
    """Restore the key registry after tests install their own."""
    from platform_core.core import keys

    original = keys.get_key_registry()
    yield keys
    keys.reset_key_registry(original)


async def _authed(client, email="sec@example.com"):
    _, headers = await register_and_login(client, email)
    return headers


# --- JWT: signing, discovery, and the shape of a token ----------------------


async def test_tokens_are_rs256_and_name_their_key(client):
    _, headers = await register_and_login(client, "rs256@example.com")
    token = headers["Authorization"].removeprefix("Bearer ")
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    assert header["kid"]  # a token must say which key signed it


async def test_jwks_publishes_only_public_material(client):
    body = (await client.get("/v1/.well-known/jwks.json")).json()
    assert body["keys"], "the discovery document must not be empty"
    key = body["keys"][0]
    assert key["kty"] == "RSA" and key["alg"] == "RS256" and key["use"] == "sig"
    assert set(key) == {"kty", "use", "alg", "kid", "n", "e"}
    # Nothing resembling private material may ever appear here.
    serialized = str(body)
    assert "PRIVATE" not in serialized and "d" not in set(key)


async def test_jwks_is_public_and_verifies_a_real_token(client):
    """A resource server must be able to verify without any platform secret."""
    from jwt import PyJWK

    _, headers = await register_and_login(client, "verify@example.com")
    token = headers["Authorization"].removeprefix("Bearer ")
    jwks = (await client.get("/v1/.well-known/jwks.json")).json()
    kid = jwt.get_unverified_header(token)["kid"]
    jwk = next(k for k in jwks["keys"] if k["kid"] == kid)
    claims = jwt.decode(
        token,
        PyJWK.from_dict(jwk).key,
        algorithms=["RS256"],
        issuer=_settings().service_name,
    )
    assert claims["typ"] == "access" and claims["sub"]


# --- JWT: forgery and tampering ---------------------------------------------


async def test_a_forged_token_signed_with_an_attacker_key_is_rejected(client, key_guard):
    """The classic attack: mint a token with your own RSA key and hope the
    server trusts the kid it is told."""
    from platform_core.core.keys import generate_keypair

    attacker = generate_keypair(kid="attacker-key")
    real_headers = await _authed(client, "victim@example.com")
    real = jwt.decode(
        real_headers["Authorization"].removeprefix("Bearer "),
        options={"verify_signature": False},
    )
    forged = jwt.encode(
        real, attacker.private_pem, algorithm="RS256", headers={"kid": attacker.kid}
    )
    r = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


async def test_a_token_naming_a_known_kid_but_signed_wrongly_is_rejected(client, key_guard):
    """Same kid, different key — the signature must still fail."""
    from platform_core.core.keys import generate_keypair

    real_headers = await _authed(client, "sigmismatch@example.com")
    token = real_headers["Authorization"].removeprefix("Bearer ")
    kid = jwt.get_unverified_header(token)["kid"]
    claims = jwt.decode(token, options={"verify_signature": False})
    impostor = generate_keypair(kid=kid)
    forged = jwt.encode(claims, impostor.private_pem, algorithm="RS256", headers={"kid": kid})
    r = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


async def test_algorithm_confusion_is_rejected(client, key_guard):
    """`alg: none` and HS256-signed-with-the-public-key are the two textbook
    JWT downgrades. Neither may be accepted while the platform runs RS256."""
    from platform_core.core.keys import get_key_registry

    claims = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "sid": str(uuid.uuid4()),
        "iss": _settings().service_name,
        "iat": utcnow(),
        "exp": utcnow() + timedelta(minutes=5),
    }
    kid = get_key_registry().current().kid
    public = get_key_registry().current().public_pem

    def _forge(alg: str, secret: bytes | None) -> str:
        """Assemble a token by hand — PyJWT refuses to build these, which is
        precisely why an attacker would not use PyJWT."""
        import base64
        import hashlib
        import hmac
        import json as jsonlib

        def b64(raw: bytes) -> bytes:
            return base64.urlsafe_b64encode(raw).rstrip(b"=")

        payload = dict(claims)
        payload["iat"] = int(claims["iat"].timestamp())
        payload["exp"] = int(claims["exp"].timestamp())
        header = b64(jsonlib.dumps({"alg": alg, "typ": "JWT", "kid": kid}).encode())
        body = b64(jsonlib.dumps(payload).encode())
        signing_input = header + b"." + body
        signature = (
            b"" if secret is None else b64(hmac.new(secret, signing_input, hashlib.sha256).digest())
        )
        return (signing_input + b"." + signature).decode()

    none_token = _forge("none", None)
    # The classic: sign with HMAC using the platform's own PUBLIC key as the
    # shared secret, hoping the server picks the algorithm from the header.
    hs_token = _forge("HS256", public.encode())
    for token in (none_token, hs_token):
        r = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


async def test_an_expired_token_is_rejected(client, key_guard):
    from platform_core.core.keys import get_key_registry

    key = get_key_registry().current()
    claims = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "sid": str(uuid.uuid4()),
        "iss": _settings().service_name,
        "iat": utcnow() - timedelta(hours=2),
        "exp": utcnow() - timedelta(hours=1),
    }
    token = jwt.encode(claims, key.private_pem, algorithm="RS256", headers={"kid": key.kid})
    r = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_a_token_from_another_issuer_is_rejected(client, key_guard):
    from platform_core.core.keys import get_key_registry

    key = get_key_registry().current()
    claims = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "sid": str(uuid.uuid4()),
        "iss": "some-other-platform",
        "iat": utcnow(),
        "exp": utcnow() + timedelta(minutes=5),
    }
    token = jwt.encode(claims, key.private_pem, algorithm="RS256", headers={"kid": key.kid})
    r = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_a_refresh_token_cannot_be_used_as_an_access_token(client):
    """Token type confusion: a refresh token is long-lived, so accepting it
    at an API endpoint would defeat the short access-token lifetime."""
    await client.post(
        "/v1/auth/register",
        json={"email": "typ@example.com", "password": "correct-horse-battery", "full_name": "T"},
    )
    pair = (
        await client.post(
            "/v1/auth/token", json={"email": "typ@example.com", "password": "correct-horse-battery"}
        )
    ).json()
    r = await client.get(
        "/v1/auth/me", headers={"Authorization": f"Bearer {pair['refresh_token']}"}
    )
    assert r.status_code == 401


async def test_a_garbage_token_is_rejected_without_a_server_error(client):
    for value in ("", "not-a-token", "a.b.c", "Bearer", "null"):
        r = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {value}"})
        assert r.status_code == 401, value


# --- key rotation ------------------------------------------------------------


async def test_rotation_keeps_existing_sessions_alive(client, key_guard):
    """The rotation guarantee: install a new signing key, and tokens minted
    under the old one keep working until they expire."""
    from platform_core.core.keys import KeyRegistry, generate_keypair, get_key_registry

    old = get_key_registry().current()
    headers = await _authed(client, "rotate@example.com")
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 200

    new = generate_keypair(kid="rotated-key")
    key_guard.reset_key_registry(KeyRegistry([old, new]))

    # The old token still verifies…
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 200
    # …and new tokens are signed by the newer key.
    fresh = await _authed(client, "rotate2@example.com")
    token = fresh["Authorization"].removeprefix("Bearer ")
    assert jwt.get_unverified_header(token)["kid"] == "rotated-key"


async def test_a_retired_key_stops_verifying_immediately(client, key_guard):
    """Emergency revocation: retiring a compromised key must invalidate every
    token it signed, at once."""
    from dataclasses import replace

    from platform_core.core.keys import KeyRegistry, generate_keypair, get_key_registry

    old = get_key_registry().current()
    headers = await _authed(client, "retire@example.com")
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 200

    replacement = generate_keypair(kid="replacement-key")
    key_guard.reset_key_registry(KeyRegistry([replace(old, retired=True), replacement]))
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 401


async def test_a_key_that_has_not_activated_yet_cannot_sign_or_verify(key_guard):
    from dataclasses import replace

    from platform_core.core.keys import KeyRegistry, KeyRegistryError, generate_keypair

    future = replace(generate_keypair(kid="future"), activates_at=utcnow() + timedelta(days=1))
    registry = KeyRegistry([future])
    with pytest.raises(KeyRegistryError):
        registry.current()
    with pytest.raises(KeyRegistryError):
        registry.verification_key("future")
    assert registry.jwks()["keys"] == []  # never advertise a key that is not live


async def test_an_expired_key_cannot_sign_or_verify(key_guard):
    from dataclasses import replace

    from platform_core.core.keys import KeyRegistry, KeyRegistryError, generate_keypair

    expired = replace(generate_keypair(kid="past"), expires_at=utcnow() - timedelta(seconds=1))
    registry = KeyRegistry([expired])
    with pytest.raises(KeyRegistryError):
        registry.verification_key("past")


async def test_an_unknown_kid_is_rejected(client, key_guard):
    from platform_core.core.keys import get_key_registry

    key = get_key_registry().current()
    claims = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "sid": str(uuid.uuid4()),
        "iss": _settings().service_name,
        "iat": utcnow(),
        "exp": utcnow() + timedelta(minutes=5),
    }
    token = jwt.encode(claims, key.private_pem, algorithm="RS256", headers={"kid": "no-such-key"})
    r = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_the_key_registry_is_platform_staff_only(client):
    headers = await _authed(client, "nokeys@example.com")
    assert (await client.get("/v1/_security/keys", headers=headers)).status_code == 403
    assert (await client.get("/v1/_security/keys")).status_code in (401, 403)


async def test_the_key_registry_never_returns_private_material(client):
    from tests.conftest import grant_platform_admin

    user_id, headers = await register_and_login(client, "keyadmin@example.com", admin=True)
    assert user_id
    body = (await client.get("/v1/_security/keys", headers=headers)).json()
    assert body and all("private" not in str(entry).lower() for entry in body)
    assert {"kid", "status", "can_sign"} <= set(body[0])
    assert grant_platform_admin


# --- session and refresh security -------------------------------------------


async def test_a_revoked_session_stops_working_immediately(client):
    """Logout must kill the ACCESS token too, not merely the refresh token —
    otherwise a stolen access token outlives the user's own decision."""
    headers = await _authed(client, "revoke@example.com")
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 200
    assert (await client.post("/v1/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 401


async def test_refresh_replay_is_treated_as_theft(client):
    """A refresh token is single-use. Presenting it twice means either the
    user or an attacker has a stale copy — the platform cannot tell which, so
    it revokes the family."""
    await client.post(
        "/v1/auth/register",
        json={
            "email": "replay@example.com",
            "password": "correct-horse-battery",
            "full_name": "R",
        },
    )
    pair = (
        await client.post(
            "/v1/auth/token",
            json={"email": "replay@example.com", "password": "correct-horse-battery"},
        )
    ).json()
    first = await client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert first.status_code == 200
    replayed = await client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert replayed.status_code == 401
    # The rotated token is dead too: reuse revokes the whole chain.
    rotated = first.json()["refresh_token"]
    assert (
        await client.post("/v1/auth/refresh", json={"refresh_token": rotated})
    ).status_code == 401


# --- privilege escalation and cross-tenant reach -----------------------------


async def test_a_tenant_header_cannot_override_the_token(client):
    """Session fixation by header: the token's tenant is authoritative, so
    naming another tenant in X-Tenant-ID must change nothing."""
    org, headers = await _tenant_admin(client)
    other_tenant = str(uuid.uuid4())
    me = (await client.get("/v1/auth/me", headers={**headers, "X-Tenant-ID": other_tenant})).json()
    assert me["tenant_id"] == org["id"]


async def test_a_user_cannot_grant_themselves_a_permission(client):
    """Vertical escalation: role management is itself permission-guarded."""
    headers = await _authed(client, "escalate@example.com")
    r = await client.post(
        "/v1/authz/roles",
        json={"name": "superuser", "permission_keys": ["*"]},
        headers=headers,
    )
    assert r.status_code == 403


async def test_permission_denials_are_audited(client):
    """An escalation attempt that leaves no trace is an escalation attempt
    nobody investigates."""
    from sqlalchemy import select

    from platform_core.core import db
    from platform_core.modules.audit.models import AuditRecord

    headers = await _authed(client, "denied@example.com")
    assert (await client.get("/v1/suppliers", headers=headers)).status_code == 403
    async with db.get_session_factory()() as s:
        records = list(
            (
                await s.scalars(
                    select(AuditRecord).where(AuditRecord.action == "security.permission.denied")
                )
            ).all()
        )
    assert records, "a denied permission must be recorded"
    assert records[0].resource_id == "supplier.read"


async def test_login_success_and_failure_are_audited(client):
    from sqlalchemy import select

    from platform_core.core import db
    from platform_core.modules.audit.models import AuditRecord

    await client.post(
        "/v1/auth/register",
        json={
            "email": "audited@example.com",
            "password": "correct-horse-battery",
            "full_name": "A",
        },
    )
    await client.post(
        "/v1/auth/token",
        json={"email": "audited@example.com", "password": "correct-horse-battery"},
    )
    await client.post(
        "/v1/auth/token", json={"email": "audited@example.com", "password": "wrong-password"}
    )
    async with db.get_session_factory()() as s:
        actions = [
            r.action
            for r in (
                await s.scalars(select(AuditRecord).where(AuditRecord.resource_type == "security"))
            ).all()
        ]
    assert "security.login.succeeded" in actions
    assert "security.login.failed" in actions


async def test_a_failed_login_does_not_reveal_whether_the_account_exists(client):
    await client.post(
        "/v1/auth/register",
        json={"email": "exists@example.com", "password": "correct-horse-battery", "full_name": "E"},
    )
    known = await client.post(
        "/v1/auth/token", json={"email": "exists@example.com", "password": "wrong-password"}
    )
    unknown = await client.post(
        "/v1/auth/token", json={"email": "nobody@example.com", "password": "wrong-password"}
    )
    assert known.status_code == unknown.status_code == 401
    assert known.json()["title"] == unknown.json()["title"]


# --- rate limiting -----------------------------------------------------------


async def test_login_is_rate_limited_with_structured_retry_information(client):
    from platform_core.core import rate_limit

    body = {"email": "brute@example.com", "password": "wrong-password"}
    last = None
    for _ in range(rate_limit.LOGIN.limit + 2):
        last = await client.post("/v1/auth/token", json=body)
    assert last.status_code == 429
    problem = last.json()
    assert problem["title"] == "rate_limited"
    assert problem["extra"]["rule"] == "login"
    assert problem["extra"]["limit"] == rate_limit.LOGIN.limit
    assert problem["extra"]["retry_after_seconds"] >= 1
    # A human-readable message, not the raw translation key.
    assert problem["detail"] == "Too many requests. Please wait and try again."
    assert last.headers["Retry-After"]  # machine-honourable, not just a body


async def test_password_reset_is_rate_limited(client):
    from platform_core.core import rate_limit

    last = None
    for _ in range(rate_limit.PASSWORD_RESET.limit + 1):
        last = await client.post(
            "/v1/auth/password-reset/request", json={"email": "someone@example.com"}
        )
    assert last.status_code == 429


async def test_a_dead_limiter_still_lets_the_dairy_log_in(client):
    """SEC-003 / F-06: `degrade` keeps the business function working.

    This is what fail-open was protecting and the reason it survived so long:
    a dairy at 5 a.m. must not stop accepting milk because a cache is down.
    Under `degrade` the request still proceeds — it is charged against the
    process-local counter instead of Redis."""
    from platform_core.core import rate_limit

    class _BrokenLimiter:
        async def hit(self, key, rule):
            raise ConnectionError("redis is gone")

    rate_limit.set_rate_limiter(_BrokenLimiter())
    r = await client.post(
        "/v1/auth/token", json={"email": "x@example.com", "password": "wrong-password"}
    )
    assert r.status_code == 401  # the request proceeded; only auth refused it


async def test_a_dead_limiter_does_not_hand_out_unlimited_credential_attempts(client):
    """SEC-003 / F-06, and the half fail-open gave away.

    The old behaviour allowed EVERY request the limiter could not judge, so a
    Redis outage silently removed brute-force protection from the login
    endpoint entirely and the only trace was a log line. `degrade` charges the
    process-local counter, so the budget still runs out.

    `LOGIN` is 10 per 60s. The eleventh attempt must be refused with Redis
    dead — under the old fail-open policy every one of these returned 401."""
    from platform_core.core import rate_limit

    class _BrokenLimiter:
        async def hit(self, key, rule):
            raise ConnectionError("redis is gone")

    rate_limit.set_rate_limiter(_BrokenLimiter())
    rate_limit.get_fallback_limiter()._counters.clear()

    statuses = []
    for _ in range(12):
        r = await client.post(
            "/v1/auth/token",
            json={"email": "brute@example.com", "password": "wrong-password"},
        )
        statuses.append(r.status_code)
    assert 429 in statuses, f"a dead limiter granted unlimited attempts: {statuses}"


async def test_the_limiter_can_be_configured_to_fail_closed(client, monkeypatch):
    from platform_core.core import rate_limit
    from platform_core.core.config import get_settings

    class _BrokenLimiter:
        async def hit(self, key, rule):
            raise ConnectionError("redis is gone")

    rate_limit.set_rate_limiter(_BrokenLimiter())
    monkeypatch.setattr(get_settings(), "rate_limit_failure_policy", "fail_closed")
    r = await client.post(
        "/v1/auth/token", json={"email": "x@example.com", "password": "wrong-password"}
    )
    assert r.status_code == 429


async def test_fail_open_remains_reachable_but_must_be_asked_for(client, monkeypatch):
    """It is still a supported posture — it just cannot be arrived at by
    accident, and `prod` refuses it (see the production-config tests)."""
    from platform_core.core import rate_limit
    from platform_core.core.config import get_settings

    class _BrokenLimiter:
        async def hit(self, key, rule):
            raise ConnectionError("redis is gone")

    rate_limit.set_rate_limiter(_BrokenLimiter())
    monkeypatch.setattr(get_settings(), "rate_limit_failure_policy", "fail_open")
    statuses = []
    for _ in range(12):
        r = await client.post(
            "/v1/auth/token",
            json={"email": "open@example.com", "password": "wrong-password"},
        )
        statuses.append(r.status_code)
    assert 429 not in statuses, "fail_open must allow everything it cannot judge"


async def test_credential_rules_are_the_ones_that_deny_when_nothing_can_judge_them(client):
    """The last-resort split, asserted as data rather than as behaviour: a
    rule that guards a credential denies, a rule that guards compute allows."""
    from platform_core.core.rate_limit import (
        CONSUMER_REPLAY,
        INVITATION_ACCEPT,
        LOGIN,
        LOGIN_PER_USER,
        NOTIFICATION_PREVIEW,
        PASSWORD_RESET,
        PROJECTION_REBUILD,
        REFRESH,
    )

    for rule in (LOGIN, LOGIN_PER_USER, REFRESH, PASSWORD_RESET, INVITATION_ACCEPT):
        assert rule.fail_closed, f"{rule.name} guards a credential and must fail closed"
    for rule in (NOTIFICATION_PREVIEW, PROJECTION_REBUILD, CONSUMER_REPLAY):
        assert not rule.fail_closed, f"{rule.name} guards compute, not a secret"


async def test_rate_limit_scopes_do_not_collide(client):
    from platform_core.core.rate_limit import LOGIN, REFRESH

    key_a = LOGIN.key(ip="1.2.3.4", user=None, endpoint="login")
    key_b = REFRESH.key(ip="1.2.3.4", user=None, endpoint="refresh")
    assert key_a != key_b
    assert LOGIN.key(ip="1.2.3.4", user=None, endpoint="login") != LOGIN.key(
        ip="5.6.7.8", user=None, endpoint="login"
    )


# --- security headers --------------------------------------------------------


async def test_security_headers_are_present_on_every_response(client):
    for response in (
        await client.get("/health/live"),
        await client.get("/v1/auth/me"),  # 401 path
    ):
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert "camera=()" in response.headers["Permissions-Policy"]
        assert response.headers["Cache-Control"] == "no-store"


async def test_hsts_is_absent_without_tls_and_present_when_enabled(client, monkeypatch):
    from platform_core.core.config import get_settings

    assert "Strict-Transport-Security" not in (await client.get("/health/live")).headers
    monkeypatch.setattr(get_settings(), "hsts_enabled", True)
    headers = (await client.get("/health/live")).headers
    assert "max-age=31536000" in headers["Strict-Transport-Security"]
    assert "includeSubDomains" in headers["Strict-Transport-Security"]


async def test_cors_grants_only_configured_origins(client):
    allowed = await client.options(
        "/v1/auth/token",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    hostile = await client.options(
        "/v1/auth/token",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in hostile.headers


async def test_cors_does_not_reflect_arbitrary_headers(client):
    """A wildcard `allow_headers` would authorise anything a future
    vulnerability needs; the list is explicit."""
    response = await client.options(
        "/v1/auth/token",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Attacker-Header",
        },
    )
    allowed = response.headers.get("access-control-allow-headers", "")
    assert "X-Attacker-Header" not in allowed


# --- secrets and configuration ----------------------------------------------


def test_production_refuses_development_credentials():
    """The settings validator is the last line between a convenient default
    and a production incident."""
    from platform_core.core.config import DEV_JWT_SECRET, DEV_MINIO_SECRET, Settings

    # Every value is passed explicitly: the test process's own LACTEVA_*
    # variables would otherwise mask the very misconfiguration under test.
    with pytest.raises(ValueError, match="LACTEVA_JWT_KEYS"):
        Settings(
            env="prod",
            jwt_algorithm="RS256",
            jwt_keys="",
            minio_secret_key="a-real-minio-secret",
        )
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(
            env="prod",
            jwt_algorithm="HS256",
            jwt_secret=DEV_JWT_SECRET,
            minio_secret_key="a-real-minio-secret",
        )
    with pytest.raises(ValueError, match="MINIO_SECRET_KEY"):
        Settings(
            env="prod",
            jwt_algorithm="HS256",
            jwt_secret="a-real-secret",
            minio_secret_key=DEV_MINIO_SECRET,
        )


def test_production_refuses_a_channel_that_reports_success_and_sends_nothing():
    """ARCH-FINAL-001: `logging` and `placeholder` both return ACCEPTED.

    The message renders, the delivery row says accepted, every dashboard is
    green — and the supplier is told nothing. Both are the DEFAULT, so a
    production deployment that sets no provider silently discards every SMS
    and every email. `dry_run` and `disabled` stay legal because both are
    deliberate: one rehearses, the other fails visibly.
    """
    from platform_core.core.config import Settings

    for provider in ("logging", "placeholder"):
        with pytest.raises(ValueError, match="NOTIFICATION_SMS_PROVIDER"):
            Settings(**_safe_prod(notification_sms_provider=provider))
        with pytest.raises(ValueError, match="NOTIFICATION_EMAIL_PROVIDER"):
            Settings(**_safe_prod(notification_email_provider=provider))

    # `dry_run` and `disabled` are deliberate choices and stay legal.
    Settings(
        **_safe_prod(notification_sms_provider="dry_run", notification_email_provider="dry_run")
    )


def _safe_prod(**overrides):
    """A production configuration that passes every check, so a test can flip
    exactly one thing and know that is what failed."""
    base = dict(
        env="prod",
        jwt_algorithm="HS256",
        jwt_secret="a-real-secret",
        minio_secret_key="a-real-minio-secret",
        database_url="postgresql+asyncpg://app_user:strong@db.internal:5432/lacteva",
        event_bus="rabbitmq",
        outbox_mode="background",
        rate_limit_backend="redis",
        notification_sms_provider="disabled",
        notification_email_provider="disabled",
        receipt_pdf_renderer="builtin",
        # BKP-003: a production deployment with nowhere independent to put a
        # backup has backups that die with the volume they protect, so the
        # reference configuration has to name a destination.
        backup_offsite_endpoint="s3.eu-central-1.amazonaws.com",
        backup_offsite_access_key="an-access-key",
        backup_offsite_secret_key="a-secret-key",
        backup_offsite_secure=True,
    )
    base.update(overrides)
    return base


def test_the_reference_production_configuration_is_accepted():
    """The control. Without it, every test below could be passing because the
    baseline is broken rather than because the flipped value is refused."""
    from platform_core.core.config import Settings

    Settings(**_safe_prod())


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        # PROD-001: each of these lets production look healthy while doing
        # nothing, or run on a credential that was never meant to leave a
        # laptop. Every one is now a startup failure.
        ({"database_url": "postgresql+asyncpg://lacteva:lacteva@db:5432/lacteva"}, "DATABASE_URL"),
        ({"database_url": "sqlite+aiosqlite:///./dev.db"}, "DATABASE_URL"),
        ({"event_bus": "memory"}, "EVENT_BUS"),
        ({"event_bus": "null"}, "EVENT_BUS"),
        ({"outbox_mode": "inline"}, "OUTBOX_MODE"),
        ({"rate_limit_backend": "memory"}, "RATE_LIMIT_BACKEND"),
        ({"receipt_pdf_renderer": "placeholder"}, "RECEIPT_PDF_RENDERER"),
        ({"notification_sms_provider": "http", "sms_api_url": "", "sms_api_key": ""}, "SMS_API"),
        ({"notification_email_provider": "smtp", "smtp_host": ""}, "SMTP_HOST"),
        # BKP-003. A backup on the database's own volume is not a backup, and
        # a backup shipped in clear text carries every farmer's records.
        ({"backup_offsite_endpoint": ""}, "BACKUP_OFFSITE_ENDPOINT"),
        ({"backup_offsite_access_key": ""}, "access key"),
        ({"backup_offsite_secret_key": ""}, "access key"),
        ({"backup_offsite_secure": False}, "BACKUP_OFFSITE_SECURE"),
        ({"backup_offsite_retain": 0}, "BACKUP_OFFSITE_RETAIN"),
    ],
)
def test_production_refuses_every_configuration_that_pretends_to_work(overrides, expected):
    from platform_core.core.config import Settings

    with pytest.raises(ValueError, match=expected):
        Settings(**_safe_prod(**overrides))


def test_a_fully_configured_gateway_is_accepted():
    """The refusals must not block a real deployment — `http` with credentials
    and `smtp` with a host are exactly what production is supposed to look
    like."""
    from platform_core.core.config import Settings

    Settings(
        **_safe_prod(
            notification_sms_provider="http",
            sms_api_url="https://sms.example/v1/send",
            sms_api_key="a-real-key",
            notification_email_provider="smtp",
            smtp_host="smtp.example",
        )
    )


def test_none_of_these_checks_apply_outside_production():
    """Development must stay convenient — every default that prod refuses is
    the right choice on a laptop."""
    from platform_core.core.config import Settings

    for env in ("dev", "test", "staging"):
        Settings(env=env)


def test_production_refuses_row_level_security_being_switched_off():
    """ARCH-FINAL-001: `rls_enabled=False` is the tenant boundary, not a knob.

    It short-circuits `bind_tenant`, `bind_platform_context` and
    `assert_rls_is_enforceable` alike — so the single environment variable
    that removes database-enforced isolation also disables the startup check
    that detects a SUPERUSER connection silently ignoring every policy. That
    is the exact failure shape VER-001 found, reachable by configuration.
    """
    from platform_core.core.config import Settings

    with pytest.raises(ValueError, match="RLS_ENABLED"):
        Settings(
            env="prod",
            jwt_algorithm="HS256",
            jwt_secret="a-real-secret",
            minio_secret_key="a-real-minio-secret",
            rls_enabled=False,
        )


def test_production_refuses_debug_and_wildcard_cors():
    from platform_core.core.config import Settings

    base = {
        "env": "prod",
        "jwt_algorithm": "HS256",
        "jwt_secret": "a-real-secret",
        "minio_secret_key": "a-real-minio-secret",
    }
    with pytest.raises(ValueError, match="DEBUG"):
        Settings(**base, debug=True)
    with pytest.raises(ValueError, match="CORS"):
        Settings(**base, cors_origins=("*",))


def test_no_secret_material_is_hardcoded_in_source():
    """A grep the reviewer would run anyway, kept honest by CI."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text()
        if "BEGIN RSA PRIVATE KEY" in text or "BEGIN PRIVATE KEY" in text:
            offenders.append(str(path))
    assert not offenders, f"private key material committed in: {offenders}"


def test_dev_defaults_are_sentinels_not_plausible_secrets():
    from platform_core.core.config import DEV_JWT_SECRET, DEV_MINIO_SECRET

    # A default that looks like a real secret is one somebody ships.
    assert "change-me" in DEV_JWT_SECRET
    assert DEV_MINIO_SECRET == "lacteva-secret"


# --- RLS: coverage and binding (execution lives in test_rls_postgres.py) -----


def test_every_tenant_owned_table_is_covered_by_a_policy():
    """The drift guard: a new tenant-owned table without a policy migration
    is a table with no database-level protection.

    The covered set is the UNION of the migrations that grant policies —
    SEC-001 established the first 37, SEC-002 added the 13 child tables that
    had been reachable only through a parent, IDM-001 the idempotency record.
    Each migration snapshots its own list on purpose: a migration is a
    historical record and must not change meaning when the models later do.

    This test earns its keep — it is what failed when IDM-001 introduced the
    first new tenant-owned table since SEC-002, again when PROD-001 added
    `document_sequence`, and again when DEMO-009 added the eight sales tables.
    That last one reached a deployment before it was caught, because the
    incremental test selection that day did not include this file — the
    deployment verifier stopped it instead. Both guards were needed; neither
    was redundant.
    """
    from migrations.versions.a1c7f3b90e22_row_level_security import TENANT_TABLES
    from migrations.versions.c8a4d2f10b73_demo_009_rls_for_the_sales_tables import (
        SALES_TABLES as DEMO009_TABLES,
    )
    from migrations.versions.e62a7e569a6a_prod_001_document_number_sequences import (
        POLICY_TABLES as PROD001_TABLES,
    )
    from migrations.versions.f2d18ba60c47_sec002_complete_rls_coverage import NEW_TENANT_TABLES
    from migrations.versions.f73f41473469_idempotency_records import POLICY_TABLES

    from platform_core.core.rls import tenant_tables

    covered = (
        set(TENANT_TABLES)
        | set(NEW_TENANT_TABLES)
        | set(POLICY_TABLES)
        | set(PROD001_TABLES)
        | set(DEMO009_TABLES)
    )
    uncovered = set(tenant_tables()) - covered
    assert not uncovered, (
        f"tenant-owned tables with no RLS policy: {sorted(uncovered)} — "
        "add a migration extending the policy set"
    )


def test_every_table_declares_an_isolation_strategy():
    """SEC-002's premise: "every table has an explicit isolation strategy".

    A table is either tenant-owned (it has a tenant_id and the standard policy
    applies), platform-global (deliberately unprotected, with the reason on
    record), or mixed (it holds both kinds of row, or is isolated by a column
    other than tenant_id). "Nobody decided" is not one of the options, and
    that is what this test enforces — a new table that fits none of the three
    fails here rather than shipping unprotected.
    """
    from platform_core.core.rls import unclassified_tables

    missing = unclassified_tables()
    assert missing == (), (
        f"tables with no declared isolation strategy: {list(missing)} — add each to "
        "PLATFORM_GLOBAL or MIXED in core/rls.py, or give it a tenant_id"
    )


def test_the_isolation_taxonomy_refers_only_to_real_tables():
    """The other direction: a renamed or dropped table leaving a stale entry
    behind turns the register above into fiction."""
    from platform_core.core.db import Base
    from platform_core.core.rls import MIXED, PLATFORM_GLOBAL

    known = set(Base.metadata.tables)
    stale = sorted((set(PLATFORM_GLOBAL) | set(MIXED)) - known)
    assert stale == [], f"isolation strategy declared for tables that do not exist: {stale}"


def test_platform_global_tables_carry_no_tenant_column():
    """Category B means "there is no tenant here". A tenant_id column on one
    of these would mean the classification is simply wrong."""
    from platform_core.core.db import Base
    from platform_core.core.rls import PLATFORM_GLOBAL

    wrong = [t for t in PLATFORM_GLOBAL if "tenant_id" in Base.metadata.tables[t].columns]
    assert wrong == [], f"platform-global tables that actually have a tenant_id: {wrong}"


def test_every_platform_global_table_records_why():
    """A bare list would decay into folklore. The reason is the artifact."""
    from platform_core.core.rls import MIXED, PLATFORM_GLOBAL

    for table, reason in {**PLATFORM_GLOBAL, **MIXED}.items():
        assert len(reason) > 40, f"{table} needs a real reason, not {reason!r}"


def test_the_money_and_pii_child_tables_are_now_tenant_owned():
    """The specific tables ABR-002 found unprotected. Named individually so a
    regression says which one, not just that the count changed."""
    from platform_core.core.rls import tenant_tables

    owned = set(tenant_tables())
    for table in (
        "supplier_profile",
        "supplier_bank_account",
        "supplier_document",
        "settlement_line",
        "payment_line",
        "payment_attempt",
        "receipt_line",
        "pricing_matrix_row",
    ):
        assert table in owned, f"{table} holds money or PII and must be tenant-owned"


def test_organization_is_isolated_by_identity_not_by_tenant_id():
    """`organization` IS the tenant, so it cannot carry a tenant_id pointing
    at itself. Its policy compares the primary key instead — and must NOT
    inherit the `IS NULL` escape, which would make every organization visible
    to every unbound session."""
    from platform_core.core.db import Base
    from platform_core.core.rls import MIXED, identity_policy_statements

    assert "tenant_id" not in Base.metadata.tables["organization"].columns
    assert "organization" in MIXED
    ddl = " ".join(identity_policy_statements("organization"))
    assert "ENABLE ROW LEVEL SECURITY" in ddl
    assert "FORCE ROW LEVEL SECURITY" in ddl
    assert "USING" in ddl and "WITH CHECK" in ddl
    assert "id::text = current_setting" in ddl
    assert "IS NULL" not in ddl, "an identity policy must not have a NULL escape hatch"


def test_the_rls_policy_denies_by_default_and_checks_writes():
    """Read the generated DDL: USING without WITH CHECK would let a caller
    move a row INTO another tenant."""
    from platform_core.core.rls import policy_statements

    ddl = " ".join(policy_statements("supplier"))
    assert "ENABLE ROW LEVEL SECURITY" in ddl
    assert "FORCE ROW LEVEL SECURITY" in ddl  # or the owner bypasses its own policy
    assert "USING" in ddl and "WITH CHECK" in ddl
    assert "lacteva.tenant_id" in ddl and "lacteva.bypass_rls" in ddl


async def test_rls_binding_is_a_no_op_on_sqlite(client):
    """The test stack must not silently believe it is protected."""
    from platform_core.core import db
    from platform_core.core.rls import bind_tenant, is_postgres

    assert not is_postgres()
    async with db.get_session_factory()() as s:
        await bind_tenant(s, uuid.uuid4())  # must not raise


async def test_application_level_tenant_isolation_holds(client):
    """Defense-in-depth, proven where RLS cannot run: one tenant's data is
    invisible to another through the API."""
    from tests.test_collection_centers import _center_fixture
    from tests.test_payments import _second_tenant
    from tests.test_suppliers import _create_supplier

    headers, _branch, _center = await _center_fixture(client)
    supplier = await _create_supplier(client, headers)
    other = await _second_tenant(client)

    assert (await client.get("/v1/suppliers", headers=other)).json()["total"] == 0
    assert (await client.get(f"/v1/suppliers/{supplier['id']}", headers=other)).status_code == 404


# --- SEC-002: the binding must precede the read ---------------------------


async def test_authentication_binds_the_tenant_before_reading_any_row(client):
    """The defect this test exists for.

    `auth_session` and `user_account` are themselves tenant-owned. Principal
    resolution read both of them and only afterwards re-bound the session to
    the token's tenant — so under RLS the session row was invisible to the
    request that owned it, and every authenticated call that did not happen to
    send an X-Tenant-ID header failed as 401. SQLite cannot execute the
    policy, so nothing caught it; what SQLite CAN prove is the ordering, and
    the ordering is the whole defect.

    Recording binds and reads on one timeline and asserting the first bind
    precedes the first read is therefore not a proxy for the bug — it is the
    bug, stated directly.
    """
    import uuid as _uuid

    from platform_core.api import deps
    from platform_core.core import rls

    timeline: list[str] = []
    real_bind = rls.bind_tenant

    async def recording_bind(session, tenant_id):
        timeline.append(f"bind:{tenant_id}")
        return await real_bind(session, tenant_id)

    class RecordingSession:
        """Wraps the real session; notes every read that RLS would filter."""

        def __init__(self, inner):
            self._inner = inner

        async def get(self, *a, **kw):
            timeline.append(f"read:{a[0].__name__}")
            return await self._inner.get(*a, **kw)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    # Build the principal BEFORE recording: the helper's own requests bind
    # tenants too, and those binds are not the ones under test.
    _org, headers = await _tenant_admin(client)
    token = headers["Authorization"].removeprefix("Bearer ")
    payload = deps.decode_token(token, expected_type="access")
    assert payload.get("tenant_id"), "helper must produce a tenant-scoped token"

    rls.bind_tenant = recording_bind
    try:
        from platform_core.core.db import get_session_factory

        async with get_session_factory()() as raw:
            from fastapi.security import HTTPAuthorizationCredentials

            from platform_core.infrastructure.events import get_event_bus
            from platform_core.modules.audit.service import AuditService

            recording = RecordingSession(raw)
            identity = deps.IdentityService(recording, get_event_bus(), AuditService(recording))
            await deps.get_current_principal(
                recording,
                identity,
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            )
    finally:
        rls.bind_tenant = real_bind

    binds = [i for i, e in enumerate(timeline) if e.startswith("bind:")]
    reads = [i for i, e in enumerate(timeline) if e.startswith("read:")]
    assert binds, f"authentication never bound a tenant: {timeline}"
    assert reads, f"authentication read no tenant-owned row: {timeline}"
    assert binds[0] < reads[0], (
        "the tenant must be bound BEFORE the first tenant-owned read — otherwise "
        f"RLS hides the session row from its own request. Timeline: {timeline}"
    )
    assert f"bind:{_uuid.UUID(payload['tenant_id'])}" in timeline


async def test_rebind_moves_the_context_and_the_database_together():
    """`set_current_tenant()` alone was the other half of the same defect: the
    context variable moved, the database binding stayed behind, and writes
    were refused by WITH CHECK. `rebind_tenant` is the pairing."""
    import uuid as _uuid

    from platform_core.core import rls
    from platform_core.core.tenancy import get_current_tenant, set_current_tenant

    bound: list = []

    async def fake_bind(session, tenant_id):
        bound.append(tenant_id)

    real = rls.bind_tenant
    rls.bind_tenant = fake_bind
    try:
        set_current_tenant(None)
        target = _uuid.uuid4()
        await rls.rebind_tenant(object(), target)
        assert get_current_tenant() == target, "context variable was not updated"
        assert bound == [target], "the database binding was not updated"
    finally:
        rls.bind_tenant = real
        set_current_tenant(None)


async def test_a_corrupted_password_hash_is_a_refusal_not_a_500(client):
    """HASH-001, found on a live deployment.

    A `password_hash` column written with a truncated value made argon2 raise
    `InvalidHashError`, which nothing caught: every login attempt for that one
    account returned 500 while every other account returned 401. Two problems —
    a password check must fail CLOSED, and a 500 where others give 401 tells an
    unauthenticated caller that this row is special.

    `InvalidHashError` derives from `ValueError`, not from `Argon2Error`, so
    catching the library's own base class alone does not cover it.
    """
    from sqlalchemy import update

    from platform_core.core import db
    from platform_core.modules.identity.models import User
    from tests.conftest import register_and_login

    await register_and_login(client, "corrupt@example.com")
    async with db.get_session_factory()() as session:
        await session.execute(
            update(User)
            .where(User.email == "corrupt@example.com")
            .values(password_hash="=19=65536,t=3,p=4+truncated")
        )
        await session.commit()

    r = await client.post(
        "/v1/auth/token",
        json={"email": "corrupt@example.com", "password": "correct-horse-battery"},
    )
    assert r.status_code == 401, f"a corrupt hash must refuse, not error: {r.status_code}"
    assert r.json()["title"] == "invalid_credentials"


def test_verify_password_never_raises_whatever_is_stored():
    from platform_core.core.security import hash_password, verify_password

    good = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", good) is True
    assert verify_password("wrong-password-here", good) is False
    for broken in ("", "not-a-hash", "=19=65536,t=3,p=4+truncated", "$argon2id$broken"):
        assert verify_password("anything", broken) is False, broken
