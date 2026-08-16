"""The vendor boundary on real PostgreSQL (DEMO-031).

`test_gateway_sandbox.py` proves the rules on SQLite. This is the half SQLite
cannot prove: its test stack shares one connection, so nothing races, and it
has no row-level security at all.

The fifteen properties the work order names:

    1        provider configuration isolation
    2, 3     dispatch, and sandbox delivery end to end
    4, 5     duplicate and CONCURRENT dispatch
    6-8      a valid receipt, an invalid one, a replayed one
    9        the delivery state transition
    10, 11   retryable and permanent failure
    12       cross-tenant notification
    13, 14   the settlement and invoice journeys
    15       financial records unchanged

Nothing here opens a socket. The sandbox gateway reaches nobody, and none of
this is evidence that a particular vendor behaves as documented.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

SECRET = "postgres-proof-gateway-secret"
INDIA = "Asia/Kolkata"
KENYA = "Africa/Nairobi"


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
    monkeypatch.setattr(settings, "messaging_mode", "sandbox")
    monkeypatch.setattr(settings, "notification_receipt_secret", SECRET)
    monkeypatch.setattr(
        settings,
        "notification_vendor_templates",
        {"settlement_finalized.whatsapp": "lacteva_settlement_v1"},
    )


@pytest.fixture
def gateway():
    from platform_core.modules.notification.providers import (
        SandboxGatewayProvider,
        register_provider,
        reset_providers,
    )

    reset_providers()
    provider = SandboxGatewayProvider("sms")
    register_provider("sms", provider)
    yield provider
    reset_providers()


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


# --- seeding -------------------------------------------------------------------


async def _make_org(maker, tenant_id: uuid.UUID, *, tz: str = INDIA, currency: str = "INR") -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="gateway proof seed")
        await session.execute(
            text(
                "INSERT INTO organization "
                "(id, name, slug, country_code, org_type, status, currency_code, timezone, "
                " supported_languages, default_locale, created_at) "
                "VALUES (:id, :n, :s, 'IN', 'processor', 'active', :cur, :tz, "
                "        '[\"en\"]', 'en', now())"
            ),
            {
                "id": tenant_id,
                "n": f"Gw {tenant_id}",
                "s": f"gw-{tenant_id}",
                "cur": currency,
                "tz": tz,
            },
        )
        await session.commit()


async def _cleanup(maker, *tenant_ids: uuid.UUID) -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="gateway proof cleanup")
        for tenant_id in tenant_ids:
            for table in ("notification_receipt_event", "notification", "config_entry"):
                await session.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tenant_id}
                )
            await session.execute(text("DELETE FROM organization WHERE id = :t"), {"t": tenant_id})
        await session.commit()


def _settlement_variables() -> dict:
    return {
        "name": "Farmer",
        "number": "STL-2026-000042",
        "gross_amount": "18562.50",
        "net_amount": "18562.50",
        "currency": "INR",
        "line_count": 31,
        "quantity": "412.500",
        "quantity_unit": "kg",
        "period_from": "2026-08-01",
        "period_to": "2026-08-31",
    }


def _invoice_variables() -> dict:
    return {
        "name": "Household",
        "number": "INV-2026-000007",
        "amount": "1250.00",
        "currency": "INR",
        "quantity": "62.000",
        "quantity_unit": "L",
        "previous_balance": "",
        "period_from": "2026-08-01",
        "period_to": "2026-08-31",
        "period": "2026-08-01 - 2026-08-31",
    }


async def _dispatch(
    maker,
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    template_key: str = "settlement_finalized",
    recipient: str = "+919845000101",
    variables: dict | None = None,
):
    """One dispatch, in its own session and transaction."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.service import (
        NotificationRequest,
        NotificationService,
    )

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        result = await NotificationService(session).dispatch(
            NotificationRequest(
                event_id=event_id,
                event_name="settlement.finalized.v1"
                if template_key == "settlement_finalized"
                else "sales.invoice-issued.v1",
                tenant_id=tenant_id,
                template_key=template_key,
                channel="sms",
                recipient=recipient,
                variables=variables
                if variables is not None
                else (
                    _settlement_variables()
                    if template_key == "settlement_finalized"
                    else _invoice_variables()
                ),
            )
        )
        await session.commit()
        return result


async def _rows(maker, tenant_id: uuid.UUID):
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.models import Notification

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        return list(
            (
                await session.scalars(
                    select(Notification).where(Notification.tenant_id == tenant_id)
                )
            ).all()
        )


