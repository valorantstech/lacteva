"""Event consumer framework (SPRINT-008B) — the receiving half of the Relay.

Consumers read the DURABLE OUTBOX LOG (not the transport): each registered
consumer has a cursor over `event_outbox` in (created_at, id) order and an
idempotency ledger (`consumer_execution`, unique per consumer+event). This
gives identical semantics in test/dev/prod, ordered per-consumer processing,
and total isolation from business transactions — a consumer failure can
never touch business writes, because those committed long before (BR-worthy
invariant: consumers NEVER affect producers).

Failure model: per-event transaction (handler writes + execution record +
cursor advance commit atomically). On failure the handler's writes roll
back, the failure is recorded with exponential backoff, and the consumer's
cursor STOPS (ordering preserved) until the event succeeds or exhausts
MAX_CONSUMER_ATTEMPTS and dead-letters — then the cursor advances past the
poison message. Dead executions are replayable.

Business modules never know consumers exist: consumers live in the separate
`platform_core.consumers` package and are discovered by import at startup.
"""

import importlib
import pkgutil
import uuid
from datetime import datetime, timedelta

import structlog
from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.modules.event_relay.models import (
    ConsumerCursor,
    ConsumerExecution,
    OutboxEvent,
)
from platform_core.modules.event_relay.service import backoff_delay, envelope_from_outbox

log = structlog.get_logger("consumers")

MAX_CONSUMER_ATTEMPTS = 5
CONSUMER_CONFIG_PREFIX = "platform.consumers"  # platform.consumers.<name>.enabled

CONSUMER_PROCESSED = Counter(
    "consumer_processed_total", "Events successfully processed", ["consumer"]
)
CONSUMER_FAILED = Counter("consumer_failed_total", "Handler failures", ["consumer"])
CONSUMER_RETRIED = Counter("consumer_retried_total", "Retries scheduled", ["consumer"])
CONSUMER_DEAD = Counter("consumer_dead_total", "Events dead-lettered", ["consumer"])
CONSUMER_LAG = Gauge("consumer_lag_events", "Events behind the log head", ["consumer"])
CONSUMER_LATENCY = Histogram(
    "consumer_latency_seconds",
    "Event-commit to consumer-processed latency",
    ["consumer"],
    buckets=(0.1, 0.5, 1, 5, 30, 120, 600),
)


class EventConsumer:
    """Base class for platform event consumers.

    Subclasses set `name` (stable, unique — it keys the cursor and the
    idempotency ledger; renaming a consumer resets its position) and
    `event_types`, and implement `handle`. The session passed to `handle`
    commits atomically with the execution record: a handler either fully
    processes an event exactly once or leaves no trace.
    """

    name: str = ""
    event_types: tuple[str, ...] = ()

    async def handle(self, envelope, session: AsyncSession) -> None:  # pragma: no cover
        raise NotImplementedError


_REGISTRY: dict[str, EventConsumer] = {}


def register_consumer(consumer: EventConsumer) -> EventConsumer:
    """Register (or re-register) a consumer instance. Import-time friendly."""
    if not consumer.name or not consumer.event_types:
        raise ValueError("consumers need a stable name and at least one event type")
    _REGISTRY[consumer.name] = consumer
    return consumer


def unregister_consumer(name: str) -> None:
    _REGISTRY.pop(name, None)


def registered_consumers() -> list[EventConsumer]:
    """Projections first (in replay order), then plain consumers.

    Read models are inputs to other consumers — the notification dispatcher
    resolves recipients from a directory projection — so a projection must
    never run after a consumer that depends on it within the same pass.
    """

    def order(consumer: EventConsumer) -> tuple[int, int, str]:
        replay_order = getattr(consumer, "replay_order", None)
        if replay_order is None:  # a plain consumer
            return (1, 0, consumer.name)
        return (0, replay_order, consumer.name)

    return sorted(_REGISTRY.values(), key=order)


def discover_consumers() -> list[str]:
    """Automatic discovery: import every module in `platform_core.consumers`
    (modules self-register on import). Idempotent."""
    import platform_core.consumers as package

    for module_info in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{package.__name__}.{module_info.name}")
    return sorted(_REGISTRY)


# --- views ------------------------------------------------------------------


class ConsumerStatus(BaseModel):
    name: str
    event_types: list[str]
    enabled: bool
    lag_events: int
    succeeded: int
    failed: int
    dead: int
    last_processed_at: datetime | None


class ConsumersHealth(BaseModel):
    status: str  # ok | degraded
    consumers: list[ConsumerStatus]


