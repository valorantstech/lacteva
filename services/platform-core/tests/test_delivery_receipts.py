"""Delivery receipts and recipient reachability (DEMO-029).

Two properties, and each is about refusing to claim something:

    **A message is DELIVERED only because a gateway said so, in a signed
    report, once.** Acceptance is not delivery, a replay is not news, and a
    late report never un-delivers an arrived message.

    **Reachability answers UNKNOWN when it does not know.** A phone number is
    not a WhatsApp account, and reporting one as reachable would be inventing a
    capability nobody has.

And one thing that must stay true throughout: **none of this blocks money.** A
farmer with no phone number is settled and paid exactly as before, and appears
in a report so somebody can see them.
"""

import uuid

import pytest
from sqlalchemy import func, select

from platform_core.core import db
from platform_core.core.config import get_settings
from platform_core.modules.notification import providers as notification_providers
from platform_core.modules.notification.models import (
    Notification,
    NotificationReceiptEvent,
)
from platform_core.modules.notification.reachability import (
    INVALID_PHONE,
    PHONE_MISSING,
    PROVIDER_UNAVAILABLE,
    REACHABLE,
    UNKNOWN,
    UNREACHABLE,
    WHATSAPP_UNKNOWN,
    evaluate,
    looks_like_a_phone_number,
    looks_like_an_email,
)
from platform_core.modules.notification.receipts import _next_status
from tests.test_notifications import _runner, provider_guard  # noqa: F401 — fixture

RECEIPTS = "/v1/notifications/receipts/receipt-test"
REACHABILITY = "/v1/notifications/reachability"
SECRET = "demo029-receipt-secret"


@pytest.fixture
def gateway(monkeypatch, provider_guard):  # noqa: F811
    """A TEST provider that accepts receipts, on the sms channel."""
    monkeypatch.setattr(get_settings(), "notification_receipt_secret", SECRET)
    provider = notification_providers.ReceiptTestProvider("sms")
    provider_guard.register_provider("sms", provider)
    return provider


async def _sent_notification(client, gateway) -> Notification:
    """One settlement statement, handed to the gateway and accepted."""
    from tests.test_message_delivery import _settlement_env

    headers, _supplier, settlement = await _settlement_env(client)
    finalized = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    assert finalized.status_code == 200, finalized.text
    await _runner().run_once()

    async with db.get_session_factory()() as session:
        row = await session.scalar(
            select(Notification).where(Notification.template_key == "settlement_finalized")
        )
    assert row is not None and row.status == "sent", "the premise: a message was accepted"
    return row


def _deliver(gateway, *, event_id: str, reference: str, status: str, reason: str | None = None):
    body = gateway.receipt_body(
        event_id=event_id, reference=reference, status=status, reason=reason
    )
    return body, {notification_providers.SIGNATURE_HEADER: gateway.sign(body)}


async def _reload(notification_id: uuid.UUID) -> Notification:
    async with db.get_session_factory()() as session:
        return await session.get(Notification, notification_id)


async def _receipt_events() -> int:
    async with db.get_session_factory()() as session:
        return await session.scalar(select(func.count()).select_from(NotificationReceiptEvent))


# --- the transition rule, as a pure function ----------------------------------


@pytest.mark.parametrize(
    ("current", "reported", "expected"),
    [
        ("sent", "delivered", "delivered"),
        ("sent", "failed", "failed"),
        ("sent", "unknown", None),
        # A late failure never un-delivers an arrived message.
        ("delivered", "failed", None),
        ("delivered", "delivered", None),
        ("delivered", "unknown", None),
        # A gateway that reported a temporary failure and then delivered has
        # told us something true and later.
        ("failed", "delivered", "delivered"),
        ("failed", "failed", None),
        # Nothing was ever handed over, so nothing can be reported on.
        ("pending", "delivered", None),
        ("dead", "delivered", None),
    ],
)
def test_a_receipt_moves_a_message_only_forwards(current, reported, expected):
    assert _next_status(current, reported) == expected


def test_delivered_is_terminal_for_every_report_a_gateway_can_send():
    """§4's explicit prohibition, stated as a property rather than a case."""
    for reported in ("delivered", "failed", "unknown", "sent", "queued", "anything"):
        assert _next_status("delivered", reported) is None


# --- the receipt path ---------------------------------------------------------


async def test_a_signed_receipt_marks_a_message_delivered(client, gateway):
    """DEMO A. The step the platform has never been able to take."""
    notification = await _sent_notification(client, gateway)
    assert notification.delivered_at is None
    assert notification.provider_status == "accepted", "acceptance is not delivery"

    body, headers = _deliver(
        gateway,
        event_id="evt-1",
        reference=notification.provider_reference,
        status="delivered",
    )
    answer = await client.post(RECEIPTS, content=body, headers=headers)
    assert answer.status_code == 200
    assert answer.json()["outcome"] == "delivered"

    after = await _reload(notification.id)
    assert after.status == "delivered"
    assert after.delivered_at is not None
    assert after.provider_status == "delivered", "the gateway's own word, kept"


