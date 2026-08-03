"""Event Relay (SPRINT-008A) — outbox bus, dispatcher, retry, DLQ, replay.

Flow: business tx commits (outbox row inside it) -> dispatcher claims the
row (CAS: pending->delivering, so two dispatchers cannot double-deliver) ->
publishes to the transport -> marks delivered (+ delivery record) -> on
failure schedules an exponential-backoff retry -> dead-letters after
MAX_ATTEMPTS. Replay resets dead events to pending with a fresh budget.
"""

import uuid
from datetime import datetime, timedelta

import structlog
from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.config import get_settings
from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.event_relay.models import DeadLetter, EventDelivery, OutboxEvent

log = structlog.get_logger("relay")

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 300.0
STALE_CLAIM_SECONDS = 60.0  # crash recovery: reclaim rows stuck in 'delivering'

RELAY_DELIVERED = Counter("relay_delivered_total", "Events delivered by the relay")
RELAY_RETRIES = Counter("relay_retries_total", "Delivery attempts that failed and were retried")
RELAY_DEAD = Counter("relay_dead_total", "Events moved to the dead letter queue")
RELAY_PENDING = Gauge("relay_pending_events", "Outbox events awaiting delivery")
RELAY_LATENCY = Histogram(
    "relay_delivery_latency_seconds",
    "Commit-to-delivery latency",
    buckets=(0.1, 0.5, 1, 5, 30, 120, 600),
)


def backoff_delay(attempts: int) -> float:
    return min(BACKOFF_BASE_SECONDS**attempts, BACKOFF_CAP_SECONDS)


def envelope_from_outbox(row: OutboxEvent) -> EventEnvelope:
    """Rebuild the wire envelope from its durable outbox record. Shared by
    the dispatcher (transport delivery) and the consumer framework."""
    return EventEnvelope(
        id=row.id,  # stable Event ID = transport message_id = idempotency key
        type=row.event_name,
        source=get_settings().service_name,
        time=as_utc(row.occurred_at).isoformat(),
        tenant_id=row.tenant_id,
        actor_id=row.created_by,
        trace_id=row.correlation_id,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        version=row.version,
        data=row.payload,
    )


class OutboxEventBus:
    """EventBus implementation that stores events transactionally.

    Injected wherever services depend on the bus port: publishes become
    outbox writes inside the caller's transaction. In `inline` mode the row
    is also dispatched immediately (dev/test); `background` mode leaves
    delivery to the relay loop. A transport failure NEVER fails the
    business transaction — the row simply stays pending for retry.
    """

    def __init__(self, session: AsyncSession, transport: EventBus):
        self._session = session
        self._transport = transport

    async def publish(self, envelope: EventEnvelope) -> None:
        row = OutboxEvent(
            id=envelope.id,
            tenant_id=envelope.tenant_id,
            aggregate_type=envelope.aggregate_type,
            aggregate_id=envelope.aggregate_id,
            event_name=envelope.type,
            payload=envelope.data,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            occurred_at=utcnow(),
            created_by=envelope.actor_id,
            version=envelope.version,
        )
        self._session.add(row)
        await self._session.flush()
        if get_settings().outbox_mode == "inline":
            relay = RelayService(self._session, self._transport)
            await relay.dispatch_one(row, now=utcnow())


class RelayStats(BaseModel):
    pending: int
    delivering: int
    delivered: int
    dead: int
    total_attempts: int
    average_latency_ms: float | None


class OutboxEventView(BaseModel):
    id: uuid.UUID
    event_name: str
    status: str
    attempts: int
    tenant_id: uuid.UUID | None
    correlation_id: str | None
    occurred_at: datetime
    delivered_at: datetime | None
    last_error: str | None

    model_config = {"from_attributes": True}


