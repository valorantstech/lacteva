"""The scheduler under real concurrency (DEMO-018).

**This test exists because production taught us.** The first real scheduler run
on `dev.phoenixsoft.in` revealed that uvicorn runs with `--workers 4`, so four
scheduler loops woke together and all four generated the same tenant's round.
The deliveries were safe — `uq_delivery_customer_date_slot` saw to that — but
the last writer's `created: 0` overwrote the first's `created: 16`, and the run
record said a day had generated nothing when it had generated everything. With
four workers that is not an edge case; it is what every day would have looked
like.

It lives here rather than in the main suite for the same reason
`test_payment_concurrency_postgres.py` does: on SQLite the test stack shares
ONE connection through a StaticPool, so four "concurrent" sessions are really
one transaction and a rollback in any of them discards the others' work. The
race cannot be expressed there, let alone proven.

Each scheduler pass gets its own session and its own transaction, which is what
makes these genuinely concurrent rather than sequential calls that look it.
"""

import asyncio
import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import func, select
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


DAY = date(2026, 8, 17)
RATE = "56.0000"
QUANTITY = "2.000"


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def _seed(maker, tenant_id: uuid.UUID, customers: int) -> None:
    """A tenant with `customers` daily standing orders, written directly.

    Direct writes rather than the API: this module is about the race, and
    standing up an organization through the HTTP surface would add a great
    deal of unrelated machinery to a test whose subject is two statements.
    """
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.customer.models import Customer, DeliveryPlan

    async with maker() as session:
        await bind_platform_context(session, reason="scheduler concurrency test seed")
        for index in range(customers):
            customer_id = uuid.uuid4()
            session.add(
                Customer(
                    id=customer_id,
                    tenant_id=tenant_id,
                    code=f"CUS-{index:04d}",
                    name=f"Household {index}",
                    currency="INR",
                )
            )
            session.add(
                DeliveryPlan(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    product="RAW-COW-MILK",
                    default_quantity=QUANTITY,
                    quantity_unit="L",
                    unit_price=RATE,
                    currency="INR",
                    effective_from=date(2026, 1, 1),
                    weekdays="1111111",
                    slot="morning",
                    active=True,
                )
            )
        await session.commit()


async def _run(maker, tenant_id: uuid.UUID, label: str):
    """One scheduler pass, in its own session and transaction."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.delivery.scheduler import record_run

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        return await record_run(
            session, tenant_id=tenant_id, day=DAY, trigger="scheduler", label=label
        )


async def _counts(maker, tenant_id: uuid.UUID) -> tuple[int, int, int]:
    """Deliveries, run rows, and the day's recorded `created`."""
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.delivery.models import DeliveryGenerationRun, MilkDelivery

    async with maker() as session:
        await bind_platform_context(session, reason="scheduler concurrency test read")
        deliveries = await session.scalar(
            select(func.count())
            .select_from(MilkDelivery)
            .where(MilkDelivery.tenant_id == tenant_id, MilkDelivery.delivery_date == DAY)
        )
        runs = (
            await session.scalars(
                select(DeliveryGenerationRun).where(
                    DeliveryGenerationRun.tenant_id == tenant_id,
                    DeliveryGenerationRun.business_date == DAY,
                )
            )
        ).all()
        return deliveries or 0, len(runs), (runs[0].created if runs else -1)


async def test_four_concurrent_schedulers_generate_one_round(factory):
    """The production shape: four workers, one tenant, one business date."""
    tenant_id = uuid.uuid4()
    await _seed(factory, tenant_id, customers=25)

    results = await asyncio.gather(
        *(_run(factory, tenant_id, f"worker-{i}") for i in range(4)),
        return_exceptions=True,
    )
    raised = [r for r in results if isinstance(r, Exception)]
    assert not raised, f"a racing scheduler raised: {raised}"

    deliveries, runs, created = await _counts(factory, tenant_id)
    assert deliveries == 25, f"four schedulers produced {deliveries} deliveries for 25 plans"
    assert runs == 1, "one run row per tenant per business date, whatever raced"
    assert created == 25, (
        f"the record says {created} created for a day that created 25 — "
        "a later pass blanked an earlier one"
    )


async def test_exactly_one_pass_does_the_work(factory):
    """Only the claim winner generates; the rest return without re-doing it.

    The deliveries would be safe regardless — that is the constraint's job —
    but four workers each inserting a whole dairy's round every minute is
    load nobody asked for.
    """
    tenant_id = uuid.uuid4()
    await _seed(factory, tenant_id, customers=10)

    results = await asyncio.gather(*(_run(factory, tenant_id, f"w{i}") for i in range(4)))
    created_counts = sorted(result[1].created for result in results)

    assert sum(created_counts) == 10, (
        f"the four passes claim to have created {sum(created_counts)} between them, not 10"
    )
    assert created_counts[-1] == 10, "one pass should have done all of it"
    assert created_counts[:-1] == [0, 0, 0], "more than one pass generated"


async def test_a_second_round_of_passes_creates_nothing(factory):
    """Idempotent across polls as well as across workers."""
    tenant_id = uuid.uuid4()
    await _seed(factory, tenant_id, customers=8)

    await asyncio.gather(*(_run(factory, tenant_id, f"first-{i}") for i in range(4)))
    second = await asyncio.gather(*(_run(factory, tenant_id, f"second-{i}") for i in range(4)))

    assert all(result[1].created == 0 for result in second)
    deliveries, runs, created = await _counts(factory, tenant_id)
    assert deliveries == 8
    assert runs == 1
    assert created == 8, "the day's count did not survive a second round of passes"