def _platform_factory(factory):
    from platform_core.core.rls import PlatformSessionFactory

    return PlatformSessionFactory(factory, "gateway proof receipt")


async def _receipt(gateway, factory, *, event_id: str, reference: str, status: str, sign=True):
    from platform_core.core import webhook_security
    from platform_core.modules.notification.receipts import process_receipt

    body = gateway.receipt_body(event_id=event_id, reference=reference, status=status)
    headers = {webhook_security.SIGNATURE_HEADER: gateway.sign(body) if sign else "deadbeef"}
    return await process_receipt(
        provider_name="sandbox-sms",
        body=body,
        headers=headers,
        factory=_platform_factory(factory),
    )


# --- 1: provider configuration isolation ----------------------------------------


async def test_a_tenants_channel_choice_does_not_leak(factory, gateway):
    """Channel selection is a tenant's own configuration row."""
    from platform_core.core.rls import rebind_tenant

    alpha, beta = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, alpha)
    await _make_org(factory, beta, tz=KENYA, currency="KES")

    async with factory() as session:
        await rebind_tenant(session, alpha)
        await session.execute(
            text(
                "INSERT INTO config_entry (id, scope, tenant_id, key, value, updated_at) "
                "VALUES (:id, 'tenant', :t, :k, :v, now())"
            ),
            {
                "id": uuid.uuid4(),
                "t": alpha,
                "k": "notification.channel.settlement_finalized",
                "v": '{"value": "whatsapp"}',
            },
        )
        await session.commit()

    try:
        async with factory() as session:
            await rebind_tenant(session, beta)
            leaked = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM config_entry WHERE key LIKE 'notification.channel.%'"
                    )
                )
            ).scalar_one()
            assert leaked == 0, "another tenant read a provider/channel configuration"
    finally:
        await _cleanup(factory, alpha, beta)


async def test_no_credential_is_stored_in_the_database(factory):
    """§5. A credential in a table is a credential in every backup."""
    async with factory() as session:
        from platform_core.core.rls import bind_platform_context

        await bind_platform_context(session, reason="credential sweep")
        hits = (
            await session.execute(
                text(
                    "SELECT count(*) FROM config_entry "
                    "WHERE key ILIKE '%api_key%' OR key ILIKE '%secret%' OR key ILIKE '%token%'"
                )
            )
        ).scalar_one()
    assert hits == 0, "a credential-shaped key is stored in the configuration table"


# --- 2, 3: dispatch and sandbox delivery ----------------------------------------


async def test_a_settlement_message_goes_through_the_sandbox_gateway(factory, gateway):
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        await _dispatch(factory, tenant_id, uuid.uuid4())
        rows = await _rows(factory, tenant_id)
        assert len(rows) == 1
        message = rows[0]
        assert message.status == "sent", "the gateway accepted it"
        assert message.provider == "sandbox-sms"
        assert message.provider_reference.startswith("sbx-")
        assert message.provider_status == "accepted", "accepted is NOT delivered"
        assert message.delivered_at is None
        assert gateway.sent and gateway.sent[0].parameters, "no parameters reached the gateway"
    finally:
        await _cleanup(factory, tenant_id)


async def test_an_invoice_message_goes_through_the_same_path(factory, gateway):
    """§7 and §13: one path, two journeys — not a second implementation."""
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        await _dispatch(factory, tenant_id, uuid.uuid4(), template_key="invoice_issued")
        message = (await _rows(factory, tenant_id))[0]
        assert message.template_key == "invoice_issued"
        assert message.status == "sent"
        assert message.provider == "sandbox-sms"
        assert "INV-2026-000007" in message.rendered_text
    finally:
        await _cleanup(factory, tenant_id)


# --- 4, 5: duplicates and concurrency -------------------------------------------


async def test_the_same_event_dispatched_repeatedly_calls_the_gateway_once(factory, gateway):
    tenant_id, event_id = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        first = await _dispatch(factory, tenant_id, event_id)
        assert first is not None
        for _ in range(4):
            assert await _dispatch(factory, tenant_id, event_id) is None
        assert len(await _rows(factory, tenant_id)) == 1
        assert len(gateway.sent) == 1, "the gateway was paid twice for one message"
    finally:
        await _cleanup(factory, tenant_id)


