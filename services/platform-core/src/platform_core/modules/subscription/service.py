"""Trial, subscription and entitlement (DEMO-026).

**One place decides whether an organization may commercially use Lacteva.** No
other module asks "is the trial still running?" — they ask this service, or
they ask nothing.

The distinction the work order draws, and the reason it matters:

    PERMISSION   — *who* may do this?          `authz`, unchanged
    ENTITLEMENT  — *may this organization*     here
                   do it at all, commercially?

Mixing them produces the failure where a dairy's own administrator is told they
lack permission when what actually happened is that a trial ended. Those need
different messages and different remedies.

**The trial is counted in the dairy's own days.** `business_date_of` converts
the organization's authoritative creation instant to a date on its own clock,
so a Kenyan cooperative signing up at 23:30 local is not charged a day it never
had. The dates are then STORED, so nothing recomputes and nothing drifts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.business_time import business_date_of, business_today
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.modules.subscription.models import Subscription
from platform_core.modules.subscription.plans import (
    UNLIMITED,
    get_plan,
    price_config_key,
)

#: How long a new organization may use Lacteva for nothing.
#:
#: Thirty DAYS on the dairy's calendar, not 720 hours: a trial that ended
#: mid-afternoon because of an hours calculation would be a support ticket in
#: every timezone that is not UTC.
TRIAL_DAYS = 30


# --- DTOs ---------------------------------------------------------------------


class SubscriptionView(BaseModel):
    plan_code: str
    plan_name: str
    status: str
    trial_started_on: date | None = None
    trial_ends_on: date | None = None
    started_on: date | None = None
    current_period_end: date | None = None
    subscribed_centres: int
    billing_period: str
    currency_code: str
    #: What the plan costs in this organization's currency, if a deployment
    #: has decided. `None` means nobody has set a price, which is the honest
    #: answer rather than a zero.
    price: str | None = None


class EntitlementView(BaseModel):
    """Everything an operator or a screen needs to know, in one answer."""

    status: str
    business_date: date
    #: Days left of the trial. Negative once it has ended, so a screen can say
    #: "ended 3 days ago" without a second call.
    trial_days_remaining: int | None = None
    #: May this organization still create new operational work?
    can_operate: bool
    #: May it still READ what it already has? Always true — see `expired`
    #: handling in `entitlement()`.
    can_read: bool
    active_centres: int
    subscribed_centres: int
    #: `None` when the plan does not limit centres (the trial).
    centre_allowance: int | None = None
    within_centre_allowance: bool
    #: DEMO-027. When a `past_due` subscription stops operating, and when the
    #: current paid period ends. Both null unless they apply — a screen should
    #: be able to say WHEN without a second call and without arithmetic of its
    #: own, because a date computed in a browser is computed in the browser's
    #: timezone.
    grace_ends_on: date | None = None
    current_period_end: date | None = None


@dataclass(frozen=True)
class Entitlement:
    """The internal answer other modules guard on."""

    status: str
    can_operate: bool
    centre_allowance: int | None
    active_centres: int


# --- the service --------------------------------------------------------------


class SubscriptionService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    # --- creation -------------------------------------------------------------

    async def ensure_trial(self, *, created_at=None, timezone: str | None = None) -> Subscription:
        """The organization's subscription, creating its trial if it has none.

        **Get-or-create, and idempotent by database constraint.** Called at
        organization creation and again lazily by every read, so an
        organization that predates this milestone acquires its trial the first
        time anyone looks — counted from ITS OWN creation date, not from the
        day the feature shipped. No data migration, and no organization
        silently without a subscription.

        The trial cannot restart. A second call finds the existing row and
        returns it, so logging in again, adding a user, adding a centre or
        restarting the platform all leave the dates exactly where they were.
        """
        existing = await self._get()
        if existing is not None:
            return existing

        org = await self._organization()
        start = business_date_of(created_at or org.created_at, timezone or org.timezone)
        subscription = Subscription(
            tenant_id=self._tenant_id,
            plan_code="LACTEVA_TRIAL",
            status="trialing",
            trial_started_on=start,
            trial_ends_on=start + timedelta(days=TRIAL_DAYS),
            subscribed_centres=0,
        )
        try:
            # The `add` sits INSIDE the savepoint: entering `begin_nested()`
            # can autoflush a pending insert first, which would put the
            # violation outside the savepoint and poison the transaction.
            # DEMO-025 shipped that bug and real PostgreSQL found it.
            async with self._session.begin_nested():
                self._session.add(subscription)
                await self._session.flush()
        except IntegrityError:
            # Another writer won. That is the correct outcome, not an error:
            # the organization has exactly one subscription and this is it.
            found = await self._get()
            if found is None:  # pragma: no cover - the row must exist by now
                raise
            return found
        return subscription

    # --- reading --------------------------------------------------------------

    async def entitlement(self) -> Entitlement:
        """**The one authoritative commercial decision.**

        Derived from stored dates and the organization's own clock, never from
        anything a client sent. A browser cannot move a status: there is no
        input to this function.

        `can_operate` is false once a trial or paid period has ended, and
        `can_read` is not modelled at all because it is never false. An expired
        dairy keeps every collection, settlement, invoice and receipt it has,
        and keeps being able to read them. Taking a dairy's own records away
        for a commercial reason would be a worse product than not selling one.
        """
        subscription = await self.ensure_trial()
        org = await self._organization()
        today = business_today(org.timezone)
        status = self._derive_status(subscription, today)

        plan = get_plan(subscription.plan_code)
        allowance = (
            None
            if plan.included_centres == UNLIMITED
            else max(plan.included_centres, subscription.subscribed_centres)
        )
        return Entitlement(
            status=status,
            # `past_due` OPERATES. That is the point of a grace period: the
            # subscription is in trouble, the dairy is not, and the platform
            # does not confuse the two.
            can_operate=status in ("trialing", "active", "past_due"),
            centre_allowance=allowance,
            active_centres=await self.active_centres(),
        )

    async def view(self) -> SubscriptionView:
        subscription = await self.ensure_trial()
        org = await self._organization()
        plan = get_plan(subscription.plan_code)
        status = self._derive_status(subscription, business_today(org.timezone))
        return SubscriptionView(
            plan_code=plan.code,
            plan_name=plan.name,
            status=status,
            trial_started_on=subscription.trial_started_on,
            trial_ends_on=subscription.trial_ends_on,
            started_on=subscription.started_on,
            current_period_end=subscription.current_period_end,
            subscribed_centres=subscription.subscribed_centres,
            billing_period=plan.billing_period,
            currency_code=org.currency_code,
            price=await self._price(plan.code, org.currency_code),
        )

    async def entitlement_view(self) -> EntitlementView:
        subscription = await self.ensure_trial()
        org = await self._organization()
        today = business_today(org.timezone)
        status = self._derive_status(subscription, today)
        entitlement = await self.entitlement()
        remaining = (
            (subscription.trial_ends_on - today).days
            if subscription.trial_ends_on is not None
            else None
        )
        return EntitlementView(
            status=status,
            business_date=today,
            trial_days_remaining=remaining,
            grace_ends_on=subscription.grace_ends_on,
            current_period_end=subscription.current_period_end,
            can_operate=entitlement.can_operate,
            can_read=True,
            active_centres=entitlement.active_centres,
            subscribed_centres=subscription.subscribed_centres,
            centre_allowance=entitlement.centre_allowance,
            within_centre_allowance=(
                entitlement.centre_allowance is None
                or entitlement.active_centres <= entitlement.centre_allowance
            ),
        )

    async def active_centres(self) -> int:
        """Operational centres — the quantity the commercial model prices.

        `active` only. A centre in maintenance or archived is not doing work
        and should not be billed for, and counting it would make the bill move
        for an operational reason nobody connected to money.
        """
        from platform_core.modules.collection_center.models import CollectionCenter

        return (
            await self._session.scalar(
                select(func.count())
                .select_from(CollectionCenter)
                .where(
                    CollectionCenter.tenant_id == self._tenant_id,
                    CollectionCenter.status == "active",
                )
            )
        ) or 0

    # --- administration -------------------------------------------------------

    async def activate(
        self, *, plan_code: str, subscribed_centres: int, period_end: date | None = None
    ) -> SubscriptionView:
        """Put an organization onto a paid plan.

        **Server-authoritative and deliberately not self-service.** Nothing a
        browser sends decides this; it is an operator action behind its own
        permission, because until a payment provider exists the only truthful
        way to become `active` is for somebody at Lacteva to say so.
        """
        plan = get_plan(plan_code)
        if not plan.billable:
            raise ConflictError(f"{plan_code} cannot be subscribed to — it is the trial plan")
        if subscribed_centres < 1:
            raise ConflictError("a subscription must cover at least one collection centre")

        subscription = await self.ensure_trial()
        org = await self._organization()
        subscription.plan_code = plan.code
        subscription.status = "active"
        subscription.subscribed_centres = subscribed_centres
        subscription.started_on = business_today(org.timezone)
        subscription.current_period_end = period_end
        await self._session.flush()
        return await self.view()

    async def cancel(self) -> SubscriptionView:
        subscription = await self.ensure_trial()
        if subscription.status == "cancelled":
            raise ConflictError("the subscription is already cancelled")
        subscription.status = "cancelled"
        await self._session.flush()
        return await self.view()

    # --- the guard ------------------------------------------------------------

    async def assert_can_activate_centre(self) -> None:
        """May this organization put another centre into service?

        The one place a commercial limit touches operations, and it guards
        ACTIVATION rather than creation — a dairy may always record what it
        has; what it may not do is put more of it to work than it pays for.

        Nothing is refused during a trial: the commercial model is that
        everything is available while a dairy is evaluating, and meeting a wall
        you were never asked to pay past is how an evaluation ends badly.
        """
        entitlement = await self.entitlement()
        if not entitlement.can_operate:
            raise ConflictError(
                "this organization's subscription has ended — existing records "
                "remain readable; choose a subscription to activate a centre"
            )
        if entitlement.centre_allowance is None:
            return
        if entitlement.active_centres >= entitlement.centre_allowance:
            raise ConflictError(
                f"the subscription covers {entitlement.centre_allowance} collection "
                f"centre(s) and {entitlement.active_centres} are already active — "
                "subscribe for more centres to activate another"
            )

    # --- internals ------------------------------------------------------------

    @staticmethod
    def _derive_status(subscription: Subscription, today: date) -> str:
        """Status from stored dates. Never from a client, never stored stale.

        A `cancelled` subscription stays cancelled. Everything else is a
        question about a date, asked on the organization's own calendar.
        """
        if subscription.status == "cancelled":
            return "cancelled"
        if subscription.status == "past_due":
            # DEMO-027. A renewal the PROVIDER said failed. Access continues to
            # the end of the grace window and then stops — it does not stop the
            # hour a bank declined a card, because on the other side of that
            # decline is a dairy with milk arriving.
            grace = subscription.grace_ends_on
            return "expired" if grace is not None and today >= grace else "past_due"
        if subscription.status == "active":
            end = subscription.current_period_end
            return "expired" if end is not None and today >= end else "active"
        # Trialing. Exactly TRIAL_DAYS of access: the last day on which the
        # trial is still running is `trial_ends_on - 1`.
        if subscription.trial_ends_on is not None and today >= subscription.trial_ends_on:
            return "expired"
        return "trialing"

    async def _get(self) -> Subscription | None:
        return await self._session.scalar(
            select(Subscription).where(Subscription.tenant_id == self._tenant_id)
        )

    async def _organization(self):
        from platform_core.modules.organization.models import Organization

        org = await self._session.get(Organization, self._tenant_id)
        if org is None:
            raise NotFoundError("organization not found")
        return org

    async def _price(self, plan_code: str, currency_code: str) -> str | None:
        from platform_core.modules.audit.service import AuditService
        from platform_core.modules.configuration.service import ConfigurationService

        try:
            value = await ConfigurationService(self._session, AuditService(self._session)).resolve(
                price_config_key(plan_code, currency_code)
            )
        except Exception:
            return None
        return None if value is None else str(value)


__all__ = [
    "TRIAL_DAYS",
    "Entitlement",
    "EntitlementView",
    "SubscriptionService",
    "SubscriptionView",
]
