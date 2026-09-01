"""Notification Engine (NOT-001): templates, rendering, providers, retry,
history, consumer integration, idempotency, permissions, replay."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from tests.clock import month_end, month_start
from tests.conftest import invite, register_and_login
from tests.test_org_structure import _tenant_admin
from tests.test_procurement_e2e import _accept_complete, _procurement_env, _run_collection


def _month_start() -> str:
    """The first of the month the collection lands in."""
    return date.today().replace(day=1).isoformat()


def _month_end() -> str:
    """The last day of that month, without a calendar dependency."""
    first = date.today().replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return (next_month - timedelta(days=1)).isoformat()


SUPPLIER_REGISTERED = "supplier.supplier-registered.v1"


@pytest.fixture
def provider_guard():
    """Restore the provider registry after tests swap in fakes."""
    from platform_core.modules.notification import providers

    yield providers
    providers.reset_providers()


class _RecordingProvider:
    name = "recording"

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.sent: list = []

    async def send(self, message):
        if self.fail_times > 0:
            self.fail_times -= 1
            from platform_core.modules.notification.providers import ProviderSendError

            raise ProviderSendError("gateway unavailable")
        self.sent.append(message)
        from platform_core.modules.notification.providers import DeliveryResult

        return DeliveryResult(provider_message_id=f"recording:{len(self.sent)}")


def _runner():
    from platform_core.core import db
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    return ConsumerRunner(db.get_session_factory())


async def _notifications(template_key: str | None = None):
    from platform_core.core import db
    from platform_core.modules.notification.models import Notification

    async with db.get_session_factory()() as s:
        stmt = select(Notification).order_by(Notification.created_at)
        if template_key:
            stmt = stmt.where(Notification.template_key == template_key)
        return list((await s.scalars(stmt)).all())


async def _supplier_env(client, *, name="Amina Njoroge", phone="+254700000001"):
    """Tenant admin + one registered supplier (fires supplier_registered)."""
    from tests.test_collection_centers import _center_fixture

    headers, _branch, center = await _center_fixture(client)
    r = await client.post(
        "/v1/suppliers",
        json={"full_name": name, "phone": phone, "village": "Kilima"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return headers, center, r.json()


# --- template registry & rendering --------------------------------------------


def test_template_catalog_covers_the_required_keys():
    from platform_core.modules.notification.templates import catalog

    keys = {t.key for t in catalog()}
    assert {
        "supplier_registered",
        "supplier_archived",
        "settlement_finalized",
        "payment_completed",
        "password_reset",
        "invitation",
        "milk_rejected",
        "price_unavailable",
    } <= keys


def test_templates_declare_title_body_channel_language_variables():
    from platform_core.modules.notification.templates import get_template

    template = get_template("settlement_finalized", "sms", "en")
    assert template.title and template.body
    assert template.channel == "sms" and template.language == "en"
    # DEMO-025 enriched the slip: it now names the period it covers and shows
    # gross beside net, so the shape does not change again when the deduction
    # engine lands.
    assert set(template.variables) == {
        "name",
        "number",
        "period_from",
        "period_to",
        "gross_amount",
        "net_amount",
        "currency",
        "line_count",
    }


def test_variable_substitution():
    from platform_core.modules.notification.templates import get_template, render

    message = render(
        get_template("settlement_finalized", "sms", "en"),
        {
            "name": "Amina",
            "number": "STL-AB12",
            "period_from": month_start().isoformat(),
            "period_to": month_end().isoformat(),
            "gross_amount": "7897.50",
            "net_amount": "7897.50",
            "currency": "KES",
            "line_count": 2,
        },
    )
    assert "Amina" in message.body and "STL-AB12" in message.body
    assert "7897.50 KES" in message.body and "{" not in message.body
    # Derived: the message echoes the settlement's own period, and the period
    # follows the reference clock. The assertion is that the dates REACH the
    # farmer's message, not which month the suite ran in.
    assert month_start().isoformat() in message.body
    assert month_end().isoformat() in message.body
    assert message.title == "Settlement STL-AB12 ready"


def test_missing_variables_are_an_error_not_a_broken_message():
    from platform_core.modules.notification.templates import (
        TemplateRenderError,
        get_template,
        render,
    )

    with pytest.raises(TemplateRenderError, match="currency"):
        render(get_template("settlement_finalized", "sms"), {"name": "A", "number": "X"})


def test_language_resolution_and_fallback():
    from platform_core.modules.notification.templates import get_template

    assert get_template("supplier_registered", "sms", "sw").language == "sw"
    # No Hindi template yet -> falls back to the platform default, never fails.
    assert get_template("supplier_registered", "sms", "hi").language == "en"
    assert get_template("supplier_registered", "sms", None).language == "en"


def test_unknown_template_raises():
    from platform_core.modules.notification.templates import (
        TemplateNotFoundError,
        get_template,
    )

    with pytest.raises(TemplateNotFoundError):
        get_template("no_such_template", "sms")


def test_channel_specific_templates():
    from platform_core.modules.notification.templates import get_template

    assert get_template("password_reset", "email").channel == "email"
    assert get_template("milk_rejected", "sms").channel == "sms"


# --- provider abstraction -------------------------------------------------------


async def test_logging_provider_delegates_to_the_notifier_port(client):
    """The platform notifier port is preserved, not bypassed."""
    from platform_core.infrastructure import notifications as port
    from platform_core.modules.notification.providers import LoggingProvider, OutboundMessage

    captured = []

    class _CapturingNotifier:
        async def send(self, notification):
            captured.append(notification)

    original = port._notifier
    port._notifier = _CapturingNotifier()
    try:
        reference = await LoggingProvider("sms").send(
            OutboundMessage(
                channel="sms",
                recipient="+254700000001",
                title="T",
                body="B",
                language="en",
                template_key="supplier_registered",
                notification_id=uuid.uuid4(),
            )
        )
    finally:
        port._notifier = original
    assert captured and captured[0].recipient == "+254700000001"
    # MSG-001: providers return a DeliveryResult, not a bare string.
    assert reference.provider_message_id.startswith("logging-sms:")


async def test_placeholder_provider_sends_nothing(provider_guard):
    from platform_core.modules.notification.providers import OutboundMessage, PlaceholderProvider

    reference = await PlaceholderProvider("email").send(
        OutboundMessage(
            channel="email",
            recipient="a@b.example",
            title="T",
            body="B",
            language="en",
            template_key="invitation",
            notification_id=uuid.uuid4(),
        )
    )
    assert reference.provider_message_id.startswith("placeholder-email:")


async def test_provider_is_swappable(provider_guard):
    from platform_core.modules.notification.providers import get_provider, register_provider

    recorder = _RecordingProvider()
    register_provider("sms", recorder)
    assert get_provider("sms") is recorder


# --- consumer integration --------------------------------------------------------


async def test_supplier_registration_sends_a_welcome_sms(client, provider_guard):
    recorder = _RecordingProvider()
    provider_guard.register_provider("sms", recorder)
    _headers, _center, supplier = await _supplier_env(client)
    await _runner().run_once()

    notifications = await _notifications("supplier_registered")
    assert len(notifications) == 1
    note = notifications[0]
    assert note.status == "sent" and note.channel == "sms"
    assert note.recipient == "+254700000001"
    assert note.recipient_ref == uuid.UUID(supplier["id"])
    assert "Amina Njoroge" in note.rendered_text
    assert supplier["code"] in note.rendered_text
    assert note.provider == "recording" and note.provider_reference
    assert note.attempt_count == 1 and note.sent_at is not None
    assert len(recorder.sent) == 1


async def test_recipient_directory_projection_is_populated(client):
    from platform_core.core import db
    from platform_core.modules.notification.models import NotificationRecipient

    _headers, _center, supplier = await _supplier_env(client)
    await _runner().run_once()
    async with db.get_session_factory()() as s:
        entry = (await s.scalars(select(NotificationRecipient))).one()
        assert str(entry.subject_id) == supplier["id"]
        assert entry.display_name == "Amina Njoroge"
        assert entry.phone == "+254700000001"
        assert entry.active is True


async def test_supplier_archived_resolves_recipient_from_the_directory(client, provider_guard):
    """The dispatch consumer never queries the supplier module — the address
    comes from its own rebuildable directory."""
    provider_guard.register_provider("sms", _RecordingProvider())
    headers, center, supplier = await _supplier_env(client)
    await client.post(
        f"/v1/suppliers/{supplier['id']}/centers",
        json={"center_id": center["id"]},
        headers=headers,
    )
    for status in ("active", "archived"):
        r = await client.post(
            f"/v1/suppliers/{supplier['id']}/status", json={"status": status}, headers=headers
        )
        assert r.status_code == 200, r.text
    await _runner().run_once()

    archived = await _notifications("supplier_archived")
    assert len(archived) == 1
    assert archived[0].status == "sent"
    assert archived[0].recipient == "+254700000001"  # resolved, not carried
    assert "Amina Njoroge" in archived[0].rendered_text


async def test_non_archival_status_change_sends_nothing(client, provider_guard):
    provider_guard.register_provider("sms", _RecordingProvider())
    headers, center, supplier = await _supplier_env(client)
    await client.post(
        f"/v1/suppliers/{supplier['id']}/centers",
        json={"center_id": center["id"]},
        headers=headers,
    )
    await client.post(
        f"/v1/suppliers/{supplier['id']}/status", json={"status": "active"}, headers=headers
    )
    await _runner().run_once()
    assert await _notifications("supplier_archived") == []


async def test_password_reset_notification_is_sent_directly(client, provider_guard):
    """The auth service sends this one itself (LACTEVA-BACKEND-004).

    It used to be driven by the event, and that is exactly how it came to be
    sent with no code in it: a consumer can only render what the event carries,
    and the event must not carry a live secret (SEC-003 — `event_outbox` is
    never pruned and is in every backup). The name and the sentence above both
    said the opposite until this was corrected.
    """
    recorder = _RecordingProvider()
    provider_guard.register_provider("email", recorder)
    await register_and_login(client, "reset@example.com")
    r = await client.post("/v1/auth/password-reset/request", json={"email": "reset@example.com"})
    assert r.status_code == 202
    await _runner().run_once()

    notifications = await _notifications("password_reset")
    assert len(notifications) == 1
    assert notifications[0].channel == "email"
    assert notifications[0].recipient == "reset@example.com"
    assert notifications[0].status == "sent"
    assert "2 hours" in notifications[0].rendered_text


async def test_invitation_notification_from_the_event(client, provider_guard):
    provider_guard.register_provider("email", _RecordingProvider())
    _org, headers = await _tenant_admin(client)
    r = await client.post(
        "/v1/invitations",
        json={"email": "invitee@kilima.example", "role_name": "tenant-viewer"},
        headers=headers,
    )
    assert r.status_code == 201
    await _runner().run_once()

    invitations = [
        n for n in await _notifications("invitation") if n.recipient == "invitee@kilima.example"
    ]
    assert len(invitations) == 1
    assert "tenant-viewer" in invitations[0].rendered_text
    assert invitations[0].status == "sent"


async def test_settlement_finalized_notification(client, provider_guard):
    from tests.test_settlements import _create_settlement

    provider_guard.register_provider("sms", _RecordingProvider())
    headers, center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])
    settlement = await _create_settlement(
        client,
        headers,
        supplier["id"],
        center["id"],
        # The period must CONTAIN the collection this settles, and the
        # collection happens today. Hard-coded August dates passed for as long
        # as it was August and began failing on 1 September in every suite that
        # used this fixture — a settlement whose period excludes its own
        # collection has no lines, and cannot be finalized.
        period_from=_month_start(),
        period_to=_month_end(),
    )
    await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    await client.post(f"/v1/settlements/{settlement['id']}/calculate", headers=headers)
    await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    await _runner().run_once()

    notifications = await _notifications("settlement_finalized")
    assert len(notifications) == 1
    body = notifications[0].rendered_text
    assert settlement["settlement_number"] in body
    assert "1125.00 KES" in body
    assert notifications[0].status == "sent"


async def test_payment_completion_notifies_the_supplier(client, provider_guard):
    """PAY-001 closes the loop NOT-001 left open: the payment_completed
    template finally has a producer, and the engine consumes it unchanged."""
    from tests.test_settlements import _create_settlement

    provider_guard.register_provider("sms", _RecordingProvider())
    headers, center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])
    settlement = await _create_settlement(
        client,
        headers,
        supplier["id"],
        center["id"],
        # The period must CONTAIN the collection this settles, and the
        # collection happens today. Hard-coded August dates passed for as long
        # as it was August and began failing on 1 September in every suite that
        # used this fixture — a settlement whose period excludes its own
        # collection has no lines, and cannot be finalized.
        period_from=_month_start(),
        period_to=_month_end(),
    )
    for action in ("collect", "calculate", "finalize"):
        r = await client.post(f"/v1/settlements/{settlement['id']}/{action}", headers=headers)
        assert r.status_code == 200, r.text

    payment = (
        await client.post(
            "/v1/payments",
            json={
                "supplier_id": supplier["id"],
                "currency": "KES",
                "method": "MOBILE_MONEY",
                "allocations": [{"settlement_id": settlement["id"]}],
            },
            headers=headers,
        )
    ).json()
    for action, body in (("submit", {}), ("execute", {}), ("complete", {"reference": "MPESA-1"})):
        r = await client.post(f"/v1/payments/{payment['id']}/{action}", json=body, headers=headers)
        assert r.status_code == 200, r.text
    await _runner().run_once()

    notifications = await _notifications("payment_completed")
    assert len(notifications) == 1
    note = notifications[0]
    assert note.status == "sent" and note.channel == "sms"
    assert note.recipient == "+254700000001"  # resolved from the directory
    assert "1125.00 KES" in note.rendered_text
    assert settlement["settlement_number"] in note.rendered_text
    assert "MPESA-1" in note.rendered_text
    assert "Amina Njoroge" in note.rendered_text


async def test_milk_rejection_notification(client, provider_guard):
    provider_guard.register_provider("sms", _RecordingProvider())
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/reject",
        json={"reason": "adulteration suspected"},
        headers=headers,
    )
    await _runner().run_once()

    notifications = await _notifications("milk_rejected")
    assert len(notifications) == 1
    assert "adulteration suspected" in notifications[0].rendered_text
    assert notifications[0].status == "sent"


async def test_business_modules_never_send_directly(client, provider_guard):
    """With NO provider able to send, business operations still succeed —
    delivery is decoupled from the write path entirely."""

    class _AlwaysFails:
        name = "always-fails"

        async def send(self, message):
            from platform_core.modules.notification.providers import ProviderSendError

            raise ProviderSendError("channel down")

    provider_guard.register_provider("sms", _AlwaysFails())
    provider_guard.register_provider("email", _AlwaysFails())
    _headers, _center, supplier = await _supplier_env(client)
    assert supplier["status"] == "draft"  # registration unaffected
    await _runner().run_once()
    notifications = await _notifications("supplier_registered")
    assert notifications[0].status == "failed"  # only delivery failed


# --- retry, failure, dead ---------------------------------------------------------


async def test_failed_delivery_retries_and_succeeds(client, provider_guard):
    from platform_core.core import db
    from platform_core.core.db import utcnow
    from platform_core.modules.notification.service import NotificationService

    recorder = _RecordingProvider(fail_times=1)
    provider_guard.register_provider("sms", recorder)
    await _supplier_env(client)
    await _runner().run_once()

    failed = (await _notifications("supplier_registered"))[0]
    assert failed.status == "failed" and failed.attempt_count == 1
    assert failed.next_attempt_at is not None and failed.error
    assert "gateway unavailable" in failed.error

    # Too early: the backoff has not elapsed.
    async with db.get_session_factory()() as s:
        result = await NotificationService(s).retry_pending(now=utcnow())
        await s.commit()
    assert result["retried"] == 0

    async with db.get_session_factory()() as s:
        result = await NotificationService(s).retry_pending(now=utcnow() + timedelta(seconds=10))
        await s.commit()
    assert result["sent"] == 1
    sent = (await _notifications("supplier_registered"))[0]
    assert sent.status == "sent" and sent.attempt_count == 2 and sent.sent_at is not None


async def test_delivery_dies_after_max_attempts(client, provider_guard):
    from platform_core.core import db
    from platform_core.core.db import utcnow
    from platform_core.modules.event_relay.consumers import MAX_CONSUMER_ATTEMPTS
    from platform_core.modules.notification.service import NotificationService

    provider_guard.register_provider("sms", _RecordingProvider(fail_times=99))
    await _supplier_env(client)
    await _runner().run_once()
    for attempt in range(1, MAX_CONSUMER_ATTEMPTS + 2):
        async with db.get_session_factory()() as s:
            await NotificationService(s).retry_pending(
                now=utcnow() + timedelta(seconds=400 * attempt)
            )
            await s.commit()
    dead = (await _notifications("supplier_registered"))[0]
    assert dead.status == "dead"
    assert dead.attempt_count == MAX_CONSUMER_ATTEMPTS
    assert dead.failed_at is not None and dead.next_attempt_at is None


async def test_backoff_grows_between_attempts(client, provider_guard):
    from platform_core.core import db
    from platform_core.core.db import as_utc, utcnow
    from platform_core.modules.notification.service import NotificationService

    provider_guard.register_provider("sms", _RecordingProvider(fail_times=99))
    await _supplier_env(client)
    await _runner().run_once()
    first = (await _notifications("supplier_registered"))[0].next_attempt_at
    async with db.get_session_factory()() as s:
        await NotificationService(s).retry_pending(now=utcnow() + timedelta(seconds=10))
        await s.commit()
    second = (await _notifications("supplier_registered"))[0].next_attempt_at
    assert as_utc(second) > as_utc(first)


async def test_missing_recipient_is_recorded_and_retryable(client, provider_guard):
    """A supplier registered without a phone has nowhere to send — the
    failure is visible in history rather than silently dropped."""
    provider_guard.register_provider("sms", _RecordingProvider())
    await _supplier_env(client, phone="")
    await _runner().run_once()
    note = (await _notifications("supplier_registered"))[0]
    assert note.status == "failed"
    assert "no recipient" in note.error


# --- idempotency & replay -----------------------------------------------------------


async def test_duplicate_event_processing_does_not_resend(client, provider_guard):
    recorder = _RecordingProvider()
    provider_guard.register_provider("sms", recorder)
    await _supplier_env(client)
    runner = _runner()
    await runner.run_once()
    await runner.run_once()  # nothing new
    assert len(recorder.sent) == 1
    assert len(await _notifications("supplier_registered")) == 1


async def test_consumer_replay_does_not_resend(client, provider_guard):
    """Rewinding the consumer (the replay scenario) must not spam suppliers."""
    from platform_core.core import db
    from platform_core.modules.event_relay.models import ConsumerCursor

    recorder = _RecordingProvider()
    provider_guard.register_provider("sms", recorder)
    await _supplier_env(client)
    runner = _runner()
    await runner.run_once()
    assert len(recorder.sent) == 1

    async with db.get_session_factory()() as s:
        for cursor in (await s.scalars(select(ConsumerCursor))).all():
            cursor.position_created_at = None
            cursor.position_event_id = None
        await s.commit()
    await runner.run_once()
    assert len(recorder.sent) == 1  # idempotency key held
    assert len(await _notifications("supplier_registered")) == 1


async def test_recipient_directory_is_rebuildable(client):
    """The directory is a PLT-001 projection: rebuild reconstructs it."""
    from platform_core.core import db
    from platform_core.modules.event_relay.projections import ProjectionRebuilder
    from platform_core.modules.notification.models import NotificationRecipient

    await _supplier_env(client)
    await _runner().run_once()
    rebuilder = ProjectionRebuilder(db.get_session_factory())
    result = await rebuilder.rebuild("notification-recipient-directory")
    assert result.status == "completed" and result.events_applied >= 1
    async with db.get_session_factory()() as s:
        entry = (await s.scalars(select(NotificationRecipient))).one()
        assert entry.phone == "+254700000001"
    verification = await rebuilder.verify("notification-recipient-directory", deep=True)
    assert verification.healthy is True


# --- history API ---------------------------------------------------------------------


async def test_history_endpoint_lists_notifications(client, provider_guard):
    provider_guard.register_provider("sms", _RecordingProvider())
    headers, _center, _supplier = await _supplier_env(client)
    await _runner().run_once()

    page = (
        await client.get("/v1/notifications?template_key=supplier_registered", headers=headers)
    ).json()
    assert page["total"] == 1
    item = page["items"][0]
    assert item["template_key"] == "supplier_registered"
    assert item["status"] == "sent" and item["channel"] == "sms"
    assert item["rendered_text"] and item["title"]
    assert item["attempt_count"] == 1
    assert item["payload"]["code"]


async def test_history_filters_and_pagination(client, provider_guard):
    provider_guard.register_provider("sms", _RecordingProvider())
    provider_guard.register_provider("email", _RecordingProvider())
    headers, _center, _supplier = await _supplier_env(client)
    await client.post(
        "/v1/invitations",
        json={"email": "invitee@kilima.example", "role_name": "tenant-viewer"},
        headers=headers,
    )
    await _runner().run_once()

    async def page(query=""):
        return (await client.get(f"/v1/notifications{query}", headers=headers)).json()

    # The tenant fixture itself sends invitation mail, so compare shapes, not
    # a global total: one SMS (the supplier), several e-mails (invitations).
    everything = await page()
    assert everything["total"] >= 2
    assert (await page("?channel=sms"))["total"] == 1
    assert (await page("?channel=email"))["total"] == everything["total"] - 1
    assert (await page("?template_key=supplier_registered"))["total"] == 1
    assert (await page("?status=sent"))["total"] == everything["total"]
    assert (await page("?status=dead"))["total"] == 0
    assert (await page("?q=amina"))["total"] == 1  # matches the rendered SMS
    limited = await page("?limit=1&offset=0")
    assert limited["total"] == everything["total"] and len(limited["items"]) == 1


async def test_history_detail_and_stats(client, provider_guard):
    provider_guard.register_provider("sms", _RecordingProvider())
    headers, _center, _supplier = await _supplier_env(client)
    await _runner().run_once()
    page = (await client.get("/v1/notifications", headers=headers)).json()
    detail = (
        await client.get(f"/v1/notifications/{page['items'][0]['id']}", headers=headers)
    ).json()
    assert detail["id"] == page["items"][0]["id"]
    assert (
        await client.get(f"/v1/notifications/{uuid.uuid4()}", headers=headers)
    ).status_code == 404

    stats = (await client.get("/v1/notifications/stats", headers=headers)).json()
    assert stats["total"] == stats["by_status"]["sent"]  # everything delivered
    assert stats["by_channel"]["sms"] == 1 and stats["retryable"] == 0


async def test_retry_endpoint(client, provider_guard):
    recorder = _RecordingProvider(fail_times=1)
    provider_guard.register_provider("sms", recorder)
    headers, _center, _supplier = await _supplier_env(client)
    await _runner().run_once()
    failures = (await client.get("/v1/notifications?status=failed", headers=headers)).json()
    assert failures["total"] == 1

    retried = (
        await client.post(f"/v1/notifications/{failures['items'][0]['id']}/retry", headers=headers)
    ).json()
    assert retried["status"] == "sent" and retried["attempt_count"] == 2
    assert (
        await client.post(f"/v1/notifications/{retried['id']}/retry", headers=headers)
    ).status_code == 409  # already delivered


async def test_retry_pending_endpoint(client, provider_guard):
    provider_guard.register_provider("sms", _RecordingProvider(fail_times=1))
    headers, _center, _supplier = await _supplier_env(client)
    await _runner().run_once()
    result = (await client.post("/v1/notifications/retry-pending", headers=headers)).json()
    assert result["retried"] == 0  # backoff not elapsed yet — nothing due


# --- template API ----------------------------------------------------------------------


async def test_template_catalog_endpoint(client):
    _org, headers = await _tenant_admin(client)
    templates = (await client.get("/v1/notification-templates", headers=headers)).json()
    keys = {t["key"] for t in templates}
    assert "settlement_finalized" in keys and "password_reset" in keys
    entry = next(
        t for t in templates if t["key"] == "settlement_finalized" and t["channel"] == "sms"
    )
    assert "name" in entry["variables"]


async def test_template_preview_endpoint(client):
    _org, headers = await _tenant_admin(client)
    body = (
        await client.post(
            "/v1/notification-templates/settlement_finalized/preview",
            json={"channel": "sms", "variables": {"name": "Amina", "currency": "KES"}},
            headers=headers,
        )
    ).json()
    assert "Amina" in body["body"] and "KES" in body["body"]
    assert "<number>" in body["body"]  # unsupplied variables show as placeholders
    assert body["language"] == "en"

    swahili = (
        await client.post(
            "/v1/notification-templates/supplier_registered/preview",
            json={"channel": "sms", "language": "sw"},
            headers=headers,
        )
    ).json()
    assert swahili["language"] == "sw" and "Karibu" in swahili["title"]

    missing = await client.post(
        "/v1/notification-templates/nope/preview", json={"channel": "sms"}, headers=headers
    )
    assert missing.status_code == 404


# --- permissions -------------------------------------------------------------------------


async def test_notification_api_requires_authentication(client):
    assert (await client.get("/v1/notifications")).status_code == 401


async def test_notification_api_requires_permission(client):
    await _tenant_admin(client)
    _, nobody = await register_and_login(client, "notifnoperm@example.com")
    assert (await client.get("/v1/notifications", headers=nobody)).status_code == 403


async def test_viewer_reads_but_cannot_retry(client, provider_guard):
    provider_guard.register_provider("sms", _RecordingProvider(fail_times=1))
    org, headers = await _tenant_admin(client)
    _inv, inv_token = await invite(
        client,
        headers,
        email="viewer@kilima.example",
        role_name="tenant-viewer",
    )
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
            "password": "viewer-password-1",
            "full_name": "Read Only",
        },
    )
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "viewer@kilima.example",
                "password": "viewer-password-1",
                "tenant_id": org["id"],
            },
        )
    ).json()
    viewer = {"Authorization": f"Bearer {pair['access_token']}"}
    assert (await client.get("/v1/notifications", headers=viewer)).status_code == 200
    assert (await client.get("/v1/notification-templates", headers=viewer)).status_code == 200
    r = await client.post(f"/v1/notifications/{uuid.uuid4()}/retry", headers=viewer)
    assert r.status_code == 403


async def test_tenant_isolation_of_history(client, provider_guard):
    provider_guard.register_provider("sms", _RecordingProvider())
    await _supplier_env(client)
    await _runner().run_once()

    _, root2 = await register_and_login(client, "root2@example.com", admin=True)
    org2 = (
        await client.post(
            "/v1/organizations",
            json={"name": "Rift Valley Dairy", "slug": "rift", "country_code": "ke"},
            headers=root2,
        )
    ).json()
    _inv, inv_token = await invite(
        client,
        {**root2, "X-Tenant-ID": org2["id"]},
        email="manager@rift.example",
        role_name="tenant-admin",
    )
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
            "password": "manager-password-2",
            "full_name": "Rift Manager",
        },
    )
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "manager@rift.example",
                "password": "manager-password-2",
                "tenant_id": org2["id"],
            },
        )
    ).json()
    other = {"Authorization": f"Bearer {pair['access_token']}"}
    page = (
        await client.get("/v1/notifications?template_key=supplier_registered", headers=other)
    ).json()
    assert page["total"] == 0  # the other tenant's supplier notification is invisible


# --- what a notification is allowed to write down (WO-47) --------------------
#
# The platform's mail carries password-reset codes and invitation tokens. Both
# are bearer secrets: whoever holds one can take the account. Logs are shipped
# to Loki, read by operators, and kept — so a body in a log line is a
# credential in a place nobody treats as a credential store.
#
# The stand-in notifier has always logged only metadata. Nothing asserted it,
# so nothing would have noticed a `body=` added in a debugging session and left
# there. These assert the property against a REAL secret rather than against a
# list of field names, which is the version that still works when somebody adds
# a field.

_SECRET = "tok-b3d9f17a2c4e8615-do-not-log"


class _Recorder:
    """Stands in for the module logger and keeps every value it was given."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def info(self, event, **kw):
        self.events.append((event, kw))

    def warning(self, event, **kw):
        self.events.append((event, kw))

    def error(self, event, **kw):
        self.events.append((event, kw))

    def everything_written(self) -> str:
        return " ".join(
            f"{event} " + " ".join(f"{k}={v!r}" for k, v in kw.items()) for event, kw in self.events
        )


