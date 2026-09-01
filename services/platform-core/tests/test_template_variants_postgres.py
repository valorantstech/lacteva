"""Variants and approval on real PostgreSQL (DEMO-033).

`test_template_variants.py` proves the rules on SQLite. This is the half SQLite
cannot prove: its test stack shares one connection, so nothing races.

The properties §15 names — fixed parameter count and order, missing and unknown
parameter rejection, variant selection, SMS and email regression, the three
approval states and a transition, audit, provider mapping, readiness, tenant
isolation, and concurrent approval.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support
from tests.clock import month_end, month_start

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

KEY = "settlement_finalized_with_quantity"
PROVIDER = "example-gateway"

SETTLEMENT = {
    "name": "Ramesh",
    "number": "STL-1",
    "period_from": month_start().isoformat(),
    "period_to": month_end().isoformat(),
    "line_count": "31",
    "gross_amount": "18562.50",
    "net_amount": "18562.50",
    "currency": "INR",
}


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


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean(factory):
    yield
    from platform_core.core.rls import bind_platform_context

    async with factory() as session:
        await bind_platform_context(session, reason="variant proof cleanup")
        await session.execute(text("DELETE FROM notification_template_approval"))
        await session.execute(
            text("DELETE FROM audit_record WHERE action = :a"),
            {"a": "notification.template_approval_recorded"},
        )
        await session.commit()


async def _record(factory, *, state, language="en", provider_template_id=None, note=None):
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.notification.service import ApprovalCommand, NotificationService

    async with factory() as session:
        await bind_platform_context(session, reason="variant proof approval")
        view = await NotificationService(session).record_approval(
            ApprovalCommand(
                template_key=KEY,
                channel="whatsapp",
                language=language,
                provider=PROVIDER,
                state=state,
                provider_template_id=provider_template_id,
                note=note,
            ),
            actor_id=uuid.uuid4(),
            audit=AuditService(session),
        )
        await session.commit()
        return view


async def _registry(factory):
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.notification.service import NotificationService

    async with factory() as session:
        await bind_platform_context(session, reason="variant proof registry")
        return await NotificationService(session).registry_with_approvals()


# --- 1-4: the fixed parameter contract --------------------------------------------


async def test_a_whatsapp_variant_has_a_fixed_ordered_parameter_list(factory):
    from platform_core.modules.notification.templates import get_template

    template = get_template(KEY, "whatsapp", "en")
    assert template.optional_variables == ()
    assert template.variables[0] == "number"
    assert template.variables == get_template(KEY, "whatsapp", "en").variables


async def test_missing_and_unknown_parameters_are_both_rejected(factory):
    from platform_core.modules.notification.templates import (
        TemplateRenderError,
        assert_fixed_parameters,
        get_template,
        render,
    )

    template = get_template(KEY, "whatsapp", "en")
    values = {name: "X" for name in template.variables}

    incomplete = dict(values)
    del incomplete["currency"]
    with pytest.raises(TemplateRenderError, match="missing parameter"):
        assert_fixed_parameters(template, incomplete)
    with pytest.raises(TemplateRenderError, match="does not use"):
        render(template, {**values, "not_a_field": "x"})
    assert render(template, values).body


# --- 5: variant selection -----------------------------------------------------------


async def test_variant_selection_follows_the_data(factory):
    from platform_core.modules.notification.templates import select_template_key

    assert select_template_key("settlement_finalized", "whatsapp", SETTLEMENT) == (
        "settlement_finalized_base"
    )
    assert (
        select_template_key(
            "settlement_finalized",
            "whatsapp",
            {**SETTLEMENT, "quantity": "412.5", "quantity_unit": "kg"},
        )
        == KEY
    )


# --- 6, 7: SMS and email unchanged ---------------------------------------------------


async def test_sms_and_email_still_render_their_optional_segments(factory):
    from platform_core.modules.notification.templates import get_template, render

    sms = get_template("settlement_finalized", "sms", "en")
    assert sms.optional_variables, "SMS lost its optional segment"
    assert (
        "412.5 kg" in render(sms, {**SETTLEMENT, "quantity": "412.5", "quantity_unit": "kg"}).body
    )
    assert "kg" not in render(sms, SETTLEMENT).body

    email = get_template("settlement_finalized", "email", "en")
    assert email.optional_variables
    assert "412.5" in render(email, {**SETTLEMENT, "quantity": "412.5", "quantity_unit": "kg"}).body


# --- 8-11: the approval states, a transition, and the audit ---------------------------


@pytest.mark.parametrize("state", ["pending", "approved", "rejected"])
async def test_each_state_is_recorded(factory, state):
    view = await _record(factory, state=state)
    assert view.state == state
    entry = next(
        e for e in (await _registry(factory)).entries if e.key == KEY and e.language == "en"
    )
    assert entry.approval_state == state.upper()


async def test_nothing_is_approved_without_a_record(factory):
    """§9: no backfill, no fabricated approval."""
    registry = await _registry(factory)
    assert {e.approval_state for e in registry.entries} == {"NOT_CONFIGURED"}
    assert registry.ready_whatsapp == 0


async def test_a_transition_keeps_one_row_and_audits_both_states(factory):
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.audit.models import AuditRecord
    from platform_core.modules.notification.models import NotificationTemplateApproval

    await _record(factory, state="pending")
    await _record(factory, state="approved", provider_template_id="gw_v1", note="ok")

    async with factory() as session:
        await bind_platform_context(session, reason="variant proof read")
        rows = list((await session.scalars(select(NotificationTemplateApproval))).all())
        audits = list(
            (
                await session.scalars(
                    select(AuditRecord).where(
                        AuditRecord.action == "notification.template_approval_recorded"
                    )
                )
            ).all()
        )
    assert len(rows) == 1, "a transition created a second row"
    assert rows[0].state == "approved"
    assert rows[0].provider_template_id == "gw_v1"
    assert len(audits) == 2
    transitions = sorted((a.detail["from"], a.detail["to"]) for a in audits)
    assert transitions == [("NOT_CONFIGURED", "pending"), ("pending", "approved")]


async def test_the_unique_constraint_exists_by_name(factory):
    async with factory() as session:
        names = {
            r[0]
            for r in (
                await session.execute(
                    text(
                        "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                        "WHERE t.relname = 'notification_template_approval' AND c.contype = 'u'"
                    )
                )
            ).all()
        }
    assert "uq_notification_template_approval" in names


# --- 12, 13: mapping and readiness ----------------------------------------------------


async def test_readiness_requires_approval_and_mapping(factory, monkeypatch):
    from platform_core.core.config import get_settings

    await _record(factory, state="approved", provider_template_id="gw_v1")
    entry = next(
        e for e in (await _registry(factory)).entries if e.key == KEY and e.language == "en"
    )
    assert entry.ready is False
    assert entry.blockers == ["provider template id missing"]

    monkeypatch.setattr(
        get_settings(), "notification_vendor_templates", {f"{KEY}.whatsapp": "gw_v1"}
    )
    registry = await _registry(factory)
    ready = next(e for e in registry.entries if e.key == KEY and e.language == "en")
    assert ready.ready is True
    assert ready.blockers == []
    assert registry.ready_whatsapp == 1


async def test_approving_one_language_does_not_approve_another(factory):
    await _record(factory, state="approved", language="en")
    states = {
        e.language: e.approval_state for e in (await _registry(factory)).entries if e.key == KEY
    }
    assert states["en"] == "APPROVED"
    assert {states["hi"], states["ar"], states["sw"]} == {"NOT_CONFIGURED"}


# --- 14: isolation ---------------------------------------------------------------------


async def test_the_approval_table_is_platform_global_and_carries_no_tenant(factory):
    """§13. The messaging account is Lacteva's, so approval is one platform
    fact — declared in `core/rls.py` PLATFORM_GLOBAL with a written reason,
    which `test_every_table_declares_an_isolation_strategy` enforces."""
    async with factory() as session:
        columns = {
            r[0]
            for r in (
                await session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'notification_template_approval'"
                    )
                )
            ).all()
        }
        rls = (
            await session.execute(
                text(
                    "SELECT relrowsecurity FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid = c.relnamespace WHERE n.nspname='public' "
                    "AND c.relname='notification_template_approval'"
                )
            )
        ).scalar_one()
    assert "tenant_id" not in columns, "a platform-global table grew a tenant column"
    assert rls is False, "RLS on a table with no tenant column protects nothing"

    from platform_core.core.rls import PLATFORM_GLOBAL

    assert "notification_template_approval" in PLATFORM_GLOBAL
    assert len(PLATFORM_GLOBAL["notification_template_approval"]) > 80, "no written reason"


async def test_no_credential_is_stored_with_an_approval(factory):
    await _record(factory, state="approved", provider_template_id="gw_v1", note="fine")
    async with factory() as session:
        row = (
            (await session.execute(text("SELECT * FROM notification_template_approval LIMIT 1")))
            .mappings()
            .first()
        )
    text_body = str(dict(row)).lower()
    for secret in ("api_key", "apikey", "secret", "password", "token"):
        assert secret not in text_body


# --- 16: concurrency --------------------------------------------------------------------


async def test_concurrent_approvals_leave_one_coherent_row(factory):
    """Two operators recording an outcome at once.

    There is no correct winner — both were entered by a human — but the outcome
    must be ONE row in one of the recorded states, never two rows or a mixture.
    """
    results = await asyncio.gather(
        *(
            _record(factory, state=state, provider_template_id=f"gw_{state}")
            for state in ("pending", "approved", "rejected", "approved")
        ),
        return_exceptions=True,
    )
    raised = [r for r in results if isinstance(r, Exception)]
    # A unique-constraint loser is an acceptable outcome; a corrupted table is not.
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.notification.models import NotificationTemplateApproval

    async with factory() as session:
        await bind_platform_context(session, reason="variant proof concurrency read")
        rows = list((await session.scalars(select(NotificationTemplateApproval))).all())
    assert len(rows) == 1, f"concurrent approvals produced {len(rows)} rows (raised: {raised})"
    assert rows[0].state in ("pending", "approved", "rejected")


# --- 15: financial safety ----------------------------------------------------------------


async def test_approval_changes_no_financial_record(factory):
    from platform_core.core.rls import bind_platform_context

    async def snapshot():
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
                    "       (SELECT count(*) FROM customer_payment)"
                )
            )
            return tuple(row.first())

    before = await snapshot()
    for state in ("pending", "approved", "rejected"):
        await _record(factory, state=state)
    await _registry(factory)
    assert await snapshot() == before
