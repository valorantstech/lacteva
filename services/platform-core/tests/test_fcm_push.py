"""WO-77 — the platform learns to speak FCM, proven against a FAKE key.

Never the real service account, never a request that reaches Google: the key
is generated here, the token endpoint and the send endpoint are a mock
transport, and every property that decides whether this survives a month in
production is asserted on what crossed that transport:

  * the envelope is FCM v1 — nested, `data` all strings, Android priority high;
  * four hundred sends mint ONE access token, and one that is about to expire
    is refreshed early, single-flight;
  * a 401 mints a fresh token and retries exactly once;
  * `UNREGISTERED` (and a 400 naming the token) is a DEAD token: the device
    registration is dropped and the notification is not retried;
  * a 400 about the message is permanent and keeps the handset;
  * 429 and 5xx are transient and go back to the relay's retry;
  * the private key, the access token and the device token appear in no log
    line, no notification row and no error;
  * the settings refuse `fcm` without a project id and a credentials path, and
    `messaging-posture` reports push as configured and able to send.
"""

import asyncio
import json
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from platform_core.modules.notification.providers import (
    DeadTokenError,
    OutboundMessage,
    PermanentSendError,
    ProviderSendError,
)

PROJECT = "lacteva-test-project"
TOKEN_URI = "https://oauth2.example.test/token"
SEND_URL = f"https://fcm.googleapis.com/v1/projects/{PROJECT}/messages:send"
DEVICE_TOKEN = "fcm-registration-token-" + "x" * 120
ACCESS_TOKEN = "ya29.fake-access-token-" + "a" * 60


def _fake_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture(scope="module")
def fake_key_pem() -> str:
    return _fake_key_pem()


@pytest.fixture
def credentials_file(tmp_path, fake_key_pem):
    """A service-account key with the SHAPE Google issues and none of the
    substance: fresh RSA material, a made-up identity."""
    path = tmp_path / "fake-service-account.json"
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": PROJECT,
                "private_key_id": "0" * 40,
                "private_key": fake_key_pem,
                "client_email": f"pusher@{PROJECT}.example.test",
                "token_uri": TOKEN_URI,
            }
        )
    )
    return path


@pytest.fixture
def fcm_settings(monkeypatch, credentials_file):
    from platform_core.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "messaging_mode", "sandbox")
    monkeypatch.setattr(settings, "notification_push_provider", "fcm")
    monkeypatch.setattr(settings, "notification_fcm_project_id", PROJECT)
    monkeypatch.setattr(settings, "notification_fcm_credentials_path", str(credentials_file))
    return settings


class _Google:
    """The two endpoints, as a mock transport the test steers."""

    def __init__(self):
        self.token_requests: list[httpx.Request] = []
        self.sends: list[httpx.Request] = []
        self.expires_in = 3600
        self.send_handler = lambda request, n: httpx.Response(
            200, json={"name": f"projects/{PROJECT}/messages/{n}"}
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URI:
            self.token_requests.append(request)
            return httpx.Response(
                200, json={"access_token": ACCESS_TOKEN, "expires_in": self.expires_in}
            )
        if str(request.url) == SEND_URL:
            self.sends.append(request)
            return self.send_handler(request, len(self.sends))
        return httpx.Response(500, text="unexpected url")


@pytest.fixture
def google(monkeypatch):
    stub = _Google()
    transport = httpx.MockTransport(stub.handle)
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return stub


def _provider():
    from platform_core.modules.notification.fcm import FcmPushProvider

    return FcmPushProvider("push")


def _message(recipient: str = DEVICE_TOKEN) -> OutboundMessage:
    return OutboundMessage(
        channel="push",
        recipient=recipient,
        title="Your bill is ready",
        body="Bill INV-1 for Aug is ready. Open Lacteva to see it.",
        language="en",
        template_key="invoice_issued",
        notification_id=uuid.uuid4(),
    )


def _fcm_error(status: int, code: str, message: str) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": status, "status": code, "message": message}}
    )


# --- the envelope ---------------------------------------------------------------


async def test_the_envelope_is_fcm_v1_with_string_data(google, fcm_settings):
    result = await _provider().send(_message())
    assert result.status == "accepted"
    assert result.provider_message_id == f"projects/{PROJECT}/messages/1"
    assert len(google.sends) == 1
    request = google.sends[0]
    assert request.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
    body = json.loads(request.content)
    message = body["message"]
    assert message["token"] == DEVICE_TOKEN
    assert message["notification"] == {
        "title": "Your bill is ready",
        "body": "Bill INV-1 for Aug is ready. Open Lacteva to see it.",
    }
    assert message["android"]["priority"] == "high"
    assert message["android"]["notification"]["channel_id"] == "lacteva"
    assert all(isinstance(v, str) for v in message["data"].values()), message["data"]
    assert message["data"]["template"] == "invoice_issued"
    assert set(message["data"]) == {"template", "notification_id", "channel"}
    # The lock screen is told WHICH record, never what it says.
    assert "amount" not in json.dumps(message["data"])