async def test_the_stand_in_notifier_writes_metadata_and_never_the_message(monkeypatch):
    from platform_core.infrastructure import notifications

    recorder = _Recorder()
    monkeypatch.setattr(notifications, "log", recorder)

    await notifications.LoggingNotifier().send(
        notifications.Notification(
            channel="email",
            recipient="operator@example.com",
            template_key="notification.password_reset",
            locale="en",
            data={"code": _SECRET, "reset_url": f"https://x.example/r/{_SECRET}"},
        )
    )

    written = recorder.everything_written()
    assert _SECRET not in written, "a reset code reached the log"
    assert "operator@example.com" in written  # recipient IS metadata, and is kept
    assert "notification.password_reset" in written

    (_event, fields) = recorder.events[0]
    assert set(fields) == {"channel", "recipient", "template", "locale", "subject"}, (
        "the stand-in notifier grew a field; if it can carry a body or a token, "
        f"say why here rather than widening this set: {sorted(fields)}"
    )


async def test_the_smtp_provider_never_logs_the_body_it_sends(monkeypatch):
    from platform_core.modules.notification import providers

    recorder = _Recorder()
    monkeypatch.setattr(providers, "log", recorder)
    monkeypatch.setattr(providers, "assert_may_reach_the_network", lambda name: None)

    settings = providers.get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.invalid", raising=False)
    monkeypatch.setattr(settings, "smtp_from_address", "no-reply@example.com", raising=False)

    sent: dict = {}

    def _capture(self, mail, sender, recipient, _settings):
        # multipart since WO-49: the text part is the one to check here.
        sent["body"] = mail.get_body(("plain",)).get_content()

    monkeypatch.setattr(providers.SmtpEmailProvider, "_deliver", _capture)

    await providers.SmtpEmailProvider().send(
        providers.OutboundMessage(
            channel="email",
            recipient="operator@example.com",
            title="Reset your password",
            body=f"Your code is {_SECRET}",
            language="en",
            template_key="notification.password_reset",
            notification_id=uuid.uuid4(),
        )
    )

    assert _SECRET in sent["body"], "the secret must reach the MESSAGE"
    assert _SECRET not in recorder.everything_written(), "…and never the log"


