"""Password reset foundation: token issuance, confirmation, session revocation."""

from tests.conftest import register_and_login


async def _request_reset_token(email: str) -> str | None:
    """Service-level: the API deliberately never returns the raw token."""
    from platform_core.api.deps import get_auth_service  # noqa: F401 (doc pointer)
    from platform_core.core.db import get_session_factory
    from platform_core.infrastructure.events import get_event_bus
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.auth.service import AuthService
    from platform_core.modules.identity.service import IdentityService
    from platform_core.modules.organization.service import MembershipService

    async with get_session_factory()() as session:
        audit = AuditService(session)
        service = AuthService(
            session,
            IdentityService(session, get_event_bus(), audit),
            MembershipService(session),
            audit,
            get_event_bus(),
        )
        token = await service.request_password_reset(email, None)
        await session.commit()
        return token


async def test_reset_request_never_reveals_accounts(client):
    r = await client.post("/v1/auth/password-reset/request", json={"email": "ghost@example.com"})
    assert r.status_code == 202  # same answer whether or not the account exists


async def test_full_reset_flow(client, bus):
    await register_and_login(client)
    pair = (
        await client.post(
            "/v1/auth/token",
            json={"email": "user@example.com", "password": "correct-horse-battery"},
        )
    ).json()

    token = await _request_reset_token("user@example.com")
    assert token is not None
    assert any(e.type == "identity.password-reset-requested.v1" for e in bus.published)

    r = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "brand-new-password-1"},
    )
    assert r.status_code == 204

    # Old password dead, old sessions revoked, new password works.
    r = await client.post(
        "/v1/auth/token",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )
    assert r.status_code == 401
    h = {"Authorization": f"Bearer {pair['access_token']}"}
    assert (await client.get("/v1/auth/me", headers=h)).status_code == 401
    r = await client.post(
        "/v1/auth/token",
        json={"email": "user@example.com", "password": "brand-new-password-1"},
    )
    assert r.status_code == 200

    # Token is single-use.
    r = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "another-password-22"},
    )
    assert r.status_code == 400


async def test_bogus_reset_token_rejected(client):
    r = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": "bogus", "new_password": "whatever-password-1"},
    )
    assert r.status_code == 400