def test_a_non_string_data_value_is_refused_before_any_network_call(fcm_settings, google):
    from platform_core.modules.notification.fcm import FcmPushProvider, assert_string_data

    envelope = FcmPushProvider.envelope(_message())
    assert all(isinstance(v, str) for v in envelope["message"]["data"].values())
    # The guard every envelope passes through: an integer is refused as
    # PERMANENT — a retry cannot turn 3 into "3" — and nothing was posted.
    with pytest.raises(PermanentSendError):
        assert_string_data({"template": "invoice_issued", "count": 3})
    assert_string_data({"template": "invoice_issued", "count": "3"})
    assert google.sends == []


# --- one token, not four hundred -------------------------------------------------


async def test_four_hundred_sends_mint_one_access_token(google, fcm_settings):
    provider = _provider()
    results = await asyncio.gather(*(provider.send(_message()) for _ in range(400)))
    assert len(results) == 400
    assert len(google.sends) == 400
    assert len(google.token_requests) == 1, "four hundred notifications cost one token"
    assert provider.tokens.mints == 1


async def test_a_token_near_expiry_is_refreshed_early(google, fcm_settings):
    # Google says the token lives 200 s; the adapter refreshes 300 s before
    # expiry, so it is ALREADY due — the next send mints again.
    google.expires_in = 200
    provider = _provider()
    await provider.send(_message())
    await provider.send(_message())
    assert len(google.token_requests) == 2
    # And a full-length token is reused.
    google.expires_in = 3600
    await provider.send(_message())
    await provider.send(_message())
    assert len(google.token_requests) == 3


async def test_a_401_mints_a_fresh_token_and_retries_once(google, fcm_settings):
    def handler(request, n):
        if n == 1:
            return _fcm_error(401, "UNAUTHENTICATED", "Request had invalid credentials")
        return httpx.Response(200, json={"name": f"projects/{PROJECT}/messages/ok"})

    google.send_handler = handler
    result = await _provider().send(_message())
    assert result.provider_message_id == f"projects/{PROJECT}/messages/ok"
    assert len(google.sends) == 2
    assert len(google.token_requests) == 2, "the retry carried a freshly minted token"

    # Twice is a credential problem, not a stale token: permanent, no third try.
    google.sends.clear()
    google.send_handler = lambda request, n: _fcm_error(401, "UNAUTHENTICATED", "bad")
    with pytest.raises(PermanentSendError) as excinfo:
        await _provider().send(_message())
    assert not isinstance(excinfo.value, DeadTokenError)
    assert len(google.sends) == 2


# --- failure classification ----------------------------------------------------------


async def test_unregistered_is_a_dead_token(google, fcm_settings):
    google.send_handler = lambda r, n: _fcm_error(
        404, "UNREGISTERED", "Requested entity was not found."
    )
    with pytest.raises(DeadTokenError):
        await _provider().send(_message())


async def test_a_400_naming_the_token_is_a_dead_token_and_one_about_the_message_is_not(
    google, fcm_settings
):
    google.send_handler = lambda r, n: _fcm_error(
        400,
        "INVALID_ARGUMENT",
        "The registration token is not a valid FCM registration token",
    )
    with pytest.raises(DeadTokenError):
        await _provider().send(_message())

    google.send_handler = lambda r, n: _fcm_error(
        400, "INVALID_ARGUMENT", "Invalid value at 'message.android.priority'"
    )
    with pytest.raises(PermanentSendError) as excinfo:
        await _provider().send(_message())
    assert not isinstance(excinfo.value, DeadTokenError)


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_429_and_5xx_are_transient(google, fcm_settings, status):
    google.send_handler = lambda r, n: _fcm_error(status, "UNAVAILABLE", "try later")
    with pytest.raises(ProviderSendError) as excinfo:
        await _provider().send(_message())
    assert not isinstance(excinfo.value, PermanentSendError)


# --- through the service: the handset is forgotten, not retried ----------------------


