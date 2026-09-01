"""Statements and bills on real PostgreSQL (DEMO-028).

`test_statement_delivery.py` proves the content and the rules on SQLite. This
is the half SQLite cannot prove: the test stack shares a single connection, so
nothing there races, and it has no row-level security at all.

The twelve properties the work order names, in the order it names them:

    1, 2   a settlement statement and a customer bill are created
    3, 4   a duplicate request for either creates nothing new
    5      concurrent duplicate dispatch produces one message and ONE gateway call
    6, 7   provider failure is recorded and a retry is safe
    8      messages do not leak or delete across tenants
    9      language follows the organization, not a default
    10     the currency is the record's own and its precision survives
    11     a business-date boundary names the dairy's day, not UTC's
    12     a disabled provider fails VISIBLY — it never reports success

The failure this file mostly defends against is expensive in a way most are
not: a duplicate message is a duplicate charge from a gateway and a farmer told
twice about the same money. There is no compensating action — the SMS has gone.
"""

import asyncio
import uuid
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support
from tests.clock import TODAY, month_end, month_start

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

INDIA = "Asia/Kolkata"
KENYA = "Africa/Nairobi"


@pytest.fixture(autouse=True)
def _settings_point_at_postgres(monkeypatch):
    """Make `is_postgres()` true, or every binding below is a no-op.

    The lesson DEMO-020 learned the hard way: without this the suite passes as
    a superuser and proves nothing about RLS at all.
    """
    from platform_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "database_url", POSTGRES_URL)
    monkeypatch.setattr(get_settings(), "rls_enabled", True)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clean_providers():
    from platform_core.modules.notification.providers import reset_providers

    reset_providers()
    yield
    reset_providers()


# --- fakes --------------------------------------------------------------------


class _CountingProvider:
    """Counts gateway calls. The number that becomes a bill from a vendor."""

    name = "counting"

    def __init__(self):
        self.calls = 0
        self.sent: list = []

    async def send(self, message):
        from platform_core.modules.notification.providers import DeliveryResult

        self.calls += 1
        self.sent.append(message)
        await asyncio.sleep(0.01)  # widen the window the constraint must close
        return DeliveryResult(provider_message_id=f"counting:{self.calls}")


class _FlakyProvider:
    """Fails `fail_times` and then succeeds — §7's retry, deterministically."""

    name = "flaky"

    def __init__(self, fail_times: int = 1):
        self.fail_times = fail_times
        self.calls = 0

    async def send(self, message):
        from platform_core.modules.notification.providers import (
            DeliveryResult,
            ProviderSendError,
        )

        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ProviderSendError("gateway unavailable")
        return DeliveryResult(provider_message_id=f"flaky:{self.calls}")


# --- seeding ------------------------------------------------------------------


async def _make_org(maker, tenant_id: uuid.UUID, *, tz: str, currency: str, language: str) -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="statement delivery test seed")
        await session.execute(
            text(
                "INSERT INTO organization "
                "(id, name, slug, country_code, org_type, status, currency_code, timezone, "
                " supported_languages, default_locale, created_at) "
                "VALUES (:id, :n, :s, 'IN', 'processor', 'active', :cur, :tz, "
                "        :langs, :loc, now())"
            ),
            {
                "id": tenant_id,
                "n": f"Statement {tenant_id}",
                "s": f"stmt-{tenant_id}",
                "cur": currency,
                "tz": tz,
                "langs": f'["{language}"]',
                "loc": language,
            },
        )
        await session.commit()


async def _cleanup(maker, *tenant_ids: uuid.UUID) -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="statement delivery test cleanup")
        for tenant_id in tenant_ids:
            await session.execute(
                text("DELETE FROM notification WHERE tenant_id = :t"), {"t": tenant_id}
            )
            await session.execute(text("DELETE FROM organization WHERE id = :t"), {"t": tenant_id})
        await session.commit()


