"""Route-aware scheduled generation on real PostgreSQL (DEMO-036).

`test_scheduler_routes.py` proves the rules on SQLite, whose test stack shares
one connection so nothing races. This is the half that cannot be proven there:

    **Two scheduler workers waking on the same dairy's morning produce one
    round — the tenant-day claim gives the work to one of them, and the routes
    are iterated underneath that claim rather than each claiming the day for
    itself.**

That distinction is DEMO-035's finding turned into a scheduler guarantee, and
it is the reason this file exists on the real engine.
"""

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
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
        await bind_platform_context(session, reason="scheduler route proof cleanup")
        for table in (
            "milk_delivery",
            "delivery_generation_run",
            "route_stop",
            "route",
            "delivery_plan",
            "customer",
        ):
            await session.execute(text(f"DELETE FROM {table}"))
        await session.commit()


async def _bind(session, tenant_id):
    from platform_core.core.rls import rebind_tenant

    await rebind_tenant(session, tenant_id)


async def _seed(factory, tenant_id, *, routes: int = 2, per_route: int = 2):
    """`routes` routes, each with `per_route` households on a daily plan."""
    from platform_core.modules.customer.models import Customer, DeliveryPlan
    from platform_core.modules.logistics.models import Route, RouteStop

    async with factory() as session:
        await _bind(session, tenant_id)
        index = 0
        for r in range(routes):
            route = Route(tenant_id=tenant_id, code=f"R-{r + 1:02d}", name=f"Round {r + 1}")
            session.add(route)
            await session.flush()
            for _ in range(per_route):
                customer = Customer(
                    tenant_id=tenant_id,
                    code=f"CUS-{index}",
                    name=f"Household {index}",
                    currency="KES",
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
                session.add(
                    RouteStop(
                        tenant_id=tenant_id,
                        route_id=route.id,
                        customer_id=customer.id,
                        position=index + 1,
                    )
                )
                index += 1
        await session.commit()


async def _seed_without_routes(factory, tenant_id, *, households: int = 3):
    from platform_core.modules.customer.models import Customer, DeliveryPlan

    async with factory() as session:
        await _bind(session, tenant_id)
        for i in range(households):
            customer = Customer(
                tenant_id=tenant_id, code=f"NR-{i}", name=f"No route {i}", currency="KES"
            )
            session.add(customer)
            await session.flush()
            session.add(
                DeliveryPlan(
                    tenant_id=tenant_id,
                    customer_id=customer.id,
                    product="RAW-COW-MILK",
                    default_quantity=Decimal("1.000"),
                    quantity_unit="L",
                    unit_price=Decimal("60.0000"),
                    currency="KES",
                    effective_from=date(2026, 1, 1),
                    weekdays="1111111",
                    slot="morning",
                    active=True,
                )
            )
        await session.commit()


async def _pass(factory, tenant_id, *, with_routes: bool = True):
    """One scheduler pass for one tenant, on its own connection."""
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.delivery.scheduler import record_run
    from platform_core.modules.logistics.service import scheduled_round_scopes

    async with factory() as session:
        await _bind(session, tenant_id)
        set_current_tenant(tenant_id)

        async def provider():
            return await scheduled_round_scopes(session, tenant_id, DAY)

        run, result = await record_run(
            session,
            tenant_id=tenant_id,
            day=DAY,
            trigger="scheduler",
            route_scopes=provider if with_routes else None,
        )
        await session.commit()
        return (run.status if run else None), result.created


async def _deliveries(factory, tenant_id):
    from platform_core.modules.delivery.models import MilkDelivery

    async with factory() as session:
        await _bind(session, tenant_id)
        return (await session.scalars(select(MilkDelivery))).all()


async def _runs(factory, tenant_id):
    from platform_core.modules.delivery.models import DeliveryGenerationRun

    async with factory() as session:
        await _bind(session, tenant_id)
        return (await session.scalars(select(DeliveryGenerationRun))).all()


# --- 1: route-aware generation on the real engine --------------------------------


async def test_the_scheduler_generates_every_route_on_real_postgresql(factory):
    tenant = uuid.uuid4()
    await _seed(factory, tenant, routes=2, per_route=2)

    status, created = await _pass(factory, tenant)

    assert status == "success", status
    assert created == 4, created
    rows = await _deliveries(factory, tenant)
    assert len(rows) == 4
    assert {r.status for r in rows} == {"scheduled"}
    assert {Decimal(r.amount) for r in rows} == {Decimal("0.00")}


# --- 2: the no-route fallback ----------------------------------------------------


async def test_a_dairy_without_routes_still_gets_its_whole_round(factory):
    """Backwards compatibility on the real engine."""
    tenant = uuid.uuid4()
    await _seed_without_routes(factory, tenant, households=3)

    status, created = await _pass(factory, tenant)

    assert status == "success"
    assert created == 3
    assert len(await _deliveries(factory, tenant)) == 3


async def test_a_dairy_with_routes_generates_only_the_routed_households(factory):
    """The two paths side by side: a routed dairy skips what is off-route."""
    tenant = uuid.uuid4()
    await _seed(factory, tenant, routes=1, per_route=2)
    await _seed_without_routes(factory, tenant, households=2)

    _status, created = await _pass(factory, tenant)

    assert created == 2, "the off-route households were generated too"
    assert len(await _deliveries(factory, tenant)) == 2


# --- 3: concurrency, which SQLite cannot show ------------------------------------


async def test_two_scheduler_workers_produce_one_round(factory):
    """§ concurrency. Three real connections, all waking on the same morning.

    The tenant-day claim gives the work to one of them; the losers return the
    day's record rather than racing to redo it. Whatever the interleaving, one
    round exists and one run row describes it.
    """
    tenant = uuid.uuid4()
    await _seed(factory, tenant, routes=2, per_route=2)

    outcomes = await asyncio.gather(
        _pass(factory, tenant), _pass(factory, tenant), _pass(factory, tenant)
    )

    rows = await _deliveries(factory, tenant)
    assert len(rows) == 4, f"concurrent scheduler passes produced {len(rows)} deliveries"

    runs = await _runs(factory, tenant)
    assert len(runs) == 1, f"{len(runs)} run rows for one tenant-day"
    # Exactly one pass did the work; the others found the day owned.
    assert sum(created for _status, created in outcomes) == 4, outcomes


async def test_repeated_passes_are_idempotent(factory):
    """Sequential rather than concurrent — the ordinary scheduler poll."""
    tenant = uuid.uuid4()
    await _seed(factory, tenant, routes=2, per_route=2)

    first = await _pass(factory, tenant)
    second = await _pass(factory, tenant)

    assert first[1] == 4
    assert second[1] == 0, "a second poll generated the round again"
    assert len(await _deliveries(factory, tenant)) == 4


async def test_one_claim_per_tenant_day_however_many_routes(factory):
    """DEMO-035's finding, guarded on the real engine.

    A run row PER ROUTE would mean the second route lost the claim and
    generated nothing. One row, four deliveries.
    """
    tenant = uuid.uuid4()
    await _seed(factory, tenant, routes=4, per_route=1)

    _status, created = await _pass(factory, tenant)

    assert created == 4, created
    runs = await _runs(factory, tenant)
    assert len(runs) == 1
    assert runs[0].created == 4


# --- 4: tenant isolation ---------------------------------------------------------


async def test_one_dairys_scheduler_pass_never_touches_another(factory):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(factory, a, routes=1, per_route=2)
    await _seed(factory, b, routes=1, per_route=3)

    await _pass(factory, a)

    assert len(await _deliveries(factory, a)) == 2
    assert await _deliveries(factory, b) == [], "the pass generated another dairy's round"

    await _pass(factory, b)
    assert len(await _deliveries(factory, b)) == 3
    assert len(await _deliveries(factory, a)) == 2


async def test_the_provider_reads_only_this_dairys_routes(factory):
    from platform_core.modules.logistics.service import scheduled_round_scopes

    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(factory, a, routes=2, per_route=1)
    await _seed(factory, b, routes=1, per_route=1)

    async with factory() as session:
        await _bind(session, a)
        scopes_a = await scheduled_round_scopes(session, a, DAY)
        await _bind(session, b)
        scopes_b = await scheduled_round_scopes(session, b, DAY)

    assert {s.label.split("/")[0] for s in scopes_a} == {"R-01", "R-02"}
    assert {s.label.split("/")[0] for s in scopes_b} == {"R-01"}
    ids_a = {c for s in scopes_a for c in s.customer_ids}
    ids_b = {c for s in scopes_b for c in s.customer_ids}
    assert ids_a.isdisjoint(ids_b)


# --- 5: financial safety ---------------------------------------------------------


async def test_a_route_aware_pass_writes_nothing_financial(factory):
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.billing.models import CustomerInvoice

    tenant = uuid.uuid4()
    await _seed(factory, tenant, routes=2, per_route=2)

    async with factory() as session:
        await bind_platform_context(session, reason="scheduler proof baseline")
        before = await session.scalar(select(text("count(*)")).select_from(CustomerInvoice))

    await _pass(factory, tenant)

    async with factory() as session:
        await bind_platform_context(session, reason="scheduler proof after")
        after = await session.scalar(select(text("count(*)")).select_from(CustomerInvoice))
        billed = await session.scalar(text("SELECT COALESCE(SUM(amount), 0) FROM milk_delivery"))
    assert after == before
    assert Decimal(billed or 0) == Decimal("0.00")
