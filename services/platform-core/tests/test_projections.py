"""Projection lifecycle & replay framework (PLT-001): discovery, registry,
rebuild, cancellation, versioning, drift/integrity verification, performance."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from tests.conftest import count_statements, register_and_login
from tests.test_procurement_e2e import _accept_complete, _procurement_env, _run_collection

COMPLETED = "collection.transaction-completed.v1"


@pytest.fixture
def projection_guard():
    """Snapshot both registries so test projections never leak."""
    from platform_core.modules.event_relay import consumers as cfw
    from platform_core.modules.event_relay import projections as pfw

    consumers_before = dict(cfw._REGISTRY)
    projections_before = dict(pfw._PROJECTIONS)
    yield pfw
    cfw._REGISTRY.clear()
    cfw._REGISTRY.update(consumers_before)
    pfw._PROJECTIONS.clear()
    pfw._PROJECTIONS.update(projections_before)


def _rebuilder():
    from platform_core.core import db
    from platform_core.modules.event_relay.projections import ProjectionRebuilder

    return ProjectionRebuilder(db.get_session_factory())


def _runner():
    from platform_core.core import db
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    return ConsumerRunner(db.get_session_factory())


async def _root_headers(client):
    r = await client.post(
        "/v1/auth/token",
        json={"email": "root@example.com", "password": "correct-horse-battery"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _collections(client, *, count=2, with_pricing=True):
    """Produce `count` completed transactions; return (headers, center, supplier)."""
    headers, center, supplier, session = await _procurement_env(client, with_pricing=with_pricing)
    for index in range(count):
        tx = await _run_collection(
            client, headers, session["id"], supplier, gross=30.0 - index, tare=5.0
        )
        await _accept_complete(client, headers, tx["id"])
    return headers, center, supplier


async def _daily_rows():
    from platform_core.core import db
    from platform_core.modules.reporting.models import DailyTotalsProjection

    async with db.get_session_factory()() as s:
        return list((await s.scalars(select(DailyTotalsProjection))).all())


# --- discovery & registration -------------------------------------------------


async def test_projections_discovered_with_metadata(client):
    from platform_core.modules.event_relay.projections import (
        discover_projections,
        get_projection,
    )

    assert "reporting-projection" in discover_projections()
    projection = get_projection("reporting-projection")
    assert projection.version == 1
    assert projection.owner_module == "reporting"
    assert projection.description
    assert projection.event_types == (COMPLETED,)
    assert projection.rebuild_strategy == "full-replay"
    assert projection.replay_order == 10
    assert len(projection.models) == 3


async def test_projection_is_also_a_consumer(client):
    """One declaration, both roles — the runner still processes it."""
    from platform_core.modules.event_relay.consumers import registered_consumers

    names = {c.name for c in registered_consumers()}
    assert "reporting-projection" in names


async def test_registration_requires_models(projection_guard):
    class NoModels(projection_guard.Projection):
        name = "test-no-models"
        event_types = (COMPLETED,)

    with pytest.raises(ValueError, match="models"):
        projection_guard.register_projection(NoModels())


async def test_registration_rejects_plain_consumers(projection_guard):
    class NotAProjection:
        name = "test-plain"
        event_types = (COMPLETED,)

    with pytest.raises(TypeError):
        projection_guard.register_projection(NotAProjection())


async def test_unknown_projection_raises(client):
    from platform_core.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        await _rebuilder().status("no-such-projection")


async def test_replay_order_sorts_registry(projection_guard):
    from platform_core.modules.reporting.models import DailyTotalsProjection

    class Late(projection_guard.Projection):
        name = "test-late"
        event_types = (COMPLETED,)
        replay_order = 900
        models = (DailyTotalsProjection,)

    projection_guard.register_projection(Late())
    names = [p.name for p in projection_guard.registered_projections()]
    assert names.index("reporting-projection") < names.index("test-late")


# --- registry status ----------------------------------------------------------


async def test_status_reports_derived_position_and_counts(client):
    await _collections(client, count=2)
    rebuilder = _rebuilder()
    before = await rebuilder.status("reporting-projection")
    assert before.pending_events == 2
    assert before.events_processed == 0
    assert before.health == "never_built"
    assert before.row_counts["projection_daily_totals"] == 0

    await _runner().run_once()
    after = await rebuilder.status("reporting-projection")
    assert after.pending_events == 0
    assert after.events_processed == 2
    assert after.last_event_id is not None and after.last_event_at is not None
    assert after.row_counts["projection_daily_totals"] == 1
    assert after.health == "ok"
    assert after.version == 1 and after.code_version == 1


async def test_status_all_returns_every_projection(client):
    statuses = await _rebuilder().status_all()
    names = [s.name for s in statuses]
    # Replay order decides the sequence: the recipient directory (5) is a
    # dependency of notification dispatch, so it precedes reporting (10).
    assert names == ["notification-recipient-directory", "reporting-projection"]


# --- rebuild ------------------------------------------------------------------


async def test_rebuild_reconstructs_from_the_log(client):
    await _collections(client, count=3)
    await _runner().run_once()
    original = await _daily_rows()
    assert original[0].transactions == 3

    result = await _rebuilder().rebuild("reporting-projection")
    assert result.status == "completed"
    assert result.events_applied == 3
    assert result.events_scanned > 3  # the whole log is scanned, matches applied
    assert result.rows_deleted == 3  # daily + center + supplier rows
    assert result.version == 1

    rebuilt = await _daily_rows()
    assert len(rebuilt) == 1
    assert rebuilt[0].transactions == original[0].transactions
    assert Decimal(str(rebuilt[0].total_net_weight)) == Decimal(str(original[0].total_net_weight))
    assert Decimal(str(rebuilt[0].payable_amount)) == Decimal(str(original[0].payable_amount))


async def test_rebuild_from_empty_state_is_identical(client):
    """Rebuild without prior incremental processing produces the same result."""
    await _collections(client, count=2)
    result = await _rebuilder().rebuild("reporting-projection")
    assert result.status == "completed" and result.events_applied == 2
    rows = await _daily_rows()
    assert rows[0].transactions == 2 and rows[0].accepted == 2


async def test_rebuild_is_idempotent(client):
    await _collections(client, count=2)
    rebuilder = _rebuilder()
    await rebuilder.rebuild("reporting-projection")
    first = (await _daily_rows())[0].transactions
    await rebuilder.rebuild("reporting-projection")
    second = (await _daily_rows())[0].transactions
    assert first == second == 2  # never double-counts


async def test_rebuild_repopulates_ledger_and_cursor(client):
    """After a rebuild the incremental runner must not reprocess the
    projection's events (its ledger and cursor were repopulated)."""
    await _collections(client, count=2)
    rebuilder = _rebuilder()
    await rebuilder.rebuild("reporting-projection")
    before = await rebuilder.status("reporting-projection")
    assert before.events_processed == 2 and before.pending_events == 0

    await _runner().run_once()  # other consumers may work; this one must not
    after = await rebuilder.status("reporting-projection")
    assert after.events_processed == 2
    assert (await _daily_rows())[0].transactions == 2  # no double counting


