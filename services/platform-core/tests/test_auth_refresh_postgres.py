"""A tenant's refresh token must renew its session on PostgreSQL (WO-73 follow-up).

Found on the live handset twenty minutes after WO-69 shipped: the app asked
`POST /v1/auth/refresh` and the platform answered 401, so the operator was
signed out at fifteen minutes exactly as before the fix. `auth_session` is
tenant-owned under RLS. The login route rebinds the tenant it was told in its
body before it looks the user up; the refresh route carries no tenant — no
bearer, no body field, only the opaque token — and never bound one, so on
PostgreSQL the tenant-scoped session was invisible to the query that renews
it. A platform-level session (tenant NULL) refreshed fine, which is why the
throwaway account used to check the route did not show it.

Every existing refresh test runs on SQLite, where there are no policies. This
one runs on PostgreSQL with the policies forced, as the platform does, and
asks the question the handset asked.
"""

import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = [postgres_support.requires_postgres, pytest.mark.asyncio]

EMAIL = "refresh-proof@lacteva-pgtests.example.com"


@pytest.fixture(autouse=True)
def _settings_point_at_postgres(monkeypatch):
    from platform_core.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", POSTGRES_URL)
    monkeypatch.setattr(settings, "rls_enabled", True)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean(factory):
    yield
    from platform_core.core.rls import bind_platform_context

    async with factory() as session:
        await bind_platform_context(session, reason="refresh proof cleanup")
        await session.execute(
            text(
                "DELETE FROM auth_session WHERE user_id IN "
                "(SELECT id FROM user_account WHERE email = :e)"
            ),
            {"e": EMAIL},
        )
        await session.execute(text("DELETE FROM user_account WHERE email = :e"), {"e": EMAIL})
        await session.commit()


def _service(session):
    from platform_core.infrastructure.events import InMemoryEventBus
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.auth.service import AuthService
    from platform_core.modules.identity.service import IdentityService
    from platform_core.modules.organization.service import MembershipService

    bus = InMemoryEventBus()
    audit = AuditService(session)
    return AuthService(
        session, IdentityService(session, bus, audit), MembershipService(session), audit, bus
    )


async def _seed_tenant_session(factory, tenant_id: uuid.UUID, secret: str) -> uuid.UUID:
    """A tenant user and a live session for it, written under the tenant's
    own binding — exactly what a login leaves behind."""
    from platform_core.core.db import utcnow
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.auth.models import AuthSession
    from platform_core.modules.auth.service import _hash_secret
    from platform_core.modules.identity.models import User

    async with factory() as session:
        await rebind_tenant(session, tenant_id)
        user = User(
            tenant_id=tenant_id,
            email=EMAIL,
            password_hash="not-a-real-hash",
            full_name="Refresh Proof",
        )
        session.add(user)
        await session.flush()
        session.add(
            AuthSession(
                user_id=user.id,
                tenant_id=tenant_id,
                refresh_token_hash=_hash_secret(secret),
                expires_at=utcnow() + timedelta(days=14),
            )
        )
        await session.commit()
        return user.id


async def test_a_tenant_session_refreshes_with_no_tenant_in_the_request(factory):
    from platform_core.core.errors import InvalidCredentialsError
    from platform_core.core.rls import bind_tenant

    tenant = uuid.uuid4()
    secret = "handset-refresh-" + uuid.uuid4().hex
    await _seed_tenant_session(factory, tenant, secret)

    # The refresh route: a session with NO tenant bound, because the request
    # carries none. This is the situation the handset was in.
    async with factory() as session:
        await bind_tenant(session, None)
        pair = await _service(session).refresh(secret)
        await session.commit()
    assert pair.access_token and pair.refresh_token and pair.refresh_token != secret

    # The new secret renews again — the rotation was written under the
    # session's own tenant binding, not lost under the bypass.
    async with factory() as session:
        await bind_tenant(session, None)
        again = await _service(session).refresh(pair.refresh_token)
        await session.commit()
    assert again.access_token and again.refresh_token != pair.refresh_token

    # Rotation still holds. The ORIGINAL secret is two generations back —
    # unknown, refused, and nothing more. The secret rotated one generation
    # back is the reuse signal the platform watches for: refused, and the
    # reuse KILLS the session, so the latest secret is dead as well. The
    # theft response is unchanged by the fix.
    async with factory() as session:
        await bind_tenant(session, None)
        with pytest.raises(InvalidCredentialsError):
            await _service(session).refresh(secret)
    async with factory() as session:
        await bind_tenant(session, None)
        with pytest.raises(InvalidCredentialsError):
            await _service(session).refresh(pair.refresh_token)
    async with factory() as session:
        await bind_tenant(session, None)
        with pytest.raises(InvalidCredentialsError):
            await _service(session).refresh(again.refresh_token)


async def test_an_unknown_token_is_still_refused(factory):
    from platform_core.core.errors import InvalidCredentialsError
    from platform_core.core.rls import bind_tenant

    async with factory() as session:
        await bind_tenant(session, None)
        with pytest.raises(InvalidCredentialsError):
            await _service(session).refresh("never-issued-" + uuid.uuid4().hex)