# --- the channel is proven at startup, not at the first send (WO-47) ---------


async def _preflight(monkeypatch, **settings_overrides):
    from platform_core.modules.notification import providers

    settings = providers.get_settings()
    for key, value in settings_overrides.items():
        monkeypatch.setattr(settings, key, value, raising=False)
    return providers


async def test_an_unreachable_mail_server_stops_the_platform_starting(monkeypatch):
    """The refusal, watched. A guard that cannot refuse is decoration."""
    providers = await _preflight(
        monkeypatch,
        env="prod",
        notification_email_provider="smtp",
        messaging_mode="production",
        smtp_host="smtp.nowhere.invalid",
        smtp_port=465,
        smtp_security="ssl",
        smtp_timeout_seconds=1.0,
    )
    with pytest.raises(providers.EmailChannelUnreachable) as refused:
        await providers.assert_email_channel_is_deliverable()
    # The message has to name the host and say why it matters, because whoever
    # reads it is looking at a platform that will not boot.
    assert "smtp.nowhere.invalid:465" in str(refused.value)
    assert "password reset" in str(refused.value)


async def test_the_probe_authenticates_rather_than_merely_connecting(monkeypatch):
    # A TCP connection proves nothing: a rotated password answers on port 465
    # exactly as a working one does, and then every message fails.
    providers = await _preflight(
        monkeypatch,
        env="prod",
        notification_email_provider="smtp",
        messaging_mode="production",
        smtp_host="smtp.example.com",
        smtp_username="postmaster@example.com",
        smtp_password="a-password",
        smtp_security="ssl",
    )
    steps: list[str] = []

    class _Client:
        def __init__(self, host, port, timeout=None):
            steps.append(f"connect {host}:{port}")

        def ehlo(self):
            steps.append("ehlo")

        def login(self, user, _password):
            steps.append(f"login {user}")

        def quit(self):
            steps.append("quit")

    monkeypatch.setattr(providers.smtplib, "SMTP_SSL", _Client)
    await providers.assert_email_channel_is_deliverable()
    assert "login postmaster@example.com" in steps, f"the probe never authenticated: {steps}"
    assert "quit" in steps, "the probe left a connection open on the mail server"


