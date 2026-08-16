"""One payment, one activation — under real concurrency (DEMO-027).

`test_subscription_payments.py` proves the rules on SQLite, where the test
stack shares a single connection and true concurrency cannot happen. This is
the half that cannot be proven there, and every property in it is a way to be
charged twice or to be given something twice:

    1. the same checkout request does not open two payments
    2. the same successful webhook does not activate twice
    3. two simultaneous deliveries produce one final state
    4. a retry after a lost response is safe
    5. one payment cannot activate two subscriptions
    6. a trial cannot become two paid subscriptions
    7. concurrent checkouts resolve deterministically

The defences are database constraints — `(tenant_id, open_key)` and
`(provider, event_id)` — and a constraint is only proven by writers racing at
it. A `SELECT` that was true a microsecond ago proves nothing.

The provider is a deterministic fake that takes no money. Nothing here is
evidence that a real gateway works.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

STANDARD = "LACTEVA_STANDARD"
SECRET = "postgres-proof-webhook-secret"


@pytest.fixture(autouse=True)
def _settings_point_at_postgres(monkeypatch):
    """Make `is_postgres()` true, or every binding below is a no-op.

    The lesson DEMO-020 learned the hard way: without this the suite passes as
    a superuser and proves nothing about RLS at all.
    """
    from platform_core.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", POSTGRES_URL)
    monkeypatch.setattr(settings, "rls_enabled", True)
    monkeypatch.setattr(settings, "subscription_payment_provider", "test")
    monkeypatch.setattr(settings, "subscription_payment_webhook_secret", SECRET)


@pytest.fixture
def gateway():
    from platform_core.modules.subscription import providers as payment_providers

    payment_providers.reset_payment_providers()
    provider = payment_providers.TestPaymentProvider("test")
    payment_providers.register_payment_provider("test", provider)
    yield provider
    payment_providers.reset_payment_providers()


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture
async def tenant(factory):
    """A Kenyan cooperative with a published price, cleaned up afterwards."""
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.subscription.plans import price_config_key

    tenant_id = uuid.uuid4()
    async with factory() as session:
        await bind_platform_context(session, reason="payment concurrency test seed")
        await session.execute(
            text(
                "INSERT INTO organization "
                "(id, name, slug, country_code, org_type, status, currency_code, timezone, "
                " supported_languages, default_locale, created_at) "
                "VALUES (:id, :n, :s, 'KE', 'processor', 'active', 'KES', 'Africa/Nairobi', "
                "        '[\"en\"]', 'en', :c)"
            ),
            {
                "id": tenant_id,
                "n": f"Race {tenant_id}",
                "s": f"race-{tenant_id}",
                "c": datetime(2026, 8, 1, 6, 0, tzinfo=UTC),
            },
        )
        await session.execute(
            text(
                "INSERT INTO config_entry (id, scope, tenant_id, key, value, updated_at) "
                "VALUES (:id, 'tenant', :t, :k, :v, now())"
            ),
            {
                "id": uuid.uuid4(),
                "t": tenant_id,
                "k": price_config_key(STANDARD, "KES"),
                "v": json.dumps({"value": "1200.00"}),
            },
        )
        await session.commit()

    yield tenant_id

    async with factory() as session:
        await bind_platform_context(session, reason="payment concurrency test cleanup")
        for table in (
            "subscription_payment_event",
            "subscription_payment",
            "subscription",
            "config_entry",
        ):
            await session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tenant_id}
            )
        await session.execute(text("DELETE FROM organization WHERE id = :t"), {"t": tenant_id})
        await session.commit()


# --- helpers ------------------------------------------------------------------


async def _checkout(factory, tenant_id: uuid.UUID, *, centres: int = 3):
    """One checkout, in its own session and transaction."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.subscription.billing import SubscriptionBillingService

    async with factory() as session:
        await rebind_tenant(session, tenant_id)
        set_current_tenant(tenant_id)
        try:
            view = await SubscriptionBillingService(session, tenant_id).start_checkout(
                plan_code=STANDARD, quantity=centres
            )
            await session.commit()
            return view
        finally:
            set_current_tenant(None)


def _platform_factory(factory):
    """A platform-bound factory over the test engine, for the webhook path."""
    from platform_core.core.rls import PlatformSessionFactory

    return PlatformSessionFactory(factory, "subscription payment webhook (test)")


async def _deliver(gateway, factory, *, event_id: str, kind: str, reference: str, amount, currency):
    from platform_core.modules.subscription import providers as payment_providers
    from platform_core.modules.subscription.webhooks import process_webhook

    body = gateway.webhook_body(
        event_id=event_id,
        kind=kind,
        provider_reference=reference,
        amount=amount,
        currency=currency,
    )
    return await process_webhook(
        provider_name="test",
        body=body,
        headers={payment_providers.SIGNATURE_HEADER: gateway.sign(body)},
        factory=_platform_factory(factory),
    )


