"""Projection lifecycle & replay framework (PLT-001).

A **projection** is a consumer that maintains derived read models. It
inherits every guarantee of the consumer framework (durable-log cursor,
idempotency ledger, ordering, backoff/DLQ, producer isolation) and adds the
lifecycle every read model needs to be trustworthy:

- **metadata** — name, version, owning module, description, source events,
  rebuild strategy, replay order;
- **rebuild** — reconstruct the read model from the EVENT LOG ALONE (never
  from transactional tables), for one, several, or all projections;
- **operations** — reset, replay, dry run, progress, cancel, statistics, ETA;
- **versioning** — a version bump marks the built model outdated until it is
  rebuilt into the new shape;
- **integrity** — verification for missing events, duplicate rows, drift
  (shadow replay compared against live rows), gaps, and corrupted replays.

BR-0015: every projection must be fully rebuildable from the event log.

Status is DERIVED, never duplicated: position comes from the consumer
cursor, processed counts from the ledger, lag from the log. `ProjectionState`
stores only the built version, the rebuild story, and the cancel flag.
"""

import time
import uuid
from datetime import datetime

import structlog
from prometheus_client import Counter, Gauge
from pydantic import BaseModel
from sqlalchemy import UniqueConstraint, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.modules.event_relay.consumers import (
    EventConsumer,
    discover_consumers,
    register_consumer,
)
from platform_core.modules.event_relay.models import (
    ConsumerCursor,
    ConsumerExecution,
    OutboxEvent,
    ProjectionState,
)
from platform_core.modules.event_relay.service import envelope_from_outbox

log = structlog.get_logger("projections")

DEFAULT_BATCH_SIZE = 500
STALE_REBUILD_SECONDS = 3600  # a rebuild still "running" after this is corrupted
ASSUMED_REPLAY_RATE = 400.0  # events/second, used for the first dry-run estimate

PROJECTION_REBUILDS = Counter(
    "projection_rebuilds_total", "Projection rebuilds started", ["projection"]
)
PROJECTION_REPLAYED = Counter(
    "projection_events_replayed_total", "Events replayed into projections", ["projection"]
)
PROJECTION_OUTDATED = Gauge(
    "projection_outdated", "1 when the built version is behind the code version", ["projection"]
)

# Column names every projection row carries that are NOT part of its derived
# value (regenerated on rebuild) — excluded from drift comparison.
_NON_VALUE_COLUMNS = frozenset({"id", "created_at", "updated_at"})


class Projection(EventConsumer):
    """Base class for rebuildable read models.

    Subclasses declare their metadata and the ORM models they own; the
    framework derives reset, rebuild, and verification from that. `handle`
    is the ordinary consumer handler — the SAME code path serves incremental
    processing and full replay, so a rebuild can never diverge from live
    behavior.
    """

    name: str = ""
    version: int = 1
    owner_module: str = ""
    description: str = ""
    event_types: tuple[str, ...] = ()
    rebuild_strategy: str = "full-replay"  # full-replay | append-only
    replay_order: int = 100  # ascending; lower rebuilds first in rebuild-all
    models: tuple[type, ...] = ()  # ORM classes owned by this projection

    async def reset(self, session: AsyncSession) -> int:
        """Delete every derived row. Override only for exotic storage."""
        deleted = 0
        for model in self.models:
            result = await session.execute(delete(model))
            deleted += result.rowcount or 0
        return deleted


_PROJECTIONS: dict[str, Projection] = {}


def register_projection(projection: Projection) -> Projection:
    """Register a projection — and, because a projection IS a consumer, its
    consumer registration too (one declaration, both roles)."""
    if not isinstance(projection, Projection):
        raise TypeError("register_projection expects a Projection")
    if not projection.models:
        raise ValueError(f"projection {projection.name!r} must declare the models it owns")
    register_consumer(projection)
    _PROJECTIONS[projection.name] = projection
    return projection


def unregister_projection(name: str) -> None:
    _PROJECTIONS.pop(name, None)


def registered_projections() -> list[Projection]:
    """Registry contents in replay order (the order rebuild-all uses)."""
    return sorted(_PROJECTIONS.values(), key=lambda p: (p.replay_order, p.name))


def discover_projections() -> list[str]:
    """Automatic discovery — reuses the consumer package import (projections
    self-register on import), so there is exactly one discovery path."""
    discover_consumers()
    return [p.name for p in registered_projections()]


