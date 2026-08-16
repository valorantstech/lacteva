"""Provider notifications (DEMO-027).

**The only unauthenticated write path in the platform**, so every line here is
about not trusting the caller.

    POST /v1/payments/webhooks/{provider}
        signature verified  ─┐
        event id recorded    ├─ or nothing happens at all
        payment looked up   ─┘
        amount re-checked
        CAS transition
        subscription activated

Four things it deliberately never does.

*It never reads a tenant from the payload.* The organization comes from the
`subscription_payment` row that the provider reference names. A body claiming
`"organization_id": "..."` is ignored, because an unauthenticated caller naming
a tenant is the whole attack.

*It never reads an amount from the payload as truth.* The stored intent holds
what the platform asked for; a signed message reporting a different number is
refused and recorded, not accepted.

*It never creates a payment.* An event for a reference this platform does not
know is dropped. That also means an unauthenticated endpoint cannot be used to
fill a table.

*It never acts twice.* `(provider, event_id)` is unique, so the second delivery
of an event does nothing — which is the normal case, not the exceptional one,
because every gateway retries deliveries it is unsure about.

It runs on a **platform session** (`core/rls.py`), because a webhook arrives
before the platform knows whose it is, and an ordinary tenant-bound session
could not find the payment at all. That is the defect MT-001 found in a
different component, and the reason the factory exists.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from platform_core.core.rls import platform_factory
from platform_core.core.tenancy import get_current_tenant, set_current_tenant
from platform_core.modules.subscription.billing import (
    SubscriptionBillingService,
    WebhookResult,
)
from platform_core.modules.subscription.models import (
    SubscriptionPayment,
    SubscriptionPaymentEvent,
)
from platform_core.modules.subscription.providers import (
    WebhookEvent,
    get_payment_provider,
)

#: Event kinds that describe a RENEWAL rather than a first payment. A renewal
#: extends the period and, when it fails, opens the grace window — a first
#: payment that fails simply did not buy anything.
RENEWAL_KINDS = ("renewal.succeeded", "renewal.failed")


async def process_webhook(
    *, provider_name: str, body: bytes, headers: dict[str, str], factory=None
) -> WebhookResult:
    """Verify, de-duplicate and act on one provider notification.

    Raises `WebhookVerificationError` (bad signature) or
    `PaymentProviderUnavailable` (unknown provider) — the route turns those
    into 401 and 404 without saying which check failed, because an attacker
    probing the endpoint learns from the difference.
    """
    provider = get_payment_provider(provider_name)
    event = provider.parse_webhook(body=body, headers=headers)

    sessions = factory or platform_factory("subscription payment webhook")
    async with sessions() as session:
        payment = await session.scalar(
            select(SubscriptionPayment).where(
                SubscriptionPayment.provider == provider.name,
                SubscriptionPayment.provider_reference == event.outcome.provider_reference,
            )
        )
        if payment is None:
            # Nothing is recorded. The platform has no payment by that
            # reference, so there is no tenant to attribute the event to and
            # nothing an attacker could accumulate here.
            return WebhookResult(outcome="unknown_reference")

        recorded = await _record(session, payment=payment, provider=provider.name, event=event)
        if not recorded:
            await session.commit()
            return WebhookResult(outcome="replayed", payment_id=payment.id)

        outcome = await _act(session, payment=payment, event=event)
        await _stamp(session, provider.name, event.event_id, outcome)
        await session.commit()
        return WebhookResult(outcome=outcome, payment_id=payment.id)


async def _record(
    session, *, payment: SubscriptionPayment, provider: str, event: WebhookEvent
) -> bool:
    """Claim this event id, or discover somebody already did.

    Returns False on a replay. The `add` sits INSIDE the savepoint — entering
    `begin_nested()` can autoflush a pending insert first, which would put the
    unique violation outside the savepoint and poison the transaction. That
    exact bug shipped in DEMO-025 and only real PostgreSQL found it.
    """
    row = SubscriptionPaymentEvent(
        tenant_id=payment.tenant_id,
        payment_id=payment.id,
        provider=provider,
        event_id=event.event_id,
        kind=event.kind,
        outcome="received",
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        return False
    return True


async def _act(session, *, payment: SubscriptionPayment, event: WebhookEvent) -> str:
    """Apply the outcome, with the payment's own tenant in context.

    Setting the contextvar matters and is not decoration: `EventEnvelope.new`
    reads it, so publishing without it would write outbox rows with no tenant —
    the defect DEMO-025 found when a consumer resolved configuration for
    nobody. It is restored afterwards because this runs inside a request whose
    context belongs to somebody else, or to nobody at all.
    """
    from platform_core.infrastructure.events import get_event_bus
    from platform_core.modules.event_relay.service import OutboxEventBus

    previous = get_current_tenant()
    set_current_tenant(payment.tenant_id)
    try:
        service = SubscriptionBillingService(
            session, payment.tenant_id, OutboxEventBus(session, get_event_bus())
        )
        return await service.apply_provider_outcome(
            payment,
            event.outcome,
            kind="renewal" if event.kind in RENEWAL_KINDS else "payment",
        )
    finally:
        set_current_tenant(previous)


async def _stamp(session, provider: str, event_id: str, outcome: str) -> None:
    """Record what was DONE, so the ledger distinguishes 'acted on' from
    'recognised and correctly ignored'."""
    row = await session.scalar(
        select(SubscriptionPaymentEvent).where(
            SubscriptionPaymentEvent.provider == provider,
            SubscriptionPaymentEvent.event_id == event_id,
        )
    )
    if row is not None:
        row.outcome = outcome
        await session.flush()


__all__ = ["RENEWAL_KINDS", "process_webhook"]
