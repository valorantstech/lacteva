"""Sync module — persistence models (OFF-001: Offline Collection Sync).

The device is the temporary owner of a collection that has not reached the
platform yet. When connectivity returns it replays what it recorded, and this
table is the server's memory of that replay: one row per client operation,
keyed by a client-generated `operation_id`.

That key is the whole idempotency story. A device that loses its ack and
re-sends gets the ORIGINAL outcome back rather than a second transaction —
the same guarantee the consumer framework gives events (BR-0014), applied to
device operations.

The row also holds the mapping from the device's LOCAL identifier
(`client_reference`) to the server id it became, so a later batch can say
"weigh the transaction I created while offline" and be understood.

Offline changes nothing about the business rules: every operation is applied
by calling the same milk-collection service the online API calls (BR-0021).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

# Server-side outcome of one replayed operation.
#   applied   — the business service accepted it
#   duplicate — already applied in an earlier batch; the original result stands
#   conflict  — the world moved on; structured reason, never a silent overwrite
#   failed    — a transient or unexpected error; retryable
SYNC_STATUSES = ("applied", "duplicate", "conflict", "failed")

# Conflict reasons a device must be able to explain to an operator.
CONFLICT_REASONS = (
    "already_accepted",  # the transaction reached a terminal state elsewhere
    "supplier_unavailable",  # supplier archived/removed since capture
    "session_closed",  # the collection session expired or was closed
    "rate_card_changed",  # priced differently than the device expected
    "unresolved_reference",  # a predecessor operation never landed
    "invalid_state",  # the state machine refuses this step now
)


class SyncOperation(Base, IdMixin):
    __tablename__ = "sync_operation"
    __table_args__ = (
        # THE idempotency guarantee: one outcome per client operation.
        UniqueConstraint("tenant_id", "operation_id", name="uq_sync_operation_id"),
        Index("ix_sync_operation_reference", "tenant_id", "client_reference"),
        Index("ix_sync_operation_monitor", "tenant_id", "status", "created_at"),
        Index("ix_sync_operation_device", "tenant_id", "device_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    device_id: Mapped[str] = mapped_column(String(80), default="")
    operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    kind: Mapped[str] = mapped_column(String(40))
    sequence: Mapped[int] = mapped_column(default=0)
    # The device's local id for the entity this operation CREATES (if any).
    client_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # The local-or-server id of the entity this operation acts ON.
    target_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(12), default="applied", index=True)
    applied: Mapped[bool] = mapped_column(default=False)
    server_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    conflict_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    conflict_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(default=1)

    # When the operator actually did this, on the device — the business time,
    # which can be hours before the platform ever hears about it.
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