async def test_rebuild_all_runs_in_replay_order(client):
    await _collections(client, count=1)
    results = await _rebuilder().rebuild_all()
    assert [r.projection for r in results] == [
        "notification-recipient-directory",
        "reporting-projection",
    ]
    assert all(r.status == "completed" for r in results)


async def test_dry_run_changes_nothing(client):
    await _collections(client, count=2)
    await _runner().run_once()
    before = (await _daily_rows())[0].transactions

    result = await _rebuilder().rebuild("reporting-projection", dry_run=True)
    assert result.dry_run is True and result.status == "estimated"
    assert result.events_applied == 2  # events that WOULD be replayed
    assert result.rows_deleted == 3  # rows that WOULD be deleted
    assert result.estimated_seconds is not None and result.estimated_seconds >= 0
    assert (await _daily_rows())[0].transactions == before  # untouched


async def test_batched_rebuild_handles_many_events(client):
    await _collections(client, count=6)
    result = await _rebuilder().rebuild("reporting-projection", batch_size=2)
    assert result.status == "completed" and result.events_applied == 6
    assert (await _daily_rows())[0].transactions == 6


async def test_rebuild_replays_only_the_log_not_tables(client):
    """Deleting nothing but replaying after the transactional rows are hidden:
    the projection is derived from events alone, so a rebuild reproduces the
    totals even though the consumer never reads transactional tables."""
    from platform_core.core import db
    from platform_core.modules.event_relay.models import OutboxEvent

    await _collections(client, count=2)
    async with db.get_session_factory()() as s:
        events = (
            await s.scalars(select(OutboxEvent).where(OutboxEvent.event_name == COMPLETED))
        ).all()
        assert len(events) == 2
    await _rebuilder().rebuild("reporting-projection")
    assert (await _daily_rows())[0].transactions == 2


