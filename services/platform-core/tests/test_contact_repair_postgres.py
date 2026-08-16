"""Contact repair and settlement-period reachability on PostgreSQL (DEMO-030).

`test_contact_repair.py` proves the rules on SQLite. This is the half SQLite
cannot prove: its test stack shares one connection, so nothing races, and it
has no row-level security at all.

The thirteen properties the work order names:

    1, 2   a contact update, and the audit entry it writes
    3      an invalid contact is refused
    4      cross-tenant contact access
    5-8    settlement-period reachability: unreachable, unknown, and a
           repaired recipient becoming reachable
    9, 10  concurrent contact updates and concurrent reachability
    11, 12 settlement and financial records unchanged
    13     RLS isolation

The failure this defends against is quiet: a repair that appears to work and
changes nothing, so the next settlement message goes to the wrong number.
"""

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

INDIA = "Asia/Kolkata"
KENYA = "Africa/Nairobi"
PERIOD_FROM = date(2026, 8, 1)
PERIOD_TO = date(2026, 8, 31)


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


@pytest.fixture(autouse=True)
def _logging_provider():
    """A provider that exists but sends nothing — so reachability is about the
    CONTACTS rather than about a disabled deployment."""
    from platform_core.modules.notification.providers import (
        LoggingProvider,
        register_provider,
        reset_providers,
    )

    reset_providers()
    register_provider("sms", LoggingProvider("sms"))
    yield
    reset_providers()


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


# --- seeding ------------------------------------------------------------------


async def _make_org(maker, tenant_id: uuid.UUID, *, tz: str = INDIA, currency: str = "INR") -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="contact repair proof seed")
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
                "n": f"Repair {tenant_id}",
                "s": f"repair-{tenant_id}",
                "cur": currency,
                "tz": tz,
            },
        )
        await session.commit()


async def _make_supplier(
    maker, tenant_id: uuid.UUID, *, name: str, phone: str, code: str
) -> uuid.UUID:
    """A supplier, its profile, and its directory entry — the three rows a real
    registration produces."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.models import NotificationRecipient
    from platform_core.modules.supplier.models import Supplier, SupplierProfile

    supplier_id = uuid.uuid4()
    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        session.add(Supplier(id=supplier_id, tenant_id=tenant_id, code=code, status="active"))
        session.add(
            SupplierProfile(
                tenant_id=tenant_id,
                supplier_id=supplier_id,
                full_name=name,
                phone=phone,
                locale="en",
            )
        )
        session.add(
            NotificationRecipient(
                tenant_id=tenant_id,
                subject_id=supplier_id,
                subject_type="supplier",
                display_name=name,
                code=code,
                phone=phone,
                email="",
                language="en",
                active=True,
            )
        )
        await session.commit()
    return supplier_id


async def _make_settlement(
    maker, tenant_id: uuid.UUID, supplier_id: uuid.UUID, *, number: str
) -> uuid.UUID:
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.settlement.models import Settlement

    settlement_id = uuid.uuid4()
    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        session.add(
            Settlement(
                id=settlement_id,
                tenant_id=tenant_id,
                supplier_id=supplier_id,
                center_id=uuid.uuid4(),
                settlement_number=number,
                period_from=PERIOD_FROM,
                period_to=PERIOD_TO,
                currency="INR",
                gross_amount=Decimal("1000.00"),
                adjustments_amount=Decimal("0.00"),
                net_amount=Decimal("1000.00"),
                status="finalized",
            )
        )
        await session.commit()
    return settlement_id


async def _cleanup(maker, *tenant_ids: uuid.UUID) -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="contact repair proof cleanup")
        for tenant_id in tenant_ids:
            for table in (
                "settlement",
                "notification_recipient",
                "supplier_profile",
                "supplier",
                "audit_record",
                "event_outbox",
            ):
                await session.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tenant_id}
                )
            await session.execute(text("DELETE FROM organization WHERE id = :t"), {"t": tenant_id})
        await session.commit()


# --- helpers ------------------------------------------------------------------


async def _repair(maker, tenant_id: uuid.UUID, supplier_id: uuid.UUID, *, phone: str, reason=None):
    """One repair, in its own session and transaction, through the real service."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.infrastructure.events import get_event_bus
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.event_relay.service import OutboxEventBus
    from platform_core.modules.supplier.service import SupplierService

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        set_current_tenant(tenant_id)
        try:
            service = SupplierService(
                session,
                OutboxEventBus(session, get_event_bus()),
                AuditService(session),
                storage=None,
            )
            profile = await service.repair_contact(
                supplier_id, phone=phone, reason=reason, actor_id=uuid.uuid4()
            )
            await session.commit()
            return profile.phone
        finally:
            set_current_tenant(None)