async def test_the_probe_sends_nothing(monkeypatch):
    # Otherwise every container restart puts a message in somebody's mailbox.
    providers = await _preflight(
        monkeypatch,
        env="prod",
        notification_email_provider="smtp",
        messaging_mode="production",
        smtp_host="smtp.example.com",
        smtp_username="",
        smtp_security="ssl",
    )

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def ehlo(self):
            pass

        def send_message(self, *a, **kw):  # pragma: no cover - must never run
            raise AssertionError("the startup probe sent a real message")

        def quit(self):
            pass

    monkeypatch.setattr(providers.smtplib, "SMTP_SSL", _Client)
    await providers.assert_email_channel_is_deliverable()


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"env": "dev"}, "a laptop has no mail server and needs none"),
        ({"notification_email_provider": "disabled"}, "not sending is a choice, and it was made"),
        ({"messaging_mode": "test"}, "nothing would be sent, so nothing is proven"),
    ],
)
async def test_the_probe_stays_out_of_the_way_where_it_would_teach_nothing(
    monkeypatch, overrides, why
):
    base = dict(
        env="prod",
        notification_email_provider="smtp",
        messaging_mode="production",
        smtp_host="smtp.nowhere.invalid",
        smtp_port=465,
        smtp_security="ssl",
        smtp_timeout_seconds=1.0,
    )
    base.update(overrides)
    providers = await _preflight(monkeypatch, **base)
    await providers.assert_email_channel_is_deliverable()  # must not raise: {why}