def get_projection(name: str) -> Projection:
    projection = _PROJECTIONS.get(name)
    if projection is None:
        raise NotFoundError(f"unknown projection: {name}")
    return projection


# --- views -------------------------------------------------------------------


class RebuildProgress(BaseModel):
    total: int
    done: int
    percent: float
    elapsed_seconds: float | None
    eta_seconds: float | None


class ProjectionStatus(BaseModel):
    name: str
    version: int  # version the stored data was built with
    code_version: int  # version the registered projection declares
    owner_module: str
    description: str
    event_types: list[str]
    rebuild_strategy: str
    replay_order: int
    status: str
    health: str  # ok | outdated | rebuilding | degraded | never_built
    last_event_id: uuid.UUID | None
    last_event_at: datetime | None
    events_processed: int
    pending_events: int
    dead_events: int
    row_counts: dict[str, int]
    last_rebuild_at: datetime | None
    last_rebuild_ms: float | None
    rebuild: RebuildProgress | None
    last_error: str | None


class RebuildResult(BaseModel):
    projection: str
    dry_run: bool
    status: str  # completed | cancelled | failed | estimated
    events_scanned: int
    events_applied: int
    rows_deleted: int
    duration_seconds: float
    estimated_seconds: float | None
    version: int
    error: str | None = None


class ResetResult(BaseModel):
    projection: str
    rows_deleted: int
    executions_cleared: int


class VerificationCheck(BaseModel):
    check: str
    passed: bool
    detail: str
    count: int = 0


class VerificationResult(BaseModel):
    projection: str
    healthy: bool
    deep: bool
    checks: list[VerificationCheck]