def _settlement_variables(*, currency: str, quantity: str = "412.500") -> dict:
    """Exactly what the settlement event carries — no more, no less."""
    return {
        "name": "Farmer",
        "number": "STL-2026-000042",
        "gross_amount": "18562.50",
        "net_amount": "18562.50",
        "currency": currency,
        "line_count": 31,
        "quantity": quantity,
        "quantity_unit": "kg",
        "period_from": month_start().isoformat(),
        "period_to": month_end().isoformat(),
    }


def _invoice_variables(*, currency: str, previous_balance: str = "") -> dict:
    return {
        "name": "Household",
        "number": "INV-2026-000007",
        "amount": "1250.00",
        "currency": currency,
        "quantity": "62.000",
        "quantity_unit": "L",
        "previous_balance": previous_balance,
        "period_from": month_start().isoformat(),
        "period_to": month_end().isoformat(),
        # WO-58: derived like the two bounds above it, or this string names a
        # different month from the variables beside it every month but one.
        "period": f"{month_start().isoformat()} - {month_end().isoformat()}",
    }


async def _dispatch(
    maker,
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    template_key: str,
    channel: str = "sms",
    variables: dict,
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
    language: str | None = None,
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
                channel=channel,
                recipient="+919845000101",
                language=language,
                source_type=source_type,
                source_id=source_id,
                variables=variables,
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


# --- 1, 2: the two journeys create their messages ------------------------------


async def test_a_settlement_statement_is_created_with_the_settlement_it_is_about(factory):
    from platform_core.modules.notification.providers import register_provider

    provider = _CountingProvider()
    register_provider("sms", provider)
    tenant_id, settlement_id = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, tenant_id, tz=INDIA, currency="INR", language="en")

    try:
        await _dispatch(
            factory,
            tenant_id,
            uuid.uuid4(),
            template_key="settlement_finalized",
            variables=_settlement_variables(currency="INR"),
            source_type="settlement",
            source_id=settlement_id,
        )
        rows = await _rows(factory, tenant_id)
        assert len(rows) == 1
        slip = rows[0]
        assert slip.status == "sent"
        assert slip.provider_status == "accepted", "the gateway ACCEPTED — it did not deliver"
        assert slip.source_type == "settlement"
        assert slip.source_id == settlement_id
        assert "412.500" in slip.rendered_text and "kg" in slip.rendered_text
        assert "18562.50" in slip.rendered_text
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_customer_bill_is_created_with_the_invoice_it_is_about(factory):
    from platform_core.modules.notification.providers import register_provider

    register_provider("sms", _CountingProvider())
    tenant_id, invoice_id = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, tenant_id, tz=KENYA, currency="KES", language="en")

    try:
        await _dispatch(
            factory,
            tenant_id,
            uuid.uuid4(),
            template_key="invoice_issued",
            variables=_invoice_variables(currency="KES"),
            source_type="customer_invoice",
            source_id=invoice_id,
        )
        bill = (await _rows(factory, tenant_id))[0]
        assert bill.source_type == "customer_invoice"
        assert bill.source_id == invoice_id
        assert "1250.00" in bill.rendered_text and "KES" in bill.rendered_text
        assert "62.000" in bill.rendered_text
    finally:
        await _cleanup(factory, tenant_id)


# --- 3, 4: a duplicate request creates nothing new -----------------------------


@pytest.mark.parametrize(
    ("template_key", "variables"),
    [
        ("settlement_finalized", _settlement_variables(currency="INR")),
        ("invoice_issued", _invoice_variables(currency="INR")),
    ],
)
async def test_the_same_request_repeated_creates_one_message(factory, template_key, variables):
    from platform_core.modules.notification.providers import register_provider

    provider = _CountingProvider()
    register_provider("sms", provider)
    tenant_id, event_id = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, tenant_id, tz=INDIA, currency="INR", language="en")

    try:
        first = await _dispatch(
            factory, tenant_id, event_id, template_key=template_key, variables=variables
        )
        assert first is not None
        for _ in range(4):
            again = await _dispatch(
                factory, tenant_id, event_id, template_key=template_key, variables=variables
            )
            assert again is None, "a repeat produced a second notification"
        assert len(await _rows(factory, tenant_id)) == 1
        assert provider.calls == 1, "the gateway was paid twice for one message"
    finally:
        await _cleanup(factory, tenant_id)


