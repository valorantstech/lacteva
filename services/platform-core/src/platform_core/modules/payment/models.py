"""Payment module — persistence models (PAY-001: Payment Execution Engine).

A Payment is the actual movement (or attempted movement) of money against
one or more FINALIZED settlements. Payments CONSUME settlements; they never
modify them — a settlement is immutable once finalized (BR-0010), and the
payment aggregate owns everything payment-related on its own side.

Scope wall (PAY-001): payment methods are METADATA only. There is no
gateway client, no bank integration, no provider SDK, and no credential
handling anywhere in this module.

Money columns are Numeric per the PRC-004 precision policy (BR-0005).

Aggregate: Payment owns its PaymentLines (the allocation against each
settlement) and its PaymentAttempts (the execution history). Cross-module
references (supplier, settlement) are plain UUIDs per the boundary rule.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

PAYMENT_STATUSES = ("draft", "pending", "processing", "completed", "failed", "cancelled")

# Statuses whose allocations RESERVE part of a settlement's payable. A draft
# reserves too: it is an intent that must stop a second payment being built
# for the same money. Failure and cancellation release the reservation.
LIVE_STATUSES = ("draft", "pending", "processing", "completed")

PAYMENT_METHODS = ("BANK_TRANSFER", "CASH", "CHEQUE", "MOBILE_MONEY")

ATTEMPT_STATUSES = ("processing", "completed", "failed")


class Payment(Base, IdMixin):
    __tablename__ = "payment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "payment_number", name="uq_payment_number"),
        # Idempotent execution: re-posting the same key returns the first payment
        # instead of moving the money twice.
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_payment_idempotency"),
        Index("ix_payment_supplier", "tenant_id", "supplier_id", "status"),
        Index("ix_payment_history", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    # The payee. One payment pays one supplier; paying many suppliers is many
    # payments (see the PAY-001 report on why no PaymentBatch aggregate exists).
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    payment_number: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(3))  # ISO 4217
    method: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    # External reference: cheque number, bank transfer id, mobile money code.
    # Metadata the operator records — nothing here calls a provider.
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    method_details: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentLine(Base, IdMixin):
    """One allocation of this payment against one finalized settlement.

    The settlement number is copied at allocation time — finalized
    settlements are immutable, so the copy can never go stale, and the
    payment's own history stays readable without querying another module.
    """

    __tablename__ = "payment_line"
    __table_args__ = (
        UniqueConstraint("payment_id", "settlement_id", name="uq_payment_line_settlement"),
    )

    # SEC-002: denormalised from payment. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment.id"), index=True)
    settlement_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    settlement_number: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentAttempt(Base, IdMixin):
    """One execution attempt. Every retry creates a NEW attempt — the row is
    never reused, so the failure history of a payment survives its success."""

    __tablename__ = "payment_attempt"
    __table_args__ = (
        UniqueConstraint("payment_id", "attempt_number", name="uq_payment_attempt_number"),
    )

    # SEC-002: denormalised from payment. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment.id"), index=True)
    attempt_number: Mapped[int] = mapped_column()
    provider: Mapped[str] = mapped_column(String(40))
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="processing")
    operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
