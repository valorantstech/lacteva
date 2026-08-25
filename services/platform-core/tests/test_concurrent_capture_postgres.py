"""Two operators capturing at the same moment, on real PostgreSQL (P1-SCALE-RACE-001).

The P0-PRODUCT-008 audit left this open as "no two-operator collection race
test", and it is the half SQLite structurally cannot evaluate.

`next_document_number` locks the counter row `FOR UPDATE` before reading it,
precisely because allocation is a read-modify-write and two concurrent
allocations would otherwise both read the same `next_value` and both return
it. **`FOR UPDATE` is a no-op on SQLite.** So the guarantee that protects every
parchi number in the platform had never been evaluated on the engine that
implements it — a PostgreSQL guarantee tested only on SQLite is untested.

What is proven here is the ALLOCATION race: N operators completing N different
captures at once, against one tenant's counter. `complete()` mints the number
through this same function (`service.py`, "the parchi's number is minted at the
moment the transaction becomes immutable"), and the public `slip()` path
reaches it for a transaction that has none — so the race exercised is the one a
real second operator creates, at the layer where it lives.

The neighbouring suite `test_collection_slip_postgres.py` proves the OTHER
race, which is a different question with a different answer: two readers
racing for the SAME transaction must converge on ONE number. Here, two
operators with two transactions must get TWO — and the series must account for
exactly what it handed out.

Why a duplicate would matter: `uq_milk_tx_slip` is a UNIQUE constraint, so the
losing allocation does not quietly produce a twin — it raises, and the operator
who was standing at the counter with a farmer's milk gets a 500 on the document
that farmer is owed.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

MARKER = "PG-RACE"


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
        await bind_platform_context(session, reason="capture race proof cleanup")
        await session.execute(
            text("DELETE FROM milk_collection_transaction WHERE container_identifier = :m"),
            {"m": MARKER},
        )
        await session.execute(
            text("DELETE FROM document_sequence WHERE doc_type = 'collection_slip'")
        )
        await session.commit()


def _bare_service(session):
    """Only what the slip path touches; anything else appearing is an alarm."""
    from platform_core.modules.milk_collection.service import MilkCollectionService

    return MilkCollectionService(session, None, None, None, None, None)


async def _seed_pre_slip(factory, tenant_id: uuid.UUID, count: int) -> list[uuid.UUID]:
    """`count` completed captures, each still without its parchi number."""
    from platform_core.core.db import utcnow
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.milk_collection.models import MilkCollectionTransaction

    async with factory() as session:
        await rebind_tenant(session, tenant_id)
        rows = [
            MilkCollectionTransaction(
                tenant_id=tenant_id,
                session_id=uuid.uuid4(),
                center_id=uuid.uuid4(),
                operator_id=uuid.uuid4(),  # a DIFFERENT operator each time
                state="COMPLETED",
                milk_type="cow",
                container_identifier=MARKER,
                completed_at=utcnow(),
            )
            for _ in range(count)
        ]
        session.add_all(rows)
        # Ids are assigned on flush, not on construction — reading them before
        # this returns None and the mint below cannot find its own row.
        await session.flush()
        ids = [tx.id for tx in rows]
        await session.commit()
    return ids


async def _mint(factory, tenant_id: uuid.UUID, tx_id: uuid.UUID) -> str:
    """One operator's capture, in its own transaction, as a request would be."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.core.tenancy import set_current_tenant

    async with factory() as session:
        # Set inside the task: `asyncio.gather` copies the context at task
        # creation, so each concurrent caller carries its own tenant — which is
        # what makes the two-tenant test below meaningful rather than lucky.
        set_current_tenant(tenant_id)
        await rebind_tenant(session, tenant_id)
        view = await _bare_service(session).slip(tx_id)
        await session.commit()
        return view.slip_number


async def _sequence_next_value(factory, tenant_id: uuid.UUID) -> int:
    from platform_core.core.rls import bind_platform_context

    async with factory() as session:
        await bind_platform_context(session, reason="capture race proof assertion")
        return await session.scalar(
            text(
                "SELECT next_value FROM document_sequence "
                "WHERE tenant_id = :t AND doc_type = 'collection_slip'"
            ),
            {"t": str(tenant_id)},
        )


async def test_two_operators_completing_at_once_get_different_numbers(factory):
    """The audit's open gap, stated as a test.

    Two operators, two farmers, two captures, one counter — at the same
    instant. Each parchi must carry its own number.
    """
    tenant = uuid.uuid4()
    first_id, second_id = await _seed_pre_slip(factory, tenant, 2)

    first, second = await asyncio.gather(
        _mint(factory, tenant, first_id),
        _mint(factory, tenant, second_id),
    )

    assert first != second, f"two captures shared one parchi number: {first}"
    assert {first[-6:], second[-6:]} == {"000001", "000002"}, (first, second)


async def test_ten_concurrent_captures_consume_exactly_ten_numbers(factory):
    """No duplicates, and no gaps either.

    A duplicate is the failure that hurts (the UNIQUE constraint turns it into
    a 500 at the counter). A GAP is the quieter one: the series is a document
    trail a dairy is audited on, and a missing number invites the question of
    what was deleted. Ten at once must consume exactly ten.
    """
    tenant = uuid.uuid4()
    ids = await _seed_pre_slip(factory, tenant, 10)

    numbers = await asyncio.gather(*(_mint(factory, tenant, i) for i in ids))

    assert len(set(numbers)) == 10, f"duplicate parchi numbers issued: {sorted(numbers)}"
    assert sorted(n[-6:] for n in numbers) == [f"{i:06d}" for i in range(1, 11)]
    # The counter agrees with what it handed out — nothing double-spent.
    assert await _sequence_next_value(factory, tenant) == 11

    # And the database itself holds ten distinct numbered rows, not nine.
    from platform_core.core.rls import bind_platform_context

    async with factory() as session:
        await bind_platform_context(session, reason="capture race proof assertion")
        stored = await session.scalar(
            text(
                "SELECT count(DISTINCT slip_number) FROM milk_collection_transaction "
                "WHERE tenant_id = :t AND container_identifier = :m"
            ),
            {"t": str(tenant), "m": MARKER},
        )
    assert stored == 10


async def test_two_dairies_capturing_at_once_keep_separate_series(factory):
    """One dairy's rush must not consume another dairy's numbers.

    The counter is per tenant, so the lock must be too. If it were not, the
    second dairy's first parchi of the year would start at 000003 — a visible,
    inexplicable jump in someone else's document trail.
    """
    left, right = uuid.uuid4(), uuid.uuid4()
    left_ids = await _seed_pre_slip(factory, left, 2)
    right_ids = await _seed_pre_slip(factory, right, 2)

    results = await asyncio.gather(
        *(_mint(factory, left, i) for i in left_ids),
        *(_mint(factory, right, i) for i in right_ids),
    )
    left_numbers, right_numbers = results[:2], results[2:]

    assert sorted(n[-6:] for n in left_numbers) == ["000001", "000002"]
    assert sorted(n[-6:] for n in right_numbers) == ["000001", "000002"]
    assert await _sequence_next_value(factory, left) == 3
    assert await _sequence_next_value(factory, right) == 3
