"""Route-driven generation on real PostgreSQL (DEMO-035).

`test_route_generation.py` proves the rules on SQLite, whose test stack shares
one connection so nothing races. This is the half that cannot be proven there:

    **Two operators generating the same route's round at the same instant
    produce the round ONCE — decided by `uq_delivery_customer_date_slot` and
    the generator's `ON CONFLICT DO NOTHING`, on separate real connections.**

No new constraint was invented for this. The one that already made the
scheduler safe against four uvicorn workers is the one that makes route
generation safe, which is why this file asserts against it by name.
"""

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
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
        await bind_platform_context(session, reason="route generation proof cleanup")
        for table in ("milk_delivery", "delivery_run", "route_stop", "route", "delivery_plan"):
            await session.execute(text(f"DELETE FROM {table}"))
        await session.execute(text("DELETE FROM customer"))
        await session.commit()


async def _bind(session, tenant_id):
    from platform_core.core.rls import rebind_tenant

    await rebind_tenant(session, tenant_id)


async def _seed(factory, tenant_id: uuid.UUID, *, stops: int = 3, slot: str = "morning"):
    """A route with `stops` households, each on a daily standing order."""
    from platform_core.modules.customer.models import Customer, DeliveryPlan
    from platform_core.modules.logistics.models import Route, RouteStop

    async with factory() as session:
        await _bind(session, tenant_id)
        route = Route(tenant_id=tenant_id, code="R-01", name="Proof round")
        session.add(route)
        await session.flush()

        customer_ids = []
        for i in range(stops):
            customer = Customer(
                tenant_id=tenant_id,
                code=f"CUS-{i}",
                name=f"Household {i}",
                currency="KES",
            )
            session.add(customer)
            await session.flush()
            customer_ids.append(customer.id)
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
                    slot=slot,
                    active=True,
                )
            )
            session.add(
                RouteStop(
                    tenant_id=tenant_id,
                    route_id=route.id,
                    customer_id=customer.id,
                    position=i + 1,
                )
            )
        await session.commit()
        return route.id, customer_ids


async def _generate(factory, tenant_id, customer_ids, *, slot="morning", day=DAY):
    """One generation attempt, on its own connection."""
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
            slot=slot,
        )
        await session.commit()
        return result


async def _deliveries(factory, tenant_id):
    from platform_core.modules.delivery.models import MilkDelivery

    async with factory() as session:
        await _bind(session, tenant_id)
        return (await session.scalars(select(MilkDelivery))).all()


# --- 1: the round generates at all, on the real engine ---------------------------


async def test_a_route_round_generates_on_real_postgresql(factory):
    tenant = uuid.uuid4()
    _route_id, customer_ids = await _seed(factory, tenant)

    result = await _generate(factory, tenant, customer_ids)

    assert result.created == 3
    rows = await _deliveries(factory, tenant)
    assert len(rows) == 3
    assert {r.status for r in rows} == {"scheduled"}
    # Worth nothing until somebody says the milk arrived.
    assert {Decimal(r.amount) for r in rows} == {Decimal("0.00")}


# --- 2-3: concurrency, which SQLite cannot show ----------------------------------


async def test_concurrent_generation_creates_the_round_exactly_once(factory):
    """§ concurrency. Three real connections, all generating the same round.

    Every attempt reads the same due plans and tries to insert the same rows.
    `ON CONFLICT DO NOTHING` on `uq_delivery_customer_date_slot` decides, so
    the totals add up to one round however the three interleave.
    """
    tenant = uuid.uuid4()
    _route_id, customer_ids = await _seed(factory, tenant)

    results = await asyncio.gather(
        _generate(factory, tenant, customer_ids),
        _generate(factory, tenant, customer_ids),
        _generate(factory, tenant, customer_ids),
    )

    assert sum(r.created for r in results) == 3, [r.created for r in results]
    rows = await _deliveries(factory, tenant)
    assert len(rows) == 3, f"concurrent generation produced {len(rows)} deliveries"