# --- the message has a page, and the page is the same message (WO-49) --------
#
# The first real password-reset mail the platform ever sent arrived as an
# unstyled paragraph with a 40-character token in the middle of a sentence.
# It was correct and it did not look like a product. These pin the fix, and —
# more importantly — pin the parts of it that are easy to break later.


def _built_email(monkeypatch, **message_kw):
    """Send one message and return the MIME object the provider handed smtplib."""
    from platform_core.modules.notification import providers

    monkeypatch.setattr(providers, "assert_may_reach_the_network", lambda name: None)
    settings = providers.get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.invalid", raising=False)
    monkeypatch.setattr(settings, "smtp_from_address", "no-reply@example.com", raising=False)

    captured: dict = {}

    def _capture(self, mail, sender, recipient, _settings):
        captured["mail"] = mail

    monkeypatch.setattr(providers.SmtpEmailProvider, "_deliver", _capture)

    base = dict(
        channel="email",
        recipient="operator@example.com",
        title="Reset your Lacteva password",
        body="A password reset was requested. Use this code: ABC-123. It expires in 2 hours.",
        language="en",
        template_key="password_reset",
        notification_id=uuid.uuid4(),
        highlight="ABC-123",
    )
    base.update(message_kw)
    return providers, providers.OutboundMessage(**base), captured


