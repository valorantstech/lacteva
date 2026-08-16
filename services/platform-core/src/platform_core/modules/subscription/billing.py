"""Paying Lacteva for a subscription (DEMO-027).

A second service file in this module, for the reason the house style allows
one: `service.py` answers "what is this organization entitled to?", which every
request asks, and this answers "how does it become entitled?", which almost
none do. Splitting them keeps the hot path small.

**Three rules govern everything here.**

*The server owns the amount.* A client sends a plan and a centre count. It
never sends a price, never sends a total and never sends a currency — those
come from the plan registry, the configuration store and the organization the
country registry configured at onboarding. A browser that could name the amount
could name one rupee.

*The provider owns the confirmation.* Nothing activates a subscription except
an outcome the provider itself reported, and the platform re-asks the provider
rather than believing a payload it was handed. A signature proves who sent a
message; it does not prove what is true.

*A repeat is not a second event.* Every step is idempotent by database
constraint — one open payment per organization, one payment per provider
reference, one action per provider event id. A gateway retrying a delivery it
is unsure landed is normal operation, and it must do nothing the second time.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.business_time import business_today
from platform_core.core.db import utcnow
from platform_core.core.errors import ConflictError, NotFoundError, ValidationError
from platform_core.core.money import format_money, quantize_money
from platform_core.modules.subscription.models import (
    OPEN,
    SubscriptionPayment,
)
from platform_core.modules.subscription.plans import get_plan, price_config_key
from platform_core.modules.subscription.providers import (
    CheckoutRequest,
    PaymentOutcome,
    PaymentProviderError,
    PaymentProviderTimeout,
    PaymentProviderUnavailable,
    get_payment_provider,
)
from platform_core.modules.subscription.service import SubscriptionService

#: Wire names for the facts this module publishes. Consumers may or may not
#: exist; the outbox row is the durable record either way.
BUS_EVENTS = {
    "payment_succeeded": "subscription.payment-succeeded.v1",
    "payment_failed": "subscription.payment-failed.v1",
    "activated": "subscription.activated.v1",
    "renewed": "subscription.renewed.v1",
    "past_due": "subscription.past-due.v1",
}


# --- period arithmetic --------------------------------------------------------


def add_period(start: date, period: str) -> date:
    """One billing period after `start`, on the calendar rather than in days.

    A pure function, tested without I/O, and clamped at month ends: a
    subscription that starts on 31 January renews on 28 February, not on 3
    March. "Thirty days" would be wrong in a different way every month, and a
    dairy reading its own renewal date should recognise it.
    """
    if period == "year":
        try:
            return start.replace(year=start.year + 1)
        except ValueError:  # 29 February
            return start.replace(year=start.year + 1, day=28)
    if period != "month":
        raise ValueError(f"unknown billing period: {period}")
    year = start.year + (start.month // 12)
    month = start.month % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


# --- DTOs ---------------------------------------------------------------------


class QuoteView(BaseModel):
    """What a subscription would cost. **Calculated by the server, always.**"""

    plan_code: str
    plan_name: str
    currency_code: str
    #: Per collection centre, per billing period. `None` when no deployment has
    #: set a price — the honest answer, and checkout refuses rather than
    #: inventing one.
    unit_price: str | None = None
    quantity: int
    amount: str | None = None
    billing_period: str
    #: How many centres are actually active right now, so an administrator can
    #: see whether the quantity they chose covers their operation.
    active_centres: int
    #: Whether this deployment can take money at all.
    payable: bool
    payable_reason: str | None = None


class SubscriptionPaymentView(BaseModel):
    id: uuid.UUID
    plan_code: str
    unit_price: str
    quantity: int
    amount: str
    currency_code: str
    status: str
    provider: str
    #: Safe to show an administrator: it is the gateway's own public id for the
    #: transaction, which is what a support conversation needs. Never a key,
    #: never a signature, never a payload.
    provider_reference: str | None = None
    checkout_url: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


@dataclass(frozen=True)
class WebhookResult:
    """What the platform did about one provider notification."""

    outcome: str
    payment_id: uuid.UUID | None = None


# --- the service --------------------------------------------------------------


class SubscriptionBillingService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, bus=None) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._bus = bus
        self._subscriptions = SubscriptionService(session, tenant_id)

    # --- quoting --------------------------------------------------------------

    async def quote(self, *, plan_code: str, quantity: int) -> QuoteView:
        """Price a subscription without creating anything.

        `quantity` is a count of collection centres — the commercial model
        DEMO-026 established, and the one thing a client legitimately chooses.
        Everything that turns it into money happens here.
        """
        plan = self._plan(plan_code)
        if quantity < 1:
            raise ValidationError("a subscription must cover at least one collection centre")
        org = await self._organization()
        unit_price = await self._unit_price(plan.code, org.currency_code)
        payable_reason = await self._unpayable_reason(unit_price)
        return QuoteView(
            plan_code=plan.code,
            plan_name=plan.name,
            currency_code=org.currency_code,
            unit_price=(
                None if unit_price is None else format_money(unit_price, org.currency_code)
            ),
            quantity=quantity,
            amount=(
                None
                if unit_price is None
                else format_money(
                    self._amount(unit_price, quantity, org.currency_code), org.currency_code
                )
            ),
            billing_period=plan.billing_period,
            active_centres=await self._subscriptions.active_centres(),
            payable=payable_reason is None,
            payable_reason=payable_reason,
        )

    # --- checkout -------------------------------------------------------------

    async def start_checkout(self, *, plan_code: str, quantity: int) -> SubscriptionPaymentView:
        """Reserve a payment and ask the provider to open a checkout.

        **Order matters.** The row is written BEFORE the provider is called, so
        a call that is lost in the network leaves something to reconcile rather
        than money taken against no record. And `(tenant_id, open_key)` is
        unique, so two racing clicks reach one row and the database decides
        which — not a `SELECT` that was true a microsecond ago.
        """
        plan = self._plan(plan_code)
        if quantity < 1:
            raise ValidationError("a subscription must cover at least one collection centre")
        org = await self._organization()
        unit_price = await self._unit_price(plan.code, org.currency_code)
        reason = await self._unpayable_reason(unit_price)
        if reason is not None:
            raise ConflictError(reason)
        assert unit_price is not None  # narrowed by `_unpayable_reason`

        amount = self._amount(unit_price, quantity, org.currency_code)
        subscription = await self._subscriptions.ensure_trial()
        provider = get_payment_provider()

        existing = await self._open_payment()
        if existing is not None:
            # A repeat of the SAME request is the common case — a refreshed tab,
            # a double click, a retried mobile request — and it must return what
            # already exists rather than opening a second checkout.
            if (
                existing.plan_code == plan.code
                and existing.quantity == quantity
                and existing.amount == amount
            ):
                return self._view(existing)
            raise ConflictError(
                "a payment is already awaiting confirmation for this organization — "
                "cancel it before starting a different one"
            )

        payment = SubscriptionPayment(
            tenant_id=self._tenant_id,
            subscription_id=subscription.id,
            plan_code=plan.code,
            unit_price=unit_price,
            quantity=quantity,
            amount=amount,
            currency_code=org.currency_code,
            status="pending",
            open_key=OPEN,
            provider=provider.name,
        )
        try:
            # The `add` sits INSIDE the savepoint. Entering `begin_nested()` can
            # autoflush a pending insert first, which would put the violation
            # outside the savepoint and poison the transaction — the defect
            # DEMO-025 shipped and real PostgreSQL found.
            async with self._session.begin_nested():
                self._session.add(payment)
                await self._session.flush()
        except IntegrityError:
            found = await self._open_payment()
            if found is None:  # pragma: no cover - the row must exist by now
                raise
            return self._view(found)

        try:
            session = provider.create_checkout(
                CheckoutRequest(
                    reference=str(payment.id),
                    amount=amount,
                    currency=org.currency_code,
                    description=f"{plan.name} — {quantity} collection centre(s)",
                )
            )
        except PaymentProviderError as exc:
            # The reservation stays, marked failed and CLOSED, so the next
            # attempt is not blocked by a checkout that never opened.
            payment.status = "failed"
            payment.open_key = None
            payment.failure_code = type(exc).__name__
            payment.failure_message = str(exc)[:500]
            payment.completed_at = utcnow()
            await self._session.flush()
            raise ConflictError(str(exc)) from exc

        payment.provider_reference = session.provider_reference
        payment.checkout_url = session.checkout_url
        await self._session.flush()
        return self._view(payment)

    async def cancel_open_payment(self) -> SubscriptionPaymentView:
        """Abandon a checkout that was never completed.

        Only ever the organization's OWN open payment — there is no id to
        supply, so there is no id to guess.
        """
        payment = await self._open_payment()
        if payment is None:
            raise NotFoundError("no payment is awaiting confirmation")
        payment.status = "cancelled"
        payment.open_key = None
        payment.completed_at = utcnow()
        await self._session.flush()
        return self._view(payment)

    # --- server-side verification --------------------------------------------

    async def refresh_open_payment(self) -> SubscriptionPaymentView:
        """Ask the PROVIDER what happened, and act on the answer.

        This is what the success page calls. It deliberately takes no argument:
        a browser returning from a hosted checkout is a hint that something may
        have changed, not evidence of what — so it may say "look again" and
        nothing more. It cannot name a payment, an amount or a status.
        """
        payment = await self._open_payment()
        if payment is None:
            raise NotFoundError("no payment is awaiting confirmation")
        if payment.provider_reference is None:
            raise ConflictError("this payment never reached the provider")

        provider = get_payment_provider(payment.provider)
        try:
            outcome = provider.verify(payment.provider_reference)
        except PaymentProviderTimeout as exc:
            # UNKNOWN, not failed. Leaving it pending is the only safe answer:
            # the payment may well have succeeded, and marking it failed would
            # invite a second charge.
            raise ConflictError(f"the payment provider did not answer — try again ({exc})") from exc
        except PaymentProviderError as exc:
            raise ConflictError(str(exc)) from exc

        await self.apply_provider_outcome(payment, outcome, kind="payment")
        return self._view(payment)

    # --- history --------------------------------------------------------------

    async def history(self, *, limit: int = 50) -> list[SubscriptionPaymentView]:
        rows = (
            await self._session.scalars(
                select(SubscriptionPayment)
                .where(SubscriptionPayment.tenant_id == self._tenant_id)
                .order_by(SubscriptionPayment.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [self._view(row) for row in rows]

    # --- applying an outcome --------------------------------------------------

    async def apply_provider_outcome(
        self, payment: SubscriptionPayment, outcome: PaymentOutcome, *, kind: str
    ) -> str:
        """Move a payment to its terminal state and, if paid, activate.

        Public because the webhook boundary calls it — the same code path
        whether the confirmation arrived by webhook or by the platform asking.
        One activation routine, so the two cannot drift.

        **Every guard that matters is here**, and each one has refused in a
        test:

        * the amount the provider reports must equal the amount the platform
          asked for — a signed message with a changed number is still wrong;
        * the currency likewise;
        * the transition is a CAS `UPDATE ... WHERE status = 'pending'`, so the
          second caller in a race changes no rows and activates nothing.
        """
        if outcome.state == "pending":
            return "still_pending"

        if outcome.state == "succeeded":
            if outcome.amount is not None and outcome.amount != payment.amount:
                # Not an error to hide: record it, refuse to activate, and let
                # a human look. Silently accepting a smaller payment is how a
                # platform gives itself away.
                payment.failure_code = "amount_mismatch"
                payment.failure_message = (
                    f"provider reported {outcome.amount}, the platform asked for {payment.amount}"
                )
                await self._close(payment, "failed")
                await self._publish("payment_failed", payment)
                return "amount_mismatch"
            if outcome.currency is not None and outcome.currency != payment.currency_code:
                payment.failure_code = "currency_mismatch"
                payment.failure_message = (
                    f"provider reported {outcome.currency}, expected {payment.currency_code}"
                )
                await self._close(payment, "failed")
                await self._publish("payment_failed", payment)
                return "currency_mismatch"

            moved = await self._close(payment, "succeeded")
            if not moved:
                return "already_final"
            await self._activate(payment, outcome, renewal=kind == "renewal")
            await self._publish("payment_succeeded", payment)
            await self._publish("renewed" if kind == "renewal" else "activated", payment)
            return "activated"

        payment.failure_code = outcome.failure_code
        payment.failure_message = outcome.failure_message
        moved = await self._close(payment, "failed" if outcome.state == "failed" else "cancelled")
        if not moved:
            return "already_final"
        if kind == "renewal":
            await self._mark_past_due()
            await self._publish("past_due", payment)
        await self._publish("payment_failed", payment)
        return "failed"

    async def _close(self, payment: SubscriptionPayment, status: str) -> bool:
        """CAS out of `pending`. Returns False if somebody else already did.

        `UPDATE ... WHERE status = 'pending'` with a rowcount check, not
        `SELECT FOR UPDATE` — portable to the SQLite test stack, and the house
        pattern everywhere else in this platform.
        """
        result = await self._session.execute(
            update(SubscriptionPayment)
            .where(
                SubscriptionPayment.id == payment.id,
                SubscriptionPayment.status == "pending",
            )
            .values(
                status=status,
                open_key=None,
                completed_at=utcnow(),
                failure_code=payment.failure_code,
                failure_message=payment.failure_message,
            )
        )
        if result.rowcount == 0:
            return False
        await self._session.refresh(payment)
        return True

    async def _activate(
        self, payment: SubscriptionPayment, outcome: PaymentOutcome, *, renewal: bool
    ) -> None:
        """TRIALING (or PAST_DUE, or ACTIVE) becomes ACTIVE. Server-side, always.

        The period runs from the organization's own business date, so a dairy
        does not lose a day to a UTC clock — the same rule DEMO-026 applied to
        the trial, for the same reason.
        """
        subscription = await self._subscriptions.ensure_trial()
        org = await self._organization()
        plan = get_plan(payment.plan_code)
        today = business_today(org.timezone)

        # A renewal extends from the period that is ending, not from today, so
        # a late confirmation does not quietly shorten what was paid for.
        start = (
            subscription.current_period_end
            if renewal and subscription.current_period_end is not None
            else today
        )
        subscription.plan_code = plan.code
        subscription.status = "active"
        subscription.subscribed_centres = payment.quantity
        subscription.started_on = subscription.started_on or today
        subscription.current_period_end = add_period(start, plan.billing_period)
        subscription.grace_ends_on = None
        subscription.payment_provider = payment.provider
        subscription.external_customer_id = (
            outcome.external_customer_id or subscription.external_customer_id
        )
        subscription.external_subscription_id = (
            outcome.external_subscription_id or subscription.external_subscription_id
        )
        await self._session.flush()

    async def _mark_past_due(self) -> None:
        """A renewal the provider says failed. **Access continues.**

        Not expired, not cancelled, and nothing deleted: a dairy whose card was
        declined keeps collecting milk until the grace period ends, because the
        alternative is a working dairy stopped by a bank on a Tuesday.
        """
        from platform_core.core.config import get_settings

        subscription = await self._subscriptions.ensure_trial()
        if subscription.status != "active":
            return
        org = await self._organization()
        today = business_today(org.timezone)
        subscription.status = "past_due"
        subscription.grace_ends_on = today + timedelta(days=get_settings().subscription_grace_days)
        await self._session.flush()

    # --- internals ------------------------------------------------------------

    def _plan(self, plan_code: str):
        try:
            plan = get_plan(plan_code)
        except KeyError as exc:
            raise NotFoundError(f"unknown plan: {plan_code}") from exc
        if not plan.billable:
            raise ConflictError(f"{plan.code} cannot be paid for — it is the trial plan")
        return plan

    @staticmethod
    def _amount(unit_price: Decimal, quantity: int, currency: str) -> Decimal:
        """Per centre, times centres. Quantized by the platform's money rules.

        `quantize_money` rather than a local `Decimal("0.01")`: the scale is a
        property of the currency, and six modules once each carried their own
        copy of that constant.
        """
        return quantize_money(unit_price * quantity, currency)

    async def _unit_price(self, plan_code: str, currency_code: str) -> Decimal | None:
        from platform_core.modules.audit.service import AuditService
        from platform_core.modules.configuration.service import ConfigurationService

        # `resolve` RAISES when nobody has set the key — which is the normal
        # state of this platform today, not an error. An unset price means
        # "not for sale yet", and checkout says so rather than 500ing.
        try:
            value = await ConfigurationService(self._session, AuditService(self._session)).resolve(
                price_config_key(plan_code, currency_code)
            )
        except NotFoundError:
            return None
        if value is None:
            return None
        try:
            price = Decimal(str(value))
        except (ArithmeticError, ValueError):
            return None
        # A zero or negative price is a misconfiguration, not a free plan.
        # Treating it as "no price" refuses the checkout instead of opening one
        # for nothing.
        return price if price > 0 else None

    async def _unpayable_reason(self, unit_price: Decimal | None) -> str | None:
        """Why this organization cannot pay right now, or None.

        Said plainly rather than as a 500 later: the two real answers are "no
        gateway is contracted" and "nobody has set a price", and an
        administrator can act on neither by retrying.
        """
        try:
            get_payment_provider()
        except PaymentProviderUnavailable as exc:
            return str(exc)
        from platform_core.core.config import get_settings

        if get_settings().subscription_payment_provider == "disabled":
            return (
                "no payment provider is configured for this deployment — "
                "subscriptions are activated by the Lacteva team"
            )
        if unit_price is None:
            return "no price has been published for this plan in this currency"
        return None

    async def _open_payment(self) -> SubscriptionPayment | None:
        return await self._session.scalar(
            select(SubscriptionPayment).where(
                SubscriptionPayment.tenant_id == self._tenant_id,
                SubscriptionPayment.open_key == OPEN,
            )
        )

    async def _organization(self):
        from platform_core.modules.organization.models import Organization

        org = await self._session.get(Organization, self._tenant_id)
        if org is None:
            raise NotFoundError("organization not found")
        return org

    async def _publish(self, event: str, payment: SubscriptionPayment) -> None:
        if self._bus is None:
            return
        from platform_core.infrastructure.events import EventEnvelope

        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS[event],
                {
                    "payment_id": str(payment.id),
                    "plan_code": payment.plan_code,
                    "amount": str(payment.amount),
                    "currency_code": payment.currency_code,
                    "quantity": payment.quantity,
                    "provider": payment.provider,
                },
                aggregate_type="subscription",
                aggregate_id=payment.subscription_id,
            )
        )

    @staticmethod
    def _view(payment: SubscriptionPayment) -> SubscriptionPaymentView:
        """Money is rendered at the CURRENCY's scale, never with `str()`.

        The PostgreSQL proof found this and SQLite could not: the column is
        NUMERIC(18, 6), so a row just created in memory stringified as
        `3600.00` while the same row read back from the database stringified as
        `3600.000000`. Same payment, two answers — the checkout would show one
        and the payment history the other, and a dairy comparing them would be
        right to ask which it had been charged. `format_money` asks the
        currency, which is the only thing that knows.
        """
        return SubscriptionPaymentView(
            id=payment.id,
            plan_code=payment.plan_code,
            unit_price=format_money(payment.unit_price, payment.currency_code),
            quantity=payment.quantity,
            amount=format_money(payment.amount, payment.currency_code),
            currency_code=payment.currency_code,
            status=payment.status,
            provider=payment.provider,
            provider_reference=payment.provider_reference,
            checkout_url=payment.checkout_url,
            failure_code=payment.failure_code,
            failure_message=payment.failure_message,
            created_at=payment.created_at,
            completed_at=payment.completed_at,
        )


__all__ = [
    "BUS_EVENTS",
    "QuoteView",
    "SubscriptionBillingService",
    "SubscriptionPaymentView",
    "WebhookResult",
    "add_period",
]
