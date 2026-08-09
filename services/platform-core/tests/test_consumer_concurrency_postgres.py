"""Two consumer runners, one database (DEPLOY-001).

Divergence #42 recorded that the platform's per-process worker loops mean
"running two API hosts runs two relays and two consumer runners", and rated it
"safe (CAS dispatch + idempotency ledger) but untested".

**The staging rehearsal tested it, and `safe` was too strong.** With the API's
own consumer loop running while a second runner drove the same events, three
unique constraints fired — `uq_consumer_execution`, `uq_receipt_payment` and
`uq_projection_daily`. The business data stayed correct (that is what the
constraints are for: no duplicate receipt, nothing dead-lettered), but every
collision marks an execution FAILED, spends one of the event's five retries,
and logs an error an operator would page on. A platform that cannot survive its
own second replica cannot be scaled horizontally, which is what "workers on
exactly one host" was papering over.

`ConsumerRunner._claim` now takes a PostgreSQL advisory lock per consumer name.
These tests prove it, and the control proves the race was real to begin with —
none of this is observable on SQLite, which has no advisory locks and only one
writer.
"""

import asyncio
import uuid

import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

RUNNERS = 4


@pytest_asyncio.fixture
async def factory(monkeypatch):
    from platform_core.core.config import get_settings
    from platform_core.core.model_registry import import_all_models

    # Consumers are discovered at application startup, which these tests never
    # perform — without this `registered_consumers()` is empty, `run_once()`
    # iterates nothing, and every assertion about concurrency passes because no
    # work happens at all.
    import_all_models()

    monkeypatch.setattr(get_settings(), "database_url", POSTGRES_URL)
    engine = create_async_engine(POSTGRES_URL, pool_size=RUNNERS + 4, max_overflow=4)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed_events(factory, count: int) -> uuid.UUID:
    """Events a real consumer handles, written straight to the durable log."""
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.event_relay.models import OutboxEvent

    tenant_id = uuid.uuid4()
    async with factory() as session:
        await bind_platform_context(session, reason="consumer concurrency seeding")
        for index in range(count):
            session.add(
                OutboxEvent(
                    tenant_id=tenant_id,
                    event_name="supplier.supplier-registered.v1",
                    aggregate_type="supplier",
                    aggregate_id=uuid.uuid4(),
                    payload={
                        "supplier_id": str(uuid.uuid4()),
                        "code": f"S-{index:06d}",
                        "full_name": f"Farmer {index}",
                        "phone": f"+25470000{index:04d}",
                        "locale": "en",
                        "status": "active",
                    },
                    status="pending",
                )
            )
        await session.commit()
    return tenant_id


async def _drive(factory, rounds: int = 3):
    """One runner, driven the way the background loop drives it."""
    from platform_core.core.rls import PlatformSessionFactory
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    runner = ConsumerRunner(PlatformSessionFactory(factory, "concurrency test runner"))
    totals = {"processed": 0, "failed": 0}
    for _ in range(rounds):
        result = await runner.run_once()
        totals["processed"] += result["processed"]
        totals["failed"] += result["failed"]
    return totals


async def _failed_executions(factory) -> int:
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.event_relay.models import ConsumerExecution

    async with factory() as session:
        await bind_platform_context(session, reason="concurrency test verification")
        return (
            await session.scalar(
                select(func.count())
                .select_from(ConsumerExecution)
                .where(ConsumerExecution.status.in_(("failed", "dead")))
            )
        ) or 0


async def test_concurrent_runners_do_not_collide(factory):
    """The fix. Four runners, the same events, no failed executions.

    A failure here means two hosts are again fighting over the same consumer —
    the platform would still be correct, but it would burn retries and page
    somebody at 05:00.

    **`processed > 0` is not decoration.** The first version of this test
    asserted only that nothing FAILED, which is trivially true when nothing is
    processed at all — and that is exactly what happened: taking the claim
    required a `commit()`, the commit discarded the `SET LOCAL` RLS bypass, and
    the runner then saw zero tenant rows and reported success. The suite stayed
    green; the staging rehearsal showed a live API generating no receipts and
    no notifications. A test that cannot tell "did the work" from "did nothing"
    is not a test.
    """
    await _seed_events(factory, 12)
    before = await _failed_executions(factory)

    totals = await asyncio.gather(*[_drive(factory) for _ in range(RUNNERS)])
    processed = sum(t["processed"] for t in totals)

    after = await _failed_executions(factory)
    assert after == before, (
        f"{after - before} execution(s) failed with {RUNNERS} concurrent runners — "
        "the per-consumer claim is not holding"
    )
    assert processed > 0, (
        "no events were processed at all — the runner is claiming the consumer "
        "and then seeing nothing, which is what losing the RLS bypass looks like"
    )


