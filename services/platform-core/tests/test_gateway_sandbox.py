"""Crossing the vendor boundary safely (DEMO-031).

Two properties, and the first is structural:

    **A deployment that configures a gateway and says nothing else sends
    nothing.** Provider selection says WHICH gateway; `messaging_mode` says
    whether the platform may talk to it at all, and it defaults to `test`.
    Forgetting a safety is not a safety, so the safety is the default.

    **A WhatsApp message is a TEMPLATE, not a paragraph.** The WhatsApp
    Business Platform will not accept business-initiated free text; it requires
    a pre-approved template named by the account and supplied with positional
    parameters. DEMO-025 wrote that limitation into its own docstring and
    shipped the text path anyway. The boundary now carries both.

No message leaves this process in any test here, and none of it is evidence
that a particular vendor behaves as documented.
"""

import uuid

import pytest

from platform_core.core.config import Settings, get_settings
from platform_core.modules.notification import providers as gateway
from platform_core.modules.notification.providers import (
    ACCEPTED,
    MessagingModeError,
    OutboundMessage,
    PermanentSendError,
    ProviderSendError,
    SandboxGatewayProvider,
    vendor_template_for,
)
from tests.test_notifications import _runner, provider_guard  # noqa: F401 — fixture

PROD = dict(
    env="prod",
    jwt_algorithm="HS256",
    jwt_secret="x" * 40,
    minio_secret_key="y" * 20,
    database_url="postgresql+asyncpg://u:p@db/lacteva",
    event_bus="rabbitmq",
    cors_origins=["https://dev.phoenixsoft.in"],
    debug=False,
    notification_sms_provider="disabled",
    notification_email_provider="disabled",
    notification_push_provider="disabled",
    notification_whatsapp_provider="disabled",
)


def _message(channel: str = "sms", **kw) -> OutboundMessage:
    return OutboundMessage(
        channel=channel,
        recipient=kw.pop("recipient", "+919845000101"),
        title="Settlement STL-1 ready",
        body="Hello Ramesh, settlement STL-1 is finalised.",
        language="en",
        template_key="settlement_finalized",
        notification_id=uuid.uuid4(),
        parameters=kw.pop("parameters", ("STL-1", "Ramesh")),
        vendor_template=kw.pop("vendor_template", None),
    )


def _problems(**overrides) -> str:
    try:
        Settings(**{**PROD, **overrides})
    except ValueError as exc:
        return str(exc)
    return ""


# --- the mode gate -------------------------------------------------------------


def test_the_default_mode_sends_nothing():
    """The safety is the DEFAULT, so forgetting it is safe."""
    assert Settings().messaging_mode == "test"


async def test_a_real_gateway_refuses_to_reach_the_network_in_test_mode(monkeypatch):
    """Configuring a gateway is not the same as permitting it to be used.

    Before DEMO-031 a deployment that set `http` with a URL and a key started
    sending the moment it came up.
    """
    monkeypatch.setattr(get_settings(), "messaging_mode", "test")
    monkeypatch.setattr(get_settings(), "sms_api_url", "https://gateway.invalid/send")
    monkeypatch.setattr(get_settings(), "sms_api_key", "k" * 20)

    provider = gateway.HttpSmsProvider("sms")
    with pytest.raises(MessagingModeError):
        await provider.send(_message())


async def test_the_refusal_is_permanent_rather_than_retried(monkeypatch):
    """A retry loop against a mode setting is just a slower refusal."""
    monkeypatch.setattr(get_settings(), "messaging_mode", "test")
    assert issubclass(MessagingModeError, PermanentSendError)


@pytest.mark.parametrize("mode", ["sandbox", "production"])
async def test_a_deliberate_mode_allows_the_network_call(monkeypatch, mode):
    """The gate opens when a deployment says so — and only then."""
    monkeypatch.setattr(get_settings(), "messaging_mode", mode)
    monkeypatch.setattr(get_settings(), "sms_api_url", "https://gateway.invalid/send")
    monkeypatch.setattr(get_settings(), "sms_api_key", "k" * 20)

    provider = gateway.HttpSmsProvider("sms")
    # It gets PAST the gate and fails on the network, which is a different
    # error — the gate is not what stopped it.
    with pytest.raises(ProviderSendError) as caught:
        await provider.send(_message())
    assert not isinstance(caught.value, MessagingModeError)


def test_production_refuses_the_sandbox_mode_and_the_sandbox_adapter():
    """A sandbox in production is a platform that believes it is telling
    farmers about their money and is telling nobody."""
    assert "MESSAGING_MODE must not be 'sandbox'" in _problems(messaging_mode="sandbox")
    assert "SMS_PROVIDER is 'sandbox'" in _problems(notification_sms_provider="sandbox")


def test_production_still_refuses_the_providers_that_pretend():
    """DEMO-025's guard, unchanged — `logging` and `placeholder` mark every
    message delivered and send nothing."""
    assert "which marks" in _problems(notification_sms_provider="logging")
    assert "which marks" in _problems(notification_sms_provider="placeholder")


