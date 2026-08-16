"""What a dairy is commercially entitled to (DEMO-026).

One table. A subscription belongs to an organization, names a plan, holds a
status and the dates that status is derived from, and carries the fields a
payment provider will one day need.

**It is commercial metadata, not the dairy's ledger.** Nothing here is money
the dairy has collected or owes a farmer; nothing here appears on a settlement
or an invoice. That separation is why this module may be added to a running
platform without touching a single financial record.

**`tenant_id` is UNIQUE**, and that constraint is the whole of the duplicate
prevention the work order asks for. A double signup, a retried worker, two
concurrent requests and a refreshed browser all end at the same insert, and the
database decides. A check-then-act in Python would leave the gap that a
constraint closes — the lesson DEMO-025 learned when its savepoint sat in the
wrong place.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

#: The states this platform can actually tell the truth about.
#:
#: `past_due` is deliberately ABSENT. It means "a payment attempt failed", and
#: nothing here can know that: there is no payment provider, so a `past_due`
#: column would be a state the platform could set and never verify. The work
#: order asks for no fake payment states and this is the one it would have
#: been. It arrives with the provider that can report it.
SUBSCRIPTION_STATUSES = (
    "trialing",  # inside the 30-day trial window
    "active",  # a paid subscription somebody activated deliberately
    "cancelled",  # ended by the customer or by us; access follows `expired` rules
    "expired",  # the trial ran out, or a paid period ended without renewal
)


class Subscription(Base, IdMixin):
    """One organization's commercial standing."""

    __tablename__ = "subscription"
    __table_args__ = (
        # One subscription per organization. See the module docstring: this is
        # the duplicate prevention, not a Python check.
        UniqueConstraint("tenant_id", name="uq_subscription_tenant"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    plan_code: Mapped[str] = mapped_column(String(40), default="LACTEVA_TRIAL")
    status: Mapped[str] = mapped_column(String(16), default="trialing", index=True)

    #: BUSINESS dates on the organization's own clock, not UTC timestamps.
    #:
    #: A trial is counted in the dairy's days, so a Kenyan cooperative that
    #: signs up at 23:30 local does not lose its first day to a UTC date that
    #: has not turned over yet. Stored rather than recomputed, so the window
    #: cannot drift if the organization's timezone is later corrected — the
    #: trial a dairy was given is a fact about what it was given.
    trial_started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    trial_ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: Set when a paid subscription begins and ends. Null throughout a trial.
    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: How many collection centres this subscription pays for. The commercial
    #: model is per centre — never per user, which would teach a dairy to share
    #: logins and destroy the audit trail, and never per litre, which is the
    #: number a dairy negotiates hardest and would make the bill seasonal.
    subscribed_centres: Mapped[int] = mapped_column(Integer, default=0)

    #: Payment-provider readiness. All null, all unused, and deliberately
    #: opaque strings: the business domain must not learn the shape of any
    #: one vendor's identifiers. Nothing in the platform writes these yet.
    payment_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    external_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_price_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