async def test_only_one_runner_enters_a_consumer_at_a_time(factory):
    """The control, stated as the property rather than as a hoped-for symptom.

    The collisions themselves were observed in the staging rehearsal, where two
    OS processes — the API's own consumer loop and a second runner — hit
    `uq_consumer_execution`, `uq_receipt_payment` and `uq_projection_daily`.
    Reproducing an IntegrityError from inside a single event loop is a race
    against the scheduler and would make this suite flaky, which is worse than
    useless.

    So this asserts what the lock actually guarantees, and of which those
    collisions were the symptom: a second holder is REFUSED. That is
    timing-independent, and it fails immediately if `_claim` ever becomes a
    no-op on PostgreSQL.
    """
    from platform_core.core.rls import PlatformSessionFactory
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    await _seed_events(factory, 6)
    before = await _failed_executions(factory)
    totals = await asyncio.gather(*[_drive(factory) for _ in range(RUNNERS)])
    # A DELTA, not an absolute: these suites share one database and an absolute
    # zero would be asserting about every test that ran before this one.
    assert await _failed_executions(factory) == before, "concurrent runners produced failures"
    assert sum(t["processed"] for t in totals) > 0, "nothing was processed — see above"

    runner = ConsumerRunner(PlatformSessionFactory(factory, "control"))
    async with factory() as first:
        assert await runner._claim(first, "control-probe") is True
        async with factory() as second:
            assert await runner._claim(second, "control-probe") is False, (
                "two runners were both granted the same consumer — the claim is a no-op"
            )
        await runner._release(first, "control-probe")


async def test_every_event_is_still_handled_exactly_once(factory):
    """The claim must not cost correctness: skipping a consumer this cycle is
    only acceptable because the next cycle picks it up."""
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.event_relay.models import ConsumerExecution

    tenant_id = await _seed_events(factory, 8)
    await asyncio.gather(*[_drive(factory, rounds=6) for _ in range(RUNNERS)])

    async with factory() as session:
        await bind_platform_context(session, reason="concurrency test verification")
        rows = (
            await session.execute(
                select(ConsumerExecution.consumer_name, ConsumerExecution.event_id, func.count())
                .where(ConsumerExecution.tenant_id == tenant_id)
                .group_by(ConsumerExecution.consumer_name, ConsumerExecution.event_id)
                .having(func.count() > 1)
            )
        ).all()
    assert not rows, f"an event was recorded twice for one consumer: {rows}"


async def test_a_second_runner_is_told_no_rather_than_blocking(factory):
    """`pg_try_advisory_lock`, not `pg_advisory_lock`.

    A blocking lock would make a slow consumer on one host stall every other
    host's whole loop — including the consumers it is not competing for.
    """
    from platform_core.core.rls import PlatformSessionFactory
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    runner = ConsumerRunner(PlatformSessionFactory(factory, "claim test"))
    name = "notification-dispatch"

    async with factory() as holder:
        assert await runner._claim(holder, name) is True
        async with factory() as contender:
            # `wait_for` is the real assertion: a BLOCKING lock would hang here
            # rather than return False.
            granted = await asyncio.wait_for(runner._claim(contender, name), timeout=5)
            assert granted is False, "the second claim was granted while the first was held"

        # The lock is transaction-scoped, so ending the transaction releases
        # it. `_run_consumer` still does this in a `finally`, because the batch
        # must not depend on scope exit to hand the consumer back.
        await runner._release(holder, name)

    async with factory() as later:
        assert await runner._claim(later, name) is True, "the claim was never released"
        await runner._release(later, name)


async def test_the_claim_cannot_be_borrowed_back_out_of_the_connection_pool(factory):
    """The defect the four-runner test only caught about one run in four.

    `pg_try_advisory_lock` is SESSION scoped — it belongs to the connection. The
    runner used to commit the claim session immediately, "so it holds no row
    locks for the duration of the batch", and that commit ended the transaction,
    which handed the connection straight back to the pool WITH the lock still on
    it. A second runner that checked out that same connection re-entered the
    lock, `pg_try_advisory_lock` answered true, and both runners worked the same
    consumer — surfacing as a `uq_notification_event` violation, one failed
    execution, and a spent retry.

    The invariant that makes borrowing impossible is that the claim is held by
    an OPEN TRANSACTION: SQLAlchemy cannot return a connection to the pool while
    its transaction is live. Assert exactly that, plus the release it buys.
    """
    from platform_core.core.rls import PlatformSessionFactory
    from platform_core.modules.event_relay.consumers import ConsumerRunner, _lock_key

    runner = ConsumerRunner(PlatformSessionFactory(factory, "pool borrow test"))
    name = "pool-borrow-probe"
    key = _lock_key(name)

    async with factory() as holder:
        assert await runner._claim(holder, name) is True
        assert holder.in_transaction(), (
            "the claim session has no open transaction — its connection is free to "
            "return to the pool carrying the lock, which is the borrow bug itself"
        )
        async with factory() as other:
            held = await other.scalar(
                select(func.count())
                .select_from(text("pg_locks"))
                .where(text("locktype = 'advisory'"))
                .where(text(f"(classid::bigint << 32) | objid::bigint = {key}"))
            )
            assert held == 1, f"expected exactly one advisory lock on {name}, saw {held}"
        await runner._release(holder, name)

    # Released by ending the transaction — no explicit unlock, and nothing left
    # behind on the connection for the next borrower.
    async with factory() as after:
        remaining = await after.scalar(
            select(func.count())
            .select_from(text("pg_locks"))
            .where(text("locktype = 'advisory'"))
            .where(text(f"(classid::bigint << 32) | objid::bigint = {key}"))
        )
        assert remaining == 0, "the advisory lock outlived its transaction"


def test_the_claim_is_a_no_op_off_postgres(monkeypatch):
    """SQLite has no advisory locks and one writer, so the test stack must
    behave exactly as it did before."""
    import platform_core.modules.event_relay.consumers as consumers_module

    monkeypatch.setattr("platform_core.core.rls.is_postgres", lambda: False)
    runner = consumers_module.ConsumerRunner.__new__(consumers_module.ConsumerRunner)
    assert asyncio.run(runner._claim(None, "any-consumer")) is True
