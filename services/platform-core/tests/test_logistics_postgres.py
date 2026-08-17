"""The route layer on real PostgreSQL (DEMO-034).

`test_logistics.py` proves the rules on SQLite. This is the half SQLite cannot
prove: its test stack shares one connection, so nothing races, and it has no
row-level security at all.

The properties §4 and §9 name — that each of the five new tables is isolated by
the database rather than by a `WHERE` clause somebody might forget, and that
two operators acting at the same instant produce one run and one loser.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

NEW_TABLES = ("route", "route_stop", "vehicle", "driver", "delivery_run")


@pytest.fixture(autouse=True)
def _settings_point_at_postgres(monkeypatch):
    """Make `is_postgres()` true, or every binding below is a no-op.

    The lesson DEMO-020 learned the hard way: without this the suite passes as
    a superuser and proves nothing about RLS at all.
    """
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
        await bind_platform_context(session, reason="logistics proof cleanup")
        for table in ("delivery_run", "route_stop", "route", "vehicle", "driver"):
            await session.execute(text(f"DELETE FROM {table}"))
        await session.commit()


async def _bind(session, tenant_id: uuid.UUID | None) -> None:
    from platform_core.core.rls import rebind_tenant

    await rebind_tenant(session, tenant_id)


async def _seed_route(factory, tenant_id: uuid.UUID, code: str = "R-01"):
    from platform_core.modules.logistics.models import Route

    async with factory() as session:
        await _bind(session, tenant_id)
        route = Route(tenant_id=tenant_id, code=code, name=f"Round {code}")
        session.add(route)
        await session.commit()
        return route.id


# --- 1-5: RLS on each of the five tables -----------------------------------------


@pytest.mark.parametrize("table", NEW_TABLES)
async def test_each_new_table_is_enabled_and_forced(factory, table):
    """ENABLE without FORCE protects nothing: the app owns these tables."""
    async with factory() as session:
        row = (
            await session.execute(
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
async def test_each_new_table_has_a_policy_with_using_and_with_check(factory, table):
    """A USING clause alone stops reads and lets a WRITE into another tenant."""
    async with factory() as session:
        rows = (
            await session.execute(
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
        assert has_using, f"{table}: policy has no USING"
        assert has_with_check, f"{table}: policy has no WITH CHECK"


# --- 6-9: one dairy cannot see or touch another's ---------------------------------


async def test_a_route_is_invisible_to_another_dairy(factory):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed_route(factory, a)

    from platform_core.modules.logistics.models import Route

    async with factory() as session:
        await _bind(session, b)
        assert (await session.scalars(select(Route))).all() == []
        await _bind(session, a)
        assert len((await session.scalars(select(Route))).all()) == 1


async def test_a_vehicle_and_a_driver_are_invisible_to_another_dairy(factory):
    from platform_core.modules.logistics.models import Driver, Vehicle

    a, b = uuid.uuid4(), uuid.uuid4()
    async with factory() as session:
        await _bind(session, a)
        session.add(Vehicle(tenant_id=a, registration="KDA 001A"))
        session.add(Driver(tenant_id=a, code="DRV-1", full_name="Joseph"))
        await session.commit()

    async with factory() as session:
        await _bind(session, b)
        assert (await session.scalars(select(Vehicle))).all() == []
        assert (await session.scalars(select(Driver))).all() == []


async def test_a_run_and_its_stops_are_invisible_to_another_dairy(factory):
    from datetime import date

    from platform_core.modules.logistics.models import DeliveryRun, RouteStop

    a, b = uuid.uuid4(), uuid.uuid4()
    route_id = await _seed_route(factory, a)
    async with factory() as session:
        await _bind(session, a)
        session.add(RouteStop(tenant_id=a, route_id=route_id, customer_id=uuid.uuid4(), position=1))
        session.add(
            DeliveryRun(
                tenant_id=a, route_id=route_id, business_date=date(2026, 8, 17), slot="morning"
            )
        )
        await session.commit()

    async with factory() as session:
        await _bind(session, b)
        assert (await session.scalars(select(RouteStop))).all() == []
        assert (await session.scalars(select(DeliveryRun))).all() == []


async def test_another_dairy_cannot_WRITE_a_route_into_this_one(factory):
    """The WITH CHECK half. A read-only proof would miss this entirely."""
    from sqlalchemy.exc import DBAPIError

    from platform_core.modules.logistics.models import Route

    a, b = uuid.uuid4(), uuid.uuid4()
    async with factory() as session:
        await _bind(session, b)
        session.add(Route(tenant_id=a, code="SMUGGLED", name="Not mine"))
        with pytest.raises(DBAPIError):
            await session.commit()


async def test_another_dairy_cannot_UPDATE_this_ones_run(factory):
    """A silent zero-row UPDATE is the correct outcome, not an error."""
    from datetime import date

    from platform_core.modules.logistics.models import DeliveryRun

    a, b = uuid.uuid4(), uuid.uuid4()
    route_id = await _seed_route(factory, a)
    async with factory() as session:
        await _bind(session, a)
        run = DeliveryRun(
            tenant_id=a, route_id=route_id, business_date=date(2026, 8, 17), slot="morning"
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    async with factory() as session:
        await _bind(session, b)
        result = await session.execute(
            text("UPDATE delivery_run SET status = 'cancelled' WHERE id = :i"), {"i": run_id}
        )
        await session.commit()
        assert result.rowcount == 0, "another dairy changed this dairy's run"

    async with factory() as session:
        await _bind(session, a)
        assert (await session.get(DeliveryRun, run_id)).status == "planned"


# --- 10-12: concurrency, which SQLite cannot show ---------------------------------


async def test_two_operators_creating_todays_run_produce_one_row(factory):
    """§9. The unique constraint decides, not a Python check.

    Two real connections, both past the pre-check, both inserting. One wins;
    the other gets an IntegrityError that the service turns into a 409.
    """
    from datetime import date

    from sqlalchemy.exc import IntegrityError

    from platform_core.modules.logistics.models import DeliveryRun

    tenant = uuid.uuid4()
    route_id = await _seed_route(factory, tenant)
    day = date(2026, 8, 17)

    async def attempt():
        async with factory() as session:
            await _bind(session, tenant)
            session.add(
                DeliveryRun(tenant_id=tenant, route_id=route_id, business_date=day, slot="morning")
            )
            try:
                await session.commit()
                return "created"
            except IntegrityError:
                await session.rollback()
                return "refused"

    outcomes = await asyncio.gather(attempt(), attempt(), attempt())
    assert outcomes.count("created") == 1, outcomes
    assert outcomes.count("refused") == 2, outcomes

    async with factory() as session:
        await _bind(session, tenant)
        rows = (await session.scalars(select(DeliveryRun))).all()
    assert len(rows) == 1, "the same round went out twice"


async def test_the_same_customer_cannot_be_added_to_a_route_twice_concurrently(factory):
    """§9's duplicate stop association, decided by the database."""
    from sqlalchemy.exc import IntegrityError

    from platform_core.modules.logistics.models import RouteStop

    tenant = uuid.uuid4()
    route_id = await _seed_route(factory, tenant)
    customer_id = uuid.uuid4()

    async def attempt(position: int):
        async with factory() as session:
            await _bind(session, tenant)
            session.add(
                RouteStop(
                    tenant_id=tenant,
                    route_id=route_id,
                    customer_id=customer_id,
                    position=position,
                )
            )
            try:
                await session.commit()
                return "added"
            except IntegrityError:
                await session.rollback()
                return "refused"

    outcomes = await asyncio.gather(attempt(1), attempt(2))
    assert outcomes.count("added") == 1, outcomes

    async with factory() as session:
        await _bind(session, tenant)
        assert len((await session.scalars(select(RouteStop))).all()) == 1


