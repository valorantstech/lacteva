"""The template registry on real PostgreSQL (DEMO-032).

`test_template_registry.py` proves the rules on SQLite. This is the half
SQLite cannot prove: its test stack shares one connection, so nothing races,
and it has no row-level security at all.

The properties §14 names:

    template read, variable validation, WhatsApp positional parameters,
    missing and unknown variable rejection, channel mismatch, language
    selection, provider mapping, an unmapped provider, tenant isolation, and
    concurrent access.

**There is no template versioning table and no template writes**, so there is
nothing to prove about creation, update or concurrent modification — the
registry is read-only by design (§10), and §17 records that decision. What IS
proven concurrently is that the registry is a pure read: many callers, one
answer, no state.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres


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


async def _make_org(maker, tenant_id: uuid.UUID, *, tz="Asia/Kolkata", currency="INR") -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="registry proof seed")
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
                "n": f"Reg {tenant_id}",
                "s": f"reg-{tenant_id}",
                "cur": currency,
                "tz": tz,
            },
        )
        await session.commit()


async def _cleanup(maker, *tenant_ids: uuid.UUID) -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="registry proof cleanup")
        for tenant_id in tenant_ids:
            await session.execute(
                text("DELETE FROM config_entry WHERE tenant_id = :t"), {"t": tenant_id}
            )
            await session.execute(text("DELETE FROM organization WHERE id = :t"), {"t": tenant_id})
        await session.commit()


# --- the registry reads -----------------------------------------------------------


async def test_the_registry_describes_the_shipped_templates(factory):
    from platform_core.modules.notification.service import NotificationService
    from platform_core.modules.notification.templates import catalog

    registry = NotificationService.registry()
    assert registry.total == len(catalog())
    assert all(entry.purpose for entry in registry.entries)


async def test_concurrent_readers_get_one_answer(factory):
    """A pure read: many callers, one answer, no state to race for."""
    from platform_core.modules.notification.service import NotificationService

    async def read():
        return NotificationService.registry().model_dump_json()

    answers = await asyncio.gather(*(read() for _ in range(8)))
    assert len(set(answers)) == 1, "concurrent readers disagreed about the registry"


# --- variable validation -----------------------------------------------------------


async def test_missing_and_unknown_variables_are_both_rejected(factory):
    from platform_core.modules.notification.templates import (
        TemplateRenderError,
        get_template,
        render,
    )

    template = get_template("settlement_finalized", "sms", "en")
    values = {name: "X" for name in template.variables}

    with pytest.raises(TemplateRenderError, match="missing variable"):
        render(template, {"number": "STL-1"})
    with pytest.raises(TemplateRenderError, match="does not use"):
        render(template, {**values, "not_a_variable": "x"})
    assert render(template, values).body, "a complete set still renders"


async def test_a_channel_mismatch_is_rejected(factory):
    from platform_core.modules.notification.templates import (
        TemplateNotFoundError,
        get_template,
    )

    with pytest.raises(TemplateNotFoundError):
        get_template("settlement_finalized", "carrier-pigeon", "en")


async def test_whatsapp_parameters_are_positional_and_stable(factory):
    """§7. `{{1}}, {{2}}` is the template's own declared order."""
    from platform_core.modules.notification.templates import get_template

    first = get_template("settlement_finalized", "whatsapp", "en").variables
    second = get_template("settlement_finalized", "whatsapp", "en").variables
    assert first == second
    assert first[0] == "number"
    assert len(first) == len(set(first)), "a duplicated positional parameter"


@pytest.mark.parametrize("language", ["en", "hi", "ar", "sw"])
async def test_language_selection_does_not_fall_back_silently(factory, language):
    from platform_core.modules.notification.templates import get_template

    template = get_template("settlement_finalized", "whatsapp", language)
    assert template.language == language, "a language silently fell back to English"


# --- provider mapping ---------------------------------------------------------------


async def test_an_unmapped_provider_is_reported_and_breaks_nothing(factory):
    from platform_core.modules.notification.service import NotificationService

    registry = NotificationService.registry()
    whatsapp = [e for e in registry.entries if e.channel == "whatsapp"]
    assert whatsapp
    assert all(e.provider_mapping_status == "NOT_CONFIGURED" for e in whatsapp)
    assert registry.unmapped_whatsapp == len(whatsapp)


async def test_a_configured_mapping_is_reported(factory, monkeypatch):
    from platform_core.core.config import get_settings
    from platform_core.modules.notification.service import NotificationService

    monkeypatch.setattr(
        get_settings(),
        "notification_vendor_templates",
        {"settlement_finalized.whatsapp": "lacteva_settlement_v1"},
    )
    registry = NotificationService.registry()
    mapped = [
        e for e in registry.entries if e.key == "settlement_finalized" and e.channel == "whatsapp"
    ]
    assert mapped and all(e.provider_template == "lacteva_settlement_v1" for e in mapped)


# --- isolation -----------------------------------------------------------------------


async def test_the_registry_carries_no_tenant_data(factory):
    """§13. Templates are code and process-wide; that is the existing
    architecture, and it is why there is nothing here to isolate. What IS
    per-tenant is the channel a dairy chose, and it is not exposed."""
    from platform_core.modules.notification.service import NotificationService

    text_body = NotificationService.registry().model_dump_json().lower()
    assert "tenant" not in text_body
    assert "phone" not in text_body


async def test_a_tenants_channel_choice_still_does_not_leak(factory):
    """The thing that IS per-tenant, still isolated by RLS."""
    from platform_core.core.rls import rebind_tenant

    alpha, beta = uuid.uuid4(), uuid.uuid4()
    await _make_org(factory, alpha)
    await _make_org(factory, beta, tz="Africa/Nairobi", currency="KES")

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
                    text("SELECT count(*) FROM config_entry WHERE key LIKE 'notification.%'")
                )
            ).scalar_one()
            assert leaked == 0, "another tenant read a channel choice"
    finally:
        await _cleanup(factory, alpha, beta)


async def test_no_credential_is_stored_for_templates(factory):
    """A vendor template name is configuration, not a database row, and no
    credential belongs in either."""
    from platform_core.core.rls import bind_platform_context

    async with factory() as session:
        await bind_platform_context(session, reason="registry credential sweep")
        hits = (
            await session.execute(
                text(
                    "SELECT count(*) FROM config_entry "
                    "WHERE key ILIKE '%api_key%' OR key ILIKE '%secret%' OR key ILIKE '%token%'"
                )
            )
        ).scalar_one()
    assert hits == 0


# --- financial safety ------------------------------------------------------------------


async def test_the_registry_changes_no_financial_record(factory):
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.notification.service import NotificationService

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
    for _ in range(5):
        NotificationService.registry()
    assert await snapshot() == before
