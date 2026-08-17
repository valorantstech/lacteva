"""Production SMS delivery (MSG-001).

The platform could render a message, dispatch it, retry it and record it —
and then hand it to a provider that threw it away. A farmer was never told
they had been paid. This suite covers the adapter that closes that, and the
retry defect the work exposed.

The central finding is not the adapter. It is that **every failure was
retried**: an invalid phone number consumed five gateway calls and five
backoff windows to reach the answer it had the first time, and a missing
template — a deployment fault — did the same. Permanence is now something a
provider can state, and the tests below are mostly about that distinction.
"""

import uuid

import httpx
import pytest

from platform_core.modules.notification.providers import (
    DeliveryResult,
    OutboundMessage,
    PermanentSendError,
    ProviderSendError,
)


def _message(recipient: str = "+254700123456") -> OutboundMessage:
    return OutboundMessage(
        channel="sms",
        recipient=recipient,
        title="Payment",
        body="You have been paid KES 5,647.50",
        language="en",
        template_key="payment_completed",
        notification_id=uuid.uuid4(),
    )


@pytest.fixture
def provider_guard():
    """Restore the provider registry after a test swaps in a fake."""
    from platform_core.modules.notification import providers

    yield providers
    providers.reset_providers()


@pytest.fixture
def gateway(monkeypatch):
    """A stand-in gateway. Returns a recorder the test drives."""

    class Gateway:
        def __init__(self):
            self.requests: list[httpx.Request] = []
            self.handler = lambda request: httpx.Response(200, json={"message_id": "gw-1"})

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


@pytest.fixture
def sms_settings(monkeypatch):
    from platform_core.core.config import get_settings

    settings = get_settings()
    # DEMO-031's mode gate refuses a real gateway call while `messaging_mode`
    # is `test`, which is the default and the right default. These tests drive
    # the REAL adapter against a mock transport, so they opt in out loud —
    # exactly the way a sandbox deployment does. The gate itself is proven in
    # tests/test_gateway_sandbox.py, which asserts the refusal.
    monkeypatch.setattr(settings, "messaging_mode", "sandbox")
    original = (settings.sms_api_url, settings.sms_api_key, settings.sms_sender_id)
    settings.sms_api_url = "https://gateway.example/send"
    settings.sms_api_key = "test-key-not-a-real-credential"
    settings.sms_sender_id = "LACTEVA"
    yield settings
    settings.sms_api_url, settings.sms_api_key, settings.sms_sender_id = original


def _provider(sms_settings):
    from platform_core.modules.notification.providers import HttpSmsProvider

    return HttpSmsProvider("sms")


# --- success ---------------------------------------------------------------


async def test_a_message_is_accepted_and_reports_the_gateway_id(gateway, sms_settings):
    result = await _provider(sms_settings).send(_message())
    assert isinstance(result, DeliveryResult)
    assert result.provider_message_id == "gw-1"
    assert result.status == "accepted"
    assert result.metadata["http_status"] == 200


async def test_the_request_carries_sender_recipient_and_body(gateway, sms_settings):
    import json

    await _provider(sms_settings).send(_message("+254711000111"))
    sent = json.loads(gateway.requests[0].content)
    assert sent["to"] == "+254711000111"
    assert sent["from"] == "LACTEVA"
    assert "5,647.50" in sent["text"]


# --- idempotency -----------------------------------------------------------


async def test_every_send_carries_a_stable_idempotency_key(gateway, sms_settings):
    """The one double-send the platform cannot prevent alone: a message the
    gateway accepted and whose response we lost. Only the gateway knows, so
    it is told — with a key that is identical on every retry."""
    message = _message()
    provider = _provider(sms_settings)
    await provider.send(message)
    await provider.send(message)  # the retry

    keys = [r.headers["Idempotency-Key"] for r in gateway.requests]
    assert keys[0] == keys[1], "a retry sent a different key — the gateway would send twice"
    assert str(message.notification_id) in keys[0]


async def test_the_key_differs_between_notifications(gateway, sms_settings):
    provider = _provider(sms_settings)
    await provider.send(_message())
    await provider.send(_message())
    assert (
        gateway.requests[0].headers["Idempotency-Key"]
        != (gateway.requests[1].headers["Idempotency-Key"])
    )


