"""Paying Lacteva for a subscription (DEMO-027).

The property under test, in one sentence:

    **A subscription becomes ACTIVE only because a payment provider said a
    payment succeeded, for the amount the server calculated, exactly once.**

Every test here is an attempt to make one of those four words false — because
a browser named the amount, because the provider was never asked, because a
webhook was replayed, or because two of them arrived at once.

The provider is a deterministic fake. It takes no money and is refused in
production by settings validation, and the tests say so where it matters: this
file proves the PLATFORM's half of a payment, and nothing here is evidence that
a real gateway works.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from platform_core.core import db
from platform_core.core.config import get_settings
from platform_core.core.tenancy import set_current_tenant
from platform_core.modules.audit.service import AuditService
from platform_core.modules.configuration.service import ConfigurationService
from platform_core.modules.subscription import providers as payment_providers
from platform_core.modules.subscription.billing import (
    add_period,
)
from platform_core.modules.subscription.models import (
    Subscription,
    SubscriptionPayment,
    SubscriptionPaymentEvent,
)
from platform_core.modules.subscription.plans import price_config_key
from tests.test_localization import _tenant_admin_for
from tests.test_org_structure import _tenant_admin

QUOTE = "/v1/organization/subscription/quote"
CHECKOUT = "/v1/organization/subscription/checkout"
REFRESH = "/v1/organization/subscription/checkout/refresh"
CANCEL = "/v1/organization/subscription/checkout/cancel"
PAYMENTS = "/v1/organization/subscription/payments"
SUBSCRIPTION = "/v1/organization/subscription"
ENTITLEMENT = "/v1/organization/entitlement"
WEBHOOK = "/v1/payments/webhooks/test"

STANDARD = "LACTEVA_STANDARD"


# --- harness ------------------------------------------------------------------


@pytest.fixture
def gateway(monkeypatch):
    """A configured TEST provider, torn down afterwards.

    Registering the instance means every test holds the same object the
    platform will use — so a test can assert what the platform ASKED the
    provider, not merely what it did afterwards.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "subscription_payment_provider", "test")
    monkeypatch.setattr(settings, "subscription_payment_webhook_secret", "test-webhook-secret")
    payment_providers.reset_payment_providers()
    provider = payment_providers.TestPaymentProvider("test")
    payment_providers.register_payment_provider("test", provider)
    yield provider
    payment_providers.reset_payment_providers()


async def _tenant_id(client, headers) -> uuid.UUID:
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    return uuid.UUID(me["tenant_id"])


async def _publish_price(tenant_id: uuid.UUID, amount: str, currency: str | None = None) -> None:
    """A deployment deciding what its plan costs, through the real store.

    The currency is the ORGANIZATION's, looked up rather than assumed — the
    first draft of this helper hard-coded INR and the suite caught it against a
    Kenyan tenant, which is the same mistake the platform must never make.
    """
    from platform_core.modules.organization.models import Organization

    async with db.get_session_factory()() as session:
        set_current_tenant(tenant_id)
        if currency is None:
            org = await session.get(Organization, tenant_id)
            currency = org.currency_code
        await ConfigurationService(session, AuditService(session)).set_value(
            price_config_key(STANDARD, currency), amount, scope="tenant", actor_id=None
        )
        await session.commit()
    set_current_tenant(None)


async def _paid_tenant(client, gateway, *, centres: int = 3, price: str = "1200.00"):
    """An organization with a price published and a checkout open."""
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    await _publish_price(tenant_id, price)
    started = await client.post(
        CHECKOUT, headers=headers, json={"plan_code": STANDARD, "subscribed_centres": centres}
    )
    assert started.status_code == 200, started.text
    payment = started.json()
    gateway.record_intent(Decimal(payment["amount"]), payment["currency_code"])
    return headers, tenant_id, payment


def _deliver(gateway, *, event_id: str, kind: str, reference: str, **kw) -> tuple[bytes, dict]:
    body = gateway.webhook_body(event_id=event_id, kind=kind, provider_reference=reference, **kw)
    return body, {payment_providers.SIGNATURE_HEADER: gateway.sign(body)}