async def test_a_replayed_receipt_changes_nothing(client, gateway):
    notification = await _sent_notification(client, gateway)
    body, headers = _deliver(
        gateway, event_id="evt-dup", reference=notification.provider_reference, status="delivered"
    )
    first = await client.post(RECEIPTS, content=body, headers=headers)
    assert first.json()["outcome"] == "delivered"
    delivered_at = (await _reload(notification.id)).delivered_at

    for _ in range(4):
        again = await client.post(RECEIPTS, content=body, headers=headers)
        assert again.status_code == 200, "a gateway reads non-2xx as retry"
        assert again.json()["outcome"] == "replayed"

    after = await _reload(notification.id)
    assert after.delivered_at == delivered_at, "a replay moved the delivery time"
    assert await _receipt_events() == 1, "a replay created a second event row"


async def test_an_out_of_order_failure_after_delivery_is_ignored_but_recorded(client, gateway):
    """The corruption §3 asks about: a duplicate must not damage the state."""
    notification = await _sent_notification(client, gateway)
    body, headers = _deliver(
        gateway, event_id="evt-ok", reference=notification.provider_reference, status="delivered"
    )
    await client.post(RECEIPTS, content=body, headers=headers)

    late, late_headers = _deliver(
        gateway,
        event_id="evt-late",
        reference=notification.provider_reference,
        status="undelivered",
        reason="handset unreachable",
    )
    answer = await client.post(RECEIPTS, content=late, headers=late_headers)
    assert answer.status_code == 200
    assert answer.json()["outcome"] == "ignored_delivered"

    after = await _reload(notification.id)
    assert after.status == "delivered", "a late failure un-delivered an arrived message"
    # It IS recorded: an operator should be able to see the gateway said it.
    assert await _receipt_events() == 2


async def test_a_failure_receipt_moves_a_sent_message_to_failed(client, gateway):
    notification = await _sent_notification(client, gateway)
    body, headers = _deliver(
        gateway,
        event_id="evt-fail",
        reference=notification.provider_reference,
        status="undelivered",
        reason="number does not exist",
    )
    answer = await client.post(RECEIPTS, content=body, headers=headers)
    assert answer.json()["outcome"] == "failed"

    after = await _reload(notification.id)
    assert after.status == "failed"
    assert after.delivered_at is None
    assert "number does not exist" in (after.error or "")


async def test_a_status_the_adapter_cannot_read_moves_nothing(client, gateway):
    """`unknown` is not progress. Guessing would be inventing information."""
    notification = await _sent_notification(client, gateway)
    body, headers = _deliver(
        gateway,
        event_id="evt-weird",
        reference=notification.provider_reference,
        status="ACCEPTED_BY_UPSTREAM_ROUTER",
    )
    answer = await client.post(RECEIPTS, content=body, headers=headers)
    assert answer.json()["outcome"] == "ignored_sent"
    after = await _reload(notification.id)
    assert after.status == "sent"
    assert after.delivered_at is None


# --- refusing what it cannot verify -------------------------------------------


async def test_an_unsigned_or_wrongly_signed_receipt_is_refused(client, gateway):
    """`{"status": "delivered"}` is not proof of anything."""
    notification = await _sent_notification(client, gateway)
    body = gateway.receipt_body(
        event_id="evt-forged", reference=notification.provider_reference, status="delivered"
    )
    for bad in ({}, {notification_providers.SIGNATURE_HEADER: "deadbeef"}):
        answer = await client.post(RECEIPTS, content=body, headers=bad)
        assert answer.status_code == 401, answer.text

    after = await _reload(notification.id)
    assert after.status == "sent"
    assert await _receipt_events() == 0


async def test_a_receipt_naming_an_unknown_message_creates_nothing(client, gateway):
    """An unauthenticated endpoint must not be a way to fill a table."""
    body, headers = _deliver(
        gateway, event_id="evt-nowhere", reference="not-a-real-reference", status="delivered"
    )
    answer = await client.post(RECEIPTS, content=body, headers=headers)
    assert answer.status_code == 200
    assert answer.json()["outcome"] == "unknown_reference"
    assert await _receipt_events() == 0


async def test_a_provider_that_does_not_do_receipts_has_no_endpoint(client, provider_guard):  # noqa: F811
    """Capability is not invented: most of these adapters cannot do this."""
    provider_guard.register_provider("sms", notification_providers.LoggingProvider("sms"))
    answer = await client.post("/v1/notifications/receipts/sms", content=b"{}")
    assert answer.status_code == 404