async def test_eight_concurrent_dispatches_reach_the_gateway_once(factory, gateway):
    """The production shape: several workers, one financial event.

    Every extra gateway call is a charge and a farmer told twice about the
    same money.
    """
    tenant_id, event_id = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        results = await asyncio.gather(
            *(_dispatch(factory, tenant_id, event_id) for _ in range(8)),
            return_exceptions=True,
        )
        raised = [r for r in results if isinstance(r, Exception)]
        assert not raised, f"a racing dispatch raised: {raised}"
        assert len(await _rows(factory, tenant_id)) == 1
        assert len(gateway.sent) == 1, f"the gateway was called {len(gateway.sent)} times"
    finally:
        await _cleanup(factory, tenant_id)


# --- 6-9: receipts and the state transition -------------------------------------


async def test_a_valid_receipt_marks_the_message_delivered(factory, gateway):
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        await _dispatch(factory, tenant_id, uuid.uuid4())
        message = (await _rows(factory, tenant_id))[0]
        result = await _receipt(
            gateway,
            factory,
            event_id="g1",
            reference=message.provider_reference,
            status="delivered",
        )
        assert result.outcome == "delivered"

        after = (await _rows(factory, tenant_id))[0]
        assert after.status == "delivered"
        assert after.delivered_at is not None
        assert after.provider_status == "delivered"
    finally:
        await _cleanup(factory, tenant_id)


async def test_an_invalid_signature_changes_nothing(factory, gateway):
    from platform_core.modules.notification.providers import ReceiptVerificationError

    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        await _dispatch(factory, tenant_id, uuid.uuid4())
        message = (await _rows(factory, tenant_id))[0]
        with pytest.raises(ReceiptVerificationError):
            await _receipt(
                gateway,
                factory,
                event_id="g2",
                reference=message.provider_reference,
                status="delivered",
                sign=False,
            )
        assert (await _rows(factory, tenant_id))[0].status == "sent"
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_replayed_receipt_does_nothing(factory, gateway):
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        await _dispatch(factory, tenant_id, uuid.uuid4())
        message = (await _rows(factory, tenant_id))[0]
        first = await _receipt(
            gateway,
            factory,
            event_id="g3",
            reference=message.provider_reference,
            status="delivered",
        )
        assert first.outcome == "delivered"
        delivered_at = (await _rows(factory, tenant_id))[0].delivered_at

        for _ in range(3):
            again = await _receipt(
                gateway,
                factory,
                event_id="g3",
                reference=message.provider_reference,
                status="delivered",
            )
            assert again.outcome == "replayed"
        assert (await _rows(factory, tenant_id))[0].delivered_at == delivered_at
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_contradictory_receipt_never_undelivers_a_message(factory, gateway):
    """§9's explicit case, following DEMO-029's transition rules unchanged."""
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        await _dispatch(factory, tenant_id, uuid.uuid4())
        message = (await _rows(factory, tenant_id))[0]
        await _receipt(
            gateway,
            factory,
            event_id="g4a",
            reference=message.provider_reference,
            status="delivered",
        )
        late = await _receipt(
            gateway,
            factory,
            event_id="g4b",
            reference=message.provider_reference,
            status="undelivered",
        )
        assert late.outcome == "ignored_delivered"
        assert (await _rows(factory, tenant_id))[0].status == "delivered"
    finally:
        await _cleanup(factory, tenant_id)


async def test_concurrent_receipts_apply_once(factory, gateway):
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        await _dispatch(factory, tenant_id, uuid.uuid4())
        message = (await _rows(factory, tenant_id))[0]
        results = await asyncio.gather(
            *(
                _receipt(
                    gateway,
                    factory,
                    event_id="g5",
                    reference=message.provider_reference,
                    status="delivered",
                )
                for _ in range(6)
            ),
            return_exceptions=True,
        )
        raised = [r for r in results if isinstance(r, Exception)]
        assert not raised, f"a racing receipt raised: {raised}"
        outcomes = [r.outcome for r in results]
        assert outcomes.count("delivered") == 1, f"more than one applied: {outcomes}"
    finally:
        await _cleanup(factory, tenant_id)


# --- 10, 11: retryable versus permanent ------------------------------------------