async def test_the_mail_carries_both_a_text_part_and_a_page(monkeypatch):
    providers, message, captured = _built_email(monkeypatch)
    await providers.SmtpEmailProvider().send(message)
    mail = captured["mail"]

    assert mail.get_content_type() == "multipart/alternative"
    subtypes = [part.get_content_subtype() for part in mail.iter_parts()]
    # Text FIRST: multipart/alternative means "last one the client can render
    # wins", so the order is the fallback order, not a detail.
    assert subtypes == ["plain", "html"], subtypes


async def test_the_text_part_is_the_template_untouched(monkeypatch):
    """The E2E harness and the demo seeder read the token out of this with a
    regular expression. Reformatting it silently breaks the only proof that
    email works at all."""
    providers, message, captured = _built_email(monkeypatch)
    await providers.SmtpEmailProvider().send(message)
    text = captured["mail"].get_body(("plain",)).get_content()
    assert text.strip() == message.body.strip()


async def test_the_page_sets_the_code_apart_and_names_it(monkeypatch):
    providers, message, captured = _built_email(monkeypatch)
    await providers.SmtpEmailProvider().send(message)
    html = captured["mail"].get_body(("html",)).get_content()

    assert "ABC-123" in html
    assert "Password reset code" in html, "the boxed value is an unexplained blob"
    assert "monospace" in html, "a code that is not monospaced is a code that is misread"
    # A token wraps mid-string on a phone; without this it overflows the card.
    assert "word-break:break-all" in html


