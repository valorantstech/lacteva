"""Notification Engine (NOT-001): templates, rendering, providers, retry,
history, consumer integration, idempotency, permissions, replay."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from tests.conftest import register_and_login
from tests.test_org_structure import _tenant_admin
from tests.test_procurement_e2e import _accept_complete, _procurement_env, _run_collection

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
        return f"recording:{len(self.sent)}"


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
    assert set(template.variables) == {"name", "number", "net_amount", "currency", "line_count"}


def test_variable_substitution():
    from platform_core.modules.notification.templates import get_template, render

    message = render(
        get_template("settlement_finalized", "sms", "en"),
        {
            "name": "Amina",
            "number": "STL-AB12",
            "net_amount": "7897.50",
            "currency": "KES",
            "line_count": 2,
        },
    )
    assert "Amina" in message.body and "STL-AB12" in message.body
    assert "7897.50 KES" in message.body and "{" not in message.body
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
    assert reference.startswith("logging-sms:")


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
    assert reference.startswith("placeholder-email:")


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


async def test_password_reset_notification_from_the_event(client, provider_guard):
    """auth no longer sends anything itself — the event drives delivery."""
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
        period_from="2026-08-01",
        period_to="2026-08-31",
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
    entry = next(t for t in templates if t["key"] == "settlement_finalized")
    assert entry["channel"] == "sms" and "name" in entry["variables"]


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
    inv = (
        await client.post(
            "/v1/invitations",
            json={"email": "viewer@kilima.example", "role_name": "tenant-viewer"},
            headers=headers,
        )
    ).json()
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv["invitation_token"],
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
    inv = (
        await client.post(
            "/v1/invitations",
            json={"email": "manager@rift.example", "role_name": "tenant-admin"},
            headers={**root2, "X-Tenant-ID": org2["id"]},
        )
    ).json()
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv["invitation_token"],
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
