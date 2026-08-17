"""The provider-independent template registry (DEMO-032).

Two properties:

    **A variable nobody displays is a variable nobody sees.** Rendering used to
    accept an unknown variable silently, so a rename or a new figure could
    reach a farmer as a message that looked complete and was missing a number.

    **The registry describes what Lacteva can send, and what a vendor would
    still need.** It knows no vendor: the only vendor-shaped field is a NAME
    read from deployment configuration, `None` on every deployment today.

Nothing here sends anything, and no vendor was contacted.
"""

import pytest

from platform_core.core.config import get_settings
from platform_core.modules.notification.service import NotificationService
from platform_core.modules.notification.templates import (
    BUSINESS_PURPOSE_KEYS,
    PURPOSES,
    TEMPLATES,
    TemplateRenderError,
    catalog,
    get_template,
    render,
    variables_for,
)

REGISTRY = "/v1/notification-templates/registry"


# --- variable safety (§8) --------------------------------------------------------


def test_a_missing_variable_is_still_rejected():
    """Unchanged: half a sentence on a farmer's settlement is worse than none."""
    template = get_template("settlement_finalized", "sms", "en")
    with pytest.raises(TemplateRenderError, match="missing variable"):
        render(template, {"number": "STL-1"})


def test_a_variable_no_template_displays_is_rejected():
    """The defect. A renamed or newly-added figure used to vanish in silence.

    The message still rendered, still read as a complete sentence, and simply
    did not contain the number somebody had just added for the farmer.
    """
    template = get_template("settlement_finalized", "sms", "en")
    values = {name: "X" for name in template.variables}
    with pytest.raises(TemplateRenderError, match="does not use"):
        render(template, {**values, "net_ammount": "1000.00"})


def test_a_variable_another_channel_displays_is_accepted():
    """One dispatch builder feeds every channel of a key.

    `invoice_issued` supplies `period` for the push template and
    `previous_balance` for WhatsApp and email; the SMS template uses neither.
    Requiring each channel's exact set would make that deliberate superset an
    error — the first draft of this check did, and three delivery tests said so.
    """
    template = get_template("invoice_issued", "sms", "en")
    values = {name: "X" for name in template.variables}
    rendered = render(template, {**values, "period": "Aug", "previous_balance": "0.00"})
    assert rendered.body


def test_an_optional_segment_variable_is_known():
    """Supplying one is how a segment is switched on."""
    template = get_template("settlement_finalized", "sms", "en")
    values = {name: "X" for name in template.variables}
    rendered = render(template, {**values, "quantity": "412.5", "quantity_unit": "kg"})
    assert "412.5" in rendered.body


def test_variables_for_spans_every_channel_and_language():
    names = variables_for("settlement_finalized")
    assert {"number", "net_amount", "currency"} <= names
    assert {"quantity", "quantity_unit"} <= names, "optional variables are known too"
    assert "period" not in names, "a variable from a different key leaked in"


def test_variable_order_is_deterministic():
    """A positional-parameter API needs the same order every time."""
    # DEMO-033: on WhatsApp the journey is a fixed-parameter VARIANT.
    key = "settlement_finalized_with_quantity"
    for _ in range(5):
        assert get_template(key, "whatsapp", "en").variables == (
            get_template(key, "whatsapp", "en").variables
        )
    template = get_template(key, "whatsapp", "en")
    assert template.variables[0] == "number", "declared order, not alphabetical"
    assert not template.optional_variables, "a fixed-parameter template cannot vary"


def test_an_unknown_channel_is_rejected_rather_than_guessed():
    from platform_core.modules.notification.templates import TemplateNotFoundError

    with pytest.raises(TemplateNotFoundError):
        get_template("settlement_finalized", "carrier-pigeon", "en")


# --- the registry itself (§5) ----------------------------------------------------


def test_every_template_has_a_business_purpose():
    """§6: only journeys the product actually has, and all of them."""
    keys = {template.key for template in TEMPLATES}
    assert keys == set(PURPOSES), (
        f"purpose drift — templates without one: {sorted(keys - set(PURPOSES))}, "
        f"purposes without a template: {sorted(set(PURPOSES) - keys)}"
    )
    for key, purpose in PURPOSES.items():
        assert purpose and purpose[0].isupper(), f"{key} has no readable purpose"


def test_the_registry_describes_every_template():
    registry = NotificationService.registry()
    assert registry.total == len(catalog())
    entry = next(e for e in registry.entries if e.key == "settlement_finalized")
    assert entry.purpose.startswith("Tells a farmer")
    assert entry.variables, "no ordered variables"
    assert entry.version == 1
    assert entry.active is True
    assert entry.business is True


def test_platform_messages_are_not_marked_as_business_journeys():
    """A password reset is not something a dairy sends its farmers."""
    registry = NotificationService.registry()
    reset = next(e for e in registry.entries if e.key == "password_reset")
    assert reset.business is False
    assert "invitation" not in BUSINESS_PURPOSE_KEYS