async def test_a_tenant_cannot_put_markup_in_somebody_else_s_mail(monkeypatch):
    """Organization names are chosen by whoever creates the tenant, and they
    reach this page. A dairy called `<script>` is a strange name, not an
    exploit."""
    providers, message, captured = _built_email(
        monkeypatch,
        body='Welcome to <script>alert(1)</script> & "Sons"',
        title="<img src=x onerror=alert(1)>",
        highlight="<b>not-bold</b>",
    )
    await providers.SmtpEmailProvider().send(message)
    html = captured["mail"].get_body(("html",)).get_content()

    # The test is not "the dangerous words are gone" — they are the tenant's
    # own text and must still be READABLE. It is that none of them survives as
    # markup: every angle bracket that came from a value is escaped, so the
    # browser renders characters rather than elements.
    assert "<script>" not in html
    assert "<img" not in html
    assert "<b>not-bold</b>" not in html
    assert "&lt;script&gt;" in html  # escaped, and still legible
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "&lt;b&gt;not-bold&lt;/b&gt;" in html


async def test_arabic_is_laid_out_right_to_left(monkeypatch):
    """The catalog ships Arabic. A message laid out left-to-right in Arabic is
    not a style problem; it is unreadable."""
    providers, message, captured = _built_email(monkeypatch, language="ar")
    await providers.SmtpEmailProvider().send(message)
    html = captured["mail"].get_body(("html",)).get_content()

    assert 'dir="rtl"' in html
    assert 'lang="ar"' in html
    # …but the CODE stays left-to-right, or its characters reorder on screen
    # and the reader copies a token that is not the token.
    assert "direction:ltr" in html


