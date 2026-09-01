"""Fixed-parameter WhatsApp variants and approval lifecycle (DEMO-033).

Two properties:

    **An approved WhatsApp template cannot vary.** DEMO-032 found all 8
    business WhatsApp templates unapprovable, because DEMO-028's optional
    segments give a varying parameter count. The two designs stop sharing a
    template: SMS and email keep the segments and behave exactly as before,
    WhatsApp gets one explicit variant per real combination.

    **Lacteva approves nothing.** `APPROVED` records that a provider or a
    regulator said so and an operator wrote it down. Nothing in the platform
    can reach that state on its own.

No message was sent and no provider was contacted.
"""

import pytest

from platform_core.core.config import get_settings
from platform_core.modules.notification.templates import (
    FIXED_PARAMETER_CHANNELS,
    TEMPLATES,
    VARIANTS,
    TemplateNotFoundError,
    TemplateRenderError,
    assert_fixed_parameters,
    fixed_parameters,
    get_template,
    present_groups,
    render,
    select_template_key,
)
from tests.clock import month_end, month_start

APPROVAL = "/v1/notification-templates/approval"
REGISTRY = "/v1/notification-templates/registry"

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
INVOICE = {
    "name": "Household",
    "number": "INV-1",
    "amount": "1250.00",
    "currency": "INR",
    "period_from": month_start().isoformat(),
    "period_to": month_end().isoformat(),
}


# --- no WhatsApp template varies any more -----------------------------------


def test_no_whatsapp_template_has_an_optional_segment():
    """The DEMO-032 blocker, removed at the source."""
    offenders = [
        (t.key, t.language)
        for t in TEMPLATES
        if t.channel in FIXED_PARAMETER_CHANNELS and t.optional_variables
    ]
    assert not offenders, f"a WhatsApp template still varies: {offenders}"


def test_every_whatsapp_variant_exists_in_every_language():
    """§12: approving English says nothing about Hindi, so all four must exist."""
    for variants in VARIANTS.values():
        for key in variants.values():
            languages = {t.language for t in TEMPLATES if t.key == key}
            assert languages == {"en", "hi", "ar", "sw"}, f"{key} has {sorted(languages)}"


def test_a_variants_parameter_list_is_fixed_and_ordered():
    template = get_template("settlement_finalized_with_quantity", "whatsapp", "en")
    assert template.optional_variables == ()
    assert template.variables[0] == "number"
    assert len(template.variables) == len(set(template.variables)), "a duplicated parameter"
    # And it is the same list every time.
    assert (
        template.variables
        == get_template("settlement_finalized_with_quantity", "whatsapp", "en").variables
    )


# --- variant selection (§4) ---------------------------------------------------


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({}, "settlement_finalized_base"),
        ({"quantity": "412.5", "quantity_unit": "kg"}, "settlement_finalized_with_quantity"),
        # Half a group is not a group — rendering half of one is the failure
        # DEMO-028 already refused.
        ({"quantity": "412.5", "quantity_unit": ""}, "settlement_finalized_base"),
        ({"quantity": "", "quantity_unit": "kg"}, "settlement_finalized_base"),
    ],
)
def test_the_settlement_variant_follows_the_data(extra, expected):
    assert (
        select_template_key("settlement_finalized", "whatsapp", {**SETTLEMENT, **extra}) == expected
    )


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({}, "invoice_issued_base"),
        ({"quantity": "62", "quantity_unit": "L"}, "invoice_issued_with_quantity"),
        ({"previous_balance": "300.00"}, "invoice_issued_with_balance"),
        (
            {"quantity": "62", "quantity_unit": "L", "previous_balance": "300.00"},
            "invoice_issued_with_quantity_and_balance",
        ),
    ],
)
def test_the_invoice_variant_follows_the_data(extra, expected):
    assert select_template_key("invoice_issued", "whatsapp", {**INVOICE, **extra}) == expected


def test_every_reachable_combination_has_a_variant():
    """§3: only variants that are real, and all of them.

    Two optional groups exist on the invoice and one on the settlement, and
    every subset is reachable — mixed units report no quantity, a bill with
    nothing carried reports no balance, and a notification stored before
    DEMO-028 has neither when retried.
    """
    from itertools import combinations

    for journey, variants in VARIANTS.items():
        groups = set()
        for subset in variants:
            groups |= set(subset)
        reachable = {
            frozenset(c) for n in range(len(groups) + 1) for c in combinations(sorted(groups), n)
        }
        assert set(variants) == reachable, (
            f"{journey}: registered {sorted(map(sorted, variants))} "
            f"but reachable is {sorted(map(sorted, reachable))}"
        )