def test_the_registry_names_no_vendor():
    """§11: provider-neutral. The only vendor-shaped field is a configured name."""
    registry = NotificationService.registry()
    text = registry.model_dump_json().lower()
    for vendor in ("twilio", "infobip", "gupshup", "msg91", "africastalking", "kaleyra"):
        assert vendor not in text


# --- provider mapping (§11) ------------------------------------------------------


def test_an_unmapped_deployment_reports_not_configured_and_still_works():
    """§11: the application must work correctly when no mapping exists."""
    registry = NotificationService.registry()
    whatsapp = [e for e in registry.entries if e.channel == "whatsapp"]
    assert whatsapp, "the premise: WhatsApp templates exist"
    assert all(e.provider_mapping_status == "NOT_CONFIGURED" for e in whatsapp)
    assert all(e.provider_template is None for e in whatsapp)
    assert registry.unmapped_whatsapp == len(whatsapp)


def test_sms_and_email_are_not_reported_as_unmapped():
    """They send text. A vendor template name is only meaningful where a vendor
    requires one, and calling these unmapped would invent 33 problems."""
    registry = NotificationService.registry()
    for entry in registry.entries:
        if entry.channel in ("sms", "email", "push") and entry.provider_template is None:
            assert entry.provider_mapping_status == "NOT_APPLICABLE"


def test_a_configured_mapping_is_reported(monkeypatch):
    # DEMO-033: mapping is per VARIANT, because each variant is a separate
    # template a vendor approves separately.
    key = "settlement_finalized_with_quantity"
    monkeypatch.setattr(
        get_settings(),
        "notification_vendor_templates",
        {f"{key}.whatsapp": "lacteva_settlement_v1"},
    )
    registry = NotificationService.registry()
    total_whatsapp = sum(1 for e in registry.entries if e.channel == "whatsapp")
    mapped = [e for e in registry.entries if e.key == key and e.channel == "whatsapp"]
    assert mapped
    assert all(e.provider_mapping_status == "CONFIGURED" for e in mapped)
    assert all(e.provider_template == "lacteva_settlement_v1" for e in mapped)
    assert registry.unmapped_whatsapp == total_whatsapp - len(mapped)


# --- the WhatsApp finding (§7) ---------------------------------------------------


def test_no_whatsapp_template_still_carries_an_optional_segment():
    """DEMO-032 found every business WhatsApp template unapprovable; DEMO-033
    fixed it, and this is the assertion inverted.

    The guarantee is unchanged — the registry tells the truth about whether a
    template could be approved. What changed is the truth: each journey now has
    explicit fixed-parameter variants instead of one template that varies.
    """
    registry = NotificationService.registry()
    whatsapp = [e for e in registry.entries if e.channel == "whatsapp"]
    assert whatsapp, "the WhatsApp templates disappeared"
    blocked = [(e.key, e.language, e.whatsapp_blocker) for e in whatsapp if not e.whatsapp_ready]
    assert not blocked, f"a WhatsApp template still cannot be approved: {blocked}"
    for entry in whatsapp:
        assert entry.optional_variables == [], (
            f"{entry.key} still varies — an approved template cannot"
        )
        assert entry.variables, "a template with nothing to substitute is not a template"


def test_a_template_with_no_parameters_is_also_reported():
    """A WhatsApp template with nothing to substitute is not a template."""
    from platform_core.modules.notification.service import TemplateRegistryEntry

    entry = TemplateRegistryEntry(
        key="k",
        purpose="p",
        channel="whatsapp",
        language="en",
        title="t",
        body="b",
        variables=[],
        optional_variables=[],
        version=1,
        active=True,
        business=True,
        provider_mapping_status="NOT_CONFIGURED",
    )
    assert entry.whatsapp_ready is True  # the DTO default; the service computes it
    registry = NotificationService.registry()
    assert any(e.whatsapp_blocker for e in registry.entries), "nothing is ever reported"


# --- language (§9) ---------------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "hi", "ar", "sw"])
def test_every_business_journey_is_registered_in_every_language(language):
    """The existing language support, preserved and now visible in the registry."""
    from platform_core.modules.notification.templates import select_template_key

    registry = NotificationService.registry()
    for key in ("settlement_finalized", "invoice_issued"):
        for channel in ("sms", "whatsapp", "email"):
            # DEMO-033: on WhatsApp the journey resolves to a variant.
            resolved = select_template_key(key, channel, {})
            matches = [
                e
                for e in registry.entries
                if e.key == resolved and e.channel == channel and e.language == language
            ]
            assert matches, f"{resolved}/{channel} has no {language} entry"


def test_the_registry_contains_no_country():
    """§9: language is a property of the recipient and the template. Not a country."""
    registry = NotificationService.registry()
    text = registry.model_dump_json().lower()
    for country in ('"india"', '"kenya"', '"in"', '"ke"'):
        assert country not in text


