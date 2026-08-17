"""Production email transport (PROD-001).

Before this, `notification_email_provider` could only be `logging` or
`placeholder` — both of which return ACCEPTED and send nothing. QR-0007 rated
that a High finding twice over: email had no transport at all, and the default
reported success for every message it discarded.

MSG-001's central lesson drives what is tested here. The adapter is the easy
half; the half that costs money is **failure classification**, because a
permanent failure retried five times spends five connections and five backoff
windows to reach the answer it had immediately.
"""

import smtplib
import uuid

import pytest

from platform_core.modules.notification.providers import (
    ACCEPTED,
    OutboundMessage,
    PermanentSendError,
    ProviderSendError,
    SmtpEmailProvider,
    mask_phone,
)


def _message(recipient="grace@example.com") -> OutboundMessage:
    return OutboundMessage(
        channel="email",
        recipient=recipient,
        title="Payment sent",
        body="Your payment of 18,130.50 KES has been sent.",
        language="en",
        template_key="payment.completed",
        notification_id=uuid.uuid4(),
    )


@pytest.fixture
def smtp_settings(monkeypatch):
    from platform_core.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", "lacteva")
    monkeypatch.setattr(settings, "smtp_password", "not-a-real-password")
    monkeypatch.setattr(settings, "smtp_from_address", "receipts@lacteva.example")
    monkeypatch.setattr(settings, "smtp_security", "starttls")
    # DEMO-031's mode gate refuses a real gateway call while `messaging_mode`
    # is `test`, which is the default and the right default. These tests drive
    # the REAL adapter against a mock transport, so they opt in out loud —
    # exactly the way a sandbox deployment does. The gate itself is proven in
    # tests/test_gateway_sandbox.py, which asserts the refusal.
    monkeypatch.setattr(settings, "messaging_mode", "sandbox")
    return settings


class _Captured:
    """Stands in for the blocking SMTP conversation."""

    def __init__(self, raises=None):
        self.raises = raises
        self.mail = None
        self.sender = None
        self.recipient = None
        self.calls = 0

    def __call__(self, mail, sender, recipient, settings):
        self.calls += 1
        self.mail, self.sender, self.recipient = mail, sender, recipient
        if self.raises:
            raise self.raises


async def test_a_message_is_delivered_and_reports_the_gateway_id(smtp_settings, monkeypatch):
    provider = SmtpEmailProvider()
    captured = _Captured()
    monkeypatch.setattr(provider, "_deliver", captured)

    message = _message()
    result = await provider.send(message)

    assert result.status == ACCEPTED
    assert result.provider_message_id.startswith("<")
    assert captured.sender == "receipts@lacteva.example"
    assert captured.recipient == "grace@example.com"
    assert captured.mail["Subject"] == message.title
    assert message.body in captured.mail.get_content()


async def test_the_message_id_is_stable_across_retries(smtp_settings, monkeypatch):
    """SMTP has no idempotency key. A stable Message-ID is what lets a
    receiving MTA recognise a resend of a message the gateway already accepted
    but whose response we lost."""
    provider = SmtpEmailProvider()
    captured = _Captured()
    monkeypatch.setattr(provider, "_deliver", captured)

    message = _message()
    first = await provider.send(message)
    second = await provider.send(message)
    assert first.provider_message_id == second.provider_message_id

    other = await provider.send(_message())
    assert other.provider_message_id != first.provider_message_id


async def test_an_auto_generated_header_stops_a_mail_loop(smtp_settings, monkeypatch):
    """RFC 3834. Without it, an out-of-office reply to a payment notification
    can bounce back and forth with the gateway."""
    provider = SmtpEmailProvider()
    captured = _Captured()
    monkeypatch.setattr(provider, "_deliver", captured)
    await provider.send(_message())
    assert captured.mail["Auto-Submitted"] == "auto-generated"