class DeadLetterView(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    event_name: str
    reason: str
    dead_at: datetime
    replayed_at: datetime | None
    replay_count: int

    model_config = {"from_attributes": True}


class RelayService:
    def __init__(self, session: AsyncSession, transport: EventBus):
        self._session = session
        self._transport = transport

    # --- dispatching -------------------------------------------------------

    async def dispatch_pending(self, *, now: datetime | None = None, limit: int = 100) -> int:
        """Deliver due events in commit order. Returns delivered count."""
        now = now or utcnow()
        stale_before = now - timedelta(seconds=STALE_CLAIM_SECONDS)
        stmt = (
            select(OutboxEvent)
            .where(
                ((OutboxEvent.status == "pending") & (OutboxEvent.next_attempt_at <= now))
                | ((OutboxEvent.status == "delivering") & (OutboxEvent.claimed_at <= stale_before))
            )
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
        )
        rows = list((await self._session.scalars(stmt)).all())
        delivered = 0
        for row in rows:
            if await self.dispatch_one(row, now=now):
                delivered += 1
        return delivered

    async def dispatch_one(self, row: OutboxEvent, *, now: datetime) -> bool:
        """Claim-and-deliver a single event; safe under concurrent dispatchers."""
        claim = await self._session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == row.id, OutboxEvent.status.in_(("pending", "delivering")))
            .values(status="delivering", claimed_at=now)
        )
        if claim.rowcount != 1:
            return False  # someone else finished it
        await self._session.refresh(row)
        attempt = row.attempts + 1
        started = utcnow()
        try:
            await self._transport.publish(self._envelope_of(row))
        except Exception as exc:
            await self._on_failure(row, attempt, str(exc)[:500], now)
            return False
        latency_ms = (utcnow() - started).total_seconds() * 1000
        commit_to_deliver = (utcnow() - as_utc(row.created_at)).total_seconds()
        row.status = "delivered"
        row.attempts = attempt
        row.delivered_at = utcnow()
        row.last_error = None
        self._session.add(
            EventDelivery(
                event_id=row.id,
                attempt=attempt,
                status="success",
                transport=type(self._transport).__name__,
                latency_ms=round(latency_ms, 3),
            )
        )
        RELAY_DELIVERED.inc()
        RELAY_LATENCY.observe(max(commit_to_deliver, 0))
        await self._session.flush()  # outcome must be visible before return
        return True

    async def _on_failure(self, row: OutboxEvent, attempt: int, error: str, now: datetime) -> None:
        self._session.add(
            EventDelivery(
                event_id=row.id,
                attempt=attempt,
                status="failed",
                transport=type(self._transport).__name__,
                error=error,
            )
        )
        row.attempts = attempt
        row.last_error = error
        if attempt >= MAX_ATTEMPTS:
            row.status = "dead"
            self._session.add(
                DeadLetter(
                    event_id=row.id,
                    tenant_id=row.tenant_id,
                    event_name=row.event_name,
                    payload=row.payload,
                    reason=error,
                )
            )
            RELAY_DEAD.inc()
            log.error("event_dead_lettered", event_id=str(row.id), name=row.event_name)
        else:
            row.status = "pending"
            row.next_attempt_at = now + timedelta(seconds=backoff_delay(attempt))
            RELAY_RETRIES.inc()
            log.warning(
                "event_delivery_failed",
                event_id=str(row.id),
                attempt=attempt,
                retry_at=row.next_attempt_at.isoformat(),
            )
        await self._session.flush()  # outcome must be visible before return

    def _envelope_of(self, row: OutboxEvent) -> EventEnvelope:
        return envelope_from_outbox(row)

    # --- replay & operations ----------------------------------------------

    async def retry_event(self, event_id: uuid.UUID) -> OutboxEvent:
        """Reset a failed/dead event to pending with a fresh attempt budget."""
        row = await self._session.get(OutboxEvent, event_id)
        if row is None:
            raise NotFoundError("outbox event not found")
        if row.status == "delivered":
            raise ConflictError("event already delivered — use replay to re-emit")
        row.status = "pending"
        row.attempts = 0
        row.next_attempt_at = utcnow()
        row.last_error = None
        await self._session.flush()
        return row

    async def replay_dead_letter(self, dead_letter_id: uuid.UUID) -> OutboxEvent:
        dl = await self._session.get(DeadLetter, dead_letter_id)
        if dl is None:
            raise NotFoundError("dead letter not found")
        row = await self.retry_event(dl.event_id)
        dl.replayed_at = utcnow()
        dl.replay_count += 1
        log.info("dead_letter_replayed", event_id=str(dl.event_id), count=dl.replay_count)
        return row

    async def replay_delivered(self, event_id: uuid.UUID) -> OutboxEvent:
        """Re-emit an already-delivered event (consumers dedupe by Event ID)."""
        row = await self._session.get(OutboxEvent, event_id)
        if row is None:
            raise NotFoundError("outbox event not found")
        row.status = "pending"
        row.next_attempt_at = utcnow()
        await self._session.flush()
        return row

    # --- monitoring ---------------------------------------------------------

    async def stats(self) -> RelayStats:
        counts: dict[str, int] = {}
        rows = await self._session.execute(
            select(OutboxEvent.status, func.count()).group_by(OutboxEvent.status)
        )
        for status, count in rows.all():
            counts[status] = count
        attempts = await self._session.scalar(select(func.sum(OutboxEvent.attempts)))
        avg_latency = await self._session.scalar(
            select(func.avg(EventDelivery.latency_ms)).where(EventDelivery.status == "success")
        )
        RELAY_PENDING.set(counts.get("pending", 0))
        return RelayStats(
            pending=counts.get("pending", 0),
            delivering=counts.get("delivering", 0),
            delivered=counts.get("delivered", 0),
            dead=counts.get("dead", 0),
            total_attempts=attempts or 0,
            average_latency_ms=round(avg_latency, 3) if avg_latency is not None else None,
        )

    async def list_events(self, *, status: str | None = None, limit: int = 50) -> list[OutboxEvent]:
        stmt = select(OutboxEvent).order_by(OutboxEvent.created_at.desc()).limit(min(limit, 200))
        if status:
            stmt = stmt.where(OutboxEvent.status == status)
        return list((await self._session.scalars(stmt)).all())

    async def find_aggregate_event(
        self, aggregate_type: str, aggregate_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> OutboxEvent | None:
        """Look up the durable event record of an aggregate (platform read
        API — e.g. settlement verifying a pricing calculation, SET-001)."""
        return await self._session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_type == aggregate_type,
                OutboxEvent.aggregate_id == aggregate_id,
                OutboxEvent.tenant_id == tenant_id,
            )
        )

    async def list_dead_letters(self, *, limit: int = 50) -> list[DeadLetter]:
        stmt = select(DeadLetter).order_by(DeadLetter.dead_at.desc()).limit(min(limit, 200))
        return list((await self._session.scalars(stmt)).all())