async def _subscription(tenant_id: uuid.UUID) -> Subscription:
    async with db.get_session_factory()() as session:
        set_current_tenant(tenant_id)
        row = await session.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
        set_current_tenant(None)
        return row


async def _payments(tenant_id: uuid.UUID) -> list[SubscriptionPayment]:
    async with db.get_session_factory()() as session:
        set_current_tenant(tenant_id)
        rows = list(
            (
                await session.scalars(
                    select(SubscriptionPayment).where(SubscriptionPayment.tenant_id == tenant_id)
                )
            ).all()
        )
        set_current_tenant(None)
        return rows


# --- the amount is the server's ----------------------------------------------


async def test_a_payment_reads_back_with_the_same_amount_it_was_created_with(client, gateway):
    """The defect the PostgreSQL proof found, pinned where it is cheap to run.

    `NUMERIC(18, 6)` means a row read from the database stringifies with six
    decimal places while the one just built in memory has two. Checkout would
    say 3600.00 and the payment history 3600.000000, about the same payment.
    """
    headers, _tenant, created = await _paid_tenant(client, gateway, centres=3)
    history = (await client.get(PAYMENTS, headers=headers)).json()
    assert history[0]["amount"] == created["amount"]
    assert history[0]["unit_price"] == created["unit_price"]
    assert created["amount"] == "3600.00"


async def test_the_quote_is_price_times_centres_and_the_client_sends_neither(client, gateway):
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    await _publish_price(tenant_id, "1200.00")

    body = (
        await client.get(
            QUOTE, headers=headers, params={"plan_code": STANDARD, "subscribed_centres": 4}
        )
    ).json()
    assert body["unit_price"] == "1200.00"
    assert body["quantity"] == 4
    assert body["amount"] == "4800.00"
    # KES, because the helper onboards a Kenyan cooperative — the currency is
    # the organization's, never the caller's and never a default.
    assert body["currency_code"] == "KES"
    assert body["payable"] is True


async def test_no_endpoint_accepts_an_amount_a_currency_or_a_status(client):
    """The schema is the guard: what a client cannot say, it cannot forge."""
    schema = (await client.get("/openapi.json")).json()
    forbidden = {"amount", "currency", "currency_code", "status", "unit_price", "paid"}
    offenders = []
    for path, operations in schema["paths"].items():
        if "subscription" not in path and "payments/webhooks" not in path:
            continue
        for method, operation in operations.items():
            if method not in ("post", "put", "patch"):
                continue
            ref = (
                operation.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
                .get("$ref")
            )
            if not ref:
                continue
            model = schema["components"]["schemas"][ref.rsplit("/", 1)[-1]]
            leaked = forbidden & set(model.get("properties", {}))
            if leaked:
                offenders.append((path, method, sorted(leaked)))
    assert not offenders, f"a client can name what only the server may decide: {offenders}"


async def test_a_client_cannot_smuggle_an_amount_through_the_checkout_body(client, gateway):
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    await _publish_price(tenant_id, "1200.00")

    started = await client.post(
        CHECKOUT,
        headers=headers,
        json={
            "plan_code": STANDARD,
            "subscribed_centres": 2,
            # All ignored: extra fields are not modelled, so they are not read.
            "amount": "1.00",
            "unit_price": "0.01",
            "currency_code": "USD",
            "status": "succeeded",
        },
    )
    assert started.status_code == 200, started.text
    payment = started.json()
    assert payment["amount"] == "2400.00"
    assert payment["currency_code"] == "KES"
    assert payment["status"] == "pending"


