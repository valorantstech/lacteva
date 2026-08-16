"""Delivery receipts and reachability on real PostgreSQL (DEMO-029).

`test_delivery_receipts.py` proves the rules on SQLite. This is the half SQLite
cannot prove: its test stack shares one connection, so nothing races, and it
has no row-level security at all.

The sixteen properties the work order names, in its order:

    1-3    a valid receipt, a duplicate, and two arriving CONCURRENTLY
    4, 5   an invalid signature and a replayed event
    6      a receipt naming a message this platform does not know
    7, 8   out-of-order events and transition safety
    9      cross-tenant isolation
    10-14  reachability: missing phone, invalid phone, disabled channel,
           unknown WhatsApp capability
    15, 16 neither settlement nor invoice communication moves money

The expensive failure here is not a duplicate row. It is telling an operator
that a farmer was told about their money when they were not.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

SECRET = "postgres-proof-receipt-secret"
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
    monkeypatch.setattr(settings, "notification_receipt_secret", SECRET)


@pytest.fixture
def gateway():
    from platform_core.modules.notification.providers import (
        ReceiptTestProvider,
        register_provider,
        reset_providers,
    )

    reset_providers()
    provider = ReceiptTestProvider("sms")
    register_provider("sms", provider)
    yield provider
    reset_providers()


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


def _platform_factory(factory):
    from platform_core.core.rls import PlatformSessionFactory

    return PlatformSessionFactory(factory, "notification delivery receipt (test)")


async def _make_org(maker, tenant_id: uuid.UUID, *, tz: str = INDIA, currency: str = "INR") -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="receipt proof seed")
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
                "n": f"Rcpt {tenant_id}",
                "s": f"rcpt-{tenant_id}",
                "cur": currency,
                "tz": tz,
            },
        )
        await session.commit()


async def _seed_notification(
    maker, tenant_id: uuid.UUID, *, reference: str, status: str = "sent"
) -> uuid.UUID:
    """A message already handed to the gateway and accepted."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.models import Notification

    notification_id = uuid.uuid4()
    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        session.add(
            Notification(
                id=notification_id,
                tenant_id=tenant_id,
                event_id=uuid.uuid4(),
                event_name="settlement.finalized.v1",
                template_key="settlement_finalized",
                channel="sms",
                language="en",
                recipient="+919845000101",
                payload={"number": "STL-1", "period_from": "2026-08-01", "period_to": "2026-08-31"},
                rendered_text="Settlement STL-1 is finalised.",
                status=status,
                provider="receipt-test",
                provider_reference=reference,
                provider_status="accepted",
                source_type="settlement",
                source_id=uuid.uuid4(),
            )
        )
        await session.commit()
    return notification_id


async def _reload(maker, tenant_id: uuid.UUID, notification_id: uuid.UUID):
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.models import Notification

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        return await session.get(Notification, notification_id)


async def _events(maker, tenant_id: uuid.UUID) -> int:
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.models import NotificationReceiptEvent

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        return (
            await session.scalar(
                select(func.count())
                .select_from(NotificationReceiptEvent)
                .where(NotificationReceiptEvent.tenant_id == tenant_id)
            )
        ) or 0


async def _cleanup(maker, *tenant_ids: uuid.UUID) -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="receipt proof cleanup")
        for tenant_id in tenant_ids:
            await session.execute(
                text("DELETE FROM notification_receipt_event WHERE tenant_id = :t"),
                {"t": tenant_id},
            )
            await session.execute(
                text("DELETE FROM notification WHERE tenant_id = :t"), {"t": tenant_id}
            )
            await session.execute(text("DELETE FROM organization WHERE id = :t"), {"t": tenant_id})
        await session.commit()


async def _post(gateway, factory, *, event_id: str, reference: str, status: str, sign: bool = True):
    from platform_core.core import webhook_security
    from platform_core.modules.notification.receipts import process_receipt

    body = gateway.receipt_body(event_id=event_id, reference=reference, status=status)
    headers = {webhook_security.SIGNATURE_HEADER: gateway.sign(body) if sign else "deadbeef"}
    return await process_receipt(
        provider_name="receipt-test",
        body=body,
        headers=headers,
        factory=_platform_factory(factory),
    )


# --- 1: a valid receipt --------------------------------------------------------


