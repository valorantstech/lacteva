"""The route-level report on real PostgreSQL (DEMO-037).

`test_route_report.py` proves the rules on SQLite. This is the half that cannot
be proven there:

    **The breakdown is derived from the route membership and the deliveries at
    read time, it is isolated by the database rather than by a `WHERE` clause,
    and it stays right while a route-aware round is being generated
    concurrently.**

The concurrency test here is not about the report racing itself — a read cannot
corrupt anything. It is about the report agreeing with what concurrent
generation actually produced, which is the question an operator asks at 06:00
while the vans are loading.
"""

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

DAY = date(2026, 8, 17)


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
        await bind_platform_context(session, reason="route report proof cleanup")
        for table in (
            "milk_delivery",
            "delivery_generation_run",
            "route_stop",
            "route",
            "delivery_plan",
            "customer",
        ):
            await session.execute(text(f"DELETE FROM {table}"))
        await session.execute(text("DELETE FROM organization WHERE slug LIKE 'proof-%'"))
        await session.commit()


async def _bind(session, tenant_id):
    from platform_core.core.rls import rebind_tenant

    await rebind_tenant(session, tenant_id)


async def _seed(factory, tenant_id, *, routes: int = 2, per_route: int = 2, unrouted: int = 0):
    """Routes over households on daily plans, plus optional off-route ones."""
    # The report asks the ORGANIZATION what its money is denominated in
    # (DEMO-013), so a fabricated tenant id is not enough — there has to be a
    # dairy. Created through the platform-global session because the
    # organization row is platform-global, not tenant-owned.
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.customer.models import Customer, DeliveryPlan
    from platform_core.modules.logistics.models import Route, RouteStop
    from platform_core.modules.organization.models import Organization

    async with factory() as session:
        await bind_platform_context(session, reason="route report proof: the dairy")
        session.add(
            Organization(
                id=tenant_id,
                name=f"Proof Dairy {tenant_id.hex[:8]}",
                slug=f"proof-{tenant_id.hex[:12]}",
                country_code="KE",
                org_type="cooperative",
                currency_code="KES",
                timezone="Africa/Nairobi",
            )
        )
        await session.commit()

    async with factory() as session:
        await _bind(session, tenant_id)
        index = 0

        async def household(code: str):
            nonlocal index
            customer = Customer(
                tenant_id=tenant_id, code=code, name=f"Household {code}", currency="KES"
            )
            session.add(customer)
            await session.flush()
            session.add(
                DeliveryPlan(
                    tenant_id=tenant_id,
                    customer_id=customer.id,
                    product="RAW-COW-MILK",
                    default_quantity=Decimal("2.000"),
                    quantity_unit="L",
                    unit_price=Decimal("60.0000"),
                    currency="KES",
                    effective_from=date(2026, 1, 1),
                    weekdays="1111111",
                    slot="morning",
                    active=True,
                )
            )
            index += 1
            return customer

        route_customers: list[list[uuid.UUID]] = []
        for r in range(routes):
            route = Route(tenant_id=tenant_id, code=f"R-{r + 1:02d}", name=f"Round {r + 1}")
            session.add(route)
            await session.flush()
            ids = []
            for s in range(per_route):
                customer = await household(f"C{r}{s}")
                ids.append(customer.id)
                session.add(
                    RouteStop(
                        tenant_id=tenant_id,
                        route_id=route.id,
                        customer_id=customer.id,
                        position=s + 1,
                    )
                )
            route_customers.append(ids)
        for u in range(unrouted):
            await household(f"U{u}")
        await session.commit()
        return route_customers


async def _generate(factory, tenant_id, customer_ids, *, day=DAY):
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.delivery.generation import generate_for_day

    async with factory() as session:
        await _bind(session, tenant_id)
        set_current_tenant(tenant_id)
        result = await generate_for_day(
            session,
            tenant_id=tenant_id,
            day=day,
            actor_id=None,
            customer_ids=set(customer_ids),
            slot="morning",
        )
        await session.commit()
        return result


async def _report(factory, tenant_id, *, day=DAY):
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.delivery.service import DeliveryService
    from platform_core.modules.logistics.service import route_memberships

    async with factory() as session:
        await _bind(session, tenant_id)
        set_current_tenant(tenant_id)

        async def membership():
            return await route_memberships(session, tenant_id)

        service = DeliveryService(session, None, AuditService(session))
        return await service.report(date_from=day, date_to=day, route_membership=membership)


# --- 1: the breakdown on the real engine -----------------------------------------