# --- 5: concurrency ------------------------------------------------------------


async def test_eight_concurrent_statement_dispatches_call_the_gateway_once(factory):
    """The production shape: several workers, one finalized settlement."""
    from platform_core.modules.notification.providers import register_provider

    provider = _CountingProvider()
    register_provider("sms", provider)
    tenant_id, event_id = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, tenant_id, tz=INDIA, currency="INR", language="en")

    try:
        results = await asyncio.gather(
            *(
                _dispatch(
                    factory,
                    tenant_id,
                    event_id,
                    template_key="settlement_finalized",
                    variables=_settlement_variables(currency="INR"),
                )
                for _ in range(8)
            ),
            return_exceptions=True,
        )
        raised = [r for r in results if isinstance(r, Exception)]
        assert not raised, f"a racing dispatch raised: {raised}"

        assert len(await _rows(factory, tenant_id)) == 1
        assert provider.calls == 1, (
            f"the gateway was called {provider.calls} times for one settlement — "
            "every extra call is a charge and a farmer told twice about the same money"
        )
    finally:
        await _cleanup(factory, tenant_id)


# --- 6, 7: failure and retry ---------------------------------------------------


async def test_a_provider_failure_is_recorded_and_claims_nothing(factory):
    from platform_core.modules.notification.providers import register_provider

    register_provider("sms", _FlakyProvider(fail_times=99))
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id, tz=INDIA, currency="INR", language="en")

    try:
        await _dispatch(
            factory,
            tenant_id,
            uuid.uuid4(),
            template_key="settlement_finalized",
            variables=_settlement_variables(currency="INR"),
        )
        slip = (await _rows(factory, tenant_id))[0]
        assert slip.status == "failed"
        assert slip.provider_status is None, "a failure must not carry a provider claim"
        assert slip.sent_at is None
        assert slip.error
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_retry_after_a_failure_sends_exactly_once(factory):
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.providers import register_provider
    from platform_core.modules.notification.service import NotificationService

    provider = _FlakyProvider(fail_times=1)
    register_provider("sms", provider)
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id, tz=INDIA, currency="INR", language="en")

    try:
        await _dispatch(
            factory,
            tenant_id,
            uuid.uuid4(),
            template_key="settlement_finalized",
            variables=_settlement_variables(currency="INR"),
        )
        first = (await _rows(factory, tenant_id))[0]
        assert first.status == "failed"

        async with factory() as session:
            await rebind_tenant(session, tenant_id)
            retried = await NotificationService(session).retry(first.id)
            await session.commit()

        assert retried.status == "sent"
        assert retried.provider_status == "accepted"
        assert provider.calls == 2, "one failed attempt and one successful one"
        assert len(await _rows(factory, tenant_id)) == 1, "a retry is not a second message"
    finally:
        await _cleanup(factory, tenant_id)


# --- 8: tenant isolation -------------------------------------------------------