async def test_a_valid_receipt_marks_a_message_delivered(factory, gateway):
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    notification_id = await _seed_notification(factory, tenant_id, reference="ref-1")

    try:
        result = await _post(gateway, factory, event_id="e1", reference="ref-1", status="delivered")
        assert result.outcome == "delivered"
        row = await _reload(factory, tenant_id, notification_id)
        assert row.status == "delivered"
        assert row.delivered_at is not None
        assert row.provider_status == "delivered"
        assert await _events(factory, tenant_id) == 1
    finally:
        await _cleanup(factory, tenant_id)


# --- 2, 5: duplicates and replays ---------------------------------------------


async def test_the_same_receipt_five_times_acts_once(factory, gateway):
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    notification_id = await _seed_notification(factory, tenant_id, reference="ref-2")

    try:
        first = await _post(gateway, factory, event_id="e2", reference="ref-2", status="delivered")
        assert first.outcome == "delivered"
        delivered_at = (await _reload(factory, tenant_id, notification_id)).delivered_at

        for _ in range(4):
            again = await _post(
                gateway, factory, event_id="e2", reference="ref-2", status="delivered"
            )
            assert again.outcome == "replayed"

        row = await _reload(factory, tenant_id, notification_id)
        assert row.delivered_at == delivered_at, "a replay moved the delivery time"
        assert await _events(factory, tenant_id) == 1
    finally:
        await _cleanup(factory, tenant_id)


# --- 3: concurrency ------------------------------------------------------------


async def test_eight_concurrent_deliveries_of_one_receipt_act_once(factory, gateway):
    """The production shape: a gateway retrying a callback it is unsure about.

    `(provider, event_id)` is unique, and a constraint is only proven by
    writers racing at it. A `SELECT`-then-`INSERT` would let two of these
    through and the second would find a message already delivered.
    """
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    notification_id = await _seed_notification(factory, tenant_id, reference="ref-3")

    try:
        results = await asyncio.gather(
            *(
                _post(gateway, factory, event_id="e3", reference="ref-3", status="delivered")
                for _ in range(8)
            ),
            return_exceptions=True,
        )
        raised = [r for r in results if isinstance(r, Exception)]
        assert not raised, f"a racing receipt raised: {raised}"

        outcomes = sorted(r.outcome for r in results)
        assert outcomes.count("delivered") == 1, f"more than one delivery applied: {outcomes}"
        assert outcomes.count("replayed") == 7

        assert await _events(factory, tenant_id) == 1
        assert (await _reload(factory, tenant_id, notification_id)).status == "delivered"
    finally:
        await _cleanup(factory, tenant_id)


# --- 4: an invalid signature ---------------------------------------------------


async def test_an_invalid_signature_changes_nothing(factory, gateway):
    from platform_core.modules.notification.providers import ReceiptVerificationError

    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    notification_id = await _seed_notification(factory, tenant_id, reference="ref-4")

    try:
        with pytest.raises(ReceiptVerificationError):
            await _post(
                gateway, factory, event_id="e4", reference="ref-4", status="delivered", sign=False
            )
        row = await _reload(factory, tenant_id, notification_id)
        assert row.status == "sent"
        assert row.delivered_at is None
        assert await _events(factory, tenant_id) == 0
    finally:
        await _cleanup(factory, tenant_id)


# --- 6: an unknown message -----------------------------------------------------


async def test_a_receipt_for_an_unknown_message_records_nothing(factory, gateway):
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    try:
        result = await _post(
            gateway, factory, event_id="e6", reference="no-such-ref", status="delivered"
        )
        assert result.outcome == "unknown_reference"
        assert await _events(factory, tenant_id) == 0
    finally:
        await _cleanup(factory, tenant_id)


# --- 7, 8: out-of-order and transition safety ---------------------------------


