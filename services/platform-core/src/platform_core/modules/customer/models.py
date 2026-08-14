"""Customer module — the people and businesses the organization SELLS to.

DEMO-009 / CAP-0006 CMA.SLS.02 (Buyer Relationship Management).

A customer is not a supplier. A supplier is somebody the organization receives
milk FROM and owes money TO; a customer is somebody the organization delivers
milk TO and is owed money BY. The two are mirror images, and modelling one as
the other would put a receivable in a payable's clothing — so this is a
separate bounded context with its own vocabulary, referenced elsewhere by UUID
like every other module.

What it deliberately does NOT hold: prices for products in general (CAP-0006
CMA.PRI.02), contracts (CMA.PRI.01), or credit scoring. A `DeliveryPlan`
carries the agreed rate for the one product this customer takes, which is what
a household or a tea shop actually has, and what the daily delivery needs to
price itself.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Index, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

#: What kind of buyer this is. Drives nothing in code today — it is reporting
#: and segmentation information, which is why it is a plain string and not a
#: behaviour switch.
CUSTOMER_TYPES = ("household", "shop", "hotel", "institution", "distributor")

CUSTOMER_STATUSES = ("active", "inactive", "suspended")

#: How a customer settles up. `prepaid` and `credit` differ only in whether an
#: invoice is expected to be paid before or after the milk arrives; the domain
#: treats both the same and reports the difference.
BILLING_MODES = ("credit", "prepaid")


class Customer(Base, IdMixin):
    __tablename__ = "customer"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_customer_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(200))
    customer_type: Mapped[str] = mapped_column(String(20), default="household")
    phone: Mapped[str] = mapped_column(String(32), default="")
    alternate_phone: Mapped[str] = mapped_column(String(32), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    #: Free text an operator writes for the next operator. Never parsed.
    notes: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)

    # --- billing -----------------------------------------------------------
    billing_mode: Mapped[str] = mapped_column(String(16), default="credit")
    #: Day of month the customer expects their bill. Reporting only — the
    #: invoice period is chosen when it is generated, not by this field.
    billing_day: Mapped[int] = mapped_column(default=1)
    #: ISO 4217. NO DEFAULT, deliberately (DEMO-013): it was `"KES"`, which
    #: meant a code path that forgot to pass a currency minted Kenyan
    #: shillings in an Indian dairy and said nothing. Every construction
    #: supplies it from the customer, which gets it from the organization.
    currency: Mapped[str] = mapped_column(String(3))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeliveryPlan(Base, IdMixin):
    """What this customer takes, and at what rate.

    The rate lives here rather than being resolved by the pricing engine, and
    that is a deliberate boundary. The pricing engine prices PROCUREMENT: it
    resolves a rate card by collection centre and quality band, because what a
    cooperative pays a farmer depends on the fat in the churn. What a customer
    pays is an agreed selling price for a product — a different mechanism
    (CAP-0006 CMA.PRI.02), and pushing it through the fat-band matrix would
    have produced a number nobody agreed to.

    One active plan per customer and product. Changing the rate supersedes the
    plan rather than editing it, so a delivery priced last week can still be
    explained.

    **DEMO-016 made it a standing order** by adding a schedule. Until then a
    plan said what a customer takes and at what price, and somebody still had
    to type six hundred deliveries a day. The schedule is the smallest thing
    that removes that:

        weekdays          a seven-character mask, Monday first
        effective_from    the plan already had one; still the first day
        effective_to      null means ongoing, which is the ordinary case
        paused_from/_to   one holiday window, because a household goes away
        quantity_overrides  optional per-weekday litres

    Deliberately NOT a scheduling engine. No recurrence rules, no calendars,
    no nth-weekday-of-the-month — the work order says so in as many words, and
    a dairy round is a weekly rhythm with holidays, not a cron expression.

    Superseding still applies, and it is what makes §8 true for free: editing a
    plan's schedule creates a new row and deactivates the old one, so
    yesterday's deliveries still point at the plan that generated them and no
    history is rewritten.
    """

    __tablename__ = "delivery_plan"
    __table_args__ = (
        # The generator's own query, and the only one that runs against every
        # plan a dairy has: "which active plans in this tenant are in date
        # today?" Tenant first because RLS filters on it before anything else,
        # then `active` because most of a mature dairy's plans are superseded
        # ones, then the date bounds.
        Index(
            "ix_delivery_plan_generation",
            "tenant_id",
            "active",
            "effective_from",
            "effective_to",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    product: Mapped[str] = mapped_column(String(40), default="RAW-COW-MILK")
    #: The standing daily quantity. A delivery may differ from it — this is
    #: what to expect, not what happened.
    default_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    quantity_unit: Mapped[str] = mapped_column(String(8), default="L")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    #: ISO 4217. NO DEFAULT, deliberately (DEMO-013): it was `"KES"`, which
    #: meant a code path that forgot to pass a currency minted Kenyan
    #: shillings in an Indian dairy and said nothing. Every construction
    #: supplies it from the customer, which gets it from the organization.
    currency: Mapped[str] = mapped_column(String(3))
    effective_from: Mapped[date] = mapped_column(Date)
    #: Null means ongoing. A dairy's standing order does not usually have an
    #: end; the ones that do are contracts and seasonal supplies.
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: Which days the round visits, Monday first: `"1111111"` is every day,
    #: `"1111110"` is Monday to Saturday, `"1111100"` is weekdays only.
    #:
    #: A string of seven characters rather than seven booleans or a bitmask.
    #: Seven columns is a schema change every time somebody wants a different
    #: question answered; a bitmask is unreadable in a psql session at 6am,
    #: when the question is "why did this household get no milk on Tuesday?".
    #: This is greppable, sorts, and reads correctly in a backup.
    weekdays: Mapped[str] = mapped_column(String(7), default="1111111")

    #: A holiday. Inclusive at both ends, and null when the plan is running.
    #: One window, not a list: two overlapping holidays is a calendar, and a
    #: calendar is the engine §3 says not to build. A second holiday is set by
    #: superseding the plan, like every other change.
    paused_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    paused_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: Per-weekday litres, keyed by the same Monday-first index as `weekdays`
    #: (`{"5": "30.000"}` is "thirty litres on Saturday"). Null — the ordinary
    #: case — means every delivery day takes `default_quantity`.
    #:
    #: Stored as JSON rather than six more columns because it is genuinely
    #: sparse: a hotel that takes more at the weekend sets one key, and every
    #: household sets none.
    quantity_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    #: Which centre serves this round, when a dairy runs more than one. Null
    #: means the organization at large, which is what every household means.
    center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)

    #: The slot this plan generates into. A customer taking milk twice a day
    #: has two plans, which is also how they have two rates if they need them.
    slot: Mapped[str] = mapped_column(String(10), default="morning")

    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