def test_selection_contains_no_vendor_and_no_channel_transport():
    """§4: no provider-specific logic, no vendor template id."""
    import inspect

    from platform_core.modules.notification import templates

    source = inspect.getsource(templates.select_template_key)
    for banned in ("twilio", "infobip", "gupshup", "msg91", "vendor_template", "provider"):
        assert banned not in source.lower(), f"{banned} leaked into template selection"


def test_an_unregistered_combination_is_refused_rather_than_approximated():
    """§5: do not silently drop a parameter, and do not invent one."""
    from platform_core.modules.notification import templates

    original = templates.VARIANTS["settlement_finalized"]
    try:
        templates.VARIANTS["settlement_finalized"] = {frozenset(): "settlement_finalized_base"}
        with pytest.raises(TemplateNotFoundError, match="no whatsapp variant"):
            select_template_key(
                "settlement_finalized",
                "whatsapp",
                {**SETTLEMENT, "quantity": "1", "quantity_unit": "kg"},
            )
    finally:
        templates.VARIANTS["settlement_finalized"] = original


# --- parameter validation (§5) -------------------------------------------------


def test_a_missing_parameter_is_rejected():
    template = get_template("settlement_finalized_with_quantity", "whatsapp", "en")
    values = {name: "X" for name in template.variables}
    del values["net_amount"]
    with pytest.raises(TemplateRenderError, match="missing parameter"):
        assert_fixed_parameters(template, values)


def test_an_unknown_parameter_is_rejected_by_render():
    template = get_template("settlement_finalized_with_quantity", "whatsapp", "en")
    values = {name: "X" for name in template.variables}
    with pytest.raises(TemplateRenderError, match="does not use"):
        render(template, {**values, "not_a_field": "x"})


def test_the_positional_parameters_are_complete_and_ordered():
    template = get_template("settlement_finalized_with_quantity", "whatsapp", "en")
    values = {name: f"v-{name}" for name in template.variables}
    params = fixed_parameters(template, values)
    assert len(params) == len(template.variables)
    assert params == tuple(f"v-{name}" for name in template.variables)


def test_the_parameter_list_refuses_a_gap_rather_than_blanking_it():
    """Found by DEMO-033's own production verification.

    `fixed_parameters` substituted an empty string for an absent variable, so
    calling it without `assert_fixed_parameters` first produced a positional
    list with holes — `('S-1', 'Grace', '', '', …)`. Dispatch does assert
    first, so nothing was ever sent that way; but a blank `{{3}}` is a farmer
    reading a message with a hole where a figure belongs, and a safety that
    depends on the caller remembering to call something else is not a safety.
    """
    template = get_template("settlement_finalized_with_quantity", "whatsapp", "en")
    values = {name: f"v-{name}" for name in template.variables}
    values.pop(template.variables[2])

    with pytest.raises(TemplateRenderError, match="missing"):
        fixed_parameters(template, values)


def test_a_template_that_still_varies_is_refused_on_a_fixed_channel():
    """Belt to the brace: if a varying template ever reaches WhatsApp again."""
    from platform_core.modules.notification.templates import Template

    varying = Template(
        key="x", channel="whatsapp", language="en", title="t", body="a {b}[[ c {d}]]"
    )
    with pytest.raises(TemplateRenderError, match="still has optional segments"):
        assert_fixed_parameters(varying, {"b": "1", "d": "2"})


# --- SMS and email are untouched (§6) -------------------------------------------


def test_sms_still_renders_its_optional_segment_when_present():
    template = get_template("settlement_finalized", "sms", "en")
    assert template.optional_variables, "SMS lost its optional segment"
    with_qty = render(template, {**SETTLEMENT, "quantity": "412.5", "quantity_unit": "kg"})
    assert "412.5 kg" in with_qty.body


def test_sms_still_omits_its_optional_segment_when_absent():
    template = get_template("settlement_finalized", "sms", "en")
    without = render(template, SETTLEMENT)
    assert "kg" not in without.body
    assert without.body.rstrip().endswith(".")


def test_email_still_renders_both_optional_segments():
    template = get_template("invoice_issued", "email", "en")
    assert set(template.optional_variables) >= {"quantity", "previous_balance"}
    full = render(
        template,
        {**INVOICE, "quantity": "62", "quantity_unit": "L", "previous_balance": "300.00"},
    )
    assert "62 L" in full.body
    assert "300.00" in full.body
    bare = render(template, INVOICE)
    assert "Delivered" not in bare.body
    assert "Brought forward" not in bare.body