async def test_a_duplicate_notification_never_reaches_the_gateway_twice(client, provider_guard):
    """The platform-level half: `dispatch` is idempotent on
    (event, template, channel), so a consumer replay re-finds the
    notification rather than sending a second message."""
    from platform_core.core import db
    from platform_core.modules.notification.providers import register_provider
    from platform_core.modules.notification.service import NotificationRequest, NotificationService

    sent = []

    class Recorder:
        name = "recorder"

        async def send(self, message):
            sent.append(message)
            return DeliveryResult(provider_message_id=f"rec-{len(sent)}")

    register_provider("sms", Recorder())
    event_id = uuid.uuid4()
    request = NotificationRequest(
        event_id=event_id,
        event_name="payment.completed.v1",
        tenant_id=uuid.uuid4(),
        template_key="payment_completed",
        channel="sms",
        recipient="+254700123456",
        variables={
            "name": "Amina",
            "amount": "100",
            "currency": "KES",
            "number": "STL-1",
            "reference": "PAY-1",
        },
    )
    async with db.get_session_factory()() as session:
        service = NotificationService(session)
        await service.dispatch(request)
        await service.dispatch(request)  # the replay
        await session.commit()
    assert len(sent) == 1, f"the duplicate dispatched {len(sent)} messages"


# --- transient failures: retry ---------------------------------------------


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
async def test_transient_gateway_failures_are_retryable(gateway, sms_settings, status):
    """Throttling and gateway faults pass. The retry budget exists for these."""
    gateway.handler = lambda request: httpx.Response(status, text="try later")
    with pytest.raises(ProviderSendError) as raised:
        await _provider(sms_settings).send(_message())
    assert not isinstance(raised.value, PermanentSendError), f"{status} must stay retryable"


async def test_a_timeout_is_retryable(gateway, sms_settings):
    """We cannot know whether it arrived, so we assume it did not — which is
    only safe because the idempotency key stops the double send."""

    def timeout(request):
        raise httpx.ReadTimeout("too slow", request=request)

    gateway.handler = timeout
    with pytest.raises(ProviderSendError) as raised:
        await _provider(sms_settings).send(_message())
    assert not isinstance(raised.value, PermanentSendError)
    assert "timeout" in str(raised.value).lower()


async def test_an_unreachable_gateway_is_retryable(gateway, sms_settings):
    def unreachable(request):
        raise httpx.ConnectError("no route to host", request=request)

    gateway.handler = unreachable
    with pytest.raises(ProviderSendError) as raised:
        await _provider(sms_settings).send(_message())
    assert not isinstance(raised.value, PermanentSendError)


# --- permanent failures: do not retry --------------------------------------


@pytest.mark.parametrize(
    ("status", "meaning"),
    [
        (400, "malformed"),
        (401, "authentication"),
        (403, "forbidden"),
        (404, "unknown number"),
        (422, "invalid phone"),
        (402, "out of credit"),
    ],
)
async def test_permanent_gateway_rejections_are_not_retried(gateway, sms_settings, status, meaning):
    """Retrying these costs a gateway call each time and cannot succeed."""
    gateway.handler = lambda request: httpx.Response(status, text=meaning)
    with pytest.raises(PermanentSendError):
        await _provider(sms_settings).send(_message("not-a-number"))


async def test_a_permanent_failure_goes_dead_on_the_first_attempt(client, provider_guard):
    """The retry engine's half of the fix. Before MSG-001 this consumed the
    whole budget to reach the same answer it had immediately."""
    from platform_core.core import db
    from platform_core.modules.notification.providers import register_provider
    from platform_core.modules.notification.service import NotificationRequest, NotificationService

    attempts = []

    class Rejecting:
        name = "rejecting"

        async def send(self, message):
            attempts.append(message)
            raise PermanentSendError("invalid phone number")

    register_provider("sms", Rejecting())
    async with db.get_session_factory()() as session:
        service = NotificationService(session)
        notification = await service.dispatch(
            NotificationRequest(
                event_id=uuid.uuid4(),
                event_name="payment.completed.v1",
                tenant_id=uuid.uuid4(),
                template_key="payment_completed",
                channel="sms",
                recipient="+254700123456",
                variables={
                    "name": "Amina",
                    "amount": "100",
                    "currency": "KES",
                    "number": "STL-1",
                    "reference": "PAY-1",
                },
            )
        )
        await session.commit()
    assert len(attempts) == 1, f"a permanent failure was retried {len(attempts)} times"
    assert notification.status == "dead"
    assert notification.next_attempt_at is None, "a permanent failure must not be rescheduled"


