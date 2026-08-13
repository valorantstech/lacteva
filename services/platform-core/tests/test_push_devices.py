"""Push to a field user's handset (DEMO-012 §10).

The work order asks for push notifications and, in the same breath, forbids a
second notification system. So there is no new dispatcher here: `push` is a
CHANNEL on the one that already exists, and it inherits that system's
idempotency, retry, dead-lettering, history and metrics without restating any
of them.

What is genuinely new — and what this file is about — is that the address of
a push notification is a **token held by a phone**, which behaves unlike a
phone number or an email address in four ways that matter:

* it is capability-like, so it must never be returned or logged;
* it rotates and is re-registered on every app start, so registration must be
  idempotent or one message reaches a handset five times;
* it can MOVE to another user, when a handset is signed into a second
  account, and the old binding must not survive that;
* it dies silently when an app is uninstalled, and the platform only ever
  learns this from the gateway.

The vendor is not chosen. `LACTEVA_NOTIFICATION_PUSH_PROVIDER` therefore
defaults to `disabled`, and this suite proves the contract against a stub
gateway — not that any particular vendor accepts it. That distinction is
stated here rather than left for someone to discover.
"""

import uuid

import httpx
import pytest

from platform_core.modules.notification.providers import (
    OutboundMessage,
    PermanentSendError,
    ProviderSendError,
)
from tests.test_org_structure import _tenant_admin


def _message(recipient: str = "device-token-aaaaaaaaaaaa") -> OutboundMessage:
    return OutboundMessage(
        channel="push",
        recipient=recipient,
        title="Milk collected",
        body="Your delivery was recorded.",
        language="en",
        template_key="delivery_recorded",
        notification_id=uuid.uuid4(),
    )


@pytest.fixture
def push_settings(monkeypatch):
    from platform_core.core.config import get_settings

    settings = get_settings()
    original = (settings.push_api_url, settings.push_api_key)
    settings.push_api_url = "https://push.example/send"
    settings.push_api_key = "test-key-not-a-real-credential"
    yield settings
    settings.push_api_url, settings.push_api_key = original