class ExecutionView(BaseModel):
    id: uuid.UUID
    consumer_name: str
    event_id: uuid.UUID
    event_name: str
    status: str
    attempts: int
    last_error: str | None
    latency_ms: float | None
    processed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConsumerRunner:
    """Processes the outbox log for every registered consumer. Safe to run
    concurrently with the relay dispatcher and (idempotently) with itself."""

    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def run_once(self, *, limit: int = 100, now: datetime | None = None) -> dict[str, int]:
        now = now or utcnow()
        totals = {"processed": 0, "failed": 0, "skipped": 0}
        for consumer in registered_consumers():
            if not await self._enabled(consumer.name):
                totals["skipped"] += 1
                continue
            result = await self._run_consumer(consumer, limit=limit, now=now)
            totals["processed"] += result["processed"]
            totals["failed"] += result["failed"]
        return totals

    async def _run_consumer(
        self, consumer: EventConsumer, *, limit: int, now: datetime
    ) -> dict[str, int]:
        processed = failed = 0
        async with self._sf() as session:
            cursor = await self._cursor(session, consumer.name)
            events = await self._next_events(session, cursor, limit)
        for event in events:
            if event.event_name not in consumer.event_types:
                await self._advance(consumer.name, event)  # skip without a ledger entry
                continue
            outcome = await self._process(consumer, event, now)
            if outcome == "processed":
                processed += 1
            elif outcome == "failed":
                failed += 1
                break  # ordering: never run ahead of a retrying event
            elif outcome == "waiting":
                break  # backoff not elapsed — try again next run
            # "skipped" (already succeeded/dead): cursor advanced, keep going
        await self._update_lag(consumer.name)
        return {"processed": processed, "failed": failed}

    async def _process(self, consumer: EventConsumer, event: OutboxEvent, now: datetime) -> str:
        async with self._sf() as session:
            execution = await session.scalar(
                select(ConsumerExecution).where(
                    ConsumerExecution.consumer_name == consumer.name,
                    ConsumerExecution.event_id == event.id,
                )
            )
            if execution is not None and execution.status in ("succeeded", "dead"):
                await self._advance(consumer.name, event)
                return "skipped"  # idempotency: never process twice
            if (
                execution is not None
                and execution.next_attempt_at is not None
                and as_utc(execution.next_attempt_at) > now
            ):
                return "waiting"
        attempts = (execution.attempts if execution else 0) + 1
        try:
            async with self._sf() as session:
                await consumer.handle(envelope_from_outbox(event), session)
                await self._record_outcome(
                    session,
                    consumer.name,
                    event,
                    status="succeeded",
                    attempts=attempts,
                    now=now,
                )
                await self._advance_in(session, consumer.name, event)
                await session.commit()
            CONSUMER_PROCESSED.labels(consumer.name).inc()
            CONSUMER_LATENCY.labels(consumer.name).observe(
                max((now - as_utc(event.created_at)).total_seconds(), 0)
            )
            return "processed"
        except Exception as exc:
            # The handler's writes rolled back with its session; record the
            # failure separately — business data is untouched by design.
            async with self._sf() as session:
                dead = attempts >= MAX_CONSUMER_ATTEMPTS
                await self._record_outcome(
                    session,
                    consumer.name,
                    event,
                    status="dead" if dead else "failed",
                    attempts=attempts,
                    now=now,
                    error=str(exc)[:500],
                )
                if dead:
                    await self._advance_in(session, consumer.name, event)
                await session.commit()
            if dead:
                CONSUMER_DEAD.labels(consumer.name).inc()
                log.error(
                    "consumer_event_dead",
                    consumer=consumer.name,
                    event_id=str(event.id),
                    error=str(exc)[:200],
                )
                return "dead"
            CONSUMER_FAILED.labels(consumer.name).inc()
            CONSUMER_RETRIED.labels(consumer.name).inc()
            log.warning(
                "consumer_event_failed",
                consumer=consumer.name,
                event_id=str(event.id),
                attempt=attempts,
            )
            return "failed"

    # --- operations ---------------------------------------------------------

    async def replay_execution(self, execution_id: uuid.UUID) -> ConsumerExecution:
        """Reset a dead execution for reprocessing with a fresh budget."""
        async with self._sf() as session:
            execution = await session.get(ConsumerExecution, execution_id)
            if execution is None:
                raise NotFoundError("consumer execution not found")
            if execution.status != "dead":
                raise ConflictError("only dead executions can be replayed")
            execution.status = "failed"
            execution.attempts = 0
            execution.next_attempt_at = utcnow()
            execution.last_error = None
            # Rewind the cursor so the ordered scan reaches the event again.
            event = await session.get(OutboxEvent, execution.event_id)
            cursor = await self._cursor(session, execution.consumer_name)
            if event is not None:
                cursor.position_created_at = event.created_at - timedelta(microseconds=1)
                cursor.position_event_id = None
            await session.commit()
            return execution

    async def health(self) -> ConsumersHealth:
        statuses: list[ConsumerStatus] = []
        degraded = False
        async with self._sf() as session:
            for consumer in registered_consumers():
                counts = dict(
                    (
                        await session.execute(
                            select(ConsumerExecution.status, func.count())
                            .where(ConsumerExecution.consumer_name == consumer.name)
                            .group_by(ConsumerExecution.status)
                        )
                    ).all()
                )
                lag = await self._lag(session, consumer.name)
                last = await session.scalar(
                    select(func.max(ConsumerExecution.processed_at)).where(
                        ConsumerExecution.consumer_name == consumer.name,
                        ConsumerExecution.status == "succeeded",
                    )
                )
                dead = counts.get("dead", 0)
                if dead > 0 or lag > 1000:
                    degraded = True
                statuses.append(
                    ConsumerStatus(
                        name=consumer.name,
                        event_types=list(consumer.event_types),
                        enabled=await self._enabled(consumer.name),
                        lag_events=lag,
                        succeeded=counts.get("succeeded", 0),
                        failed=counts.get("failed", 0),
                        dead=dead,
                        last_processed_at=last,
                    )
                )
        return ConsumersHealth(status="degraded" if degraded else "ok", consumers=statuses)

    async def list_executions(
        self, *, consumer_name: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[ConsumerExecution]:
        async with self._sf() as session:
            stmt = (
                select(ConsumerExecution)
                .order_by(ConsumerExecution.created_at.desc())
                .limit(min(limit, 200))
            )
            if consumer_name:
                stmt = stmt.where(ConsumerExecution.consumer_name == consumer_name)
            if status:
                stmt = stmt.where(ConsumerExecution.status == status)
            return list((await session.scalars(stmt)).all())

    # --- helpers ------------------------------------------------------------

    async def _cursor(self, session: AsyncSession, name: str) -> ConsumerCursor:
        cursor = await session.scalar(
            select(ConsumerCursor).where(ConsumerCursor.consumer_name == name)
        )
        if cursor is None:
            cursor = ConsumerCursor(consumer_name=name)
            session.add(cursor)
            await session.flush()
        return cursor

    async def _next_events(
        self, session: AsyncSession, cursor: ConsumerCursor, limit: int
    ) -> list[OutboxEvent]:
        stmt = select(OutboxEvent).order_by(OutboxEvent.created_at, OutboxEvent.id).limit(limit)
        if cursor.position_created_at is not None:
            after = OutboxEvent.created_at > cursor.position_created_at
            if cursor.position_event_id is not None:
                after = after | (
                    (OutboxEvent.created_at == cursor.position_created_at)
                    & (OutboxEvent.id > cursor.position_event_id)
                )
            stmt = stmt.where(after)
        return list((await session.scalars(stmt)).all())

    async def _advance(self, name: str, event: OutboxEvent) -> None:
        async with self._sf() as session:
            await self._advance_in(session, name, event)
            await session.commit()

    async def _advance_in(self, session: AsyncSession, name: str, event: OutboxEvent) -> None:
        cursor = await self._cursor(session, name)
        cursor.position_created_at = event.created_at
        cursor.position_event_id = event.id

    async def _record_outcome(
        self,
        session: AsyncSession,
        name: str,
        event: OutboxEvent,
        *,
        status: str,
        attempts: int,
        now: datetime,
        error: str | None = None,
    ) -> None:
        execution = await session.scalar(
            select(ConsumerExecution).where(
                ConsumerExecution.consumer_name == name,
                ConsumerExecution.event_id == event.id,
            )
        )
        if execution is None:
            execution = ConsumerExecution(
                consumer_name=name,
                event_id=event.id,
                event_name=event.event_name,
                tenant_id=event.tenant_id,
            )
            session.add(execution)
        execution.status = status
        execution.attempts = attempts
        execution.last_error = error
        if status == "succeeded":
            execution.processed_at = now
            execution.next_attempt_at = None
            execution.latency_ms = round(
                max((now - as_utc(event.created_at)).total_seconds(), 0) * 1000, 3
            )
        elif status == "failed":
            execution.next_attempt_at = now + timedelta(seconds=backoff_delay(attempts))
        else:  # dead
            execution.next_attempt_at = None
        await session.flush()

    async def _lag(self, session: AsyncSession, name: str) -> int:
        cursor = await session.scalar(
            select(ConsumerCursor).where(ConsumerCursor.consumer_name == name)
        )
        stmt = select(func.count()).select_from(OutboxEvent)
        if cursor is not None and cursor.position_created_at is not None:
            after = OutboxEvent.created_at > cursor.position_created_at
            if cursor.position_event_id is not None:
                after = after | (
                    (OutboxEvent.created_at == cursor.position_created_at)
                    & (OutboxEvent.id > cursor.position_event_id)
                )
            stmt = stmt.where(after)
        return (await session.scalar(stmt)) or 0

    async def _update_lag(self, name: str) -> None:
        async with self._sf() as session:
            CONSUMER_LAG.labels(name).set(await self._lag(session, name))

    async def _enabled(self, name: str) -> bool:
        """Per-consumer kill switch: global config key
        `platform.consumers.<name>.enabled` (absent = enabled)."""
        from platform_core.modules.configuration.models import ConfigEntry

        async with self._sf() as session:
            entry = await session.scalar(
                select(ConfigEntry).where(
                    ConfigEntry.scope == "global",
                    ConfigEntry.key == f"{CONSUMER_CONFIG_PREFIX}.{name}.enabled",
                )
            )
        if entry is None:
            return True
        return bool(entry.value.get("value", True))