async def test_the_currency_comes_from_the_organization_not_from_the_caller(client, gateway):
    """India in INR, Kenya in KES, and no country named anywhere in the path."""
    _org_in, india = await _tenant_admin_for(
        client, country="IN", slug="pay-in", email="admin@pay-in.example"
    )
    _org_ke, kenya = await _tenant_admin_for(
        client, country="KE", slug="pay-ke", email="admin@pay-ke.example"
    )
    india_id, kenya_id = await _tenant_id(client, india), await _tenant_id(client, kenya)
    await _publish_price(india_id, "1200.00", "INR")
    await _publish_price(kenya_id, "1500.00", "KES")

    in_quote = (
        await client.get(
            QUOTE, headers=india, params={"plan_code": STANDARD, "subscribed_centres": 2}
        )
    ).json()
    ke_quote = (
        await client.get(
            QUOTE, headers=kenya, params={"plan_code": STANDARD, "subscribed_centres": 2}
        )
    ).json()

    assert (in_quote["currency_code"], in_quote["amount"]) == ("INR", "2400.00")
    assert (ke_quote["currency_code"], ke_quote["amount"]) == ("KES", "3000.00")


async def test_no_country_or_vendor_appears_in_the_payment_LOGIC(client):
    """Asserted against the source, because a branch here would be invisible in
    behaviour until the day a third country arrived.

    It reads the AST rather than the text, and deliberately: the first version
    grepped the file and flagged the PROSE — the docstring explaining a Kenyan
    cooperative's timezone, and the comment distinguishing this module from the
    dairy's M-Pesa payments. Those sentences are why the rule is understood.
    What must not exist is a country or a vendor as a VALUE the code compares
    against, so that is what this looks for.
    """
    import ast
    import pathlib

    import platform_core.modules.subscription as package

    banned = {
        "india",
        "kenya",
        "qatar",
        "in",
        "ke",
        "qa",
        "razorpay",
        "stripe",
        "paystack",
        "flutterwave",
        "m-pesa",
        "mpesa",
        "payu",
    }
    root = pathlib.Path(package.__file__).parent
    offenders = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text())
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                doc = ast.get_docstring(node, clean=False)
                if doc is not None:
                    docstrings.add(doc)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in docstrings:
                    continue
                if node.value.strip().lower() in banned:
                    offenders.append(f"{path.name}:{node.lineno}: {node.value!r}")
    assert not offenders, f"a country or a vendor is a VALUE in the domain: {offenders}"


# --- refusing when it cannot honestly take money ------------------------------


async def test_checkout_refuses_when_no_provider_is_configured(client):
    """The default posture. It refuses LOUDLY rather than recording an intent
    nobody can complete."""
    payment_providers.reset_payment_providers()
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    await _publish_price(tenant_id, "1200.00")

    quote = (
        await client.get(
            QUOTE, headers=headers, params={"plan_code": STANDARD, "subscribed_centres": 1}
        )
    ).json()
    assert quote["payable"] is False
    assert "no payment provider" in quote["payable_reason"]

    refused = await client.post(
        CHECKOUT, headers=headers, json={"plan_code": STANDARD, "subscribed_centres": 1}
    )
    assert refused.status_code == 409
    assert await _payments(tenant_id) == []


async def test_checkout_refuses_when_no_price_has_been_published(client, gateway):
    """No deployment has decided a price. Inventing one would invent a fact."""
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)

    quote = (
        await client.get(
            QUOTE, headers=headers, params={"plan_code": STANDARD, "subscribed_centres": 1}
        )
    ).json()
    assert quote["unit_price"] is None and quote["amount"] is None
    assert quote["payable"] is False

    refused = await client.post(
        CHECKOUT, headers=headers, json={"plan_code": STANDARD, "subscribed_centres": 1}
    )
    assert refused.status_code == 409
    assert await _payments(tenant_id) == []


async def test_a_zero_price_is_a_misconfiguration_not_a_free_plan(client, gateway):
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    await _publish_price(tenant_id, "0.00")

    refused = await client.post(
        CHECKOUT, headers=headers, json={"plan_code": STANDARD, "subscribed_centres": 1}
    )
    assert refused.status_code == 409
    assert await _payments(tenant_id) == []


async def test_the_trial_plan_cannot_be_paid_for(client, gateway):
    _org, headers = await _tenant_admin(client)
    refused = await client.post(
        CHECKOUT, headers=headers, json={"plan_code": "LACTEVA_TRIAL", "subscribed_centres": 1}
    )
    assert refused.status_code == 409