async def test_a_transient_failure_is_scheduled_for_retry(client, provider_guard):
    """The contrast: the same engine, a different verdict."""
    from platform_core.core import db
    from platform_core.modules.notification.providers import register_provider
    from platform_core.modules.notification.service import NotificationRequest, NotificationService

    class Flaky:
        name = "flaky"

        async def send(self, message):
            raise ProviderSendError("gateway unavailable")

    register_provider("sms", Flaky())
    async with db.get_session_factory()() as session:
        notification = await NotificationService(session).dispatch(
            NotificationRequest(
                event_id=uuid.uuid4(),
                event_name="payment.completed.v1",
                tenant_id=uuid.uuid4(),
                template_key="payment_completed",
                channel="sms",
                recipient="+254700123456",
                variables={
                    "name": "Amina",
                    "amount": "100",
                    "currency": "KES",
                    "number": "STL-1",
                    "reference": "PAY-1",
                },
            )
        )
        await session.commit()
    assert notification.status == "failed"
    assert notification.next_attempt_at is not None, "a transient failure must be retried"


async def test_a_missing_template_is_not_retried(client, provider_guard):
    """A deployment fault, not a delivery fault. Retrying it five times
    changes nothing and buries the real signal under a retry backlog."""
    from platform_core.core import db
    from platform_core.modules.notification.service import NotificationRequest, NotificationService

    async with db.get_session_factory()() as session:
        notification = await NotificationService(session).dispatch(
            NotificationRequest(
                event_id=uuid.uuid4(),
                event_name="payment.completed.v1",
                tenant_id=uuid.uuid4(),
                template_key="no_such_template_exists",
                channel="sms",
                recipient="+254700123456",
                variables={},
            )
        )
        await session.commit()
    assert notification.status == "dead"
    assert notification.next_attempt_at is None


# --- malformed provider responses ------------------------------------------


async def test_an_unparseable_2xx_is_treated_as_accepted(gateway, sms_settings):
    """A 2xx we cannot read is still a 2xx. Failing it would resend a message
    the gateway has already taken — and charge for."""
    gateway.handler = lambda request: httpx.Response(200, text="<html>ok</html>")
    result = await _provider(sms_settings).send(_message())
    assert result.status == "unknown"
    assert result.metadata["unparseable"] is True


async def test_a_2xx_with_the_wrong_shape_is_treated_as_accepted(gateway, sms_settings):
    gateway.handler = lambda request: httpx.Response(200, json=["not", "a", "dict"])
    result = await _provider(sms_settings).send(_message())
    assert result.status == "unknown"


async def test_a_2xx_without_a_message_id_falls_back_to_our_own(gateway, sms_settings):
    gateway.handler = lambda request: httpx.Response(200, json={"status": "queued"})
    message = _message()
    result = await _provider(sms_settings).send(message)
    assert str(message.notification_id) in result.provider_message_id


# --- configuration ---------------------------------------------------------


def test_the_provider_refuses_to_start_without_a_url(sms_settings):
    from platform_core.modules.notification.providers import HttpSmsProvider

    sms_settings.sms_api_url = ""
    with pytest.raises(ValueError, match="LACTEVA_SMS_API_URL"):
        HttpSmsProvider("sms")


def test_an_unknown_provider_name_fails_loudly():
    """A typo must be a startup failure, not a message that goes nowhere."""
    from platform_core.modules.notification.providers import _build

    with pytest.raises(ValueError, match="unknown"):
        _build("sms", "twilio-ish")


