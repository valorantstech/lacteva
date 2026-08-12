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

from sqlalchemy import Boolean, Date, DateTime, Numeric, String, UniqueConstraint, Uuid
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
    currency: Mapped[str] = mapped_column(String(3), default="KES")

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
    """

    __tablename__ = "delivery_plan"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    product: Mapped[str] = mapped_column(String(40), default="RAW-COW-MILK")
    #: The standing daily quantity. A delivery may differ from it — this is
    #: what to expect, not what happened.
    default_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    quantity_unit: Mapped[str] = mapped_column(String(8), default="L")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    effective_from: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