async def test_a_subscription_must_cover_at_least_one_centre(client, gateway):
    _org, headers = await _tenant_admin(client)
    tenant_id = await _tenant_id(client, headers)
    await _publish_price(tenant_id, "1200.00")
    refused = await client.post(
        CHECKOUT, headers=headers, json={"plan_code": STANDARD, "subscribed_centres": 0}
    )
    assert refused.status_code == 422


# --- one open payment ---------------------------------------------------------


async def test_repeating_the_same_checkout_returns_the_same_payment(client, gateway):
    """A refreshed tab and a double click are not two charges."""
    headers, tenant_id, first = await _paid_tenant(client, gateway)
    again = await client.post(
        CHECKOUT, headers=headers, json={"plan_code": STANDARD, "subscribed_centres": 3}
    )
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert len(await _payments(tenant_id)) == 1


async def test_a_different_checkout_while_one_is_open_is_refused_not_stacked(client, gateway):
    headers, tenant_id, _first = await _paid_tenant(client, gateway, centres=3)
    other = await client.post(
        CHECKOUT, headers=headers, json={"plan_code": STANDARD, "subscribed_centres": 9}
    )
    assert other.status_code == 409
    assert len(await _payments(tenant_id)) == 1


async def test_cancelling_an_open_payment_frees_the_next_attempt(client, gateway):
    headers, tenant_id, first = await _paid_tenant(client, gateway, centres=3)
    cancelled = (await client.post(CANCEL, headers=headers)).json()
    assert cancelled["status"] == "cancelled"

    second = await client.post(
        CHECKOUT, headers=headers, json={"plan_code": STANDARD, "subscribed_centres": 9}
    )
    assert second.status_code == 200
    assert second.json()["id"] != first["id"]
    assert len(await _payments(tenant_id)) == 2


# --- activation is the provider's word ----------------------------------------


async def test_a_verified_payment_activates_the_subscription(client, gateway):
    headers, _tenant_id, payment = await _paid_tenant(client, gateway, centres=3)

    before = (await client.get(SUBSCRIPTION, headers=headers)).json()
    assert before["status"] == "trialing"

    refreshed = (await client.post(REFRESH, headers=headers)).json()
    assert refreshed["status"] == "succeeded"
    # The platform ASKED the provider rather than believing the browser.
    assert gateway.verifications == [payment["provider_reference"]]

    after = (await client.get(SUBSCRIPTION, headers=headers)).json()
    assert after["status"] == "active"
    assert after["plan_code"] == STANDARD
    assert after["subscribed_centres"] == 3
    assert after["current_period_end"] is not None


async def test_a_declined_payment_activates_nothing(client, gateway):
    headers, _tenant_id, _payment = await _paid_tenant(client, gateway)
    gateway.scenario = "failed"

    refreshed = (await client.post(REFRESH, headers=headers)).json()
    assert refreshed["status"] == "failed"
    assert refreshed["failure_code"] == "test_declined"

    after = (await client.get(SUBSCRIPTION, headers=headers)).json()
    assert after["status"] == "trialing", "a declined payment must not buy anything"


async def test_a_provider_timeout_leaves_the_payment_pending(client, gateway):
    """UNKNOWN is not FAILED. Marking it failed would invite a second charge."""
    headers, tenant_id, _payment = await _paid_tenant(client, gateway)
    gateway.scenario = "timeout"

    answer = await client.post(REFRESH, headers=headers)
    assert answer.status_code == 409

    rows = await _payments(tenant_id)
    assert [row.status for row in rows] == ["pending"]
    assert (await client.get(SUBSCRIPTION, headers=headers)).json()["status"] == "trialing"


async def test_a_provider_reporting_a_smaller_amount_is_refused(client, gateway):
    """The signature proves who sent it. It does not prove the number."""
    headers, _tenant_id, _payment = await _paid_tenant(client, gateway, centres=3)
    gateway.record_intent(Decimal("1.00"), "KES")  # the provider "charged" 1.00

    refreshed = (await client.post(REFRESH, headers=headers)).json()
    assert refreshed["status"] == "failed"
    assert refreshed["failure_code"] == "amount_mismatch"
    assert (await client.get(SUBSCRIPTION, headers=headers)).json()["status"] == "trialing"