async def test_the_report_breaks_the_round_down_by_route(factory):
    tenant = uuid.uuid4()
    routes = await _seed(factory, tenant, routes=2, per_route=2)
    for ids in routes:
        await _generate(factory, tenant, ids)

    report = await _report(factory, tenant)

    assert len(report.by_route) == 2
    rows = {row.code: row for row in report.by_route}
    assert rows["R-01"].stops == 2
    assert rows["R-01"].scheduled == 2
    assert rows["R-02"].scheduled == 2
    # Generated rounds are worth nothing until somebody says the milk arrived.
    assert rows["R-01"].amount == Decimal("0.00")
    assert report.routes == 2


async def test_off_route_households_are_reported_as_unrouted(factory):
    tenant = uuid.uuid4()
    routes = await _seed(factory, tenant, routes=1, per_route=2, unrouted=2)
    await _generate(factory, tenant, routes[0])

    # Then the WHOLE tenant, so the off-route households have rows too — the
    # scheduler's fallback call, unnarrowed.
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.delivery.generation import generate_for_day

    async with factory() as session:
        await _bind(session, tenant)
        set_current_tenant(tenant)
        await generate_for_day(session, tenant_id=tenant, day=DAY, actor_id=None, slot="morning")
        await session.commit()

    report = await _report(factory, tenant)

    assert sum(row.scheduled for row in report.by_route) == 2
    assert report.unrouted == 2, report.unrouted
    assert sum(row.scheduled for row in report.by_route) + report.unrouted == report.planned


# --- 2: isolation, enforced by the database --------------------------------------


async def test_another_dairys_routes_are_invisible_to_this_report(factory):
    a, b = uuid.uuid4(), uuid.uuid4()
    routes_a = await _seed(factory, a, routes=2, per_route=2)
    await _seed(factory, b, routes=1, per_route=3)
    for ids in routes_a:
        await _generate(factory, a, ids)

    report_a = await _report(factory, a)
    report_b = await _report(factory, b)

    assert {r.code for r in report_a.by_route} == {"R-01", "R-02"}
    assert report_a.routes == 2
    # Dairy B has a route but no deliveries, and sees nothing of A's round.
    assert report_b.routes == 0
    assert report_b.planned == 0
    assert all(row.scheduled == 0 for row in report_b.by_route)


async def test_the_membership_provider_is_filtered_by_the_database(factory):
    """RLS, not a WHERE clause: bound to B, A's routes are simply not there."""
    from platform_core.modules.logistics.service import route_memberships

    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(factory, a, routes=2, per_route=1)

    async with factory() as session:
        await _bind(session, b)
        # Ask for A's routes while bound to B — the policy answers, not the
        # predicate: even the tenant_id argument cannot fetch them.
        assert await route_memberships(session, a) == []


# --- 3: the report agrees with concurrent generation -----------------------------


async def test_the_report_agrees_with_a_concurrently_generated_round(factory):
    """The 06:00 question: is what I am reading what actually went out?

    Three concurrent generations of the same two routes, then one report. The
    ON CONFLICT makes the round exactly one round; the report has to say so.
    """
    tenant = uuid.uuid4()
    routes = await _seed(factory, tenant, routes=2, per_route=2)

    await asyncio.gather(*[_generate(factory, tenant, ids) for ids in routes for _ in range(3)])

    report = await _report(factory, tenant)

    assert report.planned == 4, report.planned
    assert sum(row.scheduled for row in report.by_route) == 4
    assert report.routes == 2

    async with factory() as session:
        await _bind(session, tenant)
        rows = (await session.execute(text("SELECT count(*) FROM milk_delivery"))).scalar()
    assert rows == 4, f"{rows} deliveries behind a report claiming 4"


async def test_reporting_twice_gives_the_same_answer(factory):
    """Idempotent because it is a read — asserted rather than assumed."""
    tenant = uuid.uuid4()
    routes = await _seed(factory, tenant, routes=2, per_route=2)
    for ids in routes:
        await _generate(factory, tenant, ids)

    first = await _report(factory, tenant)
    second = await _report(factory, tenant)

    assert [(r.code, r.scheduled, r.stops) for r in first.by_route] == [
        (r.code, r.scheduled, r.stops) for r in second.by_route
    ]
    assert first.planned == second.planned


# --- 4: financial safety ---------------------------------------------------------


async def test_reading_the_route_report_writes_nothing(factory):
    tenant = uuid.uuid4()
    routes = await _seed(factory, tenant, routes=2, per_route=2)
    for ids in routes:
        await _generate(factory, tenant, ids)

    async with factory() as session:
        await _bind(session, tenant)
        before = (
            await session.execute(
                text("SELECT count(*), COALESCE(SUM(amount),0) FROM milk_delivery")
            )
        ).one()

    await _report(factory, tenant)

    async with factory() as session:
        await _bind(session, tenant)
        after = (
            await session.execute(
                text("SELECT count(*), COALESCE(SUM(amount),0) FROM milk_delivery")
            )
        ).one()
    assert tuple(before) == tuple(after)
    assert Decimal(after[1] or 0) == Decimal("0.00")
