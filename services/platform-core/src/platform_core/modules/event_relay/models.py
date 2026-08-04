"""Event Relay (SPRINT-008A) — persistence models for reliable delivery.

The outbox row is written in the SAME transaction as the business change:
if the transaction rolls back, the event never existed; if it commits, the
event WILL be delivered (dispatcher retries until delivered or dead).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

OUTBOX_STATUSES = ("pending", "delivering", "delivered", "dead")


class OutboxEvent(Base, IdMixin):
    """The id doubles as the Event ID on the wire (message_id, idempotency key)."""

    __tablename__ = "event_outbox"
    __table_args__ = (
        Index("ix_outbox_dispatch", "status", "next_attempt_at"),
        # Consumer-cursor pagination: WHERE (created_at, id) > watermark
        # ORDER BY created_at, id (SPRINT-008B).
        Index("ix_outbox_consume", "created_at", "id"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    aggregate_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    event_name: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventDelivery(Base, IdMixin):
    """One row per delivery attempt — the audit trail of the relay itself."""

    __tablename__ = "event_delivery"

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))  # success | failed
    transport: Mapped[str] = mapped_column(String(30), default="")
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConsumerCursor(Base, IdMixin):
    """Per-consumer position in the outbox log (SPRINT-008B). Consumers read
    the durable log in (created_at, id) order; the cursor is their watermark."""

    __tablename__ = "consumer_cursor"

    consumer_name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    position_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    position_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ConsumerExecution(Base, IdMixin):
    """One consumer's processing record for one event (SPRINT-008B).

    Triple duty: idempotency ledger (unique consumer+event — an event is
    never successfully processed twice), execution history, and the
    consumer-side dead letter queue (status='dead' rows are the DLQ;
    replay resets them to 'failed' with a fresh attempt budget)."""

    __tablename__ = "consumer_execution"
    __table_args__ = (
        UniqueConstraint("consumer_name", "event_id", name="uq_consumer_execution"),
        Index("ix_consumer_execution_status", "consumer_name", "status"),
    )

    consumer_name: Mapped[str] = mapped_column(String(80), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    event_name: Mapped[str] = mapped_column(String(120))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="failed")  # succeeded|failed|dead
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectionState(Base, IdMixin):
    """Lifecycle state of one projection (PLT-001).

    Deliberately stores ONLY what cannot be derived: the built version, the
    rebuild story, and the cancel flag. Position, processed counts, and lag
    are derived from the consumer cursor and the idempotency ledger — one
    source of truth, so projection status can never drift from reality.
    """

    __tablename__ = "projection_state"

    projection_name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # version actually built
    status: Mapped[str] = mapped_column(String(16), default="live")
    # live | rebuilding | cancelled | failed | reset
    last_rebuild_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rebuild_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    rebuild_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rebuild_total: Mapped[int] = mapped_column(Integer, default=0)
    rebuild_done: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeadLetter(Base, IdMixin):
    """Events that exhausted retries. Nothing is deleted; replay resets them."""

    __tablename__ = "dead_letter_queue"

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    event_name: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(String(500))
    dead_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replay_count: Mapped[int] = mapped_column(Integer, default=0)
