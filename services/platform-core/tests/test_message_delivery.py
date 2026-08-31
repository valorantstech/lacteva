"""Two business journeys, delivered (DEMO-025).

A farmer's settlement slip and a customer's bill, from the financial event that
causes them to the provider that carries them. The property under test:

    **A financial fact produces exactly one message per recipient and channel,
    in the recipient's own language, carrying the tenant's own currency and the
    tenant's own business dates — and the financial fact survives whether or
    not the message does.**

That last clause is the one worth stating plainly: messaging is DOWNSTREAM. A
gateway outage must never roll back a settlement.

**What these tests do NOT prove.** They use recording and failing fakes, not a
real gateway. They prove the pipeline, the templates, the idempotency and the
isolation. They do not prove that any message left the building — that requires
a configured provider and is verified separately.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from platform_core.core import db
from platform_core.modules.notification.models import Notification, NotificationRecipient
from tests.test_notifications import (  # reuse the existing seams, do not build new ones
    _RecordingProvider,
    _runner,
    provider_guard,  # noqa: F401 — fixture
)
from tests.test_org_structure import _tenant_admin


def _month_start() -> str:
    """The first of the month the collection lands in."""
    return date.today().replace(day=1).isoformat()


def _month_end() -> str:
    """The last day of that month, without a calendar dependency."""
    first = date.today().replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return (next_month - timedelta(days=1)).isoformat()


class _FailingProvider:
    """Always fails. Distinguishes 'the pipeline ran' from 'the message went'."""

    name = "always-failing"

    def __init__(self, permanent: bool = False):
        self.attempts = 0
        self.permanent = permanent

    async def send(self, message):
        from platform_core.modules.notification.providers import (
            PermanentSendError,
            ProviderSendError,
        )

        self.attempts += 1
        if self.permanent:
            raise PermanentSendError("gateway rejected the number")
        raise ProviderSendError("gateway unavailable")


class _TimeoutProvider:
    name = "timeout"

    def __init__(self):
        self.attempts = 0

    async def send(self, message):
        from platform_core.modules.notification.providers import ProviderSendError

        self.attempts += 1
        raise ProviderSendError("gateway timeout after 10s")


async def _notifications(template_key: str) -> list[Notification]:
    async with db.get_session_factory()() as session:
        rows = await session.scalars(
            select(Notification).where(Notification.template_key == template_key)
        )
        return list(rows.all())


# --- 1, 2: the provider boundary --------------------------------------------


async def test_the_logging_provider_still_works(provider_guard):  # noqa: F811
    """DEMO-025 must not break the dev default everything else relies on."""
    from platform_core.modules.notification.providers import LoggingProvider, OutboundMessage

    provider = LoggingProvider("sms")
    result = await provider.send(
        OutboundMessage(
            notification_id=uuid.uuid4(),
            channel="sms",
            recipient="+254700000001",
            title="t",
            body="b",
            template_key="k",
            language="en",
        )
    )
    assert result.provider_message_id
    assert provider.name == "logging-sms"


def test_whatsapp_is_a_configurable_channel_not_a_country_branch():
    """The multi-country requirement, asserted at the seam.

    WhatsApp resolves through the same configuration path as every other
    channel. Nothing anywhere asks which country the tenant is in.
    """
    from platform_core.core.config import get_settings
    from platform_core.modules.notification.providers import _build

    settings = get_settings()
    assert hasattr(settings, "notification_whatsapp_provider")
    # Defaults to `disabled`: a deployment that has contracted no gateway must
    # fail visibly rather than record an undelivered message as sent.
    assert settings.notification_whatsapp_provider == "disabled"

    for name in ("logging", "placeholder", "dry_run", "disabled"):
        assert _build("whatsapp", name) is not None


def test_the_whatsapp_provider_refuses_to_start_without_configuration():
    """A missing URL is a startup failure, not a message that goes nowhere."""
    from platform_core.modules.notification.providers import HttpWhatsAppProvider

    with pytest.raises(ValueError, match="LACTEVA_WHATSAPP_API_URL"):
        HttpWhatsAppProvider()


# --- 3, 4, 5, 19: success, failure, timeout, provider reference --------------


async def test_a_delivered_message_records_the_provider_reference(client, provider_guard):  # noqa: F811
    recording = _RecordingProvider()
    provider_guard.register_provider("sms", recording)
    _org, headers = await _tenant_admin(client)
    await _issue_invoice(client, headers)
    await _runner().run_once()

    rows = await _notifications("invoice_issued")
    assert len(rows) == 1
    assert rows[0].status == "sent"
    assert rows[0].provider == "recording"
    assert rows[0].provider_reference, "the provider's own id must be persisted"
    assert rows[0].sent_at is not None


async def test_a_failed_message_records_the_reason_and_stays_failed(client, provider_guard):  # noqa: F811
    failing = _FailingProvider()
    provider_guard.register_provider("sms", failing)
    _org, headers = await _tenant_admin(client)
    await _issue_invoice(client, headers)
    await _runner().run_once()

    rows = await _notifications("invoice_issued")
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].error and "unavailable" in rows[0].error
    assert rows[0].sent_at is None, "nothing was delivered, so nothing may claim it was"
    assert failing.attempts >= 1


async def test_a_gateway_timeout_is_retried_not_abandoned(client, provider_guard):  # noqa: F811
    timing_out = _TimeoutProvider()
    provider_guard.register_provider("sms", timing_out)
    _org, headers = await _tenant_admin(client)
    await _issue_invoice(client, headers)
    await _runner().run_once()

    rows = await _notifications("invoice_issued")
    assert rows[0].status == "failed"
    assert rows[0].next_attempt_at is not None, "a timeout must be scheduled for retry"


async def test_a_recovering_gateway_delivers_on_retry(client, provider_guard):  # noqa: F811
    """Fails once, then succeeds — and the row ends up sent, once."""
    flaky = _RecordingProvider(fail_times=1)
    provider_guard.register_provider("sms", flaky)
    _org, headers = await _tenant_admin(client)
    await _issue_invoice(client, headers)
    await _runner().run_once()

    rows = await _notifications("invoice_issued")
    assert rows[0].status == "failed", "the premise: the first attempt failed"

    from platform_core.modules.notification.service import NotificationService

    async with db.get_session_factory()() as session:
        await NotificationService(session).retry(rows[0].id)
        await session.commit()

    rows = await _notifications("invoice_issued")
    assert len(rows) == 1, "a retry must not create a second message"
    assert rows[0].status == "sent"
    assert len(flaky.sent) == 1


# --- 6, 7, 8, 20: idempotency -----------------------------------------------


async def test_running_the_worker_twice_sends_one_message(client, provider_guard):  # noqa: F811
    """The duplicate-prevention property, through the real consumer."""
    recording = _RecordingProvider()
    provider_guard.register_provider("sms", recording)
    _org, headers = await _tenant_admin(client)
    await _issue_invoice(client, headers)

    await _runner().run_once()
    await _runner().run_once()
    await _runner().run_once()

    rows = await _notifications("invoice_issued")
    assert len(rows) == 1, "one financial event, one message"
    assert len(recording.sent) == 1, "the gateway must be called once"


# --- 9, 11, 12, 13, 14: the farmer settlement journey ------------------------


async def _settlement_env(client):
    from tests.test_notifications import _accept_complete, _procurement_env, _run_collection
    from tests.test_settlements import _create_settlement

    headers, center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])
    settlement = await _create_settlement(
        client,
        headers,
        supplier["id"],
        center["id"],
        # The period must CONTAIN the collection this settles, and the
        # collection happens today. Hard-coded August dates passed for as long
        # as it was August and began failing on 1 September in every suite that
        # used this fixture — a settlement whose period excludes its own
        # collection has no lines, and cannot be finalized.
        period_from=_month_start(),
        period_to=_month_end(),
    )
    # collect -> calculate -> finalize is the domain's own sequence, and a
    # settlement with no lines cannot be finalized at all.
    collected = await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    assert collected.status_code == 200, collected.text
    r = await client.post(f"/v1/settlements/{settlement['id']}/calculate", headers=headers)
    assert r.status_code == 200, r.text
    return headers, supplier, settlement


async def test_a_farmer_settlement_slip_carries_the_financial_truth(client, provider_guard):  # noqa: F811
    """DEMO A. Every figure is read from the settlement, none is computed here."""
    recording = _RecordingProvider()
    provider_guard.register_provider("sms", recording)
    headers, _supplier, settlement = await _settlement_env(client)

    r = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    assert r.status_code == 200, r.text
    finalized = r.json()
    await _runner().run_once()

    rows = await _notifications("settlement_finalized")
    assert len(rows) == 1
    body = rows[0].rendered_text
    assert finalized["settlement_number"] in body
    assert str(finalized["net_amount"]) in body, "the net must be the settlement's own"
    assert finalized["currency"] in body, "the tenant's currency, never converted"
    # Derived, not hard-coded: the period follows the collection's own month,
    # so this assertion is about the slip carrying the settlement's dates
    # rather than about which month the suite happens to run in.
    assert _month_start() in body and _month_end() in body, "the settlement's business dates"
    assert "{" not in body, "every variable must be substituted"


@pytest.mark.parametrize(
    "language,marker",
    [("en", "Settlement"), ("hi", "भुगतान"), ("ar", "تسوية"), ("sw", "Malipo")],
)
def test_the_settlement_slip_exists_in_every_supported_language(language, marker):
    from platform_core.modules.notification.templates import get_template, render

    template = get_template("settlement_finalized", "sms", language)
    assert template.language == language
    message = render(
        template,
        {
            "name": "Farmer",
            "number": "STL-2026-000001",
            "period_from": "2026-08-01",
            "period_to": "2026-08-31",
            "gross_amount": "5647.50",
            "net_amount": "5647.50",
            "currency": "KES",
            "line_count": 2,
        },
    )
    assert marker in message.title or marker in message.body
    assert "5647.50" in message.body and "KES" in message.body
    assert "{" not in message.body


@pytest.mark.parametrize("language", ["en", "hi", "ar"])
def test_the_invoice_message_exists_in_every_supported_language(language):
    from platform_core.modules.notification.templates import (
        get_template,
        render,
        select_template_key,
    )

    for channel in ("sms", "whatsapp"):
        # DEMO-033: on WhatsApp the journey resolves to a fixed-parameter
        # variant, so ask for it the way dispatch does.
        resolved = select_template_key("invoice_issued", channel, {})
        template = get_template(resolved, channel, language)
        message = render(
            template,
            {
                "name": "Household",
                "number": "INV-2026-000001",
                "amount": "1250.00",
                "currency": "INR",
                "period_from": "2026-08-01",
                "period_to": "2026-08-31",
            },
        )
        assert "1250.00" in message.body and "INR" in message.body
        assert "{" not in message.body


def test_currency_is_never_converted_only_carried():
    """A rupee invoice says INR wherever it is read."""
    from platform_core.modules.notification.templates import get_template, render

    for currency in ("INR", "KES", "QAR"):
        message = render(
            get_template("invoice_issued", "sms", "en"),
            {
                "name": "H",
                "number": "INV-1",
                "amount": "100.00",
                "currency": currency,
                "period_from": "2026-08-01",
                "period_to": "2026-08-31",
            },
        )
        assert currency in message.body


# --- 10: the customer invoice journey ---------------------------------------


async def _choose_channel(client, headers, template_key: str, channel: str) -> None:
    """Point a template at a channel, the way a dairy would.

    The invoice default remains `push` (DEMO-012's journey, untouched). A dairy
    whose households have no app configures its way to SMS or WhatsApp — so
    every invoice test below exercises the configuration path rather than
    relying on a default nobody chose.
    """
    import uuid as _uuid

    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.configuration.service import ConfigurationService

    me = (await client.get("/v1/auth/me", headers=headers)).json()
    tenant_id = _uuid.UUID(me["tenant_id"])
    async with db.get_session_factory()() as session:
        set_current_tenant(tenant_id)
        await ConfigurationService(session, AuditService(session)).set_value(
            f"notification.channel.{template_key}", channel, scope="tenant", actor_id=None
        )
        await session.commit()
    set_current_tenant(None)


async def _issue_invoice(client, headers, *, channel: str = "sms"):
    """One household, one delivery, one issued invoice — billed over `channel`."""
    await _choose_channel(client, headers, "invoice_issued", channel)
    from tests.test_daily_operations import _customer, _deliver

    customer = await _customer(
        client, headers, name="Message Household", quantity="2.000", price="50.0000"
    )
    day = date(2026, 8, 12)
    await _deliver(client, headers, customer["id"], day)
    draft = (
        await client.post(
            "/v1/invoices",
            json={
                "customer_id": customer["id"],
                "period_from": str(day),
                "period_to": str(day),
            },
            headers=headers,
        )
    ).json()
    r = await client.post(f"/v1/invoices/{draft['id']}/issue", json={}, headers=headers)
    assert r.status_code == 200, r.text
    return customer, r.json()


async def test_a_customer_invoice_message_carries_the_invoice(client, provider_guard):  # noqa: F811
    """DEMO B. The amount is the invoice's, not a second calculation."""
    recording = _RecordingProvider()
    provider_guard.register_provider("sms", recording)
    _org, headers = await _tenant_admin(client)
    _customer, invoice = await _issue_invoice(client, headers)
    await _runner().run_once()

    rows = await _notifications("invoice_issued")
    assert len(rows) == 1
    body = rows[0].rendered_text
    assert invoice["invoice_number"] in body
    assert str(invoice["amount_due"]) in body, "the invoice's own amount"
    assert invoice["currency"] in body
    assert "2026-08-12" in body, "the invoice's business dates, not a UTC slice"
    # And it actually went to the household's own number — the mechanism that
    # makes a customer reachable at all, since the directory holds suppliers.
    assert rows[0].recipient == _customer["phone"], "the bill must reach the household"


# --- 17: the financial record survives a failed message ---------------------


async def test_a_settlement_survives_a_gateway_outage(client, provider_guard):  # noqa: F811
    """Messaging is downstream. A dead gateway must not unmake money."""
    provider_guard.register_provider("sms", _FailingProvider())
    headers, _supplier, settlement = await _settlement_env(client)

    r = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    assert r.status_code == 200, r.text
    await _runner().run_once()

    # The message failed...
    rows = await _notifications("settlement_finalized")
    assert rows and rows[0].status == "failed"

    # ...and the settlement is still finalised, with its money intact.
    after = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    body = after.get("settlement", after)
    assert body["status"] == "finalized"
    assert body["net_amount"] == r.json()["net_amount"]


async def test_an_invoice_survives_a_gateway_outage(client, provider_guard):  # noqa: F811
    provider_guard.register_provider("sms", _FailingProvider(permanent=True))
    _org, headers = await _tenant_admin(client)
    _customer, invoice = await _issue_invoice(client, headers)
    await _runner().run_once()

    rows = await _notifications("invoice_issued")
    # A permanent rejection is `dead`, not `failed`: retrying an unknown
    # number cannot change the outcome, so the platform stops rather than
    # spending gateway calls. Either way nothing was delivered.
    assert rows and rows[0].status == "dead"
    assert rows[0].sent_at is None

    after = (await client.get(f"/v1/invoices/{invoice['id']}", headers=headers)).json()
    assert after["invoice"]["status"] == "issued"
    assert after["invoice"]["amount_due"] == invoice["amount_due"]


# --- 15, 16: tenant and recipient isolation ---------------------------------


async def test_one_tenant_cannot_read_anothers_messages(client, provider_guard):  # noqa: F811
    from tests.test_localization import _tenant_admin_for

    provider_guard.register_provider("sms", _RecordingProvider())
    _a, admin_a = await _tenant_admin_for(
        client, country="IN", slug="msg-a", email="msg-a@india.example"
    )
    _b, admin_b = await _tenant_admin_for(
        client, country="KE", slug="msg-b", email="msg-b@kenya.example"
    )
    await _issue_invoice(client, admin_a)
    await _runner().run_once()

    def _keys(page):
        return {row["template_key"] for row in page["items"]}

    a_page = (await client.get("/v1/notifications", headers=admin_a)).json()
    b_page = (await client.get("/v1/notifications", headers=admin_b)).json()

    # B has its own onboarding messages, which is correct and not the point.
    # The point is that A's invoice message is not among them.
    assert "invoice_issued" in _keys(a_page), "the premise: A's bill produced a message"
    assert "invoice_issued" not in _keys(b_page), (
        "another tenant's invoice message must be invisible"
    )


async def test_notification_history_requires_authentication(client):
    assert (await client.get("/v1/notifications")).status_code == 401


async def test_a_recipient_directory_entry_belongs_to_one_tenant(client, provider_guard):  # noqa: F811
    """Recipients are tenant-scoped; a phone number is not global."""
    from tests.test_localization import _tenant_admin_for

    provider_guard.register_provider("sms", _RecordingProvider())
    org_a, _admin_a = await _tenant_admin_for(
        client, country="IN", slug="rcp-a", email="rcp-a@india.example"
    )
    _b, _admin_b = await _tenant_admin_for(
        client, country="KE", slug="rcp-b", email="rcp-b@kenya.example"
    )
    _headers, supplier, _settlement = await _settlement_env(client)
    await _runner().run_once()

    async with db.get_session_factory()() as session:
        rows = list(
            (
                await session.scalars(
                    select(NotificationRecipient).where(
                        NotificationRecipient.subject_id == uuid.UUID(supplier["id"])
                    )
                )
            ).all()
        )
    assert rows, "the supplier must be in a directory"
    assert len({r.tenant_id for r in rows}) == 1, "one recipient, one tenant"
    assert uuid.UUID(org_a["id"]) not in {r.tenant_id for r in rows}


# --- 18: no secrets in logs -------------------------------------------------


def test_phone_numbers_are_masked_before_they_reach_a_log():
    from platform_core.modules.notification.providers import mask_phone

    masked = mask_phone("+919845000101")
    assert "9845000101" not in masked
    assert masked.endswith("0101") or "*" in masked


def test_no_provider_credential_is_ever_rendered_into_a_message():
    """A template may not reference a setting, and none does."""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src/platform_core/modules/notification/templates.py"
    ).read_text()
    # Provider CREDENTIALS specifically. `{invite_token}` is a deliberate
    # secret variable — the invitation's one-time token, handled by the
    # secret-payload path — and its presence is correct, not a leak.
    for forbidden in ("api_key", "API_KEY", "Authorization", "smtp_password", "_api_key"):
        assert forbidden not in source, f"the template catalog mentions {forbidden}"


