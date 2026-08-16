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
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

#: The states this platform can actually tell the truth about.
#:
#: `past_due` was ABSENT in DEMO-026 and is present now, and the reason it
#: changed is the whole point of DEMO-027. It means "a payment attempt failed",
#: and in DEMO-026 nothing could know that — there was no provider, so the
#: column would have been a state the platform could set and never verify.
#: There is now a verified provider boundary: `past_due` is reachable ONLY from
#: a signature-verified renewal failure, never from a client and never from a
#: timer. With no gateway contracted on this deployment, the only provider that
#: can drive it today is the TEST provider, which is refused in production —
#: so the state is honest, and its production reachability arrives with the
#: gateway, not with this milestone.
SUBSCRIPTION_STATUSES = (
    "trialing",  # inside the 30-day trial window
    "active",  # a paid subscription, confirmed by the provider
    "past_due",  # a renewal the provider says failed; access continues to grace end
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
    #:
    #: `current_period_end` is also the NEXT RENEWAL date: one field, because
    #: two ("period end" and "renews on") would be two chances to disagree
    #: about the same day. Where the provider runs the recurrence, this is the
    #: platform's record of what the provider said, not a schedule it drives.
    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: DEMO-027. How long access survives a renewal the provider says failed.
    #:
    #: Set when the subscription enters `past_due`, cleared when a later
    #: payment succeeds. A dairy whose card expired keeps collecting milk while
    #: somebody sorts it out — cutting off a working dairy the same hour a bank
    #: declined a renewal would be a worse product than not selling one.
    grace_ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)

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


#: What a subscription payment can be. Four states, and each one is something a
#: provider can actually report.
#:
#: `refunded` is deliberately ABSENT, for the reason DEMO-026 left `past_due`
#: out: no contracted gateway means nothing can confirm a refund, and a status
#: the platform can set but never verify is exactly the fake payment state the
#: work orders forbid. It arrives with the provider that can report it, and the
#: `subscription_payment_event` ledger is already shaped to receive it.
PAYMENT_STATUSES = ("pending", "succeeded", "failed", "cancelled")

#: Marker held in `open_key` while a payment is awaiting the provider.
#:
#: The unique constraint is `(tenant_id, open_key)`, and NULL does not collide
#: with NULL in either PostgreSQL or SQLite — so one open intent per
#: organization is enforced by the DATABASE while any number of settled ones
#: coexist. That is the whole of the duplicate-checkout prevention; a
#: check-then-act in Python would leave exactly the gap a constraint closes.
OPEN = "open"


class SubscriptionPayment(Base, IdMixin):
    """One attempt to pay Lacteva for a subscription (DEMO-027).

    **This is a PLATFORM COMMERCIAL record and not the dairy's ledger.** It is
    deliberately not in `modules/payment/`, which is the operational engine
    paying farmers against finalized settlements. A dairy's money and Lacteva's
    money share a word and nothing else: mixing them would put a SaaS invoice
    into a farmer's settlement history, and no amount of later filtering makes
    that recoverable.

    The amount is **written by the server from the plan price and the centre
    count**, never accepted from a client, and re-checked against what the
    provider says was actually charged before anything is activated.
    """

    __tablename__ = "subscription_payment"
    __table_args__ = (
        # One OPEN payment per organization. See `OPEN`.
        UniqueConstraint("tenant_id", "open_key", name="uq_subscription_payment_open"),
        # The webhook's only safe way in: a provider reference identifies the
        # payment, and the payment carries the tenant. Unique per provider, so
        # a second gateway cannot collide with the first.
        UniqueConstraint(
            "provider", "provider_reference", name="uq_subscription_payment_provider_ref"
        ),
        Index("ix_subscription_payment_tenant_created", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)

    plan_code: Mapped[str] = mapped_column(String(40))
    #: What was quoted, kept beside the amount so a historical payment can
    #: always be explained: unit price times quantity, in the currency of the day.
    #: A price that changes later must not silently rewrite what somebody paid.
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    quantity: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency_code: Mapped[str] = mapped_column(String(3))

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    open_key: Mapped[str | None] = mapped_column(String(8), nullable=True, default=OPEN)

    provider: Mapped[str] = mapped_column(String(40))
    #: The gateway's own id for this payment. Null only in the instant between
    #: reserving our row and the provider answering — which is the right order,
    #: because a row that exists before the call is a row that can be
    #: reconciled if the call is lost.
    provider_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    failure_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SubscriptionPaymentEvent(Base, IdMixin):
    """Every provider notification this platform has already acted on.

    **The replay defence, and it is a unique constraint rather than a check.**
    A provider retrying a delivery it is not sure landed is normal operation,
    not an attack — every gateway does it — so the second delivery must do
    nothing at all rather than activate a subscription twice or extend a period
    that was already extended.

    Stored cross-tenant on purpose: a webhook arrives before the platform knows
    whose it is, and the tenant is resolved from the PAYMENT the reference
    names, never from the payload. `tenant_id` is filled in once that lookup
    succeeds, which is also what makes this table tenant-owned for RLS.
    """

    __tablename__ = "subscription_payment_event"
    __table_args__ = (
        # The replay key. A provider's event id is unique per provider.
        UniqueConstraint("provider", "event_id", name="uq_subscription_payment_event"),
        Index("ix_subscription_payment_event_payment", "payment_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    provider: Mapped[str] = mapped_column(String(40))
    event_id: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(60))
    #: What the platform DID about it, so an operator reading this table can
    #: tell "acted on" from "recognised and correctly ignored".
    outcome: Mapped[str] = mapped_column(String(40))

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