class ProjectionRebuilder:
    """Lifecycle operations for projections. Reads only the outbox log."""

    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    # --- status ---------------------------------------------------------------

    async def status_all(self) -> list[ProjectionStatus]:
        return [await self.status(p.name) for p in registered_projections()]

    async def status(self, name: str) -> ProjectionStatus:
        projection = get_projection(name)
        async with self._sf() as session:
            state = await self._state(session, projection)
            cursor = await session.scalar(
                select(ConsumerCursor).where(ConsumerCursor.consumer_name == name)
            )
            processed = (
                await session.scalar(
                    select(func.count()).where(
                        ConsumerExecution.consumer_name == name,
                        ConsumerExecution.status == "succeeded",
                    )
                )
                or 0
            )
            dead = (
                await session.scalar(
                    select(func.count()).where(
                        ConsumerExecution.consumer_name == name,
                        ConsumerExecution.status == "dead",
                    )
                )
                or 0
            )
            pending = await self._pending_count(session, projection, cursor)
            row_counts = {
                model.__tablename__: (
                    await session.scalar(select(func.count()).select_from(model)) or 0
                )
                for model in projection.models
            }
            last_event_id = cursor.position_event_id if cursor else None
            last_event_at = cursor.position_created_at if cursor else None
            outdated = state.version < projection.version
            PROJECTION_OUTDATED.labels(name).set(1 if outdated else 0)
            health = self._health(state, outdated=outdated, dead=dead, processed=processed)
            return ProjectionStatus(
                name=name,
                version=state.version,
                code_version=projection.version,
                owner_module=projection.owner_module,
                description=projection.description,
                event_types=list(projection.event_types),
                rebuild_strategy=projection.rebuild_strategy,
                replay_order=projection.replay_order,
                status=state.status,
                health=health,
                last_event_id=last_event_id,
                last_event_at=last_event_at,
                events_processed=processed,
                pending_events=pending,
                dead_events=dead,
                row_counts=row_counts,
                last_rebuild_at=state.last_rebuild_at,
                last_rebuild_ms=state.last_rebuild_ms,
                rebuild=self._progress(state),
                last_error=state.last_error,
            )

    @staticmethod
    def _health(state: ProjectionState, *, outdated: bool, dead: int, processed: int) -> str:
        if state.status == "rebuilding":
            started = state.rebuild_started_at
            if started and (utcnow() - as_utc(started)).total_seconds() > STALE_REBUILD_SECONDS:
                return "degraded"  # corrupted replay: nothing has advanced it
            return "rebuilding"
        if state.status == "failed" or dead > 0:
            return "degraded"
        if outdated:
            return "outdated"
        if processed == 0 and state.last_rebuild_at is None:
            return "never_built"
        return "ok"

    @staticmethod
    def _progress(state: ProjectionState) -> RebuildProgress | None:
        if not state.rebuild_total and not state.rebuild_done:
            return None
        total = state.rebuild_total or 0
        done = state.rebuild_done or 0
        elapsed = eta = None
        if state.rebuild_started_at is not None:
            elapsed = (utcnow() - as_utc(state.rebuild_started_at)).total_seconds()
            if state.status == "rebuilding" and done > 0 and elapsed > 0:
                eta = round(max(total - done, 0) / (done / elapsed), 1)
            elif state.status != "rebuilding":
                elapsed = (state.last_rebuild_ms or 0) / 1000 or elapsed
        return RebuildProgress(
            total=total,
            done=done,
            percent=round(100.0 * done / total, 2) if total else 100.0,
            elapsed_seconds=round(elapsed, 3) if elapsed is not None else None,
            eta_seconds=eta,
        )

    # --- reset ----------------------------------------------------------------

    async def reset(self, name: str) -> ResetResult:
        """Clear derived rows AND consumer position/ledger. The incremental
        runner then rebuilds naturally from the start of the log."""
        projection = get_projection(name)
        async with self._sf() as session:
            state = await self._state(session, projection)
            if state.status == "rebuilding":
                raise ConflictError("a rebuild is in progress — cancel it first")
            rows = await projection.reset(session)
            cleared = await self._clear_consumer_state(session, name)
            state.status = "reset"
            state.rebuild_total = 0
            state.rebuild_done = 0
            state.rebuild_started_at = None
            state.last_error = None
            await session.commit()
        log.info("projection_reset", projection=name, rows=rows, executions=cleared)
        return ResetResult(projection=name, rows_deleted=rows, executions_cleared=cleared)

    # --- rebuild --------------------------------------------------------------

    async def rebuild_all(
        self, *, dry_run: bool = False, batch_size: int = DEFAULT_BATCH_SIZE
    ) -> list[RebuildResult]:
        """Rebuild every projection in declared replay order."""
        results = []
        for projection in registered_projections():
            results.append(
                await self.rebuild(projection.name, dry_run=dry_run, batch_size=batch_size)
            )
        return results

    async def rebuild(
        self, name: str, *, dry_run: bool = False, batch_size: int = DEFAULT_BATCH_SIZE
    ) -> RebuildResult:
        """Reconstruct a projection from the event log alone.

        Batched and restartable: progress is committed per batch (visible to
        concurrent status calls) and the cancel flag is honoured between
        batches. The projection's own `handle` is used, so replayed state is
        by construction identical to incrementally-built state.
        """
        projection = get_projection(name)
        batch_size = max(1, min(batch_size, 5000))
        if dry_run:
            return await self._dry_run(projection)

        async with self._sf() as session:
            state = await self._state(session, projection)
            if state.status == "rebuilding":
                raise ConflictError("rebuild already in progress")
            total = await self._match_count(session, projection)
            rows_deleted = await projection.reset(session)
            await self._clear_consumer_state(session, name)
            state.status = "rebuilding"
            state.cancel_requested = False
            state.rebuild_started_at = utcnow()
            state.rebuild_total = total
            state.rebuild_done = 0
            state.last_error = None
            await session.commit()
        PROJECTION_REBUILDS.labels(name).inc()

        started = time.monotonic()
        scanned = applied = 0
        position: tuple[datetime, uuid.UUID] | None = None
        outcome, error = "completed", None
        try:
            while True:
                async with self._sf() as session:
                    events = await self._fetch_batch(session, position, batch_size)
                    if not events:
                        break
                    for event in events:
                        if event.event_name in projection.event_types:
                            await projection.handle(envelope_from_outbox(event), session)
                            session.add(
                                ConsumerExecution(
                                    consumer_name=name,
                                    event_id=event.id,
                                    event_name=event.event_name,
                                    tenant_id=event.tenant_id,
                                    status="succeeded",
                                    attempts=1,
                                    processed_at=utcnow(),
                                )
                            )
                            applied += 1
                        scanned += 1
                        position = (event.created_at, event.id)
                    cursor = await self._cursor(session, name)
                    cursor.position_created_at, cursor.position_event_id = position
                    await self._bump_progress(session, name, applied)
                    await session.commit()
                PROJECTION_REPLAYED.labels(name).inc(len(events))
                if await self._cancel_requested(name):
                    outcome = "cancelled"
                    break
        except Exception as exc:  # a handler failed mid-replay
            outcome, error = "failed", str(exc)[:500]
            log.exception("projection_rebuild_failed", projection=name)

        duration = time.monotonic() - started
        async with self._sf() as session:
            state = await self._state(session, projection)
            state.status = {"completed": "live", "cancelled": "cancelled", "failed": "failed"}[
                outcome
            ]
            state.rebuild_done = applied
            state.last_error = error
            state.cancel_requested = False
            if outcome == "completed":
                # Only a completed rebuild may claim the code version.
                state.version = projection.version
                state.last_rebuild_at = utcnow()
                state.last_rebuild_ms = round(duration * 1000, 3)
            await session.commit()
        log.info(
            "projection_rebuild_finished",
            projection=name,
            outcome=outcome,
            scanned=scanned,
            applied=applied,
            seconds=round(duration, 3),
        )
        return RebuildResult(
            projection=name,
            dry_run=False,
            status=outcome,
            events_scanned=scanned,
            events_applied=applied,
            rows_deleted=rows_deleted,
            duration_seconds=round(duration, 3),
            estimated_seconds=None,
            version=projection.version if outcome == "completed" else 0,
            error=error,
        )

    async def cancel(self, name: str) -> ProjectionStatus:
        """Request cancellation; the running rebuild stops after its batch."""
        projection = get_projection(name)
        async with self._sf() as session:
            state = await self._state(session, projection)
            if state.status != "rebuilding":
                raise ConflictError("no rebuild is in progress")
            state.cancel_requested = True
            await session.commit()
        return await self.status(name)

    async def _dry_run(self, projection: Projection) -> RebuildResult:
        async with self._sf() as session:
            state = await self._state(session, projection)
            total = await self._match_count(session, projection)
            rows = 0
            for model in projection.models:
                rows += await session.scalar(select(func.count()).select_from(model)) or 0
        rate = ASSUMED_REPLAY_RATE
        if state.last_rebuild_ms and state.rebuild_done:
            measured = state.rebuild_done / (state.last_rebuild_ms / 1000)
            rate = measured if measured > 0 else rate
        return RebuildResult(
            projection=projection.name,
            dry_run=True,
            status="estimated",
            events_scanned=0,
            events_applied=total,  # events that WOULD be applied
            rows_deleted=rows,  # rows that WOULD be deleted
            duration_seconds=0.0,
            estimated_seconds=round(total / rate, 2),
            version=projection.version,
        )

    # --- verification ---------------------------------------------------------

    async def verify(self, name: str, *, deep: bool = False) -> VerificationResult:
        """Integrity checks. `deep` adds drift detection by shadow-replaying
        the log in a transaction that is always rolled back."""
        projection = get_projection(name)
        checks: list[VerificationCheck] = []
        async with self._sf() as session:
            state = await self._state(session, projection)
            cursor = await session.scalar(
                select(ConsumerCursor).where(ConsumerCursor.consumer_name == name)
            )

            checks.append(
                VerificationCheck(
                    check="version",
                    passed=state.version >= projection.version,
                    detail=(
                        f"built v{state.version}, code v{projection.version}"
                        + ("" if state.version >= projection.version else " — rebuild required")
                    ),
                )
            )
            stuck = state.status == "rebuilding" and (
                state.rebuild_started_at is None
                or (utcnow() - as_utc(state.rebuild_started_at)).total_seconds()
                > STALE_REBUILD_SECONDS
            )
            checks.append(
                VerificationCheck(
                    check="corrupted_replay",
                    passed=not stuck and state.status != "failed",
                    detail=(
                        f"status={state.status}"
                        + (f"; error={state.last_error}" if state.last_error else "")
                    ),
                )
            )

            missing = await self._missing_events(session, projection, cursor)
            checks.append(
                VerificationCheck(
                    check="missing_events",
                    passed=not missing,
                    detail=(
                        "every matching event behind the cursor has a ledger entry"
                        if not missing
                        else f"{len(missing)} matching event(s) behind the cursor were never "
                        f"processed, e.g. {missing[0]}"
                    ),
                    count=len(missing),
                )
            )

            dead = (
                await session.scalar(
                    select(func.count()).where(
                        ConsumerExecution.consumer_name == name,
                        ConsumerExecution.status == "dead",
                    )
                )
                or 0
            )
            checks.append(
                VerificationCheck(
                    check="dead_events",
                    passed=dead == 0,
                    detail=f"{dead} dead-lettered event(s)",
                    count=dead,
                )
            )

            duplicates = await self._duplicate_rows(session, projection)
            checks.append(
                VerificationCheck(
                    check="duplicate_rows",
                    passed=not duplicates,
                    detail=(
                        "no duplicate keys"
                        if not duplicates
                        else f"duplicate natural keys: {duplicates}"
                    ),
                    count=len(duplicates),
                )
            )

            gaps = await self._ledger_gap(session, projection, cursor)
            checks.append(
                VerificationCheck(
                    check="unexpected_gaps",
                    passed=gaps == 0,
                    detail=(
                        "ledger count matches the log behind the cursor"
                        if gaps == 0
                        else f"{gaps} event(s) unaccounted for behind the cursor"
                    ),
                    count=abs(gaps),
                )
            )

        if deep:
            checks.append(await self._drift_check(projection))
        return VerificationResult(
            projection=name,
            healthy=all(c.passed for c in checks),
            deep=deep,
            checks=checks,
        )

    async def _drift_check(self, projection: Projection) -> VerificationCheck:
        """Shadow replay: rebuild into the same tables inside a transaction,
        compare with the live rows, then ROLL BACK. Generic — it uses the
        projection's own handler, so it detects any divergence between stored
        state and what the log says it should be."""
        async with self._sf() as session:
            live = await self._snapshot(session, projection)
        async with self._sf() as session:
            try:
                await projection.reset(session)
                position = None
                while True:
                    events = await self._fetch_batch(session, position, DEFAULT_BATCH_SIZE)
                    if not events:
                        break
                    for event in events:
                        if event.event_name in projection.event_types:
                            await projection.handle(envelope_from_outbox(event), session)
                        position = (event.created_at, event.id)
                    await session.flush()
                shadow = await self._snapshot(session, projection)
            finally:
                await session.rollback()  # never mutate during verification
        differences = _diff_snapshots(live, shadow)
        return VerificationCheck(
            check="projection_drift",
            passed=not differences,
            detail=(
                "stored rows match a full replay of the log"
                if not differences
                else "; ".join(differences[:5])
            ),
            count=len(differences),
        )

    @staticmethod
    async def _snapshot(session: AsyncSession, projection: Projection) -> dict:
        """{table: {natural_key: {value_column: value}}} for comparison."""
        snapshot: dict[str, dict] = {}
        for model in projection.models:
            keys = _natural_key_columns(model)
            values = [
                c.name
                for c in model.__table__.columns
                if c.name not in _NON_VALUE_COLUMNS and c.name not in keys
            ]
            rows = (await session.scalars(select(model))).all()
            snapshot[model.__tablename__] = {
                tuple(str(getattr(row, k)) for k in keys): {v: str(getattr(row, v)) for v in values}
                for row in rows
            }
        return snapshot

    # --- helpers --------------------------------------------------------------

    async def _state(self, session: AsyncSession, projection: Projection) -> ProjectionState:
        """The lifecycle row, created (and persisted) on first touch."""
        state = await session.scalar(
            select(ProjectionState).where(ProjectionState.projection_name == projection.name)
        )
        if state is None:
            state = ProjectionState(
                projection_name=projection.name, version=projection.version, status="live"
            )
            session.add(state)
            await session.commit()
            await session.refresh(state)
        return state

    async def _bump_progress(self, session: AsyncSession, name: str, done: int) -> None:
        state = await session.scalar(
            select(ProjectionState).where(ProjectionState.projection_name == name)
        )
        if state is not None:
            state.rebuild_done = done

    async def _cancel_requested(self, name: str) -> bool:
        async with self._sf() as session:
            return bool(
                await session.scalar(
                    select(ProjectionState.cancel_requested).where(
                        ProjectionState.projection_name == name
                    )
                )
            )

    async def _cursor(self, session: AsyncSession, name: str) -> ConsumerCursor:
        cursor = await session.scalar(
            select(ConsumerCursor).where(ConsumerCursor.consumer_name == name)
        )
        if cursor is None:
            cursor = ConsumerCursor(consumer_name=name)
            session.add(cursor)
            await session.flush()
        return cursor

    @staticmethod
    async def _clear_consumer_state(session: AsyncSession, name: str) -> int:
        """Wipe ledger + cursor so the log is replayed from its start."""
        result = await session.execute(
            delete(ConsumerExecution).where(ConsumerExecution.consumer_name == name)
        )
        cursor = await session.scalar(
            select(ConsumerCursor).where(ConsumerCursor.consumer_name == name)
        )
        if cursor is not None:
            cursor.position_created_at = None
            cursor.position_event_id = None
        return result.rowcount or 0

    @staticmethod
    async def _fetch_batch(
        session: AsyncSession, position: tuple[datetime, uuid.UUID] | None, limit: int
    ) -> list[OutboxEvent]:
        stmt = select(OutboxEvent).order_by(OutboxEvent.created_at, OutboxEvent.id).limit(limit)
        if position is not None:
            created_at, event_id = position
            stmt = stmt.where(
                (OutboxEvent.created_at > created_at)
                | ((OutboxEvent.created_at == created_at) & (OutboxEvent.id > event_id))
            )
        return list((await session.scalars(stmt)).all())

    @staticmethod
    async def _match_count(session: AsyncSession, projection: Projection) -> int:
        return (
            await session.scalar(
                select(func.count()).where(OutboxEvent.event_name.in_(projection.event_types))
            )
            or 0
        )

    @staticmethod
    def _behind_cursor(cursor: ConsumerCursor | None):
        """Predicate for events at or before the cursor watermark."""
        if cursor is None or cursor.position_created_at is None:
            return None
        at_or_before = OutboxEvent.created_at < cursor.position_created_at
        if cursor.position_event_id is not None:
            at_or_before = at_or_before | (
                (OutboxEvent.created_at == cursor.position_created_at)
                & (OutboxEvent.id <= cursor.position_event_id)
            )
        return at_or_before

    async def _pending_count(
        self, session: AsyncSession, projection: Projection, cursor: ConsumerCursor | None
    ) -> int:
        stmt = select(func.count()).where(OutboxEvent.event_name.in_(projection.event_types))
        behind = self._behind_cursor(cursor)
        if behind is not None:
            stmt = stmt.where(~behind)
        return (await session.scalar(stmt)) or 0

    async def _missing_events(
        self, session: AsyncSession, projection: Projection, cursor: ConsumerCursor | None
    ) -> list[str]:
        """Matching events the cursor has passed that have no ledger entry."""
        behind = self._behind_cursor(cursor)
        if behind is None:
            return []
        processed = select(ConsumerExecution.event_id).where(
            ConsumerExecution.consumer_name == projection.name
        )
        rows = await session.scalars(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.event_name.in_(projection.event_types),
                behind,
                OutboxEvent.id.not_in(processed),
            )
            .limit(50)
        )
        return [str(r) for r in rows.all()]

    async def _ledger_gap(
        self, session: AsyncSession, projection: Projection, cursor: ConsumerCursor | None
    ) -> int:
        behind = self._behind_cursor(cursor)
        if behind is None:
            return 0
        expected = (
            await session.scalar(
                select(func.count()).where(
                    OutboxEvent.event_name.in_(projection.event_types), behind
                )
            )
            or 0
        )
        recorded = (
            await session.scalar(
                select(func.count()).where(ConsumerExecution.consumer_name == projection.name)
            )
            or 0
        )
        return expected - recorded

    @staticmethod
    async def _duplicate_rows(session: AsyncSession, projection: Projection) -> list[str]:
        """Natural-key duplicates, derived from each model's own unique
        constraint — no per-projection configuration needed."""
        duplicates = []
        for model in projection.models:
            keys = _natural_key_columns(model)
            if keys == ("id",):
                continue
            columns = [getattr(model, k) for k in keys]
            rows = await session.execute(
                select(*columns, func.count()).group_by(*columns).having(func.count() > 1).limit(10)
            )
            for row in rows.all():
                duplicates.append(f"{model.__tablename__}{tuple(str(v) for v in row[:-1])}")
        return duplicates


def _natural_key_columns(model) -> tuple[str, ...]:
    """The model's declared unique constraint = its natural key."""
    for constraint in model.__table__.constraints:
        if isinstance(constraint, UniqueConstraint):
            return tuple(column.name for column in constraint.columns)
    return ("id",)


def _diff_snapshots(live: dict, shadow: dict) -> list[str]:
    differences: list[str] = []
    for table, shadow_rows in shadow.items():
        live_rows = live.get(table, {})
        for key, values in shadow_rows.items():
            if key not in live_rows:
                differences.append(f"{table}{key}: missing from stored projection")
            elif live_rows[key] != values:
                changed = [
                    f"{column}={live_rows[key].get(column)}!={value}"
                    for column, value in values.items()
                    if live_rows[key].get(column) != value
                ]
                differences.append(f"{table}{key}: {', '.join(changed)}")
        for key in live_rows:
            if key not in shadow_rows:
                differences.append(f"{table}{key}: stored row not produced by the log")
    return differences
