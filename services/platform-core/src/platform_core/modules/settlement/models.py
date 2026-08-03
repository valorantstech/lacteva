"""Settlement module — persistence models (SET-001: Settlement Foundation).

A Settlement is the payable amount owed to a supplier for one or more
pricing calculations over a period. LIFECYCLE ONLY (SET-001 wall): no
payment, bank transfer, bonus, penalty, tax, accounting, invoice, or
receipt concepts exist here — those are later increments.

Money columns are Numeric (the PRC-004 precision policy applies to new
schema): amounts are stored and summed as exact decimals.

Aggregate: Settlement owns its SettlementLines (real foreign key inside
the aggregate). Cross-module references (supplier, center, calculation,
transaction) are plain UUIDs, per the module-boundary rule.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

SETTLEMENT_STATUSES = ("draft", "calculated", "finalized", "cancelled")


class Settlement(Base, IdMixin):
    __tablename__ = "settlement"
    __table_args__ = (
        UniqueConstraint("tenant_id", "settlement_number", name="uq_settlement_number"),
        # Serves the supplier+period overlap rule (BR-0009) and period search.
        Index("ix_settlement_supplier_period", "tenant_id", "supplier_id", "period_from"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    settlement_number: Mapped[str] = mapped_column(String(30))
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))  # ISO 4217
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    # Placeholder until the bonus/penalty/tax engines land — always 0 in SET-001.
    adjustments_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SettlementLine(Base, IdMixin):
    """One settled pricing calculation. Amounts are copied from the verified
    calculation record at add time and never recomputed (the trace_reference
    points back to the durable pricing.calculated.v1 event)."""

    __tablename__ = "settlement_line"
    __table_args__ = (
        UniqueConstraint("settlement_id", "calculation_id", name="uq_settlement_line_calc"),
        UniqueConstraint("settlement_id", "transaction_id", name="uq_settlement_line_tx"),
    )

    settlement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("settlement.id"), index=True)
    calculation_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    transaction_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    quantity_unit: Mapped[str] = mapped_column(String(20), default="kg")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    trace_reference: Mapped[uuid.UUID] = mapped_column(Uuid)  # outbox event id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