async def _counts(factory, tenant_id: uuid.UUID) -> tuple[int, int, int]:
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.subscription.models import (
        Subscription,
        SubscriptionPayment,
        SubscriptionPaymentEvent,
    )

    async with factory() as session:
        await rebind_tenant(session, tenant_id)
        payments = await session.scalar(
            select(func.count())
            .select_from(SubscriptionPayment)
            .where(SubscriptionPayment.tenant_id == tenant_id)
        )
        subscriptions = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.tenant_id == tenant_id)
        )
        events = await session.scalar(
            select(func.count())
            .select_from(SubscriptionPaymentEvent)
            .where(SubscriptionPaymentEvent.tenant_id == tenant_id)
        )
    return payments or 0, subscriptions or 0, events or 0


async def _subscription(factory, tenant_id: uuid.UUID):
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.subscription.models import Subscription

    async with factory() as session:
        await rebind_tenant(session, tenant_id)
        return await session.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))


# --- 1, 7: one open payment, however many clicks ------------------------------


async def test_eight_concurrent_checkouts_open_exactly_one_payment(factory, tenant, gateway):
    """The double click, the retried mobile request and the racing tab.

    Every caller must end at the SAME payment: eight different ids would be
    eight chances to be charged.
    """
    results = await asyncio.gather(
        *(_checkout(factory, tenant) for _ in range(8)), return_exceptions=True
    )
    raised = [r for r in results if isinstance(r, Exception)]
    assert not raised, f"a racing checkout raised: {raised}"

    payments, subscriptions, _events = await _counts(factory, tenant)
    assert payments == 1, "one organization opened more than one payment"
    assert subscriptions == 1
    assert len({r.id for r in results}) == 1, "racing callers received different payments"
    assert {r.amount for r in results} == {"3600.00"}


async def test_concurrent_checkouts_for_different_quantities_resolve_deterministically(
    factory, tenant, gateway
):
    """One wins, the rest are REFUSED — not silently merged into a wrong price.

    Deterministic does not mean everybody succeeds. Two different intentions
    cannot both be true, and the platform must not average them.
    """
    results = await asyncio.gather(
        *(_checkout(factory, tenant, centres=n) for n in (2, 5, 9)),
        return_exceptions=True,
    )
    opened = [r for r in results if not isinstance(r, Exception)]
    assert len(opened) == 1, f"more than one quantity was accepted: {opened}"

    payments, _subs, _events = await _counts(factory, tenant)
    assert payments == 1


# --- 2, 3, 5: one activation, however many deliveries -------------------------


async def test_two_simultaneous_deliveries_of_one_event_activate_once(factory, tenant, gateway):
    """A gateway delivering the same event twice at once is normal operation."""
    payment = await _checkout(factory, tenant, centres=3)
    gateway.record_intent(Decimal(payment.amount), payment.currency_code)

    results = await asyncio.gather(
        *(
            _deliver(
                gateway,
                factory,
                event_id="evt_race",
                kind="payment.succeeded",
                reference=payment.provider_reference,
                amount=Decimal(payment.amount),
                currency=payment.currency_code,
            )
            for _ in range(2)
        ),
        return_exceptions=True,
    )
    raised = [r for r in results if isinstance(r, Exception)]
    assert not raised, f"a racing delivery raised: {raised}"

    outcomes = sorted(r.outcome for r in results)
    assert outcomes == ["activated", "replayed"], f"both deliveries acted: {outcomes}"

    _payments, _subs, events = await _counts(factory, tenant)
    assert events == 1, "the same provider event was recorded twice"

    subscription = await _subscription(factory, tenant)
    assert subscription.status == "active"
    assert subscription.subscribed_centres == 3


async def test_the_same_successful_webhook_never_extends_the_period_twice(factory, tenant, gateway):
    payment = await _checkout(factory, tenant, centres=2)
    gateway.record_intent(Decimal(payment.amount), payment.currency_code)

    first = await _deliver(
        gateway,
        factory,
        event_id="evt_once",
        kind="payment.succeeded",
        reference=payment.provider_reference,
        amount=Decimal(payment.amount),
        currency=payment.currency_code,
    )
    assert first.outcome == "activated"
    after_first = await _subscription(factory, tenant)
    period_end = after_first.current_period_end

    for _ in range(4):
        again = await _deliver(
            gateway,
            factory,
            event_id="evt_once",
            kind="payment.succeeded",
            reference=payment.provider_reference,
            amount=Decimal(payment.amount),
            currency=payment.currency_code,
        )
        assert again.outcome == "replayed"

    after_replays = await _subscription(factory, tenant)
    assert after_replays.current_period_end == period_end, "a replay bought another month"


async def test_one_payment_cannot_activate_two_subscriptions(factory, tenant, gateway):
    """`tenant_id` is unique on `subscription`, so there is only ever one to
    activate — asserted here rather than assumed, because the payment path is
    new and the constraint is old."""
    payment = await _checkout(factory, tenant, centres=1)
    gateway.record_intent(Decimal(payment.amount), payment.currency_code)
    await _deliver(
        gateway,
        factory,
        event_id="evt_single",
        kind="payment.succeeded",
        reference=payment.provider_reference,
        amount=Decimal(payment.amount),
        currency=payment.currency_code,
    )

    _payments, subscriptions, _events = await _counts(factory, tenant)
    assert subscriptions == 1


