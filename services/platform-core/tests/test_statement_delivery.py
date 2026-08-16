"""Settlement statements and customer bills a person can act on (DEMO-028).

DEMO-025 built both journeys; this file is about what they were not yet saying
and what the platform was claiming that it could not know.

The properties under test:

    **A farmer is told how much milk the money is for. A household can tell
    this period's charge from what it already owed. Both are in their own
    language on whatever channel their dairy chose. And Lacteva never says a
    message was delivered when all it knows is that a gateway took it.**

Nothing here computes money. Every figure is read from a finalized settlement
or an issued invoice, and a test at the end asserts that running the whole
journey moves no financial total at all.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from platform_core.core import db
from platform_core.modules.notification.models import Notification
from platform_core.modules.notification.templates import (
    TEMPLATES,
    Template,
    TemplateRenderError,
    get_template,
    render,
)
from tests.test_message_delivery import _settlement_env
from tests.test_notifications import (  # reuse the existing seams
    _RecordingProvider,
    _runner,
    provider_guard,  # noqa: F401 — fixture
)

SETTLEMENT = "settlement_finalized"
INVOICE = "invoice_issued"
#: The two messages a dairy sends its own people, and the ones a tenant may
#: point at a different channel.
BUSINESS_TEMPLATES = (SETTLEMENT, INVOICE)


async def _notifications(template_key: str) -> list[Notification]:
    async with db.get_session_factory()() as session:
        rows = await session.scalars(
            select(Notification).where(Notification.template_key == template_key)
        )
        return list(rows.all())


# --- the optional-segment engine ---------------------------------------------


def test_an_optional_segment_disappears_when_its_variable_is_absent():
    """The whole reason the syntax exists.

    A retry re-renders from the payload STORED on the row, so a template that
    gained a REQUIRED variable would break every notification already in the
    table — production held 17 retryable bills whose payloads predate this
    milestone. An optional segment lets the template grow without rewriting
    history.
    """
    template = Template(
        key="t",
        channel="sms",
        language="en",
        title="Bill {number}",
        body="Your bill {number} is {amount}[[ for {quantity} {unit}]].",
    )
    assert template.variables == ("number", "amount")
    assert set(template.optional_variables) == {"quantity", "unit"}

    old_payload = render(template, {"number": "INV-1", "amount": "500"})
    assert old_payload.body == "Your bill INV-1 is 500."

    new_payload = render(
        template, {"number": "INV-1", "amount": "500", "quantity": "40", "unit": "L"}
    )
    assert new_payload.body == "Your bill INV-1 is 500 for 40 L."


def test_a_half_supplied_optional_segment_is_dropped_not_half_rendered():
    """ "for 40 " is worse than saying nothing."""
    template = Template(
        key="t",
        channel="sms",
        language="en",
        title="x",
        body="Total {amount}[[ for {quantity} {unit}]].",
    )
    assert render(template, {"amount": "9", "quantity": "40", "unit": ""}).body == "Total 9."
    assert render(template, {"amount": "9", "quantity": "", "unit": "L"}).body == "Total 9."


def test_a_required_variable_is_still_an_error():
    """The guarantee the optional syntax must not weaken."""
    template = Template(
        key="t", channel="sms", language="en", title="x", body="Settlement {number} is {amount}."
    )
    with pytest.raises(TemplateRenderError):
        render(template, {"number": "STL-1"})


# --- the catalog --------------------------------------------------------------


@pytest.mark.parametrize("key", BUSINESS_TEMPLATES)
def test_a_business_message_offers_the_same_languages_on_every_channel(key):
    """The gap this milestone closed, pinned so it cannot reopen.

    A Kenyan dairy that chose WhatsApp for its bills received ENGLISH ones,
    because `invoice_issued` had no Swahili WhatsApp template and the language
    fallback is SILENT. The same dairy's SMS bills were in Swahili. Nothing
    surfaced the difference — a fallback that works is exactly the kind that
    nobody notices.
    """
    by_channel: dict[str, set[str]] = {}
    for template in TEMPLATES:
        if template.key == key:
            by_channel.setdefault(template.channel, set()).add(template.language)
    assert by_channel, f"no templates at all for {key}"
    languages = set.union(*by_channel.values())
    missing = {
        channel: sorted(languages - offered)
        for channel, offered in by_channel.items()
        if languages - offered
    }
    assert not missing, (
        f"{key} silently falls back to English on: {missing} — "
        "a tenant switching channel must not also switch language"
    )


@pytest.mark.parametrize("key", BUSINESS_TEMPLATES)
@pytest.mark.parametrize("language", ["en", "hi", "ar", "sw"])
def test_every_business_message_renders_in_every_language(key, language):
    """Rendered, not merely present — the catalog-without-callers defect."""
    for channel in ("sms", "whatsapp", "email"):
        template = get_template(key, channel, language)
        assert template.language == language, (
            f"{key}/{channel} fell back to {template.language} for {language}"
        )
        variables = {name: "X" for name in template.variables}
        message = render(template, variables)
        assert message.body.strip()
        assert "{" not in message.body, "a placeholder survived rendering"


# --- the farmer's statement ---------------------------------------------------


async def test_the_settlement_slip_says_how_much_milk_the_money_is_for(client, provider_guard):  # noqa: F811
    """DEMO A. The figure the slip was missing, and the one a farmer checks first."""
    recording = _RecordingProvider()
    provider_guard.register_provider("sms", recording)

    headers, _supplier, settlement = await _settlement_env(client)
    finalized = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    assert finalized.status_code == 200, finalized.text
    await _runner().run_once()

    rows = await _notifications(SETTLEMENT)
    assert len(rows) == 1
    slip = rows[0]

    # The quantity is on the message AND is the settlement's own.
    quantity = slip.payload["quantity"]
    assert Decimal(quantity) > 0
    assert slip.payload["quantity_unit"]
    assert quantity in slip.rendered_text
    assert slip.payload["quantity_unit"] in slip.rendered_text
    # And it is still the settlement's money, unchanged.
    assert finalized.json()["net_amount"] in slip.rendered_text


async def test_the_settlement_slip_names_the_settlement_it_is_about(client, provider_guard):  # noqa: F811
    """§11. 'What did STL-000123 tell this farmer?' is one query now."""
    provider_guard.register_provider("sms", _RecordingProvider())
    headers, _supplier, settlement = await _settlement_env(client)
    await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    await _runner().run_once()

    rows = await _notifications(SETTLEMENT)
    assert rows[0].source_type == "settlement"
    assert rows[0].source_id == uuid.UUID(settlement["id"])


# --- the provider's word versus ours ------------------------------------------


async def test_the_platform_records_what_the_provider_said_not_what_it_hopes(
    client,
    provider_guard,  # noqa: F811
):
    """§12, and the defect this milestone found.

    `status = "sent"` is what LACTEVA did. `provider_status` is what the
    GATEWAY said, and for every adapter here that is `accepted`. They were one
    column, which is how the portal came to call an accepted request a
    delivery.
    """
    provider_guard.register_provider("sms", _RecordingProvider())
    headers, _supplier, settlement = await _settlement_env(client)
    await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    await _runner().run_once()

    slip = (await _notifications(SETTLEMENT))[0]
    assert slip.status == "sent", "the platform handed it over"
    assert slip.provider_status == "accepted", "and the gateway only ACCEPTED it"
    assert slip.provider_status != "delivered", (
        "no adapter in this platform receives a delivery receipt, so none may claim one"
    )


def test_no_provider_in_this_platform_claims_delivery():
    """The claim the portal was making, checked at its source.

    If an adapter ever DOES receive delivery receipts this test should be
    updated deliberately — which is the point of asserting it.
    """
    from platform_core.modules.notification import providers

    text = (providers.HttpSmsProvider.send.__doc__ or "") + (
        providers.LoggingProvider.send.__doc__ or ""
    )
    del text  # documentation is not the assertion; the default is
    from platform_core.modules.notification.providers import ACCEPTED, DeliveryResult

    assert DeliveryResult(provider_message_id="x").status == ACCEPTED


# --- the household's bill -----------------------------------------------------


async def test_the_bill_says_how_much_milk_it_is_for(client, provider_guard):  # noqa: F811
    """DEMO B. A household can check the bill against what arrived."""
    from tests.test_message_delivery import _issue_invoice
    from tests.test_org_structure import _tenant_admin

    provider_guard.register_provider("sms", _RecordingProvider())
    _org, headers = await _tenant_admin(client)
    _customer, invoice = await _issue_invoice(client, headers)
    await _runner().run_once()

    bill = (await _notifications(INVOICE))[0]
    assert Decimal(bill.payload["quantity"]) > 0
    assert bill.payload["quantity_unit"]
    assert bill.payload["quantity"] in bill.rendered_text
    # Still the invoice's own money.
    assert str(invoice["amount_due"]) in bill.rendered_text


async def test_a_bill_with_nothing_carried_forward_says_nothing_about_it(
    client,
    provider_guard,  # noqa: F811
):
    """A zero brought-forward line is noise, so the segment drops.

    This is the optional-segment engine doing the job it exists for: the line
    appears when it means something and is absent when it does not, without a
    second template and without a conditional in the consumer.
    """
    from tests.test_message_delivery import _issue_invoice
    from tests.test_org_structure import _tenant_admin

    provider_guard.register_provider("whatsapp", _RecordingProvider())
    _org, headers = await _tenant_admin(client)
    _customer, invoice = await _issue_invoice(client, headers, channel="whatsapp")
    await _runner().run_once()

    bill = (await _notifications(INVOICE))[0]
    assert Decimal(invoice["previous_balance"]) == 0, "the premise: nothing carried"
    assert bill.payload["previous_balance"] == ""
    assert "Brought forward" not in bill.rendered_text
    # And the line that DOES mean something is there.
    assert "Delivered:" in bill.rendered_text


async def test_the_bill_names_the_invoice_it_is_about(client, provider_guard):  # noqa: F811
    from tests.test_message_delivery import _issue_invoice
    from tests.test_org_structure import _tenant_admin

    provider_guard.register_provider("sms", _RecordingProvider())
    _org, headers = await _tenant_admin(client)
    _customer, invoice = await _issue_invoice(client, headers)
    await _runner().run_once()

    bill = (await _notifications(INVOICE))[0]
    assert bill.source_type == "customer_invoice"
    assert bill.source_id == uuid.UUID(invoice["id"])


# --- financial safety ---------------------------------------------------------


async def test_sending_statements_moves_no_money(client, provider_guard):  # noqa: F811
    """§18, asserted rather than asserted about.

    The messaging layer READS financial truth. If it ever became financial
    truth, this is the test that would say so.
    """
    from platform_core.modules.billing.models import CustomerInvoice
    from platform_core.modules.payment.models import Payment
    from platform_core.modules.receipt.models import Receipt
    from platform_core.modules.settlement.models import Settlement

    async def snapshot():
        async with db.get_session_factory()() as session:
            return {
                "settlements": await session.scalar(select(func.count()).select_from(Settlement)),
                "settlement_net": await session.scalar(
                    select(func.coalesce(func.sum(Settlement.net_amount), 0))
                ),
                "invoices": await session.scalar(select(func.count()).select_from(CustomerInvoice)),
                "invoiced": await session.scalar(
                    select(func.coalesce(func.sum(CustomerInvoice.amount_due), 0))
                ),
                "payments": await session.scalar(select(func.count()).select_from(Payment)),
                "receipts": await session.scalar(select(func.count()).select_from(Receipt)),
            }

    provider_guard.register_provider("sms", _RecordingProvider())
    headers, _supplier, settlement = await _settlement_env(client)
    await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)

    before = await snapshot()
    # Everything from here is MESSAGING: consuming the event, rendering,
    # dispatching, and retrying what failed.
    await _runner().run_once()
    await _runner().run_once()
    assert await _notifications(SETTLEMENT), "the premise: a message was produced"

    assert await snapshot() == before, "sending a statement changed a financial record"