async def test_the_page_needs_nothing_the_recipient_has_to_fetch(monkeypatch):
    """Remote images are blocked by default in most clients, `<svg>` is
    stripped by Gmail, and script never runs. A page that depends on any of
    them is a page most recipients never see."""
    providers, message, captured = _built_email(monkeypatch)
    await providers.SmtpEmailProvider().send(message)
    html = captured["mail"].get_body(("html",)).get_content()

    for forbidden in ("<script", "<svg", "<img", "http://", "https://", "<link"):
        assert forbidden not in html, f"the page depends on {forbidden}"


async def test_a_message_with_no_single_secret_gets_no_code_box(monkeypatch):
    providers, message, captured = _built_email(
        monkeypatch, highlight=None, template_key="settlement_finalized"
    )
    await providers.SmtpEmailProvider().send(message)
    html = captured["mail"].get_body(("html",)).get_content()
    assert "Code" not in html


async def test_the_code_appears_once_and_stands_where_the_sentence_put_it(monkeypatch):
    """The first mail this platform ever sent showed a forty-character token
    mid-paragraph and then again in a box below it. The box takes the token's
    place in the sentence; it does not repeat it."""
    providers, message, captured = _built_email(monkeypatch)
    await providers.SmtpEmailProvider().send(message)
    html = captured["mail"].get_body(("html",)).get_content()

    assert html.count("ABC-123") == 1, "the code is shown twice"
    # The words either side of it survive, in the order the template wrote
    # them — no template needed a second, HTML-shaped version.
    before = html.index("Use this code")
    box = html.index("ABC-123")
    after = html.index("It expires in 2 hours")
    assert before < box < after, "the sentence was reordered around the code"

    # And the text part still carries it inline, because that is what the
    # harness parses and what a text-only client reads.
    text = captured["mail"].get_body(("plain",)).get_content()
    assert "Use this code: ABC-123. It expires" in text