async def test_a_receipt_endpoint_needs_no_login_and_says_only_what_it_did(client, gateway):
    notification = await _sent_notification(client, gateway)
    body, headers = _deliver(
        gateway,
        event_id="evt-noauth",
        reference=notification.provider_reference,
        status="delivered",
    )
    answer = await client.post(RECEIPTS, content=body, headers=headers)
    assert answer.status_code == 200
    assert set(answer.json()) == {"outcome"}, "no tenant, no recipient, no content"


async def test_a_receipt_never_moves_a_business_date(client, gateway):
    """§15. A report arriving the next day belongs to the original message."""
    notification = await _sent_notification(client, gateway)
    period_before = (notification.payload.get("period_from"), notification.payload.get("period_to"))
    body, headers = _deliver(
        gateway,
        event_id="evt-late-day",
        reference=notification.provider_reference,
        status="delivered",
    )
    await client.post(RECEIPTS, content=body, headers=headers)

    after = await _reload(notification.id)
    assert (after.payload.get("period_from"), after.payload.get("period_to")) == period_before
    assert period_before[0], "the premise: the message carries business dates"
    assert period_before[0] in (after.rendered_text or "")


# --- reachability, as a pure function -----------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("+919845000101", True),
        ("0712345678", True),
        ("+254 712 345 678", True),
        ("(020) 555-0134", True),
        ("", False),
        (None, False),
        ("   ", False),
        ("not-a-phone", False),
        ("12345", False),  # too few digits to be anyone's number
        ("+1234567890123456789", False),  # longer than E.164 allows
        ("call the office", False),
    ],
)
def test_the_phone_check_says_only_what_it_can(value, expected):
    """Conservative on purpose: it can say 'certainly not a number', never
    'this number works'."""
    assert looks_like_a_phone_number(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("farmer@dairy.example", True), ("no-at-sign", False), ("a@b", False), ("", False)],
)
def test_the_email_check_says_only_what_it_can(value, expected):
    assert looks_like_an_email(value) is expected


def _answer(channel: str, **kw):
    return evaluate(
        channel=channel,
        phone=kw.get("phone"),
        email=kw.get("email"),
        provider_available=kw.get("provider_available", True),
        subject_id=uuid.uuid4(),
        subject_type="supplier",
        name="Farmer",
    )


def test_a_phone_number_is_not_a_whatsapp_account():
    """The most important rule in the milestone.

    Reporting a farmer as reachable on WhatsApp because a phone number exists
    would be inventing a capability. Nothing here can ask a gateway, so the
    answer is UNKNOWN.
    """
    answer = _answer("whatsapp", phone="+919845000101")
    assert answer.status == UNKNOWN
    assert answer.reason == WHATSAPP_UNKNOWN
    # And the same number IS reachable by SMS, which is the point of the
    # distinction.
    assert _answer("sms", phone="+919845000101").status == REACHABLE


def test_a_missing_number_is_unreachable_and_says_so():
    answer = _answer("sms", phone="")
    assert (answer.status, answer.reason) == (UNREACHABLE, PHONE_MISSING)


def test_a_malformed_number_is_unreachable_and_distinguishable_from_a_missing_one():
    """An operator fixes these two differently, so they are two reasons."""
    answer = _answer("sms", phone="call the office")
    assert (answer.status, answer.reason) == (UNREACHABLE, INVALID_PHONE)


def test_a_disabled_channel_blames_the_deployment_not_the_farmer():
    """`provider_unavailable` is UNKNOWN, never UNREACHABLE.

    Nobody's phone number is wrong; the deployment cannot send. Listing 250
    blameless farmers as unreachable would bury the one fact an operator needs.
    """
    answer = _answer("sms", phone="+919845000101", provider_available=False)
    assert (answer.status, answer.reason) == (UNKNOWN, PROVIDER_UNAVAILABLE)


def test_a_masked_number_is_all_the_report_shows():
    """The report must not become a list of farmers' phone numbers."""
    answer = _answer("sms", phone="+919845000101")
    assert answer.contact and answer.contact != "+919845000101"
    assert "9845000101" not in answer.contact


# --- reachability, through the API --------------------------------------------


async def test_the_settlement_report_counts_everyone_and_names_the_affected(client, gateway):
    """DEMO B. 250 farmers → reachable / unreachable / unknown, with reasons."""
    from tests.conftest import invite  # noqa: F401 — imported for parity with the suite

    headers, _supplier, _settlement = await _reachability_env(client)
    body = (
        await client.get(
            REACHABILITY,
            headers=headers,
            params={"template_key": "settlement_finalized", "subject_type": "supplier"},
        )
    ).json()

    assert body["channel"] == "sms"
    assert body["total"] >= 1
    assert body["reachable"] + body["unreachable"] + body["unknown"] == body["total"]
    # Everyone not plainly reachable is NAMED — never silently skipped.
    assert len(body["affected"]) == body["unreachable"] + body["unknown"]