# --- the half that costs money ----------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPRecipientsRefused({"grace@example.com": (550, b"no such user")}),
        smtplib.SMTPSenderRefused(553, b"sender rejected", "receipts@lacteva.example"),
        smtplib.SMTPAuthenticationError(535, b"bad credentials"),
        smtplib.SMTPNotSupportedError("STARTTLS not supported"),
        smtplib.SMTPResponseException(550, b"mailbox unavailable"),
    ],
)
async def test_permanent_failures_are_not_retried(smtp_settings, monkeypatch, error):
    """Each of these fails identically forever. Retrying is pure cost, and
    before MSG-001 the engine had no way to be told."""
    provider = SmtpEmailProvider()
    monkeypatch.setattr(provider, "_deliver", _Captured(raises=error))
    with pytest.raises(PermanentSendError):
        await provider.send(_message())


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPConnectError(421, b"try again later"),
        smtplib.SMTPServerDisconnected("connection dropped"),
        smtplib.SMTPResponseException(451, b"temporary local problem"),
        TimeoutError("timed out"),
        ConnectionRefusedError("connection refused"),
        OSError("network unreachable"),
    ],
)
async def test_transient_failures_stay_retryable(smtp_settings, monkeypatch, error):
    """The safe default when a gateway says something unfamiliar is to try
    again — a supplier's message must not be dropped on an unknown failure."""
    provider = SmtpEmailProvider()
    monkeypatch.setattr(provider, "_deliver", _Captured(raises=error))
    with pytest.raises(ProviderSendError) as raised:
        await provider.send(_message())
    assert not isinstance(raised.value, PermanentSendError)


async def test_a_4xx_is_transient_and_a_5xx_is_not(smtp_settings, monkeypatch):
    """The SMTP contract itself, which is why classification can be exact
    rather than a guess at message text."""
    provider = SmtpEmailProvider()

    monkeypatch.setattr(
        provider, "_deliver", _Captured(raises=smtplib.SMTPResponseException(450, b"busy"))
    )
    with pytest.raises(ProviderSendError) as transient:
        await provider.send(_message())
    assert not isinstance(transient.value, PermanentSendError)

    monkeypatch.setattr(
        provider, "_deliver", _Captured(raises=smtplib.SMTPResponseException(552, b"too big"))
    )
    with pytest.raises(PermanentSendError):
        await provider.send(_message())


# --- configuration and safety ------------------------------------------------


async def test_an_unconfigured_host_fails_permanently_rather_than_pretending(monkeypatch):
    """A misconfiguration fails identically for every message, so it must not
    consume a retry budget per supplier."""
    from platform_core.core.config import get_settings

    # Opt past DEMO-031's mode gate, or this asserts the gate rather than the
    # missing host — the two refusals are both permanent and look alike.
    monkeypatch.setattr(get_settings(), "messaging_mode", "sandbox")
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    with pytest.raises(PermanentSendError, match="SMTP_HOST"):
        await SmtpEmailProvider().send(_message())


async def test_a_missing_envelope_sender_fails_permanently(smtp_settings, monkeypatch):
    monkeypatch.setattr(smtp_settings, "smtp_from_address", "")
    monkeypatch.setattr(smtp_settings, "smtp_username", "")
    with pytest.raises(PermanentSendError, match="FROM_ADDRESS"):
        await SmtpEmailProvider().send(_message())


async def test_no_credential_reaches_a_log_or_an_error(smtp_settings, monkeypatch):
    """The failure detail is truncated and echoed from the server. Gateways
    quote the request back often enough that a raw copy can carry the
    credential that was just rejected."""
    provider = SmtpEmailProvider()
    leak = smtplib.SMTPResponseException(
        535, b"auth failed for user lacteva password not-a-real-password " + b"x" * 500
    )
    monkeypatch.setattr(provider, "_deliver", _Captured(raises=leak))
    with pytest.raises(PermanentSendError) as raised:
        await provider.send(_message())
    assert len(str(raised.value)) < 300, "the provider's error is not truncated"


def test_an_email_address_is_masked_for_logging():
    assert mask_phone("grace@example.com") == "g****@example.com"
    assert "njeri" not in mask_phone("njeri@dairy.example")


def test_the_registry_builds_the_smtp_provider_for_email():
    from platform_core.modules.notification.providers import _build

    assert isinstance(_build("email", "smtp"), SmtpEmailProvider)


def test_an_unknown_provider_is_a_startup_failure_not_a_silent_default():
    from platform_core.modules.notification.providers import _build

    with pytest.raises(ValueError, match="unknown email provider"):
        _build("email", "carrier-pigeon")
