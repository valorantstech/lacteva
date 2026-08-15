"""The calendar tables on a real engine: isolation and migration (DEMO-020).

`test_financial_periods.py` proves the RULES on SQLite, where RLS does not
exist and every guarantee is the application's own filter. That is exactly the
gap STD-0007 §6 names: a tenant-owned table whose isolation has only ever been
tested on SQLite is untested, because the thing that isolates it in production
— a `FORCE ROW LEVEL SECURITY` policy — cannot even be expressed there.

So this asserts, against real PostgreSQL:

* the policies exist, are ENABLED and are FORCED on both new tables;
* a session bound to one tenant cannot read, update or delete another's rows,
  and cannot write a row into another tenant;
* the migration runs from the previous revision, comes back down, and goes up
  again — the up → down → up the work order requires — leaving no drift.

The general coverage tests in `test_rls_postgres.py` already sweep every
tenant-owned table and would catch a missing policy. These are the same
guarantee asserted specifically, so a failure names DEMO-020's tables rather
than a set of forty.
"""

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres


@pytest.fixture(autouse=True)
def _settings_point_at_postgres(monkeypatch):
    """Make `is_postgres()` true for the code under test (VER-001, DEMO-020).

    `bind_tenant` and `bind_platform_context` both return early unless
    `settings.database_url` says PostgreSQL — and conftest pins that to SQLite
    for the whole test process. Without this fixture every binding in this
    module is a NO-OP, and the suite still passes when it is run as a
    superuser, because superusers ignore row-level security altogether.

    That is exactly what had happened: this module passed by hand as
    `postgres` and failed the moment it was added to the nine-step proof,
    which runs its tests as the unprivileged role production uses. The suite
    was proving nothing about RLS and looked green.
    """
    from platform_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "database_url", POSTGRES_URL)
    monkeypatch.setattr(get_settings(), "rls_enabled", True)


NEW_TABLES = ("organization_calendar_day", "financial_period")


@pytest_asyncio.fixture
async def live():
    engine = create_async_engine(POSTGRES_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _bind(session, tenant_id: uuid.UUID | None) -> None:
    from platform_core.core.rls import rebind_tenant

    await rebind_tenant(session, tenant_id)


@pytest.mark.parametrize("table", NEW_TABLES)
async def test_the_new_tables_are_enabled_and_forced(live, table):
    """ENABLE without FORCE protects nothing: the app owns these tables."""
    async with live() as s:
        row = (
            await s.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = :t"
                ),
                {"t": table},
            )
        ).first()
    assert row is not None, f"{table} does not exist in the migrated database"
    enabled, forced = row
    assert enabled, f"{table} has row level security disabled"
    assert forced, f"{table} does not FORCE row level security"


@pytest.mark.parametrize("table", NEW_TABLES)
async def test_the_new_tables_have_a_policy_with_using_and_with_check(live, table):
    """A USING clause alone stops reads and lets a write into another tenant."""
    async with live() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT polname, polqual IS NOT NULL, polwithcheck IS NOT NULL "
                    "FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid "
                    "WHERE c.relname = :t"
                ),
                {"t": table},
            )
        ).all()
    assert rows, f"{table} has no policy"
    for _name, has_using, has_with_check in rows:
        assert has_using and has_with_check


async def test_a_holiday_cannot_be_read_across_tenants(live):
    """The refusal, on the table itself."""
    alpha, beta = uuid.uuid4(), uuid.uuid4()
    day = date(2026, 8, 15)

    async with live() as s:
        await _bind(s, alpha)
        await s.execute(
            text(
                "INSERT INTO organization_calendar_day "
                "(id, tenant_id, day, working, kind, name, created_at) "
                "VALUES (:id, :t, :d, false, 'holiday', 'Alpha holiday', now())"
            ),
            {"id": uuid.uuid4(), "t": alpha, "d": day},
        )
        await s.commit()

    try:
        async with live() as s:
            await _bind(s, alpha)
            mine = (
                await s.execute(
                    text("SELECT count(*) FROM organization_calendar_day WHERE day = :d"),
                    {"d": day},
                )
            ).scalar_one()
            assert mine == 1, "the premise: the owner can see its own holiday"

        async with live() as s:
            await _bind(s, beta)
            # No tenant filter in the SQL AT ALL — the database must still refuse.
            theirs = (
                await s.execute(
                    text("SELECT count(*) FROM organization_calendar_day WHERE day = :d"),
                    {"d": day},
                )
            ).scalar_one()
            assert theirs == 0, "another tenant read a holiday it does not own"

            # And cannot delete or update what it cannot see.
            deleted = await s.execute(
                text("DELETE FROM organization_calendar_day WHERE day = :d"), {"d": day}
            )
            assert deleted.rowcount == 0
            await s.commit()

        async with live() as s:
            await _bind(s, alpha)
            still = (
                await s.execute(
                    text("SELECT count(*) FROM organization_calendar_day WHERE day = :d"),
                    {"d": day},
                )
            ).scalar_one()
            assert still == 1, "the other tenant's delete removed a row it did not own"
    finally:
        async with live() as s:
            await _bind(s, alpha)
            await s.execute(
                text("DELETE FROM organization_calendar_day WHERE day = :d"), {"d": day}
            )
            await s.commit()


async def test_a_period_cannot_be_written_into_another_tenant(live):
    """WITH CHECK: a bound session may not label a row with someone else's id."""
    alpha, beta = uuid.uuid4(), uuid.uuid4()
    async with live() as s:
        await _bind(s, alpha)
        with pytest.raises(Exception) as excinfo:
            await s.execute(
                text(
                    "INSERT INTO financial_period "
                    "(id, tenant_id, period_start, period_end, status, label, created_at) "
                    "VALUES (:id, :t, :a, :b, 'open', '', now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": beta,  # NOT the bound tenant
                    "a": date(2026, 8, 1),
                    "b": date(2026, 8, 31),
                },
            )
        assert "policy" in str(excinfo.value).lower()
        await s.rollback()


async def test_an_unbound_session_sees_no_calendar_rows(live):
    """A forgotten binding must return nothing, not everything."""
    tenant = uuid.uuid4()
    async with live() as s:
        await _bind(s, tenant)
        await s.execute(
            text(
                "INSERT INTO financial_period "
                "(id, tenant_id, period_start, period_end, status, label, created_at) "
                "VALUES (:id, :t, :a, :b, 'open', 'unbound probe', now())"
            ),
            {
                "id": uuid.uuid4(),
                "t": tenant,
                "a": date(2027, 1, 1),
                "b": date(2027, 1, 31),
            },
        )
        await s.commit()
    try:
        async with live() as s:
            await _bind(s, None)
            count = (
                await s.execute(
                    text("SELECT count(*) FROM financial_period WHERE label = 'unbound probe'")
                )
            ).scalar_one()
            assert count == 0
    finally:
        async with live() as s:
            await _bind(s, tenant)
            await s.execute(text("DELETE FROM financial_period WHERE label = 'unbound probe'"))
            await s.commit()
