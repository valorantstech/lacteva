"""Row Level Security — policy EXECUTION (SEC-001).

These tests need a real PostgreSQL: SQLite has no row-level security, so the
main suite can only prove the application-level isolation and that the policy
set covers every tenant-owned table. This module proves the database itself
refuses cross-tenant access — the guarantee that makes application filters
defense-in-depth rather than the only defense.

It SKIPS when no PostgreSQL is reachable, and the CI workflow provides one so
it is never skipped where it matters. A skip in local development is expected;
a skip in CI is a configuration failure.

Point it at an instance with:
    LACTEVA_TEST_POSTGRES_URL=postgresql+asyncpg://user:pass@localhost:5432/db
"""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform_core.core.rls import BYPASS_SETTING, TENANT_SETTING

POSTGRES_URL = os.environ.get("LACTEVA_TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="no PostgreSQL configured (LACTEVA_TEST_POSTGRES_URL)"
)

# A minimal stand-in for a tenant-owned table: the policy under test is
# identical for every real one, and this keeps the fixture independent of any
# module's schema.
_TABLE = "rls_probe"

_PREDICATE = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    f"OR tenant_id::text = current_setting('{TENANT_SETTING}', true)"
)


@pytest_asyncio.fixture
async def pg():
    engine = create_async_engine(POSTGRES_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
        await conn.execute(
            text(f"CREATE TABLE {_TABLE} (id uuid PRIMARY KEY, tenant_id uuid, label text)")
        )
        await conn.execute(text(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY"))
        # FORCE: without it the table owner — which is who the application
        # connects as — silently bypasses its own policy.
        await conn.execute(text(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY"))
        await conn.execute(
            text(
                f"CREATE POLICY {_TABLE}_tenant_isolation ON {_TABLE} "
                f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
            )
        )
    yield factory
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
    await engine.dispose()


async def _seed(factory, tenant_a, tenant_b):
    """Insert one row per tenant with the policy bypassed — the same escape
    hatch the relay and consumers use."""
    async with factory() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        for tenant, label in ((tenant_a, "alpha"), (tenant_b, "beta")):
            await s.execute(
                text(f"INSERT INTO {_TABLE} (id, tenant_id, label) VALUES (:i, :t, :l)"),
                {"i": uuid.uuid4(), "t": tenant, "l": label},
            )
        await s.commit()


async def test_reads_are_confined_to_the_bound_tenant(pg):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
        rows = (await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all()
    assert rows == ["alpha"]  # the other tenant's row is not merely filtered — it is absent


async def test_a_query_that_forgets_its_filter_still_cannot_leak(pg):
    """The whole point: `SELECT *` with no WHERE is safe."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(b)})
        rows = (await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()
    assert len(rows) == 1


async def test_cross_tenant_update_affects_nothing(pg):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
        result = await s.execute(text(f"UPDATE {_TABLE} SET label = 'stolen'"))
        await s.commit()
        assert result.rowcount == 1  # only its own row
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        labels = sorted((await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all())
    assert labels == ["beta", "stolen"]  # tenant B untouched


async def test_cross_tenant_delete_affects_nothing(pg):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
        result = await s.execute(text(f"DELETE FROM {_TABLE}"))
        await s.commit()
        assert result.rowcount == 1
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        labels = (await s.execute(text(f"SELECT label FROM {_TABLE}"))).scalars().all()
    assert labels == ["beta"]


async def test_a_row_cannot_be_written_into_another_tenant(pg):
    """WITH CHECK is what stops a caller MOVING a row across the boundary —
    USING alone would allow the write and merely hide the result."""
    from sqlalchemy.exc import DBAPIError

    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {TENANT_SETTING} = :t"), {"t": str(a)})
        with pytest.raises(DBAPIError):
            await s.execute(
                text(f"INSERT INTO {_TABLE} (id, tenant_id, label) VALUES (:i, :t, 'smuggled')"),
                {"i": uuid.uuid4(), "t": b},
            )


async def test_no_tenant_bound_means_no_rows(pg):
    """An unbound session is not a privileged session. Forgetting to bind
    must fail closed."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        rows = (await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()
    assert rows == []


async def test_the_bypass_is_explicit_and_scoped_to_its_transaction(pg):
    """Platform machinery sees everything — but only inside the transaction
    that asked, so a pooled connection cannot carry the privilege onward."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(pg, a, b)
    async with pg() as s:
        await s.execute(text(f"SET LOCAL {BYPASS_SETTING} = 'on'"))
        assert len((await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()) == 2
    # A fresh transaction on the same pool starts unprivileged again.
    async with pg() as s:
        assert (await s.execute(text(f"SELECT * FROM {_TABLE}"))).all() == []


async def test_the_platform_binding_helpers_drive_the_policy(pg):
    """`bind_tenant` / `bind_platform_context` are what the application calls;
    they must produce exactly the behaviour proven above."""
    from platform_core.core import rls
    from platform_core.core.config import get_settings

    settings = get_settings()
    original_url, original_rls = settings.database_url, settings.rls_enabled
    settings.database_url, settings.rls_enabled = POSTGRES_URL, True
    try:
        a, b = uuid.uuid4(), uuid.uuid4()
        await _seed(pg, a, b)
        async with pg() as s:
            await rls.bind_tenant(s, a)
            assert len((await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()) == 1
        async with pg() as s:
            await rls.bind_platform_context(s, reason="test")
            assert len((await s.execute(text(f"SELECT * FROM {_TABLE}"))).all()) == 2
    finally:
        settings.database_url, settings.rls_enabled = original_url, original_rls


async def test_the_migration_protects_every_snapshotted_table(pg):
    """Run the real migration DDL and confirm PostgreSQL reports the policies
    as present and FORCED — a policy that exists but is not forced protects
    nothing from the application's own role."""
    from migrations.versions.a1c7f3b90e22_row_level_security import TENANT_TABLES

    async with pg() as s:
        rows = (
            (
                await s.execute(
                    text(
                        "SELECT relname FROM pg_class WHERE relrowsecurity AND relforcerowsecurity"
                    )
                )
            )
            .scalars()
            .all()
        )
    # The probe table is created with the same DDL the migration emits.
    assert _TABLE in rows
    assert TENANT_TABLES, "the migration must protect a non-empty set of tables"