async def test_a_failure_arriving_after_a_delivery_does_not_undeliver_it(factory, gateway):
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    notification_id = await _seed_notification(factory, tenant_id, reference="ref-7")

    try:
        await _post(gateway, factory, event_id="e7a", reference="ref-7", status="delivered")
        late = await _post(
            gateway, factory, event_id="e7b", reference="ref-7", status="undelivered"
        )
        assert late.outcome == "ignored_delivered"

        row = await _reload(factory, tenant_id, notification_id)
        assert row.status == "delivered"
        assert row.delivered_at is not None
        # Both reports are on the ledger — the second was recognised and
        # correctly ignored, which is not the same as unseen.
        assert await _events(factory, tenant_id) == 2
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_delivery_arriving_after_a_failure_is_believed(factory, gateway):
    """A gateway that failed and then delivered has told us something later."""
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    notification_id = await _seed_notification(factory, tenant_id, reference="ref-8", status="sent")

    try:
        await _post(gateway, factory, event_id="e8a", reference="ref-8", status="undelivered")
        assert (await _reload(factory, tenant_id, notification_id)).status == "failed"

        after = await _post(gateway, factory, event_id="e8b", reference="ref-8", status="delivered")
        assert after.outcome == "delivered"
        row = await _reload(factory, tenant_id, notification_id)
        assert row.status == "delivered"
        assert row.error is None, "a delivered message still showed its old failure"
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_receipt_for_a_message_never_sent_moves_nothing(factory, gateway):
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    notification_id = await _seed_notification(
        factory, tenant_id, reference="ref-9", status="pending"
    )
    try:
        result = await _post(gateway, factory, event_id="e9", reference="ref-9", status="delivered")
        assert result.outcome == "ignored_pending"
        assert (await _reload(factory, tenant_id, notification_id)).status == "pending"
    finally:
        await _cleanup(factory, tenant_id)


# --- 9: tenant isolation -------------------------------------------------------


async def test_receipts_do_not_leak_or_delete_across_tenants(factory, gateway):
    """A farmer's delivery history is exactly what a competitor must not read."""
    from platform_core.core.rls import rebind_tenant

    alpha, beta = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, alpha)
    await _make_org(factory, beta, tz=KENYA, currency="KES")
    await _seed_notification(factory, alpha, reference="ref-alpha")

    try:
        await _post(gateway, factory, event_id="e-alpha", reference="ref-alpha", status="delivered")
        assert await _events(factory, alpha) == 1

        async with factory() as session:
            await rebind_tenant(session, beta)
            leaked = (
                await session.execute(
                    text("SELECT count(*) FROM notification_receipt_event WHERE tenant_id = :t"),
                    {"t": alpha},
                )
            ).scalar_one()
            assert leaked == 0, "another tenant read a delivery receipt"

            content = (
                await session.execute(
                    text("SELECT count(*) FROM notification WHERE rendered_text LIKE '%STL-1%'")
                )
            ).scalar_one()
            assert content == 0, "another tenant read the message content"

            deleted = await session.execute(
                text("DELETE FROM notification_receipt_event WHERE tenant_id = :t"), {"t": alpha}
            )
            assert deleted.rowcount == 0, "another tenant deleted a receipt it does not own"
            await session.commit()

        assert await _events(factory, alpha) == 1
    finally:
        await _cleanup(factory, alpha, beta)


async def test_the_receipt_table_forces_row_level_security(factory):
    """ENABLE without FORCE protects nothing: the app owns this table."""
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = 'notification_receipt_event'"
                )
            )
        ).first()
    assert row is not None, "the receipt ledger does not exist in the migrated database"
    enabled, forced = row
    assert enabled and forced


async def test_the_replay_constraint_exists_by_name(factory):
    async with factory() as session:
        names = {
            r[0]
            for r in (
                await session.execute(
                    text(
                        "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                        "WHERE t.relname = 'notification_receipt_event' AND c.contype = 'u'"
                    )
                )
            ).all()
        }
    assert "uq_notification_receipt_event" in names


# --- 10-14: reachability -------------------------------------------------------


async def _directory(maker, tenant_id: uuid.UUID, entries: list[tuple[str, str]]) -> None:
    """(name, phone) pairs in the directory a send would actually read."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.models import NotificationRecipient

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        for name, phone in entries:
            session.add(
                NotificationRecipient(
                    tenant_id=tenant_id,
                    subject_id=uuid.uuid4(),
                    subject_type="supplier",
                    display_name=name,
                    phone=phone,
                    email="",
                    language="en",
                    active=True,
                )
            )
        await session.commit()


async def _summary(maker, tenant_id: uuid.UUID, template_key="settlement_finalized"):
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.reachability import ReachabilityService

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        return await ReachabilityService(session, tenant_id).for_template(template_key)


async def test_reachability_counts_and_names_everyone(factory, gateway):
    """§8's report: total, reachable, unreachable, unknown, with reasons."""
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    await _directory(
        factory,
        tenant_id,
        [
            ("Reachable One", "+919845000101"),
            ("Reachable Two", "0712345678"),
            ("No Phone", ""),
            ("Also No Phone", "   "),
            ("Bad Phone", "call the office"),
        ],
    )

    try:
        summary = await _summary(factory, tenant_id)
        assert summary.channel == "sms"
        assert summary.total == 5
        assert summary.reachable == 2
        assert summary.unreachable == 3
        assert summary.reasons == {"invalid_phone": 1, "phone_missing": 2}
        # Nobody is silently skipped: every non-reachable recipient is named.
        assert len(summary.affected) == 3
        assert {item.name for item in summary.affected} == {
            "No Phone",
            "Also No Phone",
            "Bad Phone",
        }
    finally:
        await _cleanup(factory, tenant_id)