async def test_a_transient_gateway_failure_stays_retryable(factory, gateway):
    """The message is failed but SCHEDULED — a retry can still help."""
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        await _dispatch(factory, tenant_id, uuid.uuid4(), recipient="+919845000107")
        message = (await _rows(factory, tenant_id))[0]
        assert message.status == "failed"
        assert message.next_attempt_at is not None, "a transient failure was not scheduled"
        assert message.provider_status is None
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_permanent_rejection_is_not_retried(factory, gateway):
    """§10: an invalid recipient is identical on every retry."""
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        await _dispatch(factory, tenant_id, uuid.uuid4(), recipient="+919845000108")
        message = (await _rows(factory, tenant_id))[0]
        assert message.status == "dead", "a permanent rejection was queued for retry"
        assert message.next_attempt_at is None
        assert message.error
    finally:
        await _cleanup(factory, tenant_id)


async def test_the_mode_gate_is_a_permanent_failure_not_a_retry_loop(factory, monkeypatch):
    """A retry against a mode setting is just a slower refusal."""
    from platform_core.core.config import get_settings
    from platform_core.modules.notification.providers import (
        HttpSmsProvider,
        register_provider,
        reset_providers,
    )

    monkeypatch.setattr(get_settings(), "messaging_mode", "test")
    monkeypatch.setattr(get_settings(), "sms_api_url", "https://gateway.invalid/send")
    monkeypatch.setattr(get_settings(), "sms_api_key", "k" * 20)
    reset_providers()
    register_provider("sms", HttpSmsProvider("sms"))

    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    try:
        await _dispatch(factory, tenant_id, uuid.uuid4())
        message = (await _rows(factory, tenant_id))[0]
        assert message.status == "dead"
        assert "MESSAGING_MODE" in (message.error or ""), message.error
        assert message.sent_at is None
    finally:
        reset_providers()
        await _cleanup(factory, tenant_id)


# --- 12: cross-tenant -------------------------------------------------------------


async def test_notifications_and_receipts_do_not_leak_across_tenants(factory, gateway):
    from platform_core.core.rls import rebind_tenant

    alpha, beta = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, alpha)
    await _make_org(factory, beta, tz=KENYA, currency="KES")

    try:
        await _dispatch(factory, alpha, uuid.uuid4())
        message = (await _rows(factory, alpha))[0]
        await _receipt(
            gateway,
            factory,
            event_id="g6",
            reference=message.provider_reference,
            status="delivered",
        )

        async with factory() as session:
            await rebind_tenant(session, beta)
            for table in ("notification", "notification_receipt_event"):
                leaked = (
                    await session.execute(
                        text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"), {"t": alpha}
                    )
                ).scalar_one()
                assert leaked == 0, f"another tenant read {table}"
            content = (
                await session.execute(
                    text("SELECT count(*) FROM notification WHERE rendered_text LIKE '%STL-%'")
                )
            ).scalar_one()
            assert content == 0, "another tenant read the message content"
    finally:
        await _cleanup(factory, alpha, beta)


# --- 15: financial safety ---------------------------------------------------------


@pytest.mark.parametrize("template_key", ["settlement_finalized", "invoice_issued"])
async def test_gateway_delivery_moves_no_money(factory, gateway, template_key):
    async def snapshot():
        from platform_core.core.rls import bind_platform_context

        async with factory() as session:
            await bind_platform_context(session, reason="financial snapshot")
            row = await session.execute(
                text(
                    "SELECT (SELECT count(*) FROM settlement), "
                    "       (SELECT coalesce(sum(net_amount), 0) FROM settlement), "
                    "       (SELECT count(*) FROM customer_invoice), "
                    "       (SELECT coalesce(sum(amount_due), 0) FROM customer_invoice), "
                    "       (SELECT count(*) FROM payment), "
                    "       (SELECT count(*) FROM receipt), "
                    "       (SELECT count(*) FROM customer_payment), "
                    "       (SELECT count(*) FROM milk_collection_transaction)"
                )
            )
            return tuple(row.first())

    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)

    try:
        before = await snapshot()
        await _dispatch(factory, tenant_id, uuid.uuid4(), template_key=template_key)
        message = (await _rows(factory, tenant_id))[0]
        await _receipt(
            gateway,
            factory,
            event_id=f"g7-{template_key}",
            reference=message.provider_reference,
            status="delivered",
        )
        assert (await _rows(factory, tenant_id))[0].status == "delivered"
        assert await snapshot() == before, "a gateway delivery changed a financial record"
        assert Decimal(str(before[1])) >= 0  # the snapshot really read money
    finally:
        await _cleanup(factory, tenant_id)