def test_sms_and_email_selection_is_the_identity():
    for channel in ("sms", "email", "push"):
        for key in ("settlement_finalized", "invoice_issued"):
            assert select_template_key(key, channel, {}) == key


def test_present_groups_needs_every_member():
    assert present_groups({"quantity": "1", "quantity_unit": "kg"}) == frozenset({"quantity"})
    assert present_groups({"quantity": "1"}) == frozenset()
    assert present_groups({"previous_balance": "0.00"}) == frozenset({"balance"})
    assert present_groups({"previous_balance": ""}) == frozenset()


# --- approval lifecycle (§7, §9) -------------------------------------------------


async def _platform_admin(client):
    from tests.conftest import register_and_login

    _id, headers = await register_and_login(client, "approver@example.com", admin=True)
    return headers


def _command(**kw):
    return {
        "template_key": "settlement_finalized_with_quantity",
        "channel": "whatsapp",
        "language": "en",
        "provider": "example-gateway",
        "state": "pending",
        **kw,
    }


async def test_nothing_is_approved_until_somebody_records_it(client):
    """§9: existing templates must NOT automatically become APPROVED."""
    headers = await _platform_admin(client)
    body = (await client.get(REGISTRY, headers=headers)).json()
    states = {e["approval_state"] for e in body["entries"]}
    assert states == {"NOT_CONFIGURED"}, f"something was approved without being recorded: {states}"
    assert body["ready_whatsapp"] == 0


@pytest.mark.parametrize("state", ["pending", "approved", "rejected"])
async def test_an_operator_records_each_state(client, state):
    headers = await _platform_admin(client)
    answer = await client.post(APPROVAL, headers=headers, json=_command(state=state))
    assert answer.status_code == 200, answer.text
    assert answer.json()["state"] == state


async def test_a_transition_is_recorded_with_its_previous_state(client):
    """§9: previous state, new state, who and when."""
    from sqlalchemy import select

    from platform_core.core import db
    from platform_core.modules.audit.models import AuditRecord

    headers = await _platform_admin(client)
    await client.post(APPROVAL, headers=headers, json=_command(state="pending"))
    await client.post(
        APPROVAL,
        headers=headers,
        json=_command(
            state="approved", provider_template_id="gw_settle_v1", note="approved 16 Aug"
        ),
    )

    async with db.get_session_factory()() as session:
        rows = list(
            (
                await session.scalars(
                    select(AuditRecord).where(
                        AuditRecord.action == "notification.template_approval_recorded"
                    )
                )
            ).all()
        )
    assert len(rows) == 2
    first, second = sorted(rows, key=lambda r: r.created_at)
    assert first.detail["from"] == "NOT_CONFIGURED"
    assert first.detail["to"] == "pending"
    assert second.detail["from"] == "pending"
    assert second.detail["to"] == "approved"
    assert second.detail["provider_template_id"] == "gw_settle_v1"
    assert second.actor_id is not None, "an audit entry with no actor proves nothing"


async def test_an_unknown_state_is_refused(client):
    headers = await _platform_admin(client)
    answer = await client.post(APPROVAL, headers=headers, json=_command(state="probably-fine"))
    assert answer.status_code in (400, 422)


async def test_an_approval_for_a_template_that_does_not_exist_is_refused(client):
    """Recording an approval for something Lacteva cannot send is a note about
    nothing."""
    headers = await _platform_admin(client)
    answer = await client.post(
        APPROVAL, headers=headers, json=_command(template_key="not_a_template")
    )
    assert answer.status_code == 404


async def test_approving_english_does_not_approve_hindi(client):
    """§12, stated as a property."""
    headers = await _platform_admin(client)
    await client.post(
        APPROVAL,
        headers=headers,
        json=_command(state="approved", language="en", provider_template_id="gw_en"),
    )
    body = (await client.get(REGISTRY, headers=headers)).json()
    by_lang = {
        e["language"]: e["approval_state"]
        for e in body["entries"]
        if e["key"] == "settlement_finalized_with_quantity"
    }
    assert by_lang["en"] == "APPROVED"
    assert by_lang["hi"] == "NOT_CONFIGURED"
    assert by_lang["ar"] == "NOT_CONFIGURED"
    assert by_lang["sw"] == "NOT_CONFIGURED"


# --- readiness (§11) --------------------------------------------------------------


async def test_readiness_names_every_missing_condition(client):
    headers = await _platform_admin(client)
    body = (await client.get(REGISTRY, headers=headers)).json()
    entry = next(
        e
        for e in body["entries"]
        if e["key"] == "settlement_finalized_with_quantity" and e["language"] == "en"
    )
    assert entry["ready"] is False
    assert "not submitted for approval" in entry["blockers"]
    assert "provider template id missing" in entry["blockers"]