def test_the_http_providers_do_not_log_their_credentials():
    """The Authorization header must never be handed to the logger."""
    import pathlib
    import re

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src/platform_core/modules/notification/providers.py"
    ).read_text()
    for line in source.splitlines():
        if "log." in line and ("_api_key" in line or "Authorization" in line):
            raise AssertionError(f"a credential reaches a log line: {line.strip()}")
    # And the header is built from configuration rather than from the message.
    assert re.search(r'"Authorization":\s*f"Bearer \{self\._api_key\}"', source)


# --- the channel is a tenant's choice, never a country's --------------------


def test_no_country_decides_a_channel():
    """The architectural rule of this milestone, asserted against the source."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src/platform_core"
    for path in (
        root / "modules/notification/service.py",
        root / "modules/notification/providers.py",
        root / "consumers/notification_dispatch.py",
    ):
        source = path.read_text()
        for marker in ('country == "IN"', 'country == "KE"', 'country == "QA"', "country_code =="):
            assert marker not in source, f"{path.name} branches on country: {marker}"


async def test_a_tenant_may_choose_whatsapp_without_any_country_logic(client, provider_guard):  # noqa: F811
    """Configuration moves the channel; nothing else changes."""
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.notification.service import resolve_channel

    _org, headers = await _tenant_admin(client)
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    tenant_id = uuid.UUID(me["tenant_id"])

    async with db.get_session_factory()() as session:
        set_current_tenant(tenant_id)
        # Nothing configured: the mapping's own default stands.
        assert await resolve_channel(session, "invoice_issued", "sms") == "sms"

        from platform_core.modules.audit.service import AuditService
        from platform_core.modules.configuration.service import ConfigurationService

        await ConfigurationService(session, AuditService(session)).set_value(
            "notification.channel.invoice_issued",
            "whatsapp",
            scope="tenant",
            actor_id=None,
        )
        await session.commit()
        assert await resolve_channel(session, "invoice_issued", "sms") == "whatsapp"

        # A nonsense value falls back rather than stopping the message.
        await ConfigurationService(session, AuditService(session)).set_value(
            "notification.channel.invoice_issued", "carrier-pigeon", scope="tenant", actor_id=None
        )
        await session.commit()
        assert await resolve_channel(session, "invoice_issued", "sms") == "sms"
    set_current_tenant(None)