async def test_a_provider_reporting_another_currency_is_refused(client, gateway):
    headers, _tenant_id, payment = await _paid_tenant(client, gateway)
    gateway.record_intent(Decimal(payment["amount"]), "USD")

    refreshed = (await client.post(REFRESH, headers=headers)).json()
    assert refreshed["status"] == "failed"
    assert refreshed["failure_code"] == "currency_mismatch"
    assert (await client.get(SUBSCRIPTION, headers=headers)).json()["status"] == "trialing"


# --- webhooks -----------------------------------------------------------------


async def test_a_signed_webhook_activates_and_a_replay_does_nothing(client, gateway):
    headers, tenant_id, payment = await _paid_tenant(client, gateway, centres=2)
    body, signed = _deliver(
        gateway,
        event_id="evt_1",
        kind="payment.succeeded",
        reference=payment["provider_reference"],
        amount=Decimal(payment["amount"]),
        currency=payment["currency_code"],
    )

    first = await client.post(WEBHOOK, content=body, headers=signed)
    assert first.status_code == 200
    assert first.json()["outcome"] == "activated"

    after = (await client.get(SUBSCRIPTION, headers=headers)).json()
    assert after["status"] == "active"
    period_end = after["current_period_end"]

    # The same delivery again — normal gateway behaviour, not an attack.
    replay = await client.post(WEBHOOK, content=body, headers=signed)
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "replayed"

    unchanged = (await client.get(SUBSCRIPTION, headers=headers)).json()
    assert unchanged["current_period_end"] == period_end, "a replay extended the subscription"
    assert len(await _payments(tenant_id)) == 1


async def test_an_unsigned_webhook_is_refused(client, gateway):
    """`{"success": true}` is not proof of payment."""
    _headers, tenant_id, payment = await _paid_tenant(client, gateway)
    body = gateway.webhook_body(
        event_id="evt_forged",
        kind="payment.succeeded",
        provider_reference=payment["provider_reference"],
    )

    for bad in ({}, {payment_providers.SIGNATURE_HEADER: "deadbeef"}):
        answer = await client.post(WEBHOOK, content=body, headers=bad)
        assert answer.status_code == 401, answer.text

    rows = await _payments(tenant_id)
    assert [row.status for row in rows] == ["pending"]


async def test_a_signed_webhook_naming_an_unknown_reference_creates_nothing(client, gateway):
    """An unauthenticated endpoint must not be a way to fill a table."""
    body, signed = _deliver(
        gateway, event_id="evt_unknown", kind="payment.succeeded", reference="test_nonexistent"
    )
    answer = await client.post(WEBHOOK, content=body, headers=signed)
    assert answer.status_code == 200
    assert answer.json()["outcome"] == "unknown_reference"

    async with db.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(SubscriptionPaymentEvent)) == 0


async def test_a_webhook_cannot_name_the_tenant_it_activates(client, gateway):
    """The organization comes from OUR row, never from the payload."""
    headers_a, _tenant_a, payment_a = await _paid_tenant(client, gateway, centres=2)
    _org_b, headers_b = await _tenant_admin_for(
        client, country="IN", slug="pay-victim", email="admin@pay-victim.example"
    )
    tenant_b = await _tenant_id(client, headers_b)

    body = gateway.webhook_body(
        event_id="evt_cross",
        kind="payment.succeeded",
        provider_reference=payment_a["provider_reference"],
        amount=Decimal(payment_a["amount"]),
        currency=payment_a["currency_code"],
    )
    # A body that also claims a tenant. It must change nothing about that one.
    import json

    payload = json.loads(body)
    payload["organization_id"] = str(tenant_b)
    payload["tenant_id"] = str(tenant_b)
    forged = json.dumps(payload, sort_keys=True).encode()

    answer = await client.post(
        WEBHOOK, content=forged, headers={payment_providers.SIGNATURE_HEADER: gateway.sign(forged)}
    )
    assert answer.status_code == 200

    assert (await client.get(SUBSCRIPTION, headers=headers_a)).json()["status"] == "active"
    assert (await client.get(SUBSCRIPTION, headers=headers_b)).json()["status"] == "trialing"


