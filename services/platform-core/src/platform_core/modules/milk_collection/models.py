"""Milk Collection module — persistence models.

The MilkCollectionTransaction is the first core dairy record: one attempt by
a supplier to deliver milk during an ACTIVE collection session. Completed
transactions are IMMUTABLE — the snapshot row is the frozen source of truth
for future pricing, settlement, inventory, analytics, and AI. Corrections
are future Adjustment Transactions; nothing here is ever overwritten.

CollectionSession is deliberately minimal (open/close). The full shift
engine (PSP-0003…0006: opening checks, reconciliation, variance) will
extend it — this table is its forward-compatible seed.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

SESSION_STATUSES = ("open", "closed")

TRANSACTION_STATES = (
    "NEW",
    "SUPPLIER_IDENTIFIED",
    "MILK_RECEIVED",
    "WEIGHT_CAPTURED",
    "QUALITY_PENDING",
    "QUALITY_CAPTURED",
    "PRICING_PENDING",
    "PRICED",
    "ACCEPTED",
    "REJECTED",
    "COMPLETED",
    "CANCELLED",
)
TERMINAL_STATES = ("COMPLETED", "CANCELLED")
MILK_TYPES = ("cow", "buffalo", "goat", "mixed", "custom")
#: How a measurement was obtained (WO-49; hardware spec §5, §7).
#:
#: `scale` and `analyzer` are REAL instruments reporting through a registered
#: device. They sit beside `manual`, which stays first-class and is the default
#: — a manual reading at an instrumented centre is not an error, it is recorded
#: as manual so the shift record shows it (spec §7).
#:
#: The `mock_*` values are NOT joined by these. A mock stays production-refused
#: by two independent guards, permanently, and a real adapter never reuses a
#: mock name (spec §14). FINAL-001 is why: a SHA-256 of a container id was
#: priced, settled and paid.
CAPTURE_SOURCES = ("manual", "scale", "analyzer", "mock_scale", "mock_analyzer")

#: An instrument source names the device CATEGORY that may produce it. A
#: reading attributed to an instrument with no registered device behind it is
#: an unattributed claim wearing a device's name, which is the failure
#: provenance exists to prevent — so the mapping is also the guard.
INSTRUMENT_SOURCES = {"scale": "scale", "analyzer": "milk_analyzer"}


class CollectionSession(Base, IdMixin):
    __tablename__ = "collection_session"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)
    label: Mapped[str] = mapped_column(String(40), default="")  # e.g. "morning"
    opened_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MilkCollectionTransaction(Base, IdMixin):
    __tablename__ = "milk_collection_transaction"
    # P0-BIZ-003: one slip number per transaction, per tenant. NULLs do not
    # collide (both engines), so pre-slip history and in-flight transactions
    # coexist with the constraint.
    __table_args__ = (UniqueConstraint("tenant_id", "slip_number", name="uq_milk_tx_slip"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    state: Mapped[str] = mapped_column(String(24), default="NEW", index=True)

    # Milk information (MILK_RECEIVED)
    milk_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    milk_type_custom: Mapped[str | None] = mapped_column(String(60), nullable=True)
    container_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    container_identifier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    arrival_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Weight (WEIGHT_CAPTURED)
    weight_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "kg"
    gross_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    tare_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_source: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Quality (QUALITY_CAPTURED) — raw readings only; no derived calculations yet
    fat: Mapped[float | None] = mapped_column(Float, nullable=True)
    snf: Mapped[float | None] = mapped_column(Float, nullable=True)
    clr: Mapped[float | None] = mapped_column(Float, nullable=True)
    density: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_remarks: Mapped[str] = mapped_column(String(300), default="")
    quality_source: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Pricing (wired to the Pricing Platform in MVP-001: resolution +
    # calculator run at the pricing step; amounts are copies of the verified
    # calculation, Numeric per the money precision policy)
    pricing_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    gross_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    calculation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    pricing_detail: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # BR-0029. An authorized rate override.
    #
    # `unit_price` stays the EFFECTIVE rate — the number the dairy agreed to
    # pay — so settlement, the parchi and every report consume the override
    # without knowing one happened, and no consumer can accidentally settle on
    # a rate that was superseded. The resolved rate moves here instead of being
    # overwritten, because a departure that erases what it departed from is
    # indistinguishable from an error.
    base_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    overridden_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Decision (ACCEPTED / REJECTED)
    rejected_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cancelled_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # P0-BIZ-003: the parchi's human-readable number (SLP-2026-000001), minted
    # from the shared per-tenant-year document series at completion. NULL means
    # the transaction completed before slips existed — the slip endpoint mints
    # lazily on first read, so history gets numbers without a data migration.
    slip_number: Mapped[str | None] = mapped_column(String(30), nullable=True)


class TransactionEvent(Base, IdMixin):
    """Append-only per-transaction event log (ordered by sequence)."""

    __tablename__ = "transaction_event"
    __table_args__ = (UniqueConstraint("transaction_id", "sequence", name="uq_txevent_tx_seq"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(40))  # e.g. WeightCaptured
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TransactionSnapshot(Base, IdMixin):
    """Immutable full-state snapshot written exactly once at completion."""

    __tablename__ = "transaction_snapshot"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TransactionMetrics(Base, IdMixin):
    """Denormalized timing/actor metrics written at completion (analytics seed)."""

    __tablename__ = "transaction_metrics"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float] = mapped_column(Float)
    final_state: Mapped[str] = mapped_column(String(24))