async def _reachability_env(client):
    """A dairy with one contactable farmer in the directory."""
    from tests.test_message_delivery import _settlement_env

    headers, supplier, settlement = await _settlement_env(client)
    await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    await _runner().run_once()  # populates the recipient directory
    return headers, supplier, settlement


async def test_reachability_never_blocks_a_settlement(client, gateway):
    """§10, and the line that matters most: money and communication are
    separate domains.

    A farmer with no phone number is settled, finalized and owed exactly the
    same amount. The only consequence is that somebody can see them.
    """
    from platform_core.modules.notification.models import NotificationRecipient
    from tests.test_message_delivery import _settlement_env

    headers, supplier, settlement = await _settlement_env(client)

    # Take the farmer's phone away BEFORE the settlement is finalized.
    async with db.get_session_factory()() as session:
        entry = await session.scalar(
            select(NotificationRecipient).where(
                NotificationRecipient.subject_id == uuid.UUID(supplier["id"])
            )
        )
        if entry is not None:
            entry.phone = ""
            await session.commit()

    finalized = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    assert finalized.status_code == 200, "an unreachable farmer was refused a settlement"
    assert finalized.json()["status"] == "finalized"
    assert finalized.json()["net_amount"]


async def test_the_report_refuses_an_anonymous_caller(client):
    assert (await client.get(REACHABILITY)).status_code == 401


async def test_the_report_never_leaves_the_organization(client, gateway):
    """One dairy must not learn which of another dairy's farmers are unreachable."""
    from tests.test_localization import _tenant_admin_for

    headers_a, _supplier, _settlement = await _reachability_env(client)
    _org_b, headers_b = await _tenant_admin_for(
        client, country="IN", slug="reach-other", email="admin@reach-other.example"
    )

    mine = (await client.get(REACHABILITY, headers=headers_a)).json()
    theirs = (await client.get(REACHABILITY, headers=headers_b)).json()
    assert mine["total"] >= 1
    assert theirs["total"] == 0, "another organization's farmers were counted"
    assert theirs["affected"] == []


# --- financial safety ---------------------------------------------------------


async def test_a_delivery_receipt_moves_no_money(client, gateway):
    """§18. A receipt is a communication event, not a financial one."""
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

    notification = await _sent_notification(client, gateway)
    before = await snapshot()

    for index, status in enumerate(("delivered", "undelivered", "delivered")):
        body, headers = _deliver(
            gateway,
            event_id=f"evt-money-{index}",
            reference=notification.provider_reference,
            status=status,
        )
        assert (await client.post(RECEIPTS, content=body, headers=headers)).status_code == 200

    assert (await _reload(notification.id)).status == "delivered"
    assert await snapshot() == before, "a delivery receipt changed a financial record"


async def test_the_receipt_path_never_imports_the_financial_modules():
    """A boundary that is only a convention is a boundary until somebody is busy."""
    import pathlib

    import platform_core.modules.notification as package

    root = pathlib.Path(package.__file__).parent
    offenders = [
        path.name
        for path in (root / "receipts.py", root / "reachability.py")
        if "modules.settlement" in path.read_text() or "modules.payment" in path.read_text()
    ]
    assert not offenders, f"communication reached into the ledger: {offenders}"


# --- the shared mechanism -----------------------------------------------------


def test_both_webhooks_use_one_signature_mechanism():
    """DEMO-028 said DEMO-027's boundary should be REUSED, not copied.

    If a second HMAC implementation ever appears, this is what says so.
    """
    import pathlib

    import platform_core as package

    root = pathlib.Path(package.__file__).parent
    # Scoped to the files that handle PROVIDER CALLBACKS. The codebase has
    # other legitimate HMACs — supplier QR payloads are signed so a collection
    # centre can verify a farmer's card offline — and this is not about them.
    # It is about there being one way to verify that a webhook came from who it
    # claims, which is the thing DEMO-028 asked to be reused rather than
    # copied.
    webhook_files = [
        path
        for path in root.rglob("*.py")
        if path.name in ("webhooks.py", "receipts.py")
        or (path.name == "providers.py" and "modules" in path.parts)
    ]
    assert webhook_files, "the files this test is about have moved"
    offenders = [
        str(path.relative_to(root))
        for path in webhook_files
        if "compare_digest" in path.read_text() or "hmac.new(" in path.read_text()
    ]
    assert not offenders, (
        f"a second webhook signature implementation exists in {offenders} — "
        "there must be exactly one, in core/webhook_security.py"
    )