# --- 4, 6: retries and the trial ----------------------------------------------


async def test_a_retry_after_a_lost_response_charges_nothing_extra(factory, tenant, gateway):
    """The client never saw the answer, so it asks again. It must not pay again."""
    first = await _checkout(factory, tenant, centres=4)
    second = await _checkout(factory, tenant, centres=4)
    assert second.id == first.id
    assert second.provider_reference == first.provider_reference

    payments, _subs, _events = await _counts(factory, tenant)
    assert payments == 1


async def test_a_trial_cannot_become_two_paid_subscriptions(factory, tenant, gateway):
    """Two paid checkouts, both confirmed — one subscription, the later terms.

    The second payment is only reachable after the first has settled, which is
    itself the guard; what this asserts is that settling both does not leave
    the organization holding two.
    """
    first = await _checkout(factory, tenant, centres=2)
    gateway.record_intent(Decimal(first.amount), first.currency_code)
    await _deliver(
        gateway,
        factory,
        event_id="evt_a",
        kind="payment.succeeded",
        reference=first.provider_reference,
        amount=Decimal(first.amount),
        currency=first.currency_code,
    )

    second = await _checkout(factory, tenant, centres=5)
    gateway.record_intent(Decimal(second.amount), second.currency_code)
    await _deliver(
        gateway,
        factory,
        event_id="evt_b",
        kind="payment.succeeded",
        reference=second.provider_reference,
        amount=Decimal(second.amount),
        currency=second.currency_code,
    )

    payments, subscriptions, events = await _counts(factory, tenant)
    assert (payments, subscriptions, events) == (2, 1, 2)
    subscription = await _subscription(factory, tenant)
    assert subscription.subscribed_centres == 5


# --- isolation and the database's own guarantees ------------------------------


async def test_a_payment_does_not_leak_or_delete_across_tenants(factory, tenant, gateway):
    """Commercial standing is exactly what a competitor must not read."""
    from platform_core.core.rls import bind_platform_context, rebind_tenant

    other = uuid.uuid4()
    async with factory() as session:
        await bind_platform_context(session, reason="payment isolation seed")
        await session.execute(
            text(
                "INSERT INTO organization "
                "(id, name, slug, country_code, org_type, status, currency_code, timezone, "
                " supported_languages, default_locale, created_at) "
                "VALUES (:id, :n, :s, 'IN', 'processor', 'active', 'INR', 'Asia/Kolkata', "
                "        '[\"en\"]', 'en', now())"
            ),
            {"id": other, "n": f"Other {other}", "s": f"other-{other}"},
        )
        await session.commit()

    try:
        await _checkout(factory, tenant, centres=2)

        async with factory() as session:
            await rebind_tenant(session, other)
            leaked = (
                await session.execute(
                    text("SELECT count(*) FROM subscription_payment WHERE tenant_id = :t"),
                    {"t": tenant},
                )
            ).scalar_one()
            assert leaked == 0, "another tenant read a payment it does not own"

            deleted = await session.execute(
                text("DELETE FROM subscription_payment WHERE tenant_id = :t"), {"t": tenant}
            )
            assert deleted.rowcount == 0, "another tenant deleted a payment it does not own"
            await session.commit()

        payments, _subs, _events = await _counts(factory, tenant)
        assert payments == 1, "the payment survived"
    finally:
        async with factory() as session:
            await bind_platform_context(session, reason="payment isolation cleanup")
            for table in ("subscription_payment", "subscription"):
                await session.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": other}
                )
            await session.execute(text("DELETE FROM organization WHERE id = :t"), {"t": other})
            await session.commit()


@pytest.mark.parametrize("table", ["subscription_payment", "subscription_payment_event"])
async def test_the_payment_tables_force_row_level_security(factory, table):
    """ENABLE without FORCE protects nothing: the app owns these tables."""
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = :t"
                ),
                {"t": table},
            )
        ).first()
    assert row is not None, f"{table} does not exist in the migrated database"
    enabled, forced = row
    assert enabled and forced


async def test_the_constraints_that_are_the_guarantees_exist(factory):
    """Named explicitly: these, not Python, are what stop a double charge."""
    async with factory() as session:
        names = {
            r[0]
            for r in (
                await session.execute(
                    text(
                        "SELECT conname FROM pg_constraint c "
                        "JOIN pg_class t ON t.oid = c.conrelid "
                        "WHERE t.relname IN "
                        "  ('subscription_payment', 'subscription_payment_event') "
                        "  AND c.contype = 'u'"
                    )
                )
            ).all()
        }
    assert "uq_subscription_payment_open" in names
    assert "uq_subscription_payment_provider_ref" in names
    assert "uq_subscription_payment_event" in names
