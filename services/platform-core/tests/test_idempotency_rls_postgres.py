"""The idempotency reservation under RLS, on real PostgreSQL (P0-MOB fix).

The defect this file exists to keep dead — pre-existing since IDM-001, latent
until the driver's round became the first keyed, token-authenticated request
ever to reach a live deployment:

    `get_session` binds RLS from the X-Tenant-ID header, because at
    route-class time authentication has not run. A token client sends no
    header, so the session sat on a NULL tenant while the reservation row
    carried the token's verified tenant — and the policy's WITH CHECK refused
    the INSERT with a 500. SQLite cannot see any of this.

The fix rebinds the request session to the token's verified tenant before
reserving. Proven here at the layer it broke: the unbound session is REFUSED
(the defect, demonstrated), the rebound one is accepted (the fix), and the
guard's source is asserted to carry the rebind so a refactor cannot quietly
drop it.
"""

import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres


@pytest.fixture(autouse=True)
def _settings_point_at_postgres(monkeypatch):
    """Make `is_postgres()` true, or every binding below is a no-op."""
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
        await bind_platform_context(session, reason="idempotency RLS proof cleanup")
        await session.execute(
            text("DELETE FROM idempotency_record WHERE idempotency_key LIKE 'p0mob-%'")
        )
        await session.commit()


async def _reserve(session, tenant_id, key):
    from platform_core.core import idempotency

    return await idempotency.reserve(
        session,
        tenant_id=tenant_id,
        key=key,
        fingerprint="f" * 64,
        method="POST",
        path="/v1/delivery-runs/x/stops/y/outcome",
        retention=timedelta(hours=24),
    )


async def test_the_defect_a_null_bound_session_cannot_reserve_a_tenant_key(factory):
    """The pre-fix behaviour, demonstrated so the fix has a shape to refuse.

    This is exactly the state `get_session` left a token client in: session
    bound to no tenant (no X-Tenant-ID header), row carrying the token's
    tenant. The policy must refuse it — if this ever starts PASSING, the
    table's isolation has been weakened, which would be the worse bug.
    """
    from platform_core.core.rls import bind_tenant

    tenant = uuid.uuid4()
    async with factory() as session:
        await bind_tenant(session, None)  # the header-less starting point
        with pytest.raises((ProgrammingError, DBAPIError)):
            await _reserve(session, tenant, f"p0mob-{uuid.uuid4()}")
            await session.commit()


async def test_the_fix_a_rebound_session_reserves_and_replays(factory):
    """The guard's corrected sequence: rebind to the token's verified tenant,
    then reserve — and the same key reserved again is recognised as a replay
    rather than inserted twice."""
    from platform_core.core.rls import bind_tenant, rebind_tenant

    tenant = uuid.uuid4()
    key = f"p0mob-{uuid.uuid4()}"

    from platform_core.core import idempotency

    async with factory() as session:
        await bind_tenant(session, None)
        await rebind_tenant(session, tenant)  # what the guard now does
        record = await _reserve(session, tenant, key)
        assert record.status == "in_progress"
        # The handler answered; the guard records the response — which is what
        # turns the NEXT identical request into a replay rather than a
        # concurrent-attempt conflict.
        await idempotency.record_response(
            session, record.id, status_code=201, body={"delivery_status": "delivered"}
        )
        await session.commit()

    async with factory() as session:
        await rebind_tenant(session, tenant)
        replay = await _reserve(session, tenant, key)
        # Found COMPLETED and returned, not re-inserted — the replay path.
        assert replay.idempotency_key == key
        assert replay.status == "completed"
        await session.commit()

    async with factory() as session:
        await rebind_tenant(session, tenant)
        rows = (
            await session.execute(
                text("SELECT count(*) FROM idempotency_record WHERE idempotency_key = :k"),
                {"k": key},
            )
        ).scalar()
    assert rows == 1


async def test_a_reservation_is_invisible_to_another_tenant(factory):
    """The isolation the WITH CHECK exists to protect, read back."""
    from platform_core.core.rls import rebind_tenant

    a, b = uuid.uuid4(), uuid.uuid4()
    key = f"p0mob-{uuid.uuid4()}"
    async with factory() as session:
        await rebind_tenant(session, a)
        await _reserve(session, a, key)
        await session.commit()

    async with factory() as session:
        await rebind_tenant(session, b)
        rows = (
            await session.execute(
                text("SELECT count(*) FROM idempotency_record WHERE idempotency_key = :k"),
                {"k": key},
            )
        ).scalar()
    assert rows == 0


async def test_the_guard_actually_carries_the_rebind(factory):
    """The wiring, asserted — a refactor that drops the rebind would put every
    keyed mobile request back on a 500, and nothing else would notice."""
    import inspect

    from platform_core.api import idempotent_route

    source = inspect.getsource(idempotent_route.idempotency_guard)
    assert "rebind_tenant" in source
    assert "tenant_id=tenant_id" in source