async def test_an_approved_and_mapped_template_is_ready(client, monkeypatch):
    """§11: the conjunction. Approval alone is not readiness."""
    headers = await _platform_admin(client)
    key = "settlement_finalized_with_quantity"

    await client.post(
        APPROVAL, headers=headers, json=_command(state="approved", provider_template_id="gw_v1")
    )
    only_approved = (await client.get(REGISTRY, headers=headers)).json()
    entry = next(e for e in only_approved["entries"] if e["key"] == key and e["language"] == "en")
    assert entry["ready"] is False, "approval without a provider mapping is not readiness"
    assert entry["blockers"] == ["provider template id missing"]

    monkeypatch.setattr(
        get_settings(), "notification_vendor_templates", {f"{key}.whatsapp": "gw_v1"}
    )
    now = (await client.get(REGISTRY, headers=headers)).json()
    ready = next(e for e in now["entries"] if e["key"] == key and e["language"] == "en")
    assert ready["ready"] is True
    assert ready["blockers"] == []
    assert now["ready_whatsapp"] == 1, "only the approved-and-mapped one is ready"


async def test_a_rejected_template_is_not_ready_and_says_so(client, monkeypatch):
    headers = await _platform_admin(client)
    key = "settlement_finalized_with_quantity"
    monkeypatch.setattr(
        get_settings(), "notification_vendor_templates", {f"{key}.whatsapp": "gw_v1"}
    )
    await client.post(
        APPROVAL, headers=headers, json=_command(state="rejected", note="wording too long")
    )
    body = (await client.get(REGISTRY, headers=headers)).json()
    entry = next(e for e in body["entries"] if e["key"] == key and e["language"] == "en")
    assert entry["ready"] is False
    assert entry["blockers"] == ["approval rejected"]
    assert entry["approval_note"] == "wording too long"


# --- security (§14) ----------------------------------------------------------------


async def test_an_anonymous_caller_cannot_record_an_approval(client):
    assert (await client.post(APPROVAL, json=_command())).status_code == 401


async def test_a_tenant_administrator_cannot_record_an_approval(client):
    """The messaging account is Lacteva's, so a dairy asserting an approval
    would be asserting something about somebody else's account."""
    from tests.test_org_structure import _tenant_admin

    _org, headers = await _tenant_admin(client)
    answer = await client.post(APPROVAL, headers=headers, json=_command())
    assert answer.status_code == 403


async def test_approval_is_the_same_platform_fact_for_every_tenant(client):
    """§13: approval is platform-global because the account is.

    Two tenants see the same answer — which is correct, and is why the table is
    declared PLATFORM_GLOBAL with a written reason rather than carrying a
    tenant_id nobody could fill in.
    """
    from tests.test_localization import _tenant_admin_for
    from tests.test_org_structure import _tenant_admin

    admin = await _platform_admin(client)
    await client.post(APPROVAL, headers=admin, json=_command(state="approved"))

    _org_a, headers_a = await _tenant_admin(client)
    _org_b, headers_b = await _tenant_admin_for(
        client, country="IN", slug="approval-other", email="admin@approval-other.example"
    )
    a = (await client.get(REGISTRY, headers=headers_a)).json()
    b = (await client.get(REGISTRY, headers=headers_b)).json()
    assert a == b
    assert "tenant" not in str(a).lower()


async def test_the_registry_still_exposes_no_credential(client):
    headers = await _platform_admin(client)
    body = (await client.get(REGISTRY, headers=headers)).json()
    fields = {k.lower() for e in body["entries"] for k in e}
    for forbidden in ("api_key", "apikey", "secret", "password", "credential"):
        assert not any(forbidden in f for f in fields)


# --- financial safety (§16) ---------------------------------------------------------


async def test_recording_an_approval_moves_no_money(client):
    from sqlalchemy import func, select

    from platform_core.core import db
    from platform_core.modules.billing.models import CustomerInvoice
    from platform_core.modules.payment.models import Payment
    from platform_core.modules.settlement.models import Settlement

    async def snapshot():
        async with db.get_session_factory()() as session:
            return (
                await session.scalar(select(func.count()).select_from(Settlement)),
                await session.scalar(select(func.coalesce(func.sum(Settlement.net_amount), 0))),
                await session.scalar(select(func.count()).select_from(CustomerInvoice)),
                await session.scalar(select(func.count()).select_from(Payment)),
            )

    headers = await _platform_admin(client)
    before = await snapshot()
    for state in ("pending", "approved", "rejected"):
        await client.post(APPROVAL, headers=headers, json=_command(state=state))
    assert await snapshot() == before