async def test_a_webhook_for_an_unknown_provider_is_a_404(client, gateway):
    body, signed = _deliver(gateway, event_id="e", kind="payment.succeeded", reference="r")
    answer = await client.post("/v1/payments/webhooks/acme-pay", content=body, headers=signed)
    assert answer.status_code == 404


async def test_the_webhook_endpoint_needs_no_login_and_grants_none(client, gateway):
    """It is unauthenticated by design, and that is not a way in: it reads one
    signature and writes one row it can already name."""
    _headers, _tenant, payment = await _paid_tenant(client, gateway)
    body, signed = _deliver(
        gateway,
        event_id="evt_noauth",
        kind="payment.succeeded",
        reference=payment["provider_reference"],
        amount=Decimal(payment["amount"]),
        currency=payment["currency_code"],
    )
    answer = await client.post(WEBHOOK, content=body, headers=signed)
    assert answer.status_code == 200
    # And it says only what it did — no tenant, no amount, no user.
    assert set(answer.json()) == {"outcome"}


# --- renewal, grace and expiry ------------------------------------------------


async def test_a_renewal_extends_from_the_period_end_not_from_today(client, gateway):
    headers, _tenant_id, payment = await _paid_tenant(client, gateway, centres=2)
    body, signed = _deliver(
        gateway,
        event_id="evt_first",
        kind="payment.succeeded",
        reference=payment["provider_reference"],
        amount=Decimal(payment["amount"]),
        currency=payment["currency_code"],
    )
    await client.post(WEBHOOK, content=body, headers=signed)
    first_end = date.fromisoformat(
        (await client.get(SUBSCRIPTION, headers=headers)).json()["current_period_end"]
    )

    # A second payment, delivered as a RENEWAL.
    second = await client.post(
        CHECKOUT, headers=headers, json={"plan_code": STANDARD, "subscribed_centres": 2}
    )
    reference = second.json()["provider_reference"]
    gateway.record_intent(Decimal(second.json()["amount"]), second.json()["currency_code"])
    body, signed = _deliver(
        gateway,
        event_id="evt_renewal",
        kind="renewal.succeeded",
        reference=reference,
        amount=Decimal(second.json()["amount"]),
        currency=second.json()["currency_code"],
    )
    await client.post(WEBHOOK, content=body, headers=signed)

    second_end = date.fromisoformat(
        (await client.get(SUBSCRIPTION, headers=headers)).json()["current_period_end"]
    )
    assert second_end == add_period(first_end, "month"), (
        "a renewal confirmed late must not shorten what was paid for"
    )


async def test_a_failed_renewal_becomes_past_due_and_keeps_operating(client, gateway):
    """The grace period exists so a bank decline does not stop a working dairy."""
    headers, _tenant_id, payment = await _paid_tenant(client, gateway, centres=2)
    body, signed = _deliver(
        gateway,
        event_id="evt_paid",
        kind="payment.succeeded",
        reference=payment["provider_reference"],
        amount=Decimal(payment["amount"]),
        currency=payment["currency_code"],
    )
    await client.post(WEBHOOK, content=body, headers=signed)

    second = (
        await client.post(
            CHECKOUT, headers=headers, json={"plan_code": STANDARD, "subscribed_centres": 2}
        )
    ).json()
    body, signed = _deliver(
        gateway,
        event_id="evt_renewal_failed",
        kind="renewal.failed",
        reference=second["provider_reference"],
        state="failed",
    )
    answer = await client.post(WEBHOOK, content=body, headers=signed)
    assert answer.status_code == 200

    entitlement = (await client.get(ENTITLEMENT, headers=headers)).json()
    assert entitlement["status"] == "past_due"
    assert entitlement["can_operate"] is True, "a declined renewal must not stop the dairy"
    assert entitlement["can_read"] is True
    assert entitlement["grace_ends_on"] is not None