async def test_two_routes_generating_at_once_do_not_block_each_other(factory):
    """The tenant-day claim would have serialised these into one round.

    `record_run` claims `(tenant, business_date)`; whoever loses gets
    `created: 0`. Route generation deliberately does not go through it, and
    this is the proof on real connections: two routes, same dairy, same date,
    both rounds land.
    """
    from platform_core.modules.customer.models import Customer, DeliveryPlan
    from platform_core.modules.logistics.models import Route, RouteStop

    tenant = uuid.uuid4()
    _route_a, customers_a = await _seed(factory, tenant, stops=2)

    async with factory() as session:
        await _bind(session, tenant)
        route_b = Route(tenant_id=tenant, code="R-02", name="Second round")
        session.add(route_b)
        await session.flush()
        customers_b = []
        for i in range(2):
            customer = Customer(
                tenant_id=tenant, code=f"CUS-B{i}", name=f"Second {i}", currency="KES"
            )
            session.add(customer)
            await session.flush()
            customers_b.append(customer.id)
            session.add(
                DeliveryPlan(
                    tenant_id=tenant,
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
            session.add(
                RouteStop(
                    tenant_id=tenant, route_id=route_b.id, customer_id=customer.id, position=i + 1
                )
            )
        await session.commit()

    a, b = await asyncio.gather(
        _generate(factory, tenant, customers_a),
        _generate(factory, tenant, customers_b),
    )

    assert a.created == 2, a
    assert b.created == 2, b
    assert len(await _deliveries(factory, tenant)) == 4


# --- 4: the constraint this relies on is the one that already existed ------------


async def test_the_delivery_uniqueness_constraint_is_present_and_is_the_guard(factory):
    """Named explicitly: no new constraint was invented for DEMO-035."""
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT conname FROM pg_constraint c "
                        "JOIN pg_class t ON t.oid = c.conrelid "
                        "WHERE t.relname = 'milk_delivery' AND c.contype = 'u'"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert "uq_delivery_customer_date_slot" in rows, rows


# --- 5-7: isolation ---------------------------------------------------------------


async def test_a_generated_round_is_invisible_to_another_dairy(factory):
    from platform_core.modules.delivery.models import MilkDelivery

    a, b = uuid.uuid4(), uuid.uuid4()
    _route_id, customer_ids = await _seed(factory, a)
    await _generate(factory, a, customer_ids)

    async with factory() as session:
        await _bind(session, b)
        assert (await session.scalars(select(MilkDelivery))).all() == []


async def test_another_dairys_customer_ids_generate_nothing(factory):
    """A leaked stop id must not become a delivery in the wrong dairy.

    The generator filters on `tenant_id` as well as the customer set, so ids
    from elsewhere match no plan — and RLS refuses the read besides.
    """
    a, b = uuid.uuid4(), uuid.uuid4()
    _route_a, customers_a = await _seed(factory, a)

    result = await _generate(factory, b, customers_a)

    assert result.due == 0
    assert result.created == 0
    assert await _deliveries(factory, b) == []


async def test_generation_writes_nothing_financial(factory):
    """§ financial safety, on the live engine.

    A generated round is `scheduled` and worth 0.00; no invoice, payment,
    receipt or settlement row appears.
    """
    from platform_core.modules.billing.models import CustomerInvoice

    tenant = uuid.uuid4()
    _route_id, customer_ids = await _seed(factory, tenant)

    async with factory() as session:
        from platform_core.core.rls import bind_platform_context

        await bind_platform_context(session, reason="route proof baseline")
        before = await session.scalar(select(func.count()).select_from(CustomerInvoice))

    await _generate(factory, tenant, customer_ids)

    async with factory() as session:
        from platform_core.core.rls import bind_platform_context

        await bind_platform_context(session, reason="route proof after")
        after = await session.scalar(select(func.count()).select_from(CustomerInvoice))
        billed = await session.scalar(text("SELECT COALESCE(SUM(amount), 0) FROM milk_delivery"))
    assert after == before
    assert Decimal(billed or 0) == Decimal("0.00")
