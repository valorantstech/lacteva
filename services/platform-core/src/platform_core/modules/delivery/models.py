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
    "scheduled",  # generated from a standing order; not yet been anywhere
    "delivered",  # milk handed over — the normal case, and billable
    "skipped",  # customer away or declined; nothing delivered, nothing billed
    "returned",  # delivered then returned (spoiled, wrong product); not billed
    "cancelled",  # recorded in error
)

#: Only a delivery that actually happened is worth money.
#:
#: `scheduled` is deliberately absent, and that single omission is what makes
#: DEMO-016 safe to deploy. A generator that produced BILLABLE rows would
#: invoice a dairy's whole round every morning whether the milk arrived or not
#: — so a generated delivery is worth 0.00 until somebody says it happened,
#: and every report, balance and invoice already filters on this tuple.
BILLABLE_STATUSES = ("delivered",)

#: A delivery that has been generated and not yet acted on. Recording over one
#: of these FILLS IT IN rather than colliding with it (see `DeliveryService.
#: record`), which is what lets an operator work without knowing or caring
#: whether the round was typed or generated.
PENDING_STATUSES = ("scheduled",)


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
    #: ISO 4217. NO DEFAULT, deliberately (DEMO-013): it was `"KES"`, which
    #: meant a code path that forgot to pass a currency minted Kenyan
    #: shillings in an Indian dairy and said nothing. Every construction
    #: supplies it from the customer, which gets it from the organization.
    currency: Mapped[str] = mapped_column(String(3))
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


#: What a scheduler run can be. Deliberately three states and not a workflow:
#: this is a record of what happened, not a job to be managed (DEMO-017 §5).
RUN_STATUSES = ("running", "success", "failed")

#: How many times the scheduler retries a failed day before leaving it alone.
#: Three, because the failures worth retrying are transient — a database
#: restarting, a deploy rolling — and a fourth attempt on the same day means
#: something is broken that retrying will not fix. After that the row stays
#: `failed` and visible, and a person decides.
MAX_ATTEMPTS = 3


class DeliveryGenerationRun(Base, IdMixin):
    """One tenant's attempt at one business date's round (DEMO-017 §5).

    **The unique constraint is the second idempotency guard.** The first is
    `uq_delivery_customer_date_slot`, which makes duplicate DELIVERIES
    impossible; this one makes duplicate WORK unlikely, so a scheduler that
    wakes every minute does not re-run a completed round sixty times an hour
    just to have the database refuse every insert.

    They are different guarantees and the platform needs both: without the
    delivery constraint two concurrent runs would duplicate milk, and without
    this one the log would be unreadable and the load pointless. The delivery
    constraint is the one that is load-bearing for correctness — this one is
    for sanity.

    One row per tenant per business date, updated in place across retries, so
    `attempts` tells an operator whether a green day was green first time.
    """

    __tablename__ = "delivery_generation_run"
    __table_args__ = (
        UniqueConstraint("tenant_id", "business_date", name="uq_generation_run_tenant_date"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    #: The DAIRY's date, not UTC's. Two tenants running the same instant can
    #: legitimately hold different dates here, and that is the point.
    business_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    #: How the run was started: `scheduler` or `manual`. Both go through the
    #: same service; this only records who asked.
    trigger: Mapped[str] = mapped_column(String(16), default="scheduler")

    plans_due: Mapped[int] = mapped_column(default=0)
    created: Mapped[int] = mapped_column(default=0)
    already_present: Mapped[int] = mapped_column(default=0)
    not_due: Mapped[int] = mapped_column(default=0)
    inactive_customers: Mapped[int] = mapped_column(default=0)

    attempts: Mapped[int] = mapped_column(default=1)
    #: Truncated: an operator needs to know WHAT broke, and the stack trace is
    #: in the logs where it belongs. A column that can hold a megabyte of
    #: traceback becomes one that does.
    error: Mapped[str] = mapped_column(String(500), default="")

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(default=0)
