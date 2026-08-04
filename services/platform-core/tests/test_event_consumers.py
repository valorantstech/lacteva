"""Event consumer framework (SPRINT-008B): normal flow, retries, DLQ,
replay, idempotency, ordering, crash recovery, isolation, performance."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from tests.conftest import count_statements, register_and_login
from tests.test_procurement_e2e import _accept_complete, _procurement_env, _run_collection

COMPLETED = "collection.transaction-completed.v1"


@pytest.fixture
def registry_guard():
    """Snapshot the consumer registry; restore after the test so temporary
    test consumers never leak between tests."""
    from platform_core.modules.event_relay import consumers as fw

    before = dict(fw._REGISTRY)
    yield fw
    fw._REGISTRY.clear()
    fw._REGISTRY.update(before)


def _runner():
    from platform_core.core import db
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    return ConsumerRunner(db.get_session_factory())


async def _root_headers(client):
    """The platform-admin (root) token for /_consumers operations."""
    r = await client.post(
        "/v1/auth/token",
        json={"email": "root@example.com", "password": "correct-horse-battery"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _one_completed_tx(client, *, with_pricing=True, quantity_gross=30.0):
    headers, center, supplier, session = await _procurement_env(client, with_pricing=with_pricing)
    tx = await _run_collection(
        client, headers, session["id"], supplier, gross=quantity_gross, tare=5.0
    )
    tx = await _accept_complete(client, headers, tx["id"])
    return headers, center, supplier, session, tx


class _FailingConsumer:
    """Test consumer with a togglable failure mode."""

    def __init__(self, name="test-failing", event_types=(COMPLETED,)):
        self.name = name
        self.event_types = event_types
        self.fail = True
        self.handled: list[str] = []

    async def handle(self, envelope, session):
        if self.fail:
            raise RuntimeError("poison message")
        self.handled.append(str(envelope.id))


# --- discovery & registration -------------------------------------------------


async def test_production_consumers_discovered(client):
    from platform_core.modules.event_relay.consumers import discover_consumers

    names = discover_consumers()
    assert "notification-dispatch" in names  # the real engine (NOT-001)
    assert "reporting-projection" in names
    assert "notification-recipient-directory" in names


async def test_registration_validates(registry_guard):
    class Nameless(registry_guard.EventConsumer):
        name = ""
        event_types = (COMPLETED,)

    with pytest.raises(ValueError):
        registry_guard.register_consumer(Nameless())


# --- normal flow --------------------------------------------------------------


async def test_normal_flow_notification_and_projection(client):
    _headers, center, supplier, _session, _tx = await _one_completed_tx(client)
    result = await _runner().run_once()
    assert result["processed"] >= 2  # both production consumers handled it

    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerExecution
    from platform_core.modules.reporting.models import (
        CenterTotalsProjection,
        DailyTotalsProjection,
        SupplierTotalsProjection,
    )

    async with db.get_session_factory()() as s:
        executions = (
            await s.scalars(
                select(ConsumerExecution).where(ConsumerExecution.status == "succeeded")
            )
        ).all()
        by_consumer = {e.consumer_name for e in executions}
        assert {"notification-dispatch", "reporting-projection"} <= by_consumer
        assert all(e.latency_ms is not None for e in executions)

        daily = (await s.scalars(select(DailyTotalsProjection))).one()
        assert daily.transactions == 1 and daily.accepted == 1 and daily.rejected == 0
        assert Decimal(str(daily.total_net_weight)) == Decimal("25")
        assert Decimal(str(daily.payable_amount)) == Decimal("1125.00")
        assert daily.currency == "KES"
        center_row = (await s.scalars(select(CenterTotalsProjection))).one()
        assert str(center_row.center_id) == center["id"]
        supplier_row = (await s.scalars(select(SupplierTotalsProjection))).one()
        assert str(supplier_row.supplier_id) == supplier["id"]


async def test_projection_accumulates_and_counts_rejections(client):
    headers, _center, supplier, session, _tx = await _one_completed_tx(client)
    second = await _run_collection(client, headers, session["id"], supplier, gross=20.0, tare=5.0)
    await _accept_complete(client, headers, second["id"])
    third = await _run_collection(client, headers, session["id"], supplier)
    await client.post(
        f"/v1/milk-transactions/{third['id']}/reject", json={"reason": "spoiled"}, headers=headers
    )
    await client.post(f"/v1/milk-transactions/{third['id']}/complete", headers=headers)
    await _runner().run_once()

    from platform_core.core import db
    from platform_core.modules.reporting.models import DailyTotalsProjection

    async with db.get_session_factory()() as s:
        daily = (await s.scalars(select(DailyTotalsProjection))).one()
        assert daily.transactions == 3
        assert daily.accepted == 2 and daily.rejected == 1
        assert Decimal(str(daily.total_net_weight)) == Decimal("40")  # rejected excluded
        assert Decimal(str(daily.payable_amount)) == Decimal("1800.00")  # 1125 + 675


async def test_unpriced_transaction_projected_without_payable(client):
    await _one_completed_tx(client, with_pricing=False)
    await _runner().run_once()
    from platform_core.core import db
    from platform_core.modules.reporting.models import DailyTotalsProjection

    async with db.get_session_factory()() as s:
        daily = (await s.scalars(select(DailyTotalsProjection))).one()
        assert daily.accepted == 1
        assert Decimal(str(daily.total_net_weight)) == Decimal("25")
        assert Decimal(str(daily.payable_amount)) == Decimal("0.00")
        assert daily.currency is None


async def test_consumers_never_query_transactional_tables(client):
    """The projection is derived purely from the event payload: the enriched
    completed event carries everything the projection needs."""
    from platform_core.core import db
    from platform_core.modules.event_relay.models import OutboxEvent

    await _one_completed_tx(client)
    async with db.get_session_factory()() as s:
        event = await s.scalar(select(OutboxEvent).where(OutboxEvent.event_name == COMPLETED))
        for key in (
            "center_id",
            "supplier_id",
            "net_weight",
            "gross_amount",
            "currency",
            "rejected",
        ):
            assert key in event.payload, key
        assert event.aggregate_type == "milk_collection_transaction"


# --- idempotency & duplicate delivery ----------------------------------------


async def test_idempotency_run_twice_no_double_counting(client):
    await _one_completed_tx(client)
    runner = _runner()
    first = await runner.run_once()
    assert first["processed"] >= 2
    second = await runner.run_once()
    assert second["processed"] == 0  # nothing new

    from platform_core.core import db
    from platform_core.modules.reporting.models import DailyTotalsProjection

    async with db.get_session_factory()() as s:
        daily = (await s.scalars(select(DailyTotalsProjection))).one()
        assert daily.transactions == 1  # not 2


async def test_duplicate_delivery_of_same_event_id_skipped(client):
    """Even if the cursor is rewound (duplicate delivery), the idempotency
    ledger prevents reprocessing."""
    await _one_completed_tx(client)
    runner = _runner()
    await runner.run_once()

    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerCursor
    from platform_core.modules.reporting.models import DailyTotalsProjection

    async with db.get_session_factory()() as s:
        for cursor in (await s.scalars(select(ConsumerCursor))).all():
            cursor.position_created_at = None  # rewind everything to the log start
            cursor.position_event_id = None
        await s.commit()
    result = await runner.run_once()
    assert result["processed"] == 0  # all skipped by the ledger
    async with db.get_session_factory()() as s:
        daily = (await s.scalars(select(DailyTotalsProjection))).one()
        assert daily.transactions == 1


# --- retry, DLQ, replay -------------------------------------------------------


async def test_retry_with_exponential_backoff(client, registry_guard):
    failing = _FailingConsumer()
    registry_guard.register_consumer(failing)
    await _one_completed_tx(client)
    runner = _runner()
    from platform_core.core.db import utcnow

    now = utcnow()
    await runner.run_once(now=now)

    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerExecution

    async with db.get_session_factory()() as s:
        execution = await s.scalar(
            select(ConsumerExecution).where(ConsumerExecution.consumer_name == failing.name)
        )
        assert execution.status == "failed" and execution.attempts == 1
        assert execution.last_error and "poison" in execution.last_error
        first_due = execution.next_attempt_at

    # Before the backoff elapses: waiting, attempts unchanged.
    await runner.run_once(now=now + timedelta(seconds=1))
    async with db.get_session_factory()() as s:
        execution = await s.scalar(
            select(ConsumerExecution).where(ConsumerExecution.consumer_name == failing.name)
        )
        assert execution.attempts == 1

    # After the backoff: retried, attempts increment, next delay grows.
    await runner.run_once(now=now + timedelta(seconds=3))
    async with db.get_session_factory()() as s:
        execution = await s.scalar(
            select(ConsumerExecution).where(ConsumerExecution.consumer_name == failing.name)
        )
        assert execution.attempts == 2
        from platform_core.core.db import as_utc

        assert as_utc(execution.next_attempt_at) > as_utc(first_due)


async def test_poison_message_dead_letters_and_cursor_advances(client, registry_guard):
    failing = _FailingConsumer()
    registry_guard.register_consumer(failing)
    headers, _center, supplier, session, _tx = await _one_completed_tx(client)
    # A second event AFTER the poison one.
    second = await _run_collection(client, headers, session["id"], supplier, gross=20.0, tare=5.0)
    await _accept_complete(client, headers, second["id"])

    runner = _runner()
    from platform_core.core.db import utcnow

    now = utcnow()
    for i in range(6):  # drive through MAX_CONSUMER_ATTEMPTS
        await runner.run_once(now=now + timedelta(seconds=400 * (i + 1)))

    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerExecution

    async with db.get_session_factory()() as s:
        executions = (
            await s.scalars(
                select(ConsumerExecution)
                .where(ConsumerExecution.consumer_name == failing.name)
                .order_by(ConsumerExecution.created_at)
            )
        ).all()
        # First event dead after 5 attempts; SECOND event also attempted
        # (cursor advanced past the poison) and dead too (consumer still failing).
        assert executions[0].status == "dead" and executions[0].attempts == 5
        assert len(executions) == 2  # ordering: second only reached after first died


async def test_ordering_blocks_behind_retrying_event(client, registry_guard):
    failing = _FailingConsumer()
    registry_guard.register_consumer(failing)
    headers, _center, supplier, session, _tx = await _one_completed_tx(client)
    second = await _run_collection(client, headers, session["id"], supplier, gross=20.0, tare=5.0)
    await _accept_complete(client, headers, second["id"])

    runner = _runner()
    await runner.run_once()  # first event fails (attempt 1), second NOT attempted

    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerExecution

    async with db.get_session_factory()() as s:
        executions = (
            await s.scalars(
                select(ConsumerExecution).where(ConsumerExecution.consumer_name == failing.name)
            )
        ).all()
        assert len(executions) == 1  # strict per-consumer ordering


async def test_replay_dead_execution(client, registry_guard):
    failing = _FailingConsumer()
    registry_guard.register_consumer(failing)
    await _one_completed_tx(client)
    runner = _runner()
    from platform_core.core.db import utcnow

    now = utcnow()
    for i in range(6):
        await runner.run_once(now=now + timedelta(seconds=400 * (i + 1)))

    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerExecution

    async with db.get_session_factory()() as s:
        dead = await s.scalar(
            select(ConsumerExecution).where(
                ConsumerExecution.consumer_name == failing.name,
                ConsumerExecution.status == "dead",
            )
        )
        assert dead is not None
        dead_id = dead.id

    failing.fail = False  # "fix" the consumer
    await runner.replay_execution(dead_id)
    await runner.run_once(now=now + timedelta(seconds=4000))
    async with db.get_session_factory()() as s:
        replayed = await s.get(ConsumerExecution, dead_id)
        assert replayed.status == "succeeded"
    assert len(failing.handled) == 1


async def test_replay_requires_dead_status(client):
    await _one_completed_tx(client)
    runner = _runner()
    await runner.run_once()
    from platform_core.core import db
    from platform_core.core.errors import ConflictError, NotFoundError
    from platform_core.modules.event_relay.models import ConsumerExecution

    async with db.get_session_factory()() as s:
        succeeded = (await s.scalars(select(ConsumerExecution))).first()
    with pytest.raises(ConflictError):
        await runner.replay_execution(succeeded.id)
    with pytest.raises(NotFoundError):
        await runner.replay_execution(uuid.uuid4())


# --- isolation ----------------------------------------------------------------


async def test_consumer_failure_never_affects_business_flow(client, registry_guard):
    """With a permanently failing consumer registered, the entire business
    journey still works — consumers are invisible to producers."""
    registry_guard.register_consumer(_FailingConsumer())
    headers, _center, _supplier, _session, tx = await _one_completed_tx(client)
    assert tx["state"] == "COMPLETED"  # business flow unaffected
    await _runner().run_once()  # consumer fails; still no impact
    detail = (await client.get(f"/v1/milk-transactions/{tx['id']}", headers=headers)).json()
    assert detail["state"] == "COMPLETED"


async def test_multiple_consumers_isolated(client, registry_guard):
    """One consumer failing does not block the others."""
    registry_guard.register_consumer(_FailingConsumer())
    await _one_completed_tx(client)
    await _runner().run_once()

    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerExecution

    async with db.get_session_factory()() as s:
        rows = (await s.scalars(select(ConsumerExecution))).all()
        by_name = {r.consumer_name: r.status for r in rows}
        assert by_name["notification-dispatch"] == "succeeded"
        assert by_name["reporting-projection"] == "succeeded"
        assert by_name["test-failing"] == "failed"


async def test_handler_writes_roll_back_on_failure(client, registry_guard):
    """A consumer that writes and then fails leaves no partial state."""
    from platform_core.modules.reporting.models import DailyTotalsProjection

    class WriteThenFail(registry_guard.EventConsumer):
        name = "test-write-then-fail"
        event_types = (COMPLETED,)

        async def handle(self, envelope, session):
            session.add(
                DailyTotalsProjection(
                    tenant_id=envelope.tenant_id or uuid.uuid4(),
                    day=__import__("datetime").date(2030, 1, 1),
                    transactions=999,
                )
            )
            await session.flush()
            raise RuntimeError("after write")

    registry_guard.register_consumer(WriteThenFail())
    await _one_completed_tx(client)
    await _runner().run_once()

    from platform_core.core import db

    async with db.get_session_factory()() as s:
        ghost = await s.scalar(
            select(DailyTotalsProjection).where(DailyTotalsProjection.transactions == 999)
        )
        assert ghost is None  # rolled back with the failed handler


# --- crash recovery & ordering ------------------------------------------------


async def test_crash_recovery_resumes_from_cursor(client):
    headers, _center, supplier, session, _tx = await _one_completed_tx(client)
    runner_a = _runner()
    await runner_a.run_once()
    # "Crash": a brand-new runner instance (fresh process equivalent).
    second = await _run_collection(client, headers, session["id"], supplier, gross=20.0, tare=5.0)
    await _accept_complete(client, headers, second["id"])
    runner_b = _runner()
    result = await runner_b.run_once()
    # Only the NEW event is processed (the projection consumes completions;
    # the notification dispatcher does not subscribe to them).
    assert result["processed"] >= 1

    from platform_core.core import db
    from platform_core.modules.reporting.models import DailyTotalsProjection

    async with db.get_session_factory()() as s:
        daily = (await s.scalars(select(DailyTotalsProjection))).one()
        assert daily.transactions == 2  # no double-processing across "restart"


async def test_events_processed_in_log_order(client):
    headers, _center, supplier, session, _tx = await _one_completed_tx(client)
    second = await _run_collection(client, headers, session["id"], supplier, gross=20.0, tare=5.0)
    await _accept_complete(client, headers, second["id"])
    await _runner().run_once()

    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerExecution, OutboxEvent

    async with db.get_session_factory()() as s:
        events = (
            await s.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.event_name == COMPLETED)
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
            )
        ).all()
        executions = (
            await s.scalars(
                select(ConsumerExecution)
                .where(ConsumerExecution.consumer_name == "reporting-projection")
                .order_by(ConsumerExecution.created_at, ConsumerExecution.id)
            )
        ).all()
        assert [e.event_id for e in executions] == [e.id for e in events]


async def test_non_matching_events_skipped_without_ledger_entries(client):
    await _one_completed_tx(client)  # produces many non-completed events too
    await _runner().run_once()

    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerExecution

    async with db.get_session_factory()() as s:
        rows = (
            await s.scalars(
                select(ConsumerExecution).where(
                    ConsumerExecution.consumer_name == "reporting-projection"
                )
            )
        ).all()
        assert all(r.event_name == COMPLETED for r in rows)
        assert len(rows) == 1  # dozens of other events created no entries


# --- configuration ------------------------------------------------------------


async def test_consumer_disabled_via_configuration(client):
    headers, *_ = await _one_completed_tx(client)
    r = await client.put(
        "/v1/config/platform.consumers.reporting-projection.enabled",
        json={"value": False, "scope": "global"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    result = await _runner().run_once()
    assert result["skipped"] >= 1

    from platform_core.core import db
    from platform_core.modules.reporting.models import DailyTotalsProjection

    async with db.get_session_factory()() as s:
        assert (await s.scalars(select(DailyTotalsProjection))).first() is None
    # Notification consumer (not disabled) still ran.
    from platform_core.modules.event_relay.models import ConsumerExecution

    async with db.get_session_factory()() as s:
        note = await s.scalar(
            select(ConsumerExecution).where(
                ConsumerExecution.consumer_name == "notification-dispatch"
            )
        )
        assert note is not None and note.status == "succeeded"


# --- operations API -----------------------------------------------------------


async def test_health_endpoint(client):
    await _one_completed_tx(client)
    root = await _root_headers(client)
    body = (await client.get("/v1/_consumers/status", headers=root)).json()
    assert body["status"] == "ok"
    names = {c["name"] for c in body["consumers"]}
    assert {"notification-dispatch", "reporting-projection"} <= names
    projection = next(c for c in body["consumers"] if c["name"] == "reporting-projection")
    assert projection["lag_events"] > 0  # not yet run
    r = await client.post("/v1/_consumers/run", headers=root)
    assert r.status_code == 200 and r.json()["processed"] >= 2
    body = (await client.get("/v1/_consumers/status", headers=root)).json()
    projection = next(c for c in body["consumers"] if c["name"] == "reporting-projection")
    assert projection["lag_events"] == 0
    assert projection["succeeded"] == 1
    assert projection["last_processed_at"] is not None


async def test_executions_and_dead_letters_endpoints(client, registry_guard):
    registry_guard.register_consumer(_FailingConsumer())
    await _one_completed_tx(client)
    runner = _runner()
    from platform_core.core.db import utcnow

    now = utcnow()
    for i in range(6):
        await runner.run_once(now=now + timedelta(seconds=400 * (i + 1)))
    root = await _root_headers(client)
    executions = (
        await client.get("/v1/_consumers/executions?consumer=test-failing", headers=root)
    ).json()
    assert len(executions) == 1 and executions[0]["status"] == "dead"
    dead = (await client.get("/v1/_consumers/dead-letters", headers=root)).json()
    assert len(dead) == 1 and dead[0]["consumer_name"] == "test-failing"
    r = await client.post(f"/v1/_consumers/executions/{dead[0]['id']}/replay", headers=root)
    assert r.status_code == 200 and r.json()["status"] == "failed"  # re-queued


async def test_consumer_api_requires_platform_permission(client):
    headers, *_ = await _one_completed_tx(client)  # tenant admin
    assert (await client.get("/v1/_consumers/status", headers=headers)).status_code == 403
    assert (await client.get("/v1/_consumers/status")).status_code == 401
    _, nobody = await register_and_login(client, "consnoperm@example.com")
    assert (await client.post("/v1/_consumers/run", headers=nobody)).status_code == 403


# --- performance --------------------------------------------------------------


async def test_batch_processing_reaches_zero_lag(client):
    headers, _center, supplier, session, _tx = await _one_completed_tx(client)
    for _ in range(4):
        tx = await _run_collection(client, headers, session["id"], supplier, gross=20.0, tare=5.0)
        await _accept_complete(client, headers, tx["id"])
    await _runner().run_once()

    from platform_core.core import db
    from platform_core.modules.reporting.models import DailyTotalsProjection

    runner = _runner()
    async with db.get_session_factory()() as s:
        assert await runner._lag(s, "reporting-projection") == 0
        daily = (await s.scalars(select(DailyTotalsProjection))).one()
        assert daily.transactions == 5


async def test_per_event_query_budget(client):
    """A caught-up run stays cheap: no per-event scans of history."""
    from platform_core.modules.event_relay.consumers import registered_consumers

    await _one_completed_tx(client)
    runner = _runner()
    await runner.run_once()
    _, statements = await count_statements(lambda: runner.run_once(), selects_only=False)
    per_consumer = statements / max(len(registered_consumers()), 1)
    assert per_consumer <= 6, f"caught-up run too expensive: {statements} statements"