# --- the sandbox gateway --------------------------------------------------------


async def test_the_sandbox_accepts_a_plausible_message(monkeypatch):
    monkeypatch.setattr(get_settings(), "messaging_mode", "sandbox")
    provider = SandboxGatewayProvider("sms")
    result = await provider.send(_message())
    assert result.status == ACCEPTED
    assert result.provider_message_id.startswith("sbx-")
    assert result.metadata["sandbox"] is True
    assert len(provider.sent) == 1


async def test_the_sandbox_refuses_to_run_in_production_mode(monkeypatch):
    """It reaches nobody. In production that is worse than failing."""
    monkeypatch.setattr(get_settings(), "messaging_mode", "production")
    with pytest.raises(PermanentSendError, match="must not run in production"):
        await SandboxGatewayProvider("sms").send(_message())


async def test_the_sandbox_refuses_an_implausible_recipient(monkeypatch):
    monkeypatch.setattr(get_settings(), "messaging_mode", "sandbox")
    with pytest.raises(PermanentSendError, match="implausible recipient"):
        await SandboxGatewayProvider("sms").send(_message(recipient="12345"))


@pytest.mark.parametrize(
    ("recipient", "expected"),
    [
        ("+919845000101", None),
        ("+919845000107", ProviderSendError),  # temporary — retryable
        ("+919845000108", PermanentSendError),  # permanent — do not retry
    ],
)
async def test_outcomes_are_deterministic_and_addressable(monkeypatch, recipient, expected):
    """Driven by the recipient rather than a clock or a random source, so a
    test can address retryable and permanent failure without patching."""
    monkeypatch.setattr(get_settings(), "messaging_mode", "sandbox")
    provider = SandboxGatewayProvider("sms")
    if expected is None:
        assert (await provider.send(_message(recipient=recipient))).status == ACCEPTED
    else:
        with pytest.raises(expected):
            await provider.send(_message(recipient=recipient))


async def test_a_temporary_failure_is_not_a_permanent_one(monkeypatch):
    """§10: the existing classification decides whether a retry is spent."""
    monkeypatch.setattr(get_settings(), "messaging_mode", "sandbox")
    provider = SandboxGatewayProvider("sms")
    with pytest.raises(ProviderSendError) as caught:
        await provider.send(_message(recipient="+919845000107"))
    assert not isinstance(caught.value, PermanentSendError), (
        "a transient upstream failure was classified as permanent — the message "
        "would never be retried"
    )


# --- WhatsApp needs a template, not a paragraph ---------------------------------


async def test_whatsapp_refuses_a_message_with_no_approved_template(monkeypatch):
    """The constraint DEMO-025 documented and could not enforce.

    A business-initiated WhatsApp message must name a pre-approved template.
    An adapter with none configured is refused PERMANENTLY, because a retry
    cannot approve a template that was never submitted.
    """
    monkeypatch.setattr(get_settings(), "messaging_mode", "sandbox")
    with pytest.raises(PermanentSendError, match="requires an approved template"):
        await SandboxGatewayProvider("whatsapp").send(_message(channel="whatsapp"))


async def test_whatsapp_sends_the_template_and_its_parameters(monkeypatch):
    monkeypatch.setattr(get_settings(), "messaging_mode", "sandbox")
    provider = SandboxGatewayProvider("whatsapp")
    result = await provider.send(
        _message(
            channel="whatsapp",
            vendor_template="lacteva_settlement_v1",
            parameters=("STL-1", "Ramesh", "1000.00"),
        )
    )
    assert result.status == ACCEPTED
    assert provider.sent[0].vendor_template == "lacteva_settlement_v1"
    assert provider.sent[0].parameters == ("STL-1", "Ramesh", "1000.00")


async def test_a_template_message_with_no_parameters_is_refused(monkeypatch):
    monkeypatch.setattr(get_settings(), "messaging_mode", "sandbox")
    with pytest.raises(PermanentSendError, match="needs parameters"):
        await SandboxGatewayProvider("whatsapp").send(
            _message(channel="whatsapp", vendor_template="t", parameters=())
        )


def test_a_vendor_template_name_is_configuration_and_never_a_constant(monkeypatch):
    """An approved name is issued per account and per market. Hard-coding one
    would put a vendor's registry into this repository."""
    assert vendor_template_for("settlement_finalized", "whatsapp") is None
    monkeypatch.setattr(
        get_settings(),
        "notification_vendor_templates",
        {"settlement_finalized.whatsapp": "lacteva_settlement_v1"},
    )
    assert vendor_template_for("settlement_finalized", "whatsapp") == "lacteva_settlement_v1"