@pytest.fixture
def gateway(monkeypatch):
    """A stand-in push gateway the test drives."""

    class Gateway:
        def __init__(self):
            self.requests: list[httpx.Request] = []
            self.handler = lambda request: httpx.Response(200, json={"message_id": "push-1"})

        def install(self):
            transport = httpx.MockTransport(self._handle)
            original = httpx.AsyncClient

            def factory(*args, **kwargs):
                kwargs["transport"] = transport
                return original(*args, **kwargs)

            monkeypatch.setattr(httpx, "AsyncClient", factory)
            return self

        def _handle(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self.handler(request)

    return Gateway().install()


def _provider(push_settings):
    from platform_core.modules.notification.providers import HttpPushProvider

    return HttpPushProvider("push")


# --- the adapter -------------------------------------------------------------


async def test_a_push_is_accepted_and_reports_the_gateway_id(gateway, push_settings):
    result = await _provider(push_settings).send(_message())
    assert result.provider_message_id == "push-1"
    assert result.status == "accepted"


async def test_the_notification_carries_a_reference_and_not_the_content(gateway, push_settings):
    """A lock screen is a public surface.

    The phone is told WHICH record to open, never what it says. A balance or
    an amount in the data payload would be readable by anyone holding the
    handset, and would also be a figure computed somewhere other than the
    invoice it belongs to.
    """
    import json

    await _provider(push_settings).send(_message())
    sent = json.loads(gateway.requests[0].content)
    assert sent["data"]["template"] == "delivery_recorded"
    assert "notification_id" in sent["data"]
    assert not any(k in sent["data"] for k in ("amount", "balance", "outstanding"))


async def test_every_send_carries_a_stable_idempotency_key(gateway, push_settings):
    """The double-send the platform cannot prevent alone: a push the gateway
    accepted and whose response we lost."""
    message = _message()
    provider = _provider(push_settings)
    await provider.send(message)
    await provider.send(message)

    keys = [r.headers["Idempotency-Key"] for r in gateway.requests]
    assert keys[0] == keys[1]
    assert str(message.notification_id) in keys[0]


async def test_a_dead_token_is_permanent_not_retried(gateway, push_settings):
    """410 Gone means the app is uninstalled. Retrying it five times over five
    backoff windows reaches the same answer it had the first time."""
    gateway.handler = lambda request: httpx.Response(410, text="NotRegistered")
    with pytest.raises(PermanentSendError):
        await _provider(push_settings).send(_message())


async def test_a_gateway_outage_is_retried(gateway, push_settings):
    gateway.handler = lambda request: httpx.Response(503, text="unavailable")
    with pytest.raises(ProviderSendError) as excinfo:
        await _provider(push_settings).send(_message())
    assert not isinstance(excinfo.value, PermanentSendError)


async def test_a_bad_credential_is_permanent(gateway, push_settings):
    gateway.handler = lambda request: httpx.Response(401, text="bad key")
    with pytest.raises(PermanentSendError):
        await _provider(push_settings).send(_message())


async def test_the_provider_refuses_to_start_unconfigured(push_settings):
    """A gateway selected but not configured would fail every send at runtime,
    one message at a time, instead of failing once at startup."""
    push_settings.push_api_url = ""
    with pytest.raises(ValueError, match="LACTEVA_PUSH_API_URL"):
        _provider(push_settings)


async def test_push_defaults_to_disabled_not_logging():
    """`logging` marks every message delivered and sends nothing.

    No push vendor has been chosen or paid for. A deployment that has not made
    that decision must FAIL a push visibly, not record it as sent — which is
    this platform's own "looks healthy while doing nothing" rule.
    """
    from platform_core.core.config import Settings

    assert Settings().notification_push_provider == "disabled"


# --- registration ------------------------------------------------------------


async def test_a_phone_registers_itself_and_gets_no_token_back(client):
    _org, headers = await _tenant_admin(client)
    r = await client.post(
        "/v1/notification-devices",
        json={"token": "fcm-token-abcdef123456", "platform": "android", "label": "Pixel"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["platform"] == "android"
    assert body["token_suffix"] == "…123456"
    assert "token" not in body, "the endpoint handed back a way to push to the handset"


async def test_registering_the_same_token_twice_does_not_double_the_device(client):
    """The app calls this on every start. A row per launch is five copies of
    every notification."""
    _org, headers = await _tenant_admin(client)
    for _ in range(3):
        r = await client.post(
            "/v1/notification-devices",
            json={"token": "fcm-token-stable", "platform": "android"},
            headers=headers,
        )
        assert r.status_code == 201, r.text

    devices = (await client.get("/v1/notification-devices", headers=headers)).json()
    assert len(devices) == 1


async def test_a_handset_signed_into_another_account_stops_reaching_the_first(client):
    """Not a conflict to reject.

    Rejecting would leave the OLD binding in place, and the previous user
    would keep receiving notifications on a phone that is now somebody else's
    — which is the outcome that actually leaks.
    """
    from tests.conftest import register_and_login

    _org, headers = await _tenant_admin(client)
    r = await client.post(
        "/v1/notification-devices",
        json={"token": "shared-handset-token"},
        headers=headers,
    )
    assert r.status_code == 201

    # A second user in the same tenant signs in on the same handset.
    second = await _second_user(client, headers)
    r = await client.post(
        "/v1/notification-devices",
        json={"token": "shared-handset-token"},
        headers=second,
    )
    assert r.status_code == 201, r.text

    assert (await client.get("/v1/notification-devices", headers=headers)).json() == []
    assert len((await client.get("/v1/notification-devices", headers=second)).json()) == 1
    assert register_and_login  # imported for the helper below


async def _second_user(client, admin_headers):
    from tests.conftest import invite

    _inv, token = await invite(
        client, admin_headers, email="rider@kilima.example", role_name="tenant-admin"
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "rider-password-1", "full_name": "Rider"},
    )
    assert r.status_code == 201, r.text
    pair = await client.post(
        "/v1/auth/token",
        json={"email": "rider@kilima.example", "password": "rider-password-1"},
    )
    assert pair.status_code == 200, pair.text
    return {"Authorization": f"Bearer {pair.json()['access_token']}"}


async def test_a_device_list_shows_only_your_own(client):
    _org, headers = await _tenant_admin(client)
    await client.post("/v1/notification-devices", json={"token": "mine-000001"}, headers=headers)
    second = await _second_user(client, headers)
    await client.post("/v1/notification-devices", json={"token": "theirs-000002"}, headers=second)

    mine = (await client.get("/v1/notification-devices", headers=headers)).json()
    assert [d["token_suffix"] for d in mine] == ["…000001"]


async def test_revoking_another_persons_device_is_a_404(client):
    """Never a 403 — that would confirm the device exists."""
    _org, headers = await _tenant_admin(client)
    second = await _second_user(client, headers)
    theirs = (
        await client.post(
            "/v1/notification-devices", json={"token": "theirs-000002"}, headers=second
        )
    ).json()

    r = await client.delete(f"/v1/notification-devices/{theirs['id']}", headers=headers)
    assert r.status_code == 404


async def test_revoking_removes_the_token_entirely(client):
    """Deleted, not deactivated. A revoked token is not evidence of anything
    and keeping it keeps a way to reach a handset."""
    from sqlalchemy import func, select

    from platform_core.core import db
    from platform_core.modules.notification.models import NotificationDevice

    _org, headers = await _tenant_admin(client)
    device = (
        await client.post(
            "/v1/notification-devices", json={"token": "to-be-revoked"}, headers=headers
        )
    ).json()
    r = await client.delete(f"/v1/notification-devices/{device['id']}", headers=headers)
    assert r.status_code == 204

    async with db.get_session_factory()() as session:
        remaining = await session.scalar(select(func.count()).select_from(NotificationDevice))
    assert remaining == 0, "the token survived revocation"


async def test_a_blank_token_is_refused(client):
    _org, headers = await _tenant_admin(client)
    r = await client.post("/v1/notification-devices", json={"token": "   "}, headers=headers)
    assert r.status_code == 422


async def test_an_unknown_platform_is_refused(client):
    """A value the gateway does not know is a message that silently goes
    nowhere."""
    _org, headers = await _tenant_admin(client)
    r = await client.post(
        "/v1/notification-devices",
        json={"token": "t-000001", "platform": "symbian"},
        headers=headers,
    )
    assert r.status_code == 422


async def test_registering_requires_a_signed_in_principal(client):
    r = await client.post("/v1/notification-devices", json={"token": "anonymous"})
    assert r.status_code == 401


# --- the dispatcher's side ----------------------------------------------------


async def test_the_dispatcher_pushes_to_the_most_recent_handset(client):
    """One device, not all of them.

    A notification row per device would break the `(event, template, channel)`
    idempotency key that stops a replay re-sending.
    """
    from platform_core.core import db, tenancy
    from platform_core.modules.notification import providers
    from platform_core.modules.notification.service import (
        NotificationRequest,
        NotificationService,
    )

    _org, headers = await _tenant_admin(client)
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    tenant_id = uuid.UUID(me["tenant_id"])
    for token in ("old-handset-1", "new-handset-2"):
        assert (
            await client.post("/v1/notification-devices", json={"token": token}, headers=headers)
        ).status_code == 201

    sent: list[str] = []

    class _Recorder:
        name = "recorder"

        async def send(self, message):
            sent.append(message.recipient)
            return providers.DeliveryResult(provider_message_id="rec-1", status=providers.ACCEPTED)

    previous = providers._PROVIDERS.get("push")
    providers.register_provider("push", _Recorder())
    tenancy.set_current_tenant(tenant_id)
    try:
        async with db.get_session_factory()() as session:
            await NotificationService(session).dispatch(
                NotificationRequest(
                    tenant_id=tenant_id,
                    event_id=uuid.uuid4(),
                    event_name="sales.invoice-issued.v1",
                    template_key="invoice_issued",
                    channel="push",
                    recipient_ref=uuid.UUID(me["user"]["id"]),
                    variables={"number": "INV-1", "period": "2026-08"},
                )
            )
            await session.commit()
    finally:
        tenancy.set_current_tenant(None)
        providers.reset_providers()
        if previous is not None:
            providers.register_provider("push", previous)

    assert sent == ["new-handset-2"]


async def test_a_households_bill_reaches_the_phone_it_registered(client):
    """End to end, through the relay: issue a bill, and the handset the
    household registered is the one the gateway is asked to reach.

    This is the test that makes the channel more than a class. It runs the
    real consumer over the real durable event log, and the recipient it
    resolves is a CUSTOMER — the invoice-issued event has never heard of a
    user account.
    """
    from platform_core.core.rls import platform_factory
    from platform_core.modules.event_relay.consumers import ConsumerRunner
    from platform_core.modules.notification import providers
    from tests.test_customer_scope import _bill, _customer, _customer_login, _deliver

    org, admin = await _tenant_admin(client)
    household = await _customer(client, admin, "Registered Household")
    other = await _customer(client, admin, "Silent Household")
    await _deliver(client, admin, household["id"])
    await _deliver(client, admin, other["id"])
    mine = await _customer_login(
        client, admin, org["id"], household["id"], "phone@household.example"
    )
    assert (
        await client.post(
            "/v1/notification-devices",
            json={"token": "household-handset-token"},
            headers=mine,
        )
    ).status_code == 201

    sent: list[tuple[str, str]] = []

    class _Recorder:
        name = "recorder"

        async def send(self, message):
            sent.append((message.recipient, message.body))
            return providers.DeliveryResult(provider_message_id="rec-1", status=providers.ACCEPTED)

    providers.register_provider("push", _Recorder())
    try:
        await _bill(client, admin, household["id"])
        await _bill(client, admin, other["id"])
        await ConsumerRunner(platform_factory("test: run consumers")).run_once()
    finally:
        providers.reset_providers()

    assert len(sent) == 1, "the household with no handset should resolve to no device"
    recipient, body = sent[0]
    assert recipient == "household-handset-token"
    # A lock screen is a public surface: the bill is announced, never quoted.
    assert "ready" in body
    for forbidden in ("180.00", "amount", "balance", "owe"):
        assert forbidden not in body, f"a lock screen would show {forbidden!r}"