async def _directory_phone(maker, tenant_id: uuid.UUID, supplier_id: uuid.UUID) -> str:
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.models import NotificationRecipient

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        entry = await session.scalar(
            select(NotificationRecipient).where(
                NotificationRecipient.tenant_id == tenant_id,
                NotificationRecipient.subject_id == supplier_id,
            )
        )
        return entry.phone if entry else ""


async def _drain(maker, tenant_id: uuid.UUID) -> None:
    """Run the directory projection over what the repair published."""
    from platform_core.core.rls import PlatformSessionFactory
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    await ConsumerRunner(PlatformSessionFactory(maker, "contact repair proof")).run_once()


async def _period(maker, tenant_id: uuid.UUID):
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.reachability import ReachabilityService

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        # The route composes these two; the proof does the same, because the
        # notification module must not query settlement tables itself.
        from platform_core.core.tenancy import set_current_tenant
        from platform_core.modules.settlement.service import SettlementService

        set_current_tenant(tenant_id)
        try:
            subject_ids = await SettlementService(session, None, None, None).supplier_ids_in_period(
                PERIOD_FROM, PERIOD_TO
            )
        finally:
            set_current_tenant(None)
        return await ReachabilityService(session, tenant_id).for_subjects(subject_ids)


# --- 1, 2: the update and its audit --------------------------------------------


async def test_a_repair_updates_the_profile_and_reaches_the_directory(factory):
    """The defect, on real PostgreSQL: profile AND directory, not just one."""
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    supplier_id = await _make_supplier(
        factory, tenant_id, name="Farmer", phone="0712345678", code="S-1"
    )

    try:
        assert await _repair(factory, tenant_id, supplier_id, phone="+919845000199")
        await _drain(factory, tenant_id)
        assert await _directory_phone(factory, tenant_id, supplier_id) == "+919845000199", (
            "the repair never reached the directory a message is sent from"
        )
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_repair_writes_an_audit_entry_with_before_and_after(factory):
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.audit.models import AuditRecord

    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    supplier_id = await _make_supplier(
        factory, tenant_id, name="Farmer", phone="0712345678", code="S-2"
    )

    try:
        await _repair(
            factory, tenant_id, supplier_id, phone="+919845000123", reason="number changed"
        )
        async with factory() as session:
            await rebind_tenant(session, tenant_id)
            record = await session.scalar(
                select(AuditRecord).where(
                    AuditRecord.tenant_id == tenant_id,
                    AuditRecord.action == "supplier.profile_updated",
                )
            )
        assert record is not None
        assert record.detail["changed"] == ["phone"]
        assert record.detail["reason"] == "number changed"
        assert record.detail["phone"]["from"] != record.detail["phone"]["to"]
        assert "9845000123" not in str(record.detail), "the audit stored a full number"
    finally:
        await _cleanup(factory, tenant_id)


# --- 3: invalid contact ---------------------------------------------------------


async def test_a_nonsense_number_is_refused_and_changes_nothing(factory):
    from platform_core.core.errors import ValidationError

    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    supplier_id = await _make_supplier(
        factory, tenant_id, name="Farmer", phone="0712345678", code="S-3"
    )

    try:
        with pytest.raises(ValidationError):
            await _repair(factory, tenant_id, supplier_id, phone="call the office")
        assert await _directory_phone(factory, tenant_id, supplier_id) == "0712345678"
    finally:
        await _cleanup(factory, tenant_id)


# --- 4, 13: cross-tenant --------------------------------------------------------


async def test_one_tenant_cannot_read_or_repair_anothers_contact(factory):
    """A farmer's phone number is exactly what a competitor must not reach."""
    from platform_core.core.errors import NotFoundError
    from platform_core.core.rls import rebind_tenant

    alpha, beta = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, alpha)
    await _make_org(factory, beta, tz=KENYA, currency="KES")
    supplier_id = await _make_supplier(
        factory, alpha, name="Alpha Farmer", phone="0712345678", code="S-A"
    )

    try:
        # Reading: RLS refuses even with no tenant filter in the SQL.
        async with factory() as session:
            await rebind_tenant(session, beta)
            leaked = (
                await session.execute(
                    text("SELECT count(*) FROM supplier_profile WHERE supplier_id = :s"),
                    {"s": supplier_id},
                )
            ).scalar_one()
            assert leaked == 0, "another tenant read a farmer's contact"
            visible = (
                await session.execute(
                    text("SELECT count(*) FROM notification_recipient WHERE phone = '0712345678'")
                )
            ).scalar_one()
            assert visible == 0, "another tenant read a farmer's phone number"

        # Repairing: the service refuses, as a NOT FOUND rather than a 403.
        with pytest.raises(NotFoundError):
            await _repair(factory, beta, supplier_id, phone="+919845000111")

        assert await _directory_phone(factory, alpha, supplier_id) == "0712345678"
    finally:
        await _cleanup(factory, alpha, beta)


