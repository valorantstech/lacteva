"""Sale items — the thing sold that is not a delivery (WO-81 · LACTEVA-SALES-001).

A household on the round sometimes takes a pot of dahi or a box of sweets with
its milk. The client's own month sheet records that as ONE rupee figure per
household — `other item: 160` — and this table is what lets that figure exist
on a bill beside the milk.

Why not a delivery: a delivery is priced from a STANDING ORDER and is unique
per (customer, date, slot, product), because the round visits once and a
second morning litre is a correction. A sale item has no plan behind it and
no uniqueness at all: two dahi on one day is two rows or one row with
quantity 2, and both are fine.

Priced from the catalogue's `default_price` at record time unless the command
carries a price of its own — which is a PERMISSION, not a field: the owner
may quote a household a different rate (`sales.item.price`); the delivery boy
may not, and records at the catalogue price (`sales.item.record`). A product
with no default price can only be sold at a typed price, so the driver cannot
sell it at all, and the app says so rather than writing a zero-rupee line.

`cancelled` releases the item from billing exactly as a cancelled delivery is
released; a billed item is frozen by its `invoice_id` exactly as a billed
delivery is.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

ITEM_STATUSES = ("recorded", "cancelled")

#: Only a recorded item is worth money — the mirror of `BILLABLE_STATUSES`.
BILLABLE_ITEM_STATUSES = ("recorded",)

RECORDED_VIA = ("portal", "mobile")


class SaleItem(Base, IdMixin):
    __tablename__ = "sale_items"
    __table_args__ = (
        # The phone replays. A queued item sent twice must exist once, and the
        # key is the client's, exactly as the run-outcome path already works.
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_sale_item_idempotency"),
        Index("ix_sale_item_customer_date", "tenant_id", "customer_id", "sale_date"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    sale_date: Mapped[date] = mapped_column(Date, index=True)
    product_code: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(8), default="pc")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    #: quantity times unit_price, computed once in Decimal at record time.
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    #: ISO 4217, from the customer's organisation. No default (DEMO-013).
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), default="recorded", index=True)
    notes: Mapped[str] = mapped_column(String(300), default="")
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    recorded_via: Mapped[str] = mapped_column(String(10), default="portal")
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: Set once billed; a billed item is frozen like a billed delivery.
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
