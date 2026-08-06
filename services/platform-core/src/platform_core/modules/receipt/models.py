"""Receipt module — persistence models (RCP-001: Receipt Engine).

A Receipt is an immutable business artifact proving that a payment was made.
It is generated from a COMPLETED payment and never modifies the payment or
the settlements behind it — like a printed receipt, it records a fact that
already happened.

Immutability is the whole point (BR-0020): once generated, the content of a
receipt never changes. Only its lifecycle marker moves (generated ->
delivered -> archived), and archived receipts stay fully queryable. There is
no edit path and no delete path anywhere in this module.

Because the content is frozen, the receipt COPIES everything it shows —
supplier name, payment reference, settlement numbers, centers, amounts — at
generation time. Re-reading those later could show a different world; a
receipt must show the world as it was when the money moved.

Money columns are Numeric per the PRC-004 precision policy (BR-0005).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
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

RECEIPT_STATUSES = ("generated", "delivered", "archived")

# Rendering formats the engine can produce. PDF is a placeholder renderer —
# no external PDF service is integrated (RCP-001 scope wall).
RENDER_FORMATS = ("json", "html", "pdf")

DEFAULT_RENDER_FORMAT = "json"


class Receipt(Base, IdMixin):
    __tablename__ = "receipt"
    __table_args__ = (
        UniqueConstraint("tenant_id", "receipt_number", name="uq_receipt_number"),
        # One payment generates exactly one receipt — the duplicate guard that
        # makes generation idempotent under consumer replay.
        UniqueConstraint("tenant_id", "payment_id", name="uq_receipt_payment"),
        Index("ix_receipt_history", "tenant_id", "generated_at"),
        Index("ix_receipt_supplier", "tenant_id", "supplier_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    receipt_number: Mapped[str] = mapped_column(String(30))
    payment_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)

    # --- copied payee identity (frozen at generation) ---
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    supplier_name: Mapped[str] = mapped_column(String(200), default="")
    supplier_code: Mapped[str] = mapped_column(String(30), default="")

    # --- copied payment facts ---
    payment_number: Mapped[str] = mapped_column(String(30))
    payment_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(20))
    payment_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- money (BR-0005). net_amount is what was ACTUALLY PAID; gross and
    # adjustments describe the settlements this payment was made against, so a
    # partial payment shows net < gross - adjustments and the lines say why. ---
    currency: Mapped[str] = mapped_column(String(3))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    adjustments_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)

    status: Mapped[str] = mapped_column(String(12), default="generated", index=True)
    render_format: Mapped[str] = mapped_column(String(8), default=DEFAULT_RENDER_FORMAT)
    version: Mapped[int] = mapped_column(default=1)

    # --- trace: how to get back to the facts behind this artifact ---
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReceiptLine(Base, IdMixin):
    """One settlement covered by the receipt's payment.

    Carries both the settlement's own totals and the amount actually paid on
    this receipt, so a partial payment is self-explaining on the artifact.
    """

    __tablename__ = "receipt_line"
    __table_args__ = (
        UniqueConstraint("receipt_id", "settlement_id", name="uq_receipt_line_settlement"),
    )

    # SEC-002: denormalised from receipt. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receipt.id"), index=True)
    settlement_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    settlement_number: Mapped[str] = mapped_column(String(30))
    center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    period_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    adjustments_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