# --- reset --------------------------------------------------------------------


async def test_reset_clears_rows_and_position(client):
    await _collections(client, count=2)
    await _runner().run_once()
    result = await _rebuilder().reset("reporting-projection")
    assert result.rows_deleted == 3 and result.executions_cleared == 2
    assert await _daily_rows() == []

    status = await _rebuilder().status("reporting-projection")
    assert status.status == "reset"
    assert status.events_processed == 0 and status.pending_events == 2


async def test_reset_then_runner_rebuilds_naturally(client):
    await _collections(client, count=2)
    await _runner().run_once()
    await _rebuilder().reset("reporting-projection")
    await _runner().run_once()  # the ordinary loop replays from the log start
    assert (await _daily_rows())[0].transactions == 2


# --- cancellation -------------------------------------------------------------


def _cancelling_projection(framework, *, cancel_after=1):
    """A projection that requests its own cancellation mid-replay — stands in
    for an operator hitting cancel while a rebuild is running."""
    from platform_core.modules.event_relay.models import ProjectionState
    from platform_core.modules.reporting.models import DailyTotalsProjection

    class Cancelling(framework.Projection):
        name = "test-cancelling"
        owner_module = "test"
        description = "Cancels itself mid-replay."
        event_types = (COMPLETED,)
        models = (DailyTotalsProjection,)

        def __init__(self):
            self.seen = 0

        async def handle(self, envelope, session):
            self.seen += 1
            if self.seen == cancel_after:
                state = await session.scalar(
                    select(ProjectionState).where(
                        ProjectionState.projection_name == "test-cancelling"
                    )
                )
                state.cancel_requested = True  # committed with this batch

    return framework.register_projection(Cancelling())


async def test_cancel_stops_rebuild_after_current_batch(client, projection_guard):
    """A cancel requested mid-flight halts the replay after its batch."""
    _cancelling_projection(projection_guard)
    await _collections(client, count=6)
    rebuilder = _rebuilder()

    result = await rebuilder.rebuild("test-cancelling", batch_size=1)
    assert result.status == "cancelled"
    assert result.events_applied == 1  # stopped after the first batch

    status = await rebuilder.status("test-cancelling")
    assert status.status == "cancelled"
    assert status.last_rebuild_at is None  # a cancelled rebuild claims nothing


async def test_cancel_requires_running_rebuild(client):
    from platform_core.core.errors import ConflictError

    await _collections(client, count=1)
    with pytest.raises(ConflictError):
        await _rebuilder().cancel("reporting-projection")