async def test_two_operators_completing_a_run_produce_one_transition(factory):
    """CAS, on real connections. `UPDATE … WHERE status = <expected>`.

    Without the status predicate both updates succeed and two audit entries
    claim the same change.
    """
    from datetime import date

    from platform_core.modules.logistics.models import DeliveryRun

    tenant = uuid.uuid4()
    route_id = await _seed_route(factory, tenant)
    async with factory() as session:
        await _bind(session, tenant)
        run = DeliveryRun(
            tenant_id=tenant,
            route_id=route_id,
            business_date=date(2026, 8, 17),
            slot="morning",
            status="in_progress",
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    async def complete():
        async with factory() as session:
            await _bind(session, tenant)
            result = await session.execute(
                text(
                    "UPDATE delivery_run SET status = 'completed' "
                    "WHERE id = :i AND status = 'in_progress'"
                ),
                {"i": run_id},
            )
            await session.commit()
            return result.rowcount

    counts = await asyncio.gather(complete(), complete())
    assert sum(counts) == 1, f"the transition applied {sum(counts)} times"


# --- 13-14: the boundary and financial safety, on the real engine -----------------


async def test_the_run_tables_carry_no_financial_column(factory):
    """Asserted against the LIVE schema, not the model file."""
    async with factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = ANY(:tables)"
                ),
                {"tables": list(NEW_TABLES)},
            )
        ).all()
    financial = ("amount", "quantity", "unit_price", "currency", "total", "balance", "invoice")
    offenders = [
        f"{table}.{column}" for table, column in rows if any(word in column for word in financial)
    ]
    assert not offenders, f"a route table carries a financial column: {offenders}"


async def test_no_logistics_table_references_a_financial_table(factory):
    """No foreign key from the route layer into the books, in either direction."""
    async with factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT tc.table_name, ccu.table_name AS refs "
                    "FROM information_schema.table_constraints tc "
                    "JOIN information_schema.constraint_column_usage ccu "
                    "  ON tc.constraint_name = ccu.constraint_name "
                    "WHERE tc.constraint_type = 'FOREIGN KEY' "
                    "  AND (tc.table_name = ANY(:tables) OR ccu.table_name = ANY(:tables))"
                ),
                {"tables": list(NEW_TABLES)},
            )
        ).all()
    assert rows == [], f"the route layer is wired to another table by FK: {rows}"