async def test_a_past_due_subscription_expires_when_the_grace_period_ends(client, gateway):
    """The transition is a DATE question, asked on the organization's calendar."""
    headers, tenant_id, payment = await _paid_tenant(client, gateway, centres=1)
    body, signed = _deliver(
        gateway,
        event_id="evt_p",
        kind="payment.succeeded",
        reference=payment["provider_reference"],
        amount=Decimal(payment["amount"]),
        currency=payment["currency_code"],
    )
    await client.post(WEBHOOK, content=body, headers=signed)

    async with db.get_session_factory()() as session:
        set_current_tenant(tenant_id)
        row = await session.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
        row.status = "past_due"
        row.grace_ends_on = date.today() - timedelta(days=1)
        await session.commit()
    set_current_tenant(None)

    entitlement = (await client.get(ENTITLEMENT, headers=headers)).json()
    assert entitlement["status"] == "expired"
    assert entitlement["can_operate"] is False
    assert entitlement["can_read"] is True, "an expired dairy keeps its own records"


async def test_a_successful_payment_clears_the_grace_window(client, gateway):
    headers, tenant_id, _payment = await _paid_tenant(client, gateway, centres=1)
    async with db.get_session_factory()() as session:
        set_current_tenant(tenant_id)
        row = await session.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
        row.status = "past_due"
        row.grace_ends_on = date.today() + timedelta(days=3)
        await session.commit()
    set_current_tenant(None)

    await client.post(REFRESH, headers=headers)
    subscription = await _subscription(tenant_id)
    assert subscription.status == "active"
    assert subscription.grace_ends_on is None


# --- period arithmetic (pure) -------------------------------------------------


@pytest.mark.parametrize(
    ("start", "period", "expected"),
    [
        (date(2026, 1, 15), "month", date(2026, 2, 15)),
        (date(2026, 1, 31), "month", date(2026, 2, 28)),  # clamped, not overflowed
        (date(2026, 12, 15), "month", date(2027, 1, 15)),  # year rolls
        (date(2026, 3, 31), "month", date(2026, 4, 30)),
        (date(2026, 5, 1), "year", date(2027, 5, 1)),
        (date(2028, 2, 29), "year", date(2029, 2, 28)),  # leap day
    ],
)
def test_a_billing_period_lands_on_a_date_a_dairy_would_recognise(start, period, expected):
    assert add_period(start, period) == expected


def test_an_unknown_billing_period_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        add_period(date(2026, 1, 1), "fortnight")


# --- security -----------------------------------------------------------------


async def test_every_payment_endpoint_refuses_an_anonymous_caller(client):
    assert (
        await client.get(QUOTE, params={"plan_code": STANDARD, "subscribed_centres": 1})
    ).status_code == 401
    assert (
        await client.post(CHECKOUT, json={"plan_code": STANDARD, "subscribed_centres": 1})
    ).status_code == 401
    assert (await client.post(REFRESH)).status_code == 401
    assert (await client.get(PAYMENTS)).status_code == 401


async def test_a_viewer_cannot_start_a_checkout(client, gateway):
    """Normal users do not manage billing. A viewer may LOOK and may not pay."""
    from tests.conftest import invite

    org, admin = await _tenant_admin(client)
    _inv, token = await invite(
        client,
        {**admin, "X-Tenant-ID": org["id"]},
        email="viewer@billing.example",
        role_name="tenant-viewer",
    )
    await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "viewer-password-1", "full_name": "Viewer"},
    )
    pair = await client.post(
        "/v1/auth/token",
        json={
            "email": "viewer@billing.example",
            "password": "viewer-password-1",
            "tenant_id": org["id"],
        },
    )
    viewer = {"Authorization": f"Bearer {pair.json()['access_token']}"}

    refused = await client.post(
        CHECKOUT, headers=viewer, json={"plan_code": STANDARD, "subscribed_centres": 1}
    )
    assert refused.status_code == 403