async def test_an_audit_entry_does_not_leak_across_tenants(factory):
    from platform_core.core.rls import rebind_tenant

    alpha, beta = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, alpha)
    await _make_org(factory, beta, tz=KENYA, currency="KES")
    supplier_id = await _make_supplier(
        factory, alpha, name="Alpha", phone="0712345678", code="S-AA"
    )

    try:
        await _repair(factory, alpha, supplier_id, phone="+919845000101", reason="private")
        async with factory() as session:
            await rebind_tenant(session, beta)
            leaked = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM audit_record "
                        "WHERE action = 'supplier.profile_updated'"
                    )
                )
            ).scalar_one()
            assert leaked == 0, "another tenant read a contact-repair audit trail"
    finally:
        await _cleanup(factory, alpha, beta)


# --- 5-8: settlement-period reachability ----------------------------------------


async def test_the_period_report_covers_the_settled_farmers(factory):
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    reachable = await _make_supplier(
        factory, tenant_id, name="Has Phone", phone="+919845000101", code="S-R"
    )
    unreachable = await _make_supplier(factory, tenant_id, name="No Phone", phone="", code="S-U")
    # A supplier with NO settlement in the period — must not appear.
    await _make_supplier(factory, tenant_id, name="Not Settled", phone="", code="S-N")
    await _make_settlement(factory, tenant_id, reachable, number="STL-1")
    await _make_settlement(factory, tenant_id, unreachable, number="STL-2")

    try:
        summary = await _period(factory, tenant_id)
        assert summary.total == 2, "the report was not scoped to the settled farmers"
        assert summary.reachable == 1
        assert summary.unreachable == 1
        assert summary.reasons == {"phone_missing": 1}
        assert [item.name for item in summary.affected] == ["No Phone"]
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_settled_farmer_absent_from_the_directory_is_reported(factory):
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.models import NotificationRecipient

    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    supplier_id = await _make_supplier(
        factory, tenant_id, name="Ghost", phone="+919845000101", code="S-G"
    )
    await _make_settlement(factory, tenant_id, supplier_id, number="STL-G")

    async with factory() as session:
        await rebind_tenant(session, tenant_id)
        entry = await session.scalar(
            select(NotificationRecipient).where(NotificationRecipient.subject_id == supplier_id)
        )
        await session.delete(entry)
        await session.commit()

    try:
        summary = await _period(factory, tenant_id)
        assert summary.total == 1
        assert summary.unreachable == 1
        assert summary.reasons == {"not_in_directory": 1}
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_repaired_farmer_becomes_reachable_in_the_period_report(factory):
    """§12.8, and the milestone in one test."""
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    supplier_id = await _make_supplier(factory, tenant_id, name="Fixable", phone="", code="S-F")
    await _make_settlement(factory, tenant_id, supplier_id, number="STL-F")

    try:
        before = await _period(factory, tenant_id)
        assert (before.reachable, before.unreachable) == (0, 1)

        await _repair(factory, tenant_id, supplier_id, phone="+919845000101", reason="repaired")
        await _drain(factory, tenant_id)

        after = await _period(factory, tenant_id)
        assert (after.reachable, after.unreachable) == (1, 0), (
            "the repair did not change what the operator sees"
        )
    finally:
        await _cleanup(factory, tenant_id)


async def test_the_period_report_does_not_leak_across_tenants(factory):
    alpha, beta = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, alpha)
    await _make_org(factory, beta, tz=KENYA, currency="KES")
    supplier_id = await _make_supplier(factory, alpha, name="Alpha", phone="", code="S-AB")
    await _make_settlement(factory, alpha, supplier_id, number="STL-AB")

    try:
        assert (await _period(factory, alpha)).total == 1
        theirs = await _period(factory, beta)
        assert theirs.total == 0, "another organization's settled farmers were counted"
        assert theirs.affected == []
    finally:
        await _cleanup(factory, alpha, beta)


# --- 9, 10: concurrency ----------------------------------------------------------