async def test_dry_run_sends_nothing_but_reports_success(provider_guard):
    from platform_core.modules.notification.providers import DryRunProvider

    result = await DryRunProvider("sms").send(_message())
    assert result.metadata["dry_run"] is True
    assert result.status == "accepted"


async def test_disabled_refuses_permanently(provider_guard):
    """Silent success would be a lie the platform then repeats to an operator
    asking why a supplier was never told."""
    from platform_core.modules.notification.providers import DisabledProvider

    with pytest.raises(PermanentSendError):
        await DisabledProvider("sms").send(_message())


@pytest.mark.parametrize("name", ["logging", "placeholder", "dry_run", "disabled"])
def test_every_configured_provider_can_be_built(name):
    from platform_core.modules.notification.providers import _build

    assert _build("sms", name) is not None


# --- security ---------------------------------------------------------------


def test_phone_numbers_are_masked_for_logging():
    """A log carrying every supplier's number is a copy of the directory with
    weaker access control than the database it came from."""
    from platform_core.modules.notification.providers import mask_phone

    masked = mask_phone("+254700123456")
    assert masked.startswith("+2547") and masked.endswith("3456")
    assert "0012" not in masked
    assert mask_phone("a@b.example").startswith("a*")
    assert mask_phone("") == ""
    assert "1234" not in mask_phone("123456")


def test_no_provider_logs_a_full_recipient():
    """Structural: every recipient reaching a log goes through the mask."""
    import inspect

    from platform_core.modules.notification import providers

    source = inspect.getsource(providers)
    # Every place a recipient is handed to a logger must wrap it. Sending the
    # real number to the gateway is the point; logging it is the leak.
    # Only LOG calls matter: handing the real number to the notifier port or
    # the gateway is the entire point of having it.
    lines = source.splitlines()
    unmasked = []
    for i, line in enumerate(lines):
        if "recipient=message.recipient" not in line.replace(" ", ""):
            continue
        context = "\n".join(lines[max(0, i - 6) : i])
        if "log." in context:
            unmasked.append(line.strip())
    assert unmasked == [], f"a recipient reaches a log unmasked: {unmasked}"
    assert source.count("mask_phone(message.recipient)") >= 3


async def test_a_gateway_error_body_is_truncated_and_not_echoed_whole(gateway, sms_settings):
    """Error bodies echo the request often enough to carry the phone number,
    and occasionally the credential."""
    gateway.handler = lambda request: httpx.Response(400, text="x" * 5000)
    with pytest.raises(PermanentSendError) as raised:
        await _provider(sms_settings).send(_message())
    assert len(str(raised.value)) < 400


async def test_the_api_key_never_appears_in_an_error(gateway, sms_settings):
    gateway.handler = lambda request: httpx.Response(500, text="upstream failed")
    with pytest.raises(ProviderSendError) as raised:
        await _provider(sms_settings).send(_message())
    assert sms_settings.sms_api_key not in str(raised.value)


# --- observability ----------------------------------------------------------


def test_provider_errors_are_counted_by_whether_a_retry_can_help():
    from platform_core.core import metrics

    assert hasattr(metrics, "NOTIFICATION_PROVIDER_ERRORS")
    labels = metrics.NOTIFICATION_PROVIDER_ERRORS._labelnames
    assert labels == ("channel", "provider", "kind"), labels


def test_the_error_metric_has_bounded_cardinality():
    """`kind` is three values, never the provider's error string — which is
    unbounded and partly attacker-influenced."""
    import inspect

    from platform_core.modules.notification import service

    source = inspect.getsource(service)
    assert '"permanent"' in source and '"transient"' in source and '"timeout"' in source


async def test_segments_are_reported_so_a_costly_template_is_visible(gateway, sms_settings):
    """Segments are what a gateway bills. A template that quietly crosses the
    160-character boundary doubles the cost of every message it sends."""
    from platform_core.modules.notification.providers import _segments

    assert _segments("short") == 1
    assert _segments("x" * 161) == 2
    assert _segments("é" * 71) == 2  # non-GSM alphabet halves the budget

    result = await _provider(sms_settings).send(_message())
    assert "segments" in result.metadata