async def test_payment_history_never_leaves_the_organization(client, gateway):
    headers_a, _tenant_a, _payment = await _paid_tenant(client, gateway, centres=2)
    _org_b, headers_b = await _tenant_admin_for(
        client, country="IN", slug="pay-other", email="admin@pay-other.example"
    )

    mine = (await client.get(PAYMENTS, headers=headers_a)).json()
    theirs = (await client.get(PAYMENTS, headers=headers_b)).json()
    assert len(mine) == 1
    assert theirs == [], "another organization's payments were visible"


async def test_payment_history_exposes_no_secret(client, gateway):
    headers, _tenant, _payment = await _paid_tenant(client, gateway)
    body = (await client.get(PAYMENTS, headers=headers)).json()
    assert body
    text = str(body).lower()
    for secret in ("secret", "signature", "api_key", "apikey", "webhook_secret", "authorization"):
        assert secret not in text, f"{secret} reached a client"
    # What it DOES show is what a support conversation needs.
    assert set(body[0]) >= {"amount", "currency_code", "status", "provider", "provider_reference"}


async def test_the_test_provider_is_refused_in_production():
    """A fake gateway reachable in production is free software, not a test double."""
    from platform_core.core.config import Settings

    with pytest.raises(ValueError, match="must not be 'test' in prod"):
        Settings(
            env="prod",
            jwt_algorithm="HS256",
            jwt_secret="x" * 40,
            minio_secret_key="y" * 20,
            subscription_payment_provider="test",
            subscription_payment_webhook_secret="z" * 20,
        )


async def test_a_provider_without_a_webhook_secret_fails_the_deployment():
    """Without it, an unsigned POST would be proof of payment."""
    from platform_core.core.config import Settings

    with pytest.raises(ValueError, match="WEBHOOK_SECRET is required"):
        Settings(
            env="prod",
            jwt_algorithm="HS256",
            jwt_secret="x" * 40,
            minio_secret_key="y" * 20,
            subscription_payment_provider="test",
        )


async def test_no_credential_is_committed_to_the_payment_source():
    import pathlib
    import re

    import platform_core.modules.subscription as package

    root = pathlib.Path(package.__file__).parent
    pattern = re.compile(
        r"""(api[_-]?key|secret|token|password)\s*=\s*["'][A-Za-z0-9_\-]{12,}["']""",
        re.IGNORECASE,
    )
    offenders = [
        f"{path.name}: {match.group(0)}"
        for path in root.glob("*.py")
        for match in pattern.finditer(path.read_text())
    ]
    assert not offenders, f"a credential is committed: {offenders}"


# --- the wall between platform money and dairy money --------------------------


async def test_paying_lacteva_writes_nothing_to_the_dairy_ledger(client, gateway):
    """The separation the work order insists on, asserted rather than asserted about."""
    from platform_core.modules.payment.models import Payment
    from platform_core.modules.settlement.models import Settlement

    async def counts() -> tuple[int, int]:
        async with db.get_session_factory()() as session:
            return (
                await session.scalar(select(func.count()).select_from(Payment)),
                await session.scalar(select(func.count()).select_from(Settlement)),
            )

    before = await counts()
    headers, _tenant, payment = await _paid_tenant(client, gateway, centres=2)
    body, signed = _deliver(
        gateway,
        event_id="evt_wall",
        kind="payment.succeeded",
        reference=payment["provider_reference"],
        amount=Decimal(payment["amount"]),
        currency=payment["currency_code"],
    )
    await client.post(WEBHOOK, content=body, headers=signed)
    assert (await client.get(SUBSCRIPTION, headers=headers)).json()["status"] == "active"

    assert await counts() == before, "a SaaS payment touched the dairy's financial records"


async def test_the_subscription_module_never_imports_the_dairy_payment_module():
    """A boundary that is only a convention is a boundary until somebody is busy."""
    import pathlib

    import platform_core.modules.subscription as package

    root = pathlib.Path(package.__file__).parent
    offenders = [
        path.name
        for path in root.glob("*.py")
        if "modules.payment" in path.read_text() or "modules.settlement" in path.read_text()
    ]
    assert not offenders, f"the platform's billing reached into the dairy's ledger: {offenders}"