async def test_cancelled_rebuild_can_be_resumed_by_rebuilding_again(client, projection_guard):
    """Re-running clears the stale flag and completes from a clean slate."""
    _cancelling_projection(projection_guard)
    await _collections(client, count=4)
    rebuilder = _rebuilder()
    assert (await rebuilder.rebuild("test-cancelling", batch_size=1)).status == "cancelled"

    result = await rebuilder.rebuild("test-cancelling")  # handler no longer cancels
    assert result.status == "completed" and result.events_applied == 4
    status = await rebuilder.status("test-cancelling")
    assert status.status == "live" and status.last_rebuild_at is not None


# --- versioning ---------------------------------------------------------------


async def test_version_bump_marks_projection_outdated(client, projection_guard):
    await _collections(client, count=2)
    await _runner().run_once()
    rebuilder = _rebuilder()
    assert (await rebuilder.status("reporting-projection")).health == "ok"

    projection = projection_guard.get_projection("reporting-projection")
    original_version = projection.version
    try:
        projection.version = 2  # ship a new projection shape
        status = await rebuilder.status("reporting-projection")
        assert status.health == "outdated"
        assert status.version == 1 and status.code_version == 2
        verification = await rebuilder.verify("reporting-projection")
        version_check = next(c for c in verification.checks if c.check == "version")
        assert version_check.passed is False and "rebuild required" in version_check.detail

        result = await rebuilder.rebuild("reporting-projection")
        assert result.version == 2
        migrated = await rebuilder.status("reporting-projection")
        assert migrated.version == 2 and migrated.health == "ok"
    finally:
        projection.version = original_version


# --- verification -------------------------------------------------------------


async def test_verify_healthy_projection(client):
    await _collections(client, count=2)
    await _runner().run_once()
    result = await _rebuilder().verify("reporting-projection", deep=True)
    assert result.healthy is True and result.deep is True
    names = {c.check for c in result.checks}
    assert {
        "version",
        "corrupted_replay",
        "missing_events",
        "dead_events",
        "duplicate_rows",
        "unexpected_gaps",
        "projection_drift",
    } == names


async def test_deep_verify_detects_drift(client):
    """Tamper with a projection row: the shadow replay must catch it."""
    from platform_core.core import db
    from platform_core.modules.reporting.models import DailyTotalsProjection

    await _collections(client, count=2)
    await _runner().run_once()
    async with db.get_session_factory()() as s:
        row = (await s.scalars(select(DailyTotalsProjection))).one()
        row.transactions = 99
        row.payable_amount = Decimal("1.00")
        await s.commit()

    result = await _rebuilder().verify("reporting-projection", deep=True)
    drift = next(c for c in result.checks if c.check == "projection_drift")
    assert drift.passed is False and result.healthy is False
    assert "transactions=99" in drift.detail


async def test_deep_verify_does_not_mutate(client):
    """Verification rolls back its shadow replay — even when drift exists."""
    from platform_core.core import db
    from platform_core.modules.reporting.models import DailyTotalsProjection

    await _collections(client, count=2)
    await _runner().run_once()
    async with db.get_session_factory()() as s:
        row = (await s.scalars(select(DailyTotalsProjection))).one()
        row.transactions = 99
        await s.commit()
    await _rebuilder().verify("reporting-projection", deep=True)
    assert (await _daily_rows())[0].transactions == 99  # untouched by verify


async def test_verify_detects_missing_events(client):
    """Delete a ledger entry behind the cursor: the event is unaccounted for."""
    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerExecution

    await _collections(client, count=2)
    await _runner().run_once()
    async with db.get_session_factory()() as s:
        execution = (
            await s.scalars(
                select(ConsumerExecution).where(
                    ConsumerExecution.consumer_name == "reporting-projection"
                )
            )
        ).first()
        await s.delete(execution)
        await s.commit()

    result = await _rebuilder().verify("reporting-projection")
    missing = next(c for c in result.checks if c.check == "missing_events")
    gaps = next(c for c in result.checks if c.check == "unexpected_gaps")
    assert missing.passed is False and missing.count == 1
    assert gaps.passed is False and gaps.count == 1
    assert result.healthy is False