async def test_concurrent_repairs_leave_one_coherent_contact(factory):
    """Two operators fixing the same farmer at once.

    There is no "correct" winner — both numbers were offered by a human — but
    the outcome must be ONE of them, in both the profile and the directory,
    and never a mixture.
    """
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    supplier_id = await _make_supplier(factory, tenant_id, name="Contested", phone="", code="S-C")
    candidates = ["+919845000101", "+919845000102", "+919845000103", "+919845000104"]

    try:
        results = await asyncio.gather(
            *(_repair(factory, tenant_id, supplier_id, phone=p) for p in candidates),
            return_exceptions=True,
        )
        raised = [r for r in results if isinstance(r, Exception)]
        assert not raised, f"a racing repair raised: {raised}"

        await _drain(factory, tenant_id)
        from platform_core.core.rls import rebind_tenant
        from platform_core.modules.supplier.models import SupplierProfile

        async with factory() as session:
            await rebind_tenant(session, tenant_id)
            profile = await session.scalar(
                select(SupplierProfile).where(SupplierProfile.supplier_id == supplier_id)
            )
        final = profile.phone
        assert final in candidates, f"the contact ended as something nobody entered: {final!r}"
        assert await _directory_phone(factory, tenant_id, supplier_id) in candidates
    finally:
        await _cleanup(factory, tenant_id)


async def test_concurrent_reachability_calculations_agree(factory):
    """A read-only report must not depend on who asked first."""
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    for index in range(4):
        supplier_id = await _make_supplier(
            factory,
            tenant_id,
            name=f"F{index}",
            phone=f"+91984500010{index}" if index % 2 == 0 else "",
            code=f"S-{index}",
        )
        await _make_settlement(factory, tenant_id, supplier_id, number=f"STL-{index}")

    try:
        summaries = await asyncio.gather(*(_period(factory, tenant_id) for _ in range(6)))
        shapes = {(s.total, s.reachable, s.unreachable, s.unknown) for s in summaries}
        assert len(shapes) == 1, f"concurrent reports disagreed: {shapes}"
        assert shapes.pop() == (4, 2, 2, 0)
    finally:
        await _cleanup(factory, tenant_id)


# --- 11, 12: nothing financial moves ---------------------------------------------


async def test_repair_and_reachability_change_no_settlement_and_no_money(factory):
    """§7 and §15. Communication status is not a financial input."""

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
    supplier_id = await _make_supplier(factory, tenant_id, name="Paid", phone="", code="S-P")
    settlement_id = await _make_settlement(factory, tenant_id, supplier_id, number="STL-P")

    try:
        before = await snapshot()
        await _repair(factory, tenant_id, supplier_id, phone="+919845000101", reason="fix")
        await _drain(factory, tenant_id)
        await _period(factory, tenant_id)
        await _repair(factory, tenant_id, supplier_id, phone="")
        await _drain(factory, tenant_id)
        await _period(factory, tenant_id)

        assert await snapshot() == before, "communication work changed a financial record"

        # And the settlement itself is untouched, to the amount.
        from platform_core.core.rls import rebind_tenant
        from platform_core.modules.settlement.models import Settlement

        async with factory() as session:
            await rebind_tenant(session, tenant_id)
            settlement = await session.get(Settlement, settlement_id)
        assert settlement.status == "finalized"
        assert Decimal(settlement.net_amount) == Decimal("1000.00")
    finally:
        await _cleanup(factory, tenant_id)


async def test_an_unreachable_farmer_still_has_a_finalized_settlement(factory):
    """The rule stated as a property: reachability never cancels anything."""
    tenant_id = uuid.uuid4()
    await _make_org(factory, tenant_id)
    supplier_id = await _make_supplier(factory, tenant_id, name="Silent", phone="", code="S-S")
    await _make_settlement(factory, tenant_id, supplier_id, number="STL-S")

    try:
        summary = await _period(factory, tenant_id)
        assert summary.unreachable == 1, "the premise: this farmer cannot be told"

        async with factory() as session:
            from platform_core.core.rls import rebind_tenant

            await rebind_tenant(session, tenant_id)
            count = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM settlement "
                        "WHERE tenant_id = :t AND status = 'finalized'"
                    ),
                    {"t": tenant_id},
                )
            ).scalar_one()
        assert count == 1, "an unreachable farmer lost their settlement"
    finally:
        await _cleanup(factory, tenant_id)


async def test_the_supplier_tables_force_row_level_security(factory):
    """ENABLE without FORCE protects nothing: the app owns these tables."""
    for table in ("supplier_profile", "notification_recipient", "audit_record"):
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
        assert row is not None, f"{table} is missing"
        enabled, forced = row
        assert enabled and forced, f"{table} does not force RLS"