def test_no_vendor_name_appears_in_the_notification_domain():
    """§3 and §13: the domain knows notification, channel, recipient, template,
    message, delivery status — and no vendor, and no country."""
    import ast
    import pathlib

    import platform_core.modules.notification as package

    banned = {
        "twilio",
        "infobip",
        "gupshup",
        "msg91",
        "kaleyra",
        "africastalking",
        "africas talking",
        "vonage",
        "sinch",
        "karix",
        "textlocal",
        "india",
        "kenya",
        "in",
        "ke",
    }
    root = pathlib.Path(package.__file__).parent
    offenders = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text())
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                doc = ast.get_docstring(node, clean=False)
                if doc is not None:
                    docstrings.add(doc)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in docstrings:
                    continue
                if node.value.strip().lower() in banned:
                    offenders.append(f"{path.name}:{node.lineno}: {node.value!r}")
    assert not offenders, f"a vendor or a country is a VALUE in the domain: {offenders}"


# --- the ordered parameters come from the template itself ------------------------


def test_the_parameters_are_the_templates_own_declared_order():
    """No new concept in the domain: WhatsApp's `{{1}}, {{2}}` is exactly the
    order the template already declares."""
    from platform_core.modules.notification.templates import get_template

    # DEMO-033: on WhatsApp the journey is a fixed-parameter VARIANT, so the
    # old key no longer resolves — which is the point. What DEMO-031 asserted
    # (the order is the template's own) is unchanged and now stronger, because
    # the variant has NO optional segments at all.
    template = get_template("settlement_finalized_with_quantity", "whatsapp", "en")
    assert template.variables[0] == "number"
    assert "name" in template.variables
    assert template.optional_variables == (), (
        "a WhatsApp template with a varying parameter count is not a template"
    )


async def test_dispatch_carries_the_parameters_to_the_boundary(client, provider_guard, monkeypatch):  # noqa: F811
    """End to end: a settlement produces a message whose parameters an adapter
    could hand to a template API."""
    monkeypatch.setattr(get_settings(), "messaging_mode", "sandbox")
    recorder = SandboxGatewayProvider("sms")
    provider_guard.register_provider("sms", recorder)

    from tests.test_message_delivery import _settlement_env

    headers, _supplier, settlement = await _settlement_env(client)
    finalized = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    assert finalized.status_code == 200, finalized.text
    await _runner().run_once()

    assert recorder.sent, "the sandbox gateway received nothing"
    # The registration message reaches the gateway first; this is about the
    # settlement one.
    settlements = [m for m in recorder.sent if m.template_key == "settlement_finalized"]
    assert settlements, f"no settlement message: {[m.template_key for m in recorder.sent]}"
    message = settlements[0]
    assert message.parameters, "no positional parameters reached the boundary"
    # Every parameter is substituted — a template API rejects a placeholder.
    assert all("{" not in value for value in message.parameters)
    assert finalized.json()["settlement_number"] in message.parameters


# --- financial safety ------------------------------------------------------------


async def test_crossing_the_vendor_boundary_moves_no_money(client, provider_guard, monkeypatch):  # noqa: F811
    """§16. A gateway is a way to tell someone about money, not to move it."""
    from sqlalchemy import func, select

    from platform_core.core import db
    from platform_core.modules.billing.models import CustomerInvoice
    from platform_core.modules.payment.models import Payment
    from platform_core.modules.receipt.models import Receipt
    from platform_core.modules.settlement.models import Settlement

    async def snapshot():
        async with db.get_session_factory()() as session:
            return {
                "settlements": await session.scalar(select(func.count()).select_from(Settlement)),
                "settled": await session.scalar(
                    select(func.coalesce(func.sum(Settlement.net_amount), 0))
                ),
                "invoices": await session.scalar(select(func.count()).select_from(CustomerInvoice)),
                "receivable": await session.scalar(
                    select(func.coalesce(func.sum(CustomerInvoice.amount_due), 0))
                ),
                "payments": await session.scalar(select(func.count()).select_from(Payment)),
                "receipts": await session.scalar(select(func.count()).select_from(Receipt)),
            }

    monkeypatch.setattr(get_settings(), "messaging_mode", "sandbox")
    provider_guard.register_provider("sms", SandboxGatewayProvider("sms"))

    from tests.test_message_delivery import _settlement_env

    headers, _supplier, settlement = await _settlement_env(client)
    await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)

    before = await snapshot()
    await _runner().run_once()
    await _runner().run_once()
    assert await snapshot() == before, "sending through a gateway changed a financial record"


# --- credentials never leave ------------------------------------------------------


async def test_no_endpoint_exposes_a_credential(client):
    """§5 and §11. A credential in an API response is a credential published."""
    schema = (await client.get("/openapi.json")).json()
    text = str(schema).lower()
    for secret in ("api_key", "apikey", "sms_api_key", "whatsapp_api_key", "receipt_secret"):
        assert secret not in text, f"{secret} appears in the API schema"


def test_no_credential_is_committed_to_the_notification_source():
    import pathlib
    import re

    import platform_core.modules.notification as package

    pattern = re.compile(
        r"""(api[_-]?key|secret|token|password)\s*=\s*["'][A-Za-z0-9_\-]{12,}["']""",
        re.IGNORECASE,
    )
    root = pathlib.Path(package.__file__).parent
    offenders = [
        f"{path.name}: {match.group(0)}"
        for path in root.glob("*.py")
        for match in pattern.finditer(path.read_text())
    ]
    assert not offenders, f"a credential is committed: {offenders}"
