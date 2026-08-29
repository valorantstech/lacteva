"""The tenant binding must outlive a commit (LACTEVA-BACKEND-006).

FOUND ON THE DEPLOYED PLATFORM, not in this suite. `POST /v1/deliveries/generate`
refused its own audit write:

    InsufficientPrivilegeError: new row violates row-level security policy
    for table "audit_record"   (action sales.delivery.generated)

THE MECHANISM. `bind_tenant` sets `lacteva.tenant_id` with
`set_config(..., is_local := true)` — that is `SET LOCAL`, and SET LOCAL is
**transaction-scoped**. `record_run` commits the CALLER's session partway
through the request. The commit ends the transaction and takes the binding
with it, so control returns to `DeliveryService.generate` on a session whose
next statement opens a NEW, UNBOUND transaction. The audit row carries a real
tenant; `current_setting('lacteva.tenant_id')` is empty; WITH CHECK refuses it.

The hazard was known and handled TWICE: both of `record_run`'s exception paths
call `rebind_tenant` after `session.rollback()`. The success path — the one
every ordinary request takes — was missed.

WHY NOTHING CAUGHT IT, which is the part worth keeping:

  * SQLite: `bind_tenant` returns early on `is_postgres()`, so the entire
    mechanism is inert and every one of these writes passes.
  * PostgreSQL as a SUPERUSER: RLS is bypassed even with FORCE, so a local
    run — including the one that seeded this demo — cannot see it either.

It appears only as a NOSUPERUSER NOBYPASSRLS role with FORCE, which is
precisely what production runs and what `postgres-proof.sh` already provides.
The gap was never the harness; it was that nothing exercised a
commit-then-write path under it.
"""

import uuid

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


TENANT = uuid.UUID("11111111-2222-3333-4444-555555555555")


@pytest_asyncio.fixture(autouse=True)
async def _clean(factory):
    yield
    from platform_core.core.rls import bind_platform_context

    async with factory() as session:
        await bind_platform_context(session, reason="commit-binding proof cleanup")
        await session.execute(
            text("DELETE FROM audit_record WHERE tenant_id = :t"), {"t": str(TENANT)}
        )
        await session.commit()


async def _write_audit(session) -> None:
    """One tenant-owned INSERT, the same shape the failing path writes."""
    await session.execute(
        text(
            "INSERT INTO audit_record (id, tenant_id, actor_id, action, "
            "resource_type, resource_id, detail, request_id, created_at) "
            "VALUES (:id, :t, :a, 'proof.binding', 'proof', 'proof-row', "
            "'{}'::json, 'proof', now())"
        ),
        {"id": str(uuid.uuid4()), "t": str(TENANT), "a": str(uuid.uuid4())},
    )


async def _bound(session) -> str:
    row = await session.scalar(
        text("SELECT current_setting('lacteva.tenant_id', true)")
    )
    return row or ""


class TestTheBindingOutlivesACommit:
    async def test_a_write_after_a_commit_is_still_bound(self, factory):
        """THE DEFECT. Bind, commit, write — exactly what the request did."""
        from platform_core.core.rls import bind_tenant

        async with factory() as session:
            await bind_tenant(session, TENANT)
            assert await _bound(session) == str(TENANT)

            # Something the request called committed the caller's session.
            # `record_run` does this on its success path.
            await session.commit()

            # The request is not over: it still has an audit row to write.
            await _write_audit(session)
            await session.commit()

    async def test_the_setting_itself_survives(self, factory):
        """The same thing one layer down, so a failure says WHICH half broke."""
        from platform_core.core.rls import bind_tenant

        async with factory() as session:
            await bind_tenant(session, TENANT)
            await session.commit()
            assert await _bound(session) == str(TENANT), (
                "SET LOCAL is transaction-scoped; the binding must be "
                "re-applied when a new transaction begins"
            )


class TestTheGuardCanStillRefuse:
    """The other half. A binding that survives everything protects nothing."""

    async def test_an_unbound_write_is_refused(self, factory):
        """A session that was NEVER bound may not write a tenant's row.

        This must keep failing forever. If it ever passes, the fix above has
        been implemented by weakening the policy rather than by restoring the
        binding — which is the worse bug, and silent.
        """
        async with factory() as session:
            assert await _bound(session) == ""
            with pytest.raises((ProgrammingError, DBAPIError)) as caught:
                await _write_audit(session)
                await session.commit()
            assert "row-level security" in str(caught.value).lower()

    async def test_a_write_for_ANOTHER_tenant_is_refused(self, factory):
        """Bound to one tenant, writing another's row: still refused."""
        from platform_core.core.rls import bind_tenant

        async with factory() as session:
            await bind_tenant(session, uuid.uuid4())
            with pytest.raises((ProgrammingError, DBAPIError)) as caught:
                await _write_audit(session)
                await session.commit()
            assert "row-level security" in str(caught.value).lower()