async def test_whatsapp_capability_is_unknown_not_assumed(factory, gateway):
    """A phone number is not a WhatsApp account, and nothing here can ask."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.configuration.service import ConfigurationService
    from platform_core.modules.notification.providers import ReceiptTestProvider, register_provider

    register_provider("whatsapp", ReceiptTestProvider("whatsapp"))
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    await _directory(factory, tenant_id, [("Has A Phone", "+919845000101")])

    async with factory() as session:
        await rebind_tenant(session, tenant_id)
        set_current_tenant(tenant_id)
        try:
            await ConfigurationService(session, AuditService(session)).set_value(
                "notification.channel.settlement_finalized",
                "whatsapp",
                scope="tenant",
                actor_id=None,
            )
            await session.commit()
        finally:
            set_current_tenant(None)

    try:
        summary = await _summary(factory, tenant_id)
        assert summary.channel == "whatsapp"
        assert summary.reachable == 0, "a phone number was taken as proof of WhatsApp"
        assert summary.unknown == 1
        assert summary.reasons == {"whatsapp_unknown": 1}
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_disabled_channel_blames_the_deployment_not_the_farmers(factory):
    """250 blameless farmers must not be reported as unreachable."""
    from platform_core.modules.notification.providers import (
        DisabledProvider,
        register_provider,
        reset_providers,
    )

    reset_providers()
    register_provider("sms", DisabledProvider("sms"))
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    await _directory(factory, tenant_id, [("A", "+919845000101"), ("B", "+919845000102")])

    try:
        summary = await _summary(factory, tenant_id)
        assert summary.unknown == 2
        assert summary.unreachable == 0
        assert summary.reasons == {"provider_unavailable": 2}
    finally:
        reset_providers()
        await _cleanup(factory, tenant_id)


async def test_reachability_does_not_leak_across_tenants(factory, gateway):
    alpha, beta = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, alpha)
    await _make_org(factory, beta, tz=KENYA, currency="KES")
    await _directory(factory, alpha, [("Alpha Farmer", "")])

    try:
        assert (await _summary(factory, alpha)).total == 1
        theirs = await _summary(factory, beta)
        assert theirs.total == 0, "another organization's farmers were counted"
        assert theirs.affected == []
    finally:
        await _cleanup(factory, alpha, beta)


# --- 15, 16: communication moves no money --------------------------------------


@pytest.mark.parametrize("template_key", ["settlement_finalized", "invoice_issued"])
async def test_communication_never_moves_a_financial_total(factory, gateway, template_key):
    """§18. The same infrastructure serves both journeys and neither is money."""

    async def snapshot():
        async with factory() as session:
            from platform_core.core.rls import bind_platform_context

            await bind_platform_context(session, reason="financial snapshot")
            rows = await session.execute(
                text(
                    "SELECT (SELECT count(*) FROM settlement), "
                    "       (SELECT coalesce(sum(net_amount), 0) FROM settlement), "
                    "       (SELECT count(*) FROM customer_invoice), "
                    "       (SELECT coalesce(sum(amount_due), 0) FROM customer_invoice), "
                    "       (SELECT count(*) FROM payment), "
                    "       (SELECT count(*) FROM receipt), "
                    "       (SELECT count(*) FROM customer_payment)"
                )
            )
            return tuple(rows.first())

    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    reference = f"ref-money-{template_key}"
    await _seed_notification(factory, tenant_id, reference=reference)
    await _directory(factory, tenant_id, [("A", "+919845000101"), ("B", "")])

    try:
        before = await snapshot()
        await _summary(factory, tenant_id, template_key)
        for index, status in enumerate(("delivered", "undelivered")):
            await _post(
                gateway,
                factory,
                event_id=f"e-money-{template_key}-{index}",
                reference=reference,
                status=status,
            )
        assert await snapshot() == before, "communication changed a financial record"
        assert Decimal(str(before[1])) >= 0  # the snapshot really read money
    finally:
        await _cleanup(factory, tenant_id)
