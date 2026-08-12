"""Delivery module — milk leaving the organization for a customer.

DEMO-009 / CAP-0006 CMA.DST.01 (Distribution & Fulfillment).

The mirror of `milk_collection`, and deliberately not the same table. A
collection is milk arriving from a supplier with a quality reading that decides
its price; a delivery is milk leaving for a customer at an agreed rate. They
share a shape and nothing else — one is a payable, the other a receivable.

The money rule is the platform's: `amount` is computed once, in `Decimal`, by
the domain, and stored. Nothing downstream recomputes it, and no client sends
it.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

#: Households take milk once or twice a day, and a dairy that could not record
#: both would lose half its round. The slot is part of a delivery's identity.
DELIVERY_SLOTS = ("morning", "evening")

DELIVERY_STATUSES = (
    "delivered",  # milk handed over — the normal case, and billable
    "skipped",  # customer away or declined; nothing delivered, nothing billed
    "returned",  # delivered then returned (spoiled, wrong product); not billed
    "cancelled",  # recorded in error
)

#: Only a delivery that actually happened is worth money.
BILLABLE_STATUSES = ("delivered",)


class MilkDelivery(Base, IdMixin):
    __tablename__ = "milk_delivery"
    __table_args__ = (
        # One delivery per customer, per day, per slot. A dairy round visits
        # once in the morning and once in the evening; a second morning
        # delivery to the same customer is a correction, not another sale, and
        # would double the bill if it were allowed to be both.
        UniqueConstraint(
            "tenant_id",
            "customer_id",
            "delivery_date",
            "slot",
            name="uq_delivery_customer_date_slot",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    delivery_date: Mapped[date] = mapped_column(Date, index=True)
    slot: Mapped[str] = mapped_column(String(10), default="morning")

    product: Mapped[str] = mapped_column(String(40), default="RAW-COW-MILK")
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    quantity_unit: Mapped[str] = mapped_column(String(8), default="L")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    #: quantity multiplied by unit_price, computed by the domain in Decimal
    #: and stored. Nothing downstream recomputes it.
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))

    status: Mapped[str] = mapped_column(String(16), default="delivered", index=True)
    notes: Mapped[str] = mapped_column(String(300), default="")
    #: Which delivery plan priced it, so a rate can be explained later even
    #: after the plan is superseded.
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    #: Set once the delivery has been billed. A billed delivery is frozen:
    #: changing it would change an invoice that has already been issued.
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)

    recorded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
