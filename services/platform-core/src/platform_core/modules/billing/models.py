"""Billing module — what a customer owes, what they paid, and the proof.

DEMO-009. The receivable side of the business: the mirror of settlement →
payment → receipt, and deliberately NOT the same tables.

The direction is the whole reason. A settlement is what the organization OWES a
supplier and a payment is money going OUT; an invoice is what a customer owes
the organization and a customer payment is money coming IN. Reusing the
procurement tables would have produced a payment whose "supplier" is a
customer, and an outstanding balance that means the opposite of what it says.

What this is NOT: a general ledger. There are no accounts, no journals, no tax
engine and no revenue recognition. An invoice here is the statement a dairy
hands a household at the end of the month, and a payment is the money they hand
back. Production accounting is recorded as remaining work in DEMO-009-FINAL §14.

Immutability follows the platform's existing convention. An issued invoice
cannot be edited (the same rule BR-0010 applies to a finalized settlement) and
a receipt is generated from a recorded payment and never changes (BR-0020).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Numeric, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

INVOICE_STATUSES = (
    "draft",  # generated, still editable, not yet money owed
    "issued",  # given to the customer — immutable, payable
    "paid",  # fully settled by customer payments
    "cancelled",  # withdrawn before issue, or voided by adjustment
)

#: An invoice that the customer is expected to pay.
PAYABLE_INVOICE_STATUSES = ("issued", "paid")

PAYMENT_METHODS = ("CASH", "MOBILE_MONEY", "BANK_TRANSFER", "CHEQUE")

PAYMENT_STATUSES = ("recorded", "cancelled")


class CustomerInvoice(Base, IdMixin):
    """One customer, one billing period, one statement."""

    __tablename__ = "customer_invoice"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", name="uq_invoice_tenant_number"),
        # A customer gets ONE LIVE invoice per period. Two would each look
        # complete and together would double the bill.
        #
        # PARTIAL, excluding cancelled: a plain unique constraint would let a
        # cancelled invoice block its own period forever, so an operator who
        # cancelled a draft with the wrong dates could never re-issue it. The
        # application already refuses a live clash; this is the database
        # agreeing rather than over-reaching.
        Index(
            "uq_invoice_customer_period",
            "tenant_id",
            "customer_id",
            "period_from",
            "period_to",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
            sqlite_where=text("status <> 'cancelled'"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    invoice_number: Mapped[str] = mapped_column(String(32), index=True)
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="KES")

    #: Sum of the lines, computed by the domain in Decimal.
    subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    #: Fixed at zero until a discount/penalty mechanism exists, exactly as
    #: BR-0011 fixes settlement adjustments at zero — the arithmetic carries
    #: the term so the day it becomes real nothing has to move.
    adjustments: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    #: subtotal + adjustments.
    total: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    #: What the customer still owed when this invoice was generated — the
    #: dairy's "brought forward" line. Stored rather than derived so the
    #: statement reads the same a year later.
    previous_balance: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    #: total + previous_balance.
    amount_due: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))

    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    line_count: Mapped[int] = mapped_column(default=0)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerInvoiceLine(Base, IdMixin):
    """One delivery on one statement.

    The figures are COPIED from the delivery rather than joined at read time,
    for the same reason a settlement line copies its calculation: a statement
    handed to a customer must still say what it said, even if the delivery is
    later corrected.
    """

    __tablename__ = "customer_invoice_line"
    __table_args__ = (
        # A delivery appears on at most one invoice. The mirror of BR-0012.
        UniqueConstraint("tenant_id", "delivery_id", name="uq_invoice_line_delivery"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    delivery_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    delivery_date: Mapped[date] = mapped_column(Date)
    slot: Mapped[str] = mapped_column(String(10), default="morning")
    product: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    quantity_unit: Mapped[str] = mapped_column(String(8), default="L")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerPayment(Base, IdMixin):
    """Money RECEIVED from a customer.

    Unlike a supplier payment there is no provider to execute against and no
    attempt to retry: the money has already arrived when somebody records it.
    So the lifecycle is one step — recorded — and the only other state is
    cancelled, for an entry made in error. A correction is a new record, never
    an edit.
    """

    __tablename__ = "customer_payment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "payment_number", name="uq_customer_payment_number"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    payment_number: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    method: Mapped[str] = mapped_column(String(20), default="CASH")
    reference: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(16), default="recorded", index=True)
    notes: Mapped[str] = mapped_column(String(300), default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerPaymentAllocation(Base, IdMixin):
    """How much of a payment went against which invoice.

    A household pays 3,000 against a 3,500 bill and the rest next month; a
    shop pays one amount covering three months. Neither is expressible without
    allocations, and both are ordinary.
    """

    __tablename__ = "customer_payment_allocation"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    invoice_number: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerReceipt(Base, IdMixin):
    """Proof that a customer paid. Generated from the event, never on request.

    Mirrors BR-0020: a receipt exists because a payment was recorded, is
    produced by a consumer reading the durable log, and never changes.
    """

    __tablename__ = "customer_receipt"
    __table_args__ = (
        UniqueConstraint("tenant_id", "receipt_number", name="uq_customer_receipt_number"),
        # One receipt per payment. A second would be a second proof of the
        # same money.
        UniqueConstraint("tenant_id", "payment_id", name="uq_customer_receipt_payment"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    receipt_number: Mapped[str] = mapped_column(String(32), index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    payment_number: Mapped[str] = mapped_column(String(32))
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    customer_name: Mapped[str] = mapped_column(String(200), default="")
    customer_code: Mapped[str] = mapped_column(String(24), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    method: Mapped[str] = mapped_column(String(20), default="CASH")
    reference: Mapped[str] = mapped_column(String(80), default="")
    #: The invoices this money was applied to, as text, so the receipt is
    #: readable without joining anything.
    applied_to: Mapped[str] = mapped_column(String(300), default="")
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