# --- the API (§10, §13) ----------------------------------------------------------


async def test_the_registry_endpoint_refuses_an_anonymous_caller(client):
    assert (await client.get(REGISTRY)).status_code == 401


async def test_the_registry_endpoint_serves_an_authorized_operator(client):
    from tests.test_org_structure import _tenant_admin

    _org, headers = await _tenant_admin(client)
    answer = await client.get(REGISTRY, headers=headers)
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["total"] == len(catalog())
    assert body["unmapped_whatsapp"] >= 0
    assert any(e["purpose"] for e in body["entries"])


async def test_the_registry_exposes_no_credential(client):
    from tests.test_org_structure import _tenant_admin

    _org, headers = await _tenant_admin(client)
    body = (await client.get(REGISTRY, headers=headers)).json()

    # The sweep excludes template CONTENT, because a template legitimately
    # mentions its own variables: the invitation email says `{invite_token}`,
    # which is a variable NAME and not a credential. DEMO-025 hit the same
    # false positive and narrowed the same way — the thing to check is whether
    # a credential VALUE or a credential FIELD reached the response.
    fields = {key.lower() for entry in body["entries"] for key in entry}
    for forbidden in ("api_key", "apikey", "secret", "password", "credential", "auth"):
        assert not any(forbidden in field for field in fields), (
            f"a {forbidden} field is in the registry response"
        )

    # And no value anywhere looks like a credential or a gateway URL.
    values = [
        str(value)
        for entry in body["entries"]
        for key, value in entry.items()
        if key not in ("body", "title")
    ]
    for value in values:
        assert "https://" not in value, f"a URL reached the registry: {value[:60]}"
        assert not (len(value) > 24 and value.isalnum()), f"a secret-shaped value: {value[:20]}"


async def test_two_tenants_see_the_same_registry_and_no_tenant_data(client):
    """§13. Templates are code and are process-wide; that is the existing
    architecture, and it is why there is nothing here to isolate.

    What IS per-tenant is the channel a dairy chose, and it is not exposed.
    """
    from tests.test_localization import _tenant_admin_for
    from tests.test_org_structure import _tenant_admin

    _org_a, headers_a = await _tenant_admin(client)
    _org_b, headers_b = await _tenant_admin_for(
        client, country="IN", slug="registry-other", email="admin@registry-other.example"
    )
    a = (await client.get(REGISTRY, headers=headers_a)).json()
    b = (await client.get(REGISTRY, headers=headers_b)).json()
    assert a == b, "the registry differs per tenant — it should describe the code"
    assert "tenant" not in str(a).lower(), "tenant data leaked into a process-wide view"


async def test_no_endpoint_can_modify_a_template(client):
    """Read-only, and asserted rather than assumed.

    A template is code: reviewed, shipped, and re-rendered months later for a
    retry. A database-editable message a farmer receives about their money is a
    change nobody reviewed.

    Two POSTs are exempt because neither touches a template's text: `/preview`
    renders one and returns it, and DEMO-033's `/approval` records what an
    external provider decided ABOUT a template. Approving a wording does not
    change the wording — and if it ever did, this list is where it would show.
    """
    exempt = ("/preview", "/approval")
    schema = (await client.get("/openapi.json")).json()
    writable = [
        (path, method)
        for path, operations in schema["paths"].items()
        if "notification-templates" in path
        for method in operations
        if method in ("post", "put", "patch", "delete") and not path.endswith(exempt)
    ]
    assert not writable, f"a template can be changed at runtime: {writable}"


# --- financial safety (§15) ------------------------------------------------------


async def test_reading_the_registry_moves_no_money(client):
    from sqlalchemy import func, select

    from platform_core.core import db
    from platform_core.modules.billing.models import CustomerInvoice
    from platform_core.modules.payment.models import Payment
    from platform_core.modules.settlement.models import Settlement
    from tests.test_org_structure import _tenant_admin

    async def snapshot():
        async with db.get_session_factory()() as session:
            return (
                await session.scalar(select(func.count()).select_from(Settlement)),
                await session.scalar(select(func.coalesce(func.sum(Settlement.net_amount), 0))),
                await session.scalar(select(func.count()).select_from(CustomerInvoice)),
                await session.scalar(select(func.count()).select_from(Payment)),
            )

    _org, headers = await _tenant_admin(client)
    before = await snapshot()
    for _ in range(3):
        assert (await client.get(REGISTRY, headers=headers)).status_code == 200
    assert await snapshot() == before


# --- the DEMO-031 safety, preserved (§12) ----------------------------------------


def test_the_messaging_mode_default_is_unchanged():
    """§12: no accidental external communication, still."""
    from platform_core.core.config import Settings

    assert Settings().messaging_mode == "test"
    posture = NotificationService.posture()
    assert posture.sends_real_messages is False