async def test_a_dead_token_drops_the_registration_and_is_not_retried(client, google, fcm_settings):
    """End to end through `NotificationService`: the device row goes, the
    notification is permanently failed, and the next dispatch for the same
    household resolves to NO device rather than spending a gateway call."""
    from sqlalchemy import select

    from platform_core.core.rls import platform_factory
    from platform_core.modules.notification import providers
    from platform_core.modules.notification.models import Notification, NotificationDevice
    from platform_core.modules.notification.service import (
        NotificationRequest,
        NotificationService,
    )
    from tests.test_customer_scope import _customer, _customer_login
    from tests.test_org_structure import _tenant_admin

    org, admin = await _tenant_admin(client)
    household = await _customer(client, admin, "Uninstalled Household")
    mine = await _customer_login(
        client, admin, org["id"], household["id"], "gone@household.example"
    )
    r = await client.post("/v1/notification-devices", json={"token": DEVICE_TOKEN}, headers=mine)
    assert r.status_code == 201, r.text

    google.send_handler = lambda r, n: _fcm_error(404, "UNREGISTERED", "not found")
    providers.register_provider("push", _provider())
    try:
        async with platform_factory("test: dispatch over fcm")() as session:
            service = NotificationService(session)
            first = await service.dispatch(
                NotificationRequest(
                    event_id=uuid.uuid4(),
                    event_name="sales.invoice-issued.v1",
                    tenant_id=uuid.UUID(org["id"]),
                    template_key="invoice_issued",
                    channel="push",
                    recipient_ref=uuid.UUID(household["id"]),
                    variables={"number": "INV-1", "period": "Aug"},
                )
            )
            await session.commit()
            assert first is not None
            assert first.status in ("failed", "dead")
            assert first.next_attempt_at is None, "a dead token is not retried"
            assert DEVICE_TOKEN not in (first.error or "")
            devices = (await session.scalars(select(NotificationDevice))).all()
            assert devices == [], "the registration was dropped on the first UNREGISTERED"

            sends_before = len(google.sends)
            second = await service.dispatch(
                NotificationRequest(
                    event_id=uuid.uuid4(),
                    event_name="sales.invoice-issued.v1",
                    tenant_id=uuid.UUID(org["id"]),
                    template_key="invoice_issued",
                    channel="push",
                    recipient_ref=uuid.UUID(household["id"]),
                    variables={"number": "INV-2", "period": "Sep"},
                )
            )
            await session.commit()
            assert second is not None
            assert len(google.sends) == sends_before, "no device, no gateway call"
            assert "no recipient" in (second.error or "")
            rows = (await session.scalars(select(Notification))).all()
            assert all(DEVICE_TOKEN not in json.dumps(r.payload) for r in rows)
    finally:
        providers.reset_providers()


# --- secrets ---------------------------------------------------------------------------


async def test_no_secret_reaches_a_log_a_row_or_an_error(
    google, fcm_settings, fake_key_pem, capsys, caplog
):
    """The private key, the access token and the device token: in nothing an
    operator can read."""
    from platform_core.modules.notification.fcm import FcmPushProvider

    provider = _provider()
    await provider.send(_message())
    google.send_handler = lambda r, n: _fcm_error(
        400, "INVALID_ARGUMENT", f"bad token {DEVICE_TOKEN} in field message.token"
    )
    with pytest.raises(ProviderSendError) as excinfo:
        await provider.send(_message())
    error_text = str(excinfo.value)
    captured = capsys.readouterr()
    everything = captured.out + captured.err + caplog.text + error_text + repr(provider)
    key_line = fake_key_pem.splitlines()[1]
    assert key_line not in everything
    assert "BEGIN PRIVATE KEY" not in everything
    assert ACCESS_TOKEN not in everything
    assert DEVICE_TOKEN not in everything
    # And the provider object itself gives nothing away.
    assert fake_key_pem.splitlines()[1] not in repr(vars(provider))
    assert isinstance(provider, FcmPushProvider)


# --- configuration and posture -------------------------------------------------------


def test_fcm_without_project_or_credentials_is_refused():
    """The validator that already refuses `http` without a URL and a key
    refuses `fcm` without a project id and a credentials path — at
    construction, so the deployment fails once rather than every send."""
    from platform_core.core.config import Settings
    from tests.test_gateway_sandbox import PROD

    with pytest.raises(ValueError) as excinfo:
        Settings(
            **{
                **PROD,
                "messaging_mode": "production",
                "notification_push_provider": "fcm",
                "notification_fcm_project_id": "",
                "notification_fcm_credentials_path": "",
            }
        )
    assert "LACTEVA_NOTIFICATION_FCM_PROJECT_ID" in str(excinfo.value)


def test_the_builder_refuses_a_missing_key_file_loudly(monkeypatch, tmp_path):
    from platform_core.core.config import get_settings
    from platform_core.modules.notification.providers import _build

    settings = get_settings()
    monkeypatch.setattr(settings, "notification_fcm_project_id", PROJECT)
    monkeypatch.setattr(settings, "notification_fcm_credentials_path", str(tmp_path / "no.json"))
    with pytest.raises(ValueError) as excinfo:
        _build("push", "fcm")
    assert "does not exist" in str(excinfo.value)
    # A wrong-shaped file is refused without quoting it.
    (tmp_path / "wrong.json").write_text(json.dumps({"type": "authorized_user", "x": "y"}))
    monkeypatch.setattr(settings, "notification_fcm_credentials_path", str(tmp_path / "wrong.json"))
    with pytest.raises(ValueError) as excinfo:
        _build("push", "fcm")
    assert "not a service-account key" in str(excinfo.value)
    assert "authorized_user" not in str(excinfo.value)
    with pytest.raises(ValueError):
        _build("sms", "fcm")


async def test_messaging_posture_reports_push_as_sendable(client, fcm_settings):
    from platform_core.modules.notification import providers
    from tests.test_org_structure import _tenant_admin

    providers.reset_providers()
    try:
        _org, admin = await _tenant_admin(client)
        r = await client.get("/v1/notifications/messaging-posture", headers=admin)
        assert r.status_code == 200, r.text
        push = next(c for c in r.json()["channels"] if c["channel"] == "push")
        assert push == {
            "channel": "push",
            "provider": "fcm-push",
            "configured": True,
            "can_send": True,
            "reports_delivery": False,
        }
    finally:
        providers.reset_providers()