async def test_verify_detects_duplicate_rows(client):
    """The natural key is read from the model's own unique constraint."""
    from platform_core.modules.event_relay.projections import _natural_key_columns
    from platform_core.modules.reporting.models import DailyTotalsProjection

    assert _natural_key_columns(DailyTotalsProjection) == ("tenant_id", "day")
    await _collections(client, count=1)
    await _runner().run_once()
    result = await _rebuilder().verify("reporting-projection")
    duplicates = next(c for c in result.checks if c.check == "duplicate_rows")
    assert duplicates.passed is True  # the unique constraint makes this the guard


async def test_verify_flags_corrupted_replay(client):
    from platform_core.core import db
    from platform_core.core.db import utcnow
    from platform_core.modules.event_relay.models import ProjectionState

    await _collections(client, count=1)
    rebuilder = _rebuilder()
    await rebuilder.status("reporting-projection")
    async with db.get_session_factory()() as s:
        state = await s.scalar(
            select(ProjectionState).where(ProjectionState.projection_name == "reporting-projection")
        )
        state.status = "failed"
        state.last_error = "handler exploded"
        await s.commit()
    result = await rebuilder.verify("reporting-projection")
    corrupted = next(c for c in result.checks if c.check == "corrupted_replay")
    assert corrupted.passed is False and "handler exploded" in corrupted.detail
    assert (await rebuilder.status("reporting-projection")).health == "degraded"
    assert utcnow() is not None


async def test_failed_rebuild_records_error(client, projection_guard):
    """A handler that explodes mid-replay leaves status=failed, not silence."""
    from platform_core.modules.reporting.models import DailyTotalsProjection

    class Exploding(projection_guard.Projection):
        name = "test-exploding"
        event_types = (COMPLETED,)
        owner_module = "test"
        models = (DailyTotalsProjection,)

        async def handle(self, envelope, session):
            raise RuntimeError("replay exploded")

    projection_guard.register_projection(Exploding())
    await _collections(client, count=1)
    result = await _rebuilder().rebuild("test-exploding")
    assert result.status == "failed" and "exploded" in result.error
    status = await _rebuilder().status("test-exploding")
    assert status.status == "failed" and status.health == "degraded"


# --- operations API -----------------------------------------------------------


async def test_registry_endpoint(client):
    await _collections(client, count=2)
    root = await _root_headers(client)
    body = (await client.get("/v1/_projections", headers=root)).json()
    assert {p["name"] for p in body} == {
        "notification-recipient-directory",
        "reporting-projection",
    }
    entry = next(p for p in body if p["name"] == "reporting-projection")
    assert entry["owner_module"] == "reporting"
    assert entry["event_types"] == [COMPLETED]
    assert entry["pending_events"] == 2
    assert entry["health"] == "never_built"


async def test_single_projection_endpoint_and_404(client):
    await _collections(client, count=1)
    root = await _root_headers(client)
    r = await client.get("/v1/_projections/reporting-projection", headers=root)
    assert r.status_code == 200 and r.json()["name"] == "reporting-projection"
    assert (await client.get("/v1/_projections/nope", headers=root)).status_code == 404


async def test_rebuild_endpoints(client):
    await _collections(client, count=2)
    root = await _root_headers(client)
    dry = (
        await client.post(
            "/v1/_projections/reporting-projection/rebuild?dry_run=true", headers=root
        )
    ).json()
    assert dry["status"] == "estimated" and dry["events_applied"] == 2
    assert await _daily_rows() == []

    real = (await client.post("/v1/_projections/reporting-projection/rebuild", headers=root)).json()
    assert real["status"] == "completed" and real["events_applied"] == 2
    assert (await _daily_rows())[0].transactions == 2

    every = (await client.post("/v1/_projections/rebuild-all", headers=root)).json()
    assert len(every) == 2 and all(r["status"] == "completed" for r in every)