async def test_a_statement_does_not_leak_or_delete_across_tenants(factory):
    """A farmer's money is exactly what a competitor must not read."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.providers import register_provider

    register_provider("sms", _CountingProvider())
    alpha, beta = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, alpha, tz=INDIA, currency="INR", language="en")
    await _make_org(factory, beta, tz=KENYA, currency="KES", language="en")

    try:
        await _dispatch(
            factory,
            alpha,
            uuid.uuid4(),
            template_key="settlement_finalized",
            variables=_settlement_variables(currency="INR"),
            source_type="settlement",
            source_id=uuid.uuid4(),
        )
        assert len(await _rows(factory, alpha)) == 1, "the premise"

        async with factory() as session:
            await rebind_tenant(session, beta)
            # No tenant filter in the SQL at all — the database must refuse.
            leaked = (
                await session.execute(
                    text("SELECT count(*) FROM notification WHERE tenant_id = :t"), {"t": alpha}
                )
            ).scalar_one()
            assert leaked == 0, "another tenant read a farmer's settlement message"

            # Neither the content nor the recipient nor the source reference.
            visible = (
                await session.execute(
                    text("SELECT count(*) FROM notification WHERE rendered_text LIKE '%STL-%'")
                )
            ).scalar_one()
            assert visible == 0, "another tenant read the statement text"

            deleted = await session.execute(
                text("DELETE FROM notification WHERE tenant_id = :t"), {"t": alpha}
            )
            assert deleted.rowcount == 0, "another tenant deleted a message it does not own"
            await session.commit()

        assert len(await _rows(factory, alpha)) == 1, "alpha's message survived"
    finally:
        await _cleanup(factory, alpha, beta)


# --- 9: language ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "currency", "tz", "marker"),
    [
        ("hi", "INR", INDIA, "भुगतान"),
        ("ar", "INR", INDIA, "التسوية"),
        ("sw", "KES", KENYA, "Malipo"),
        ("en", "KES", KENYA, "Settlement"),
    ],
)
async def test_the_statement_is_written_in_the_organizations_language(
    factory, language, currency, tz, marker
):
    """The language is a fact about the DAIRY, not a parameter of the event.

    Note what is NOT passed to `dispatch`: a language. It is read from the
    organization the country registry configured at onboarding — which is why
    adding a market is a row and not a branch.
    """
    from platform_core.modules.notification.providers import register_provider

    register_provider("sms", _CountingProvider())
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id, tz=tz, currency=currency, language=language)

    try:
        await _dispatch(
            factory,
            tenant_id,
            uuid.uuid4(),
            template_key="settlement_finalized",
            variables=_settlement_variables(currency=currency),
        )
        slip = (await _rows(factory, tenant_id))[0]
        assert slip.language == language
        # Title and body together, case-insensitively: the distinctive word
        # appears capitalised in the subject and lower-case mid-sentence, and
        # what is being asserted is the LANGUAGE, not the casing.
        written = f"{slip.title} {slip.rendered_text}".lower()
        assert marker.lower() in written, (
            f"a {language} dairy received {slip.language!r} — the fallback is silent"
        )
    finally:
        await _cleanup(factory, tenant_id)


# --- 10: currency --------------------------------------------------------------


@pytest.mark.parametrize(("currency", "tz"), [("INR", INDIA), ("KES", KENYA)])
async def test_the_amount_is_the_records_own_currency_at_full_precision(factory, currency, tz):
    """No rounding, no symbol invented, no country consulted."""
    from platform_core.modules.notification.providers import register_provider

    register_provider("sms", _CountingProvider())
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id, tz=tz, currency=currency, language="en")

    try:
        variables = _settlement_variables(currency=currency)
        await _dispatch(
            factory,
            tenant_id,
            uuid.uuid4(),
            template_key="settlement_finalized",
            variables=variables,
        )
        slip = (await _rows(factory, tenant_id))[0]
        assert currency in slip.rendered_text
        assert "18562.50" in slip.rendered_text, "the exact stored amount, not a rounded one"
        # The PostgreSQL round-trip must not have touched it either.
        assert Decimal(slip.payload["net_amount"]) == Decimal("18562.50")
    finally:
        await _cleanup(factory, tenant_id)


# --- 11: the business-date boundary --------------------------------------------


@pytest.mark.parametrize(
    ("tz", "instant", "expected_local_day"),
    [
        # 19:00 UTC is already tomorrow in Bengaluru (+05:30).
        (INDIA, datetime(2026, 8, 31, 19, 0, tzinfo=ZoneInfo("UTC")), date(2026, 9, 1)),
        # 22:30 UTC is still today in Nairobi (+03:00)... just.
        (KENYA, datetime(2026, 8, 31, 20, 30, tzinfo=ZoneInfo("UTC")), date(2026, 8, 31)),
        (KENYA, datetime(2026, 8, 31, 21, 30, tzinfo=ZoneInfo("UTC")), date(2026, 9, 1)),
    ],
)
def test_a_business_date_is_the_dairys_day_not_utcs(tz, instant, expected_local_day):
    """The rule DEMO-018..023 established, restated where messages depend on it."""
    from platform_core.core.business_time import business_date_of

    assert business_date_of(instant, tz) == expected_local_day


async def test_a_statement_sent_after_local_midnight_still_names_the_period_it_settles(factory):
    """The defect DEMO-025 fixed, held down where PostgreSQL stores the dates.

    The slip must name the settlement's OWN business period. It must not name
    the day the message happened to be dispatched, and it must not name a slice
    of a UTC timestamp — which for an Indian dairy finalising at 23:30 local is
    the previous day.
    """
    from platform_core.modules.notification.providers import register_provider

    register_provider("sms", _CountingProvider())
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id, tz=INDIA, currency="INR", language="en")

    try:
        await _dispatch(
            factory,
            tenant_id,
            uuid.uuid4(),
            template_key="settlement_finalized",
            variables=_settlement_variables(currency="INR"),
        )
        slip = (await _rows(factory, tenant_id))[0]
        # The settlement's OWN period, whichever month the suite runs in.
        assert month_start().isoformat() in slip.rendered_text
        assert month_end().isoformat() in slip.rendered_text
        # Whatever day the dispatch happened, it is not on the slip — unless
        # it happens to be one of the period's own bounds, which is the first
        # and the last day of the month.
        dispatched_on = str(TODAY)
        assert dispatched_on not in slip.rendered_text or dispatched_on in (
            month_start().isoformat(),
            month_end().isoformat(),
        )
    finally:
        await _cleanup(factory, tenant_id)


# --- 12: a disabled provider ---------------------------------------------------


async def test_a_disabled_provider_fails_visibly_and_reports_no_delivery(factory):
    """The production posture, and the one that must never lie.

    Every messaging provider is `disabled` on the live deployment. A disabled
    channel must refuse LOUDLY: the message is recorded as failed, with a
    reason, and nothing anywhere says it was sent.
    """
    from platform_core.modules.notification.providers import DisabledProvider, register_provider

    register_provider("sms", DisabledProvider("sms"))
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id, tz=INDIA, currency="INR", language="en")

    try:
        await _dispatch(
            factory,
            tenant_id,
            uuid.uuid4(),
            template_key="settlement_finalized",
            variables=_settlement_variables(currency="INR"),
        )
        slip = (await _rows(factory, tenant_id))[0]
        assert slip.status in ("failed", "dead"), "a disabled channel reported success"
        assert slip.sent_at is None
        assert slip.provider_status is None
        assert slip.error, "a disabled channel must say why"
        # The row exists. A dropped message would be worse than a failed one:
        # an operator can see this and cannot see silence.
        assert slip.rendered_text or slip.error
    finally:
        await _cleanup(factory, tenant_id)


async def test_the_notification_table_forces_row_level_security(factory):
    """ENABLE without FORCE protects nothing: the app owns this table."""
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = 'notification'"
                )
            )
        ).first()
    assert row is not None
    enabled, forced = row
    assert enabled and forced


async def test_the_new_provenance_columns_exist(factory):
    """DEMO-028's migration, asserted against the migrated database."""
    async with factory() as session:
        names = {
            r[0]
            for r in (
                await session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'notification'"
                    )
                )
            ).all()
        }
    assert {"provider_status", "source_type", "source_id"} <= names