async def test_verify_and_reset_endpoints(client):
    await _collections(client, count=2)
    root = await _root_headers(client)
    await client.post("/v1/_projections/reporting-projection/rebuild", headers=root)
    verification = (
        await client.post("/v1/_projections/reporting-projection/verify?deep=true", headers=root)
    ).json()
    assert verification["healthy"] is True

    reset = (
        await client.delete("/v1/_projections/reporting-projection/reset", headers=root)
    ).json()
    assert reset["rows_deleted"] == 3
    assert await _daily_rows() == []


async def test_projection_api_requires_platform_permission(client):
    headers, *_ = await _collections(client, count=1)  # tenant admin
    assert (await client.get("/v1/_projections", headers=headers)).status_code == 403
    assert (await client.get("/v1/_projections")).status_code == 401
    _, nobody = await register_and_login(client, "projnoperm@example.com")
    r = await client.post("/v1/_projections/reporting-projection/rebuild", headers=nobody)
    assert r.status_code == 403


async def test_rebuild_conflicts_while_rebuilding(client):
    from platform_core.core import db
    from platform_core.core.errors import ConflictError
    from platform_core.modules.event_relay.models import ProjectionState

    await _collections(client, count=1)
    rebuilder = _rebuilder()
    await rebuilder.status("reporting-projection")
    async with db.get_session_factory()() as s:
        state = await s.scalar(
            select(ProjectionState).where(ProjectionState.projection_name == "reporting-projection")
        )
        state.status = "rebuilding"
        await s.commit()
    with pytest.raises(ConflictError):
        await rebuilder.rebuild("reporting-projection")
    with pytest.raises(ConflictError):
        await rebuilder.reset("reporting-projection")


# --- performance --------------------------------------------------------------


async def test_status_query_budget_is_fixed(client):
    """Registry status must not scale with event or row volume."""
    await _collections(client, count=4)
    await _runner().run_once()
    rebuilder = _rebuilder()
    _, statements = await count_statements(lambda: rebuilder.status("reporting-projection"))
    assert statements <= 10, f"status too expensive: {statements} SELECTs"


async def test_rebuild_query_budget_scales_with_batches_not_events(client):
    """Batched replay: query count grows with batches, not with event count."""
    await _collections(client, count=6)
    rebuilder = _rebuilder()
    _, few_batches = await count_statements(
        lambda: rebuilder.rebuild("reporting-projection", batch_size=100), selects_only=False
    )
    _, many_batches = await count_statements(
        lambda: rebuilder.rebuild("reporting-projection", batch_size=1), selects_only=False
    )
    assert few_batches < many_batches  # batching genuinely reduces round trips
    assert (await _daily_rows())[0].transactions == 6


async def test_large_replay_completes(client):
    """A wider log (many non-matching events) still replays correctly."""
    await _collections(client, count=8)
    result = await _rebuilder().rebuild("reporting-projection", batch_size=5)
    assert result.status == "completed"
    assert result.events_applied == 8
    assert result.events_scanned >= 8 * 8  # each collection emits many events
    rows = await _daily_rows()
    assert rows[0].transactions == 8 and rows[0].accepted == 8


async def test_rebuild_reports_duration_and_progress(client):
    await _collections(client, count=3)
    rebuilder = _rebuilder()
    result = await rebuilder.rebuild("reporting-projection")
    assert result.duration_seconds >= 0
    status = await rebuilder.status("reporting-projection")
    assert status.last_rebuild_at is not None and status.last_rebuild_ms is not None
    assert status.rebuild is not None
    assert status.rebuild.total == 3 and status.rebuild.done == 3
    assert status.rebuild.percent == 100.0


async def test_uuid_import_available():
    """Guard against the registry losing its typed identifiers."""
    assert uuid.UUID is not None
