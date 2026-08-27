"""The reset code must reach the person, and must not reach the backup
(LACTEVA-BACKEND-004; SEC-003 / F-04).

Found by the E2E harness, not by reading: a real user asked for a reset, the
platform answered 202, an email genuinely arrived — and it said

    "A password reset was requested for your account. The link expires in 2
     hours. If you did not request this, ignore this message."

No link. No code. Nothing to do next. The code was minted, hashed, stored, and
returned to a caller that dropped it; the event deliberately omitted it
(correctly — see below); and the template had no placeholder for one. So
`POST /v1/auth/password-reset/confirm` could not be reached by any real person,
and the reset UI both clients grew in ADMIN-003 was a front door to a door with
no key. Every one of those client tests mocked the platform, which is exactly
why none of them could see it.

The fix is the invitation's arrangement, applied a second time: the auth
service sends the message itself, with the code as a SECRET variable, and the
event stays tokenless.

Both halves are asserted here, in one test, because either alone is a trap:

  * a code that never arrives is the defect this closes;
  * a code that arrives AND is written into `event_outbox` is worse than the
    defect, because that table is never pruned and is in every backup.

A test that checked only the first would applaud the second.
"""

import uuid

import pytest
from sqlalchemy import select

from platform_core.core import db
from tests.conftest import register_and_login

EMAIL = "reset-delivery@example.com"


@pytest.fixture
def provider_guard():
    """Restore the provider registry after a test swaps in a fake."""
    from platform_core.modules.notification import providers

    yield providers
    providers.reset_providers()


class _Capturing:
    """Stands in for the email provider and keeps what was actually sent.

    The only place the raw code ever exists is the outbound message: it is
    hashed in the database, cleared from `secret_payload` the moment delivery
    succeeds, and redacted out of the stored `rendered_text`. So the test reads
    it the way its reader does — off the message — which is also the only way
    to prove the reader really got something usable.
    """

    name = "capturing"

    def __init__(self):
        self.sent: list = []

    async def send(self, message):
        from platform_core.modules.notification.providers import ACCEPTED, DeliveryResult

        self.sent.append(message)
        return DeliveryResult(
            provider_message_id=f"capture:{message.notification_id}", status=ACCEPTED
        )


async def _notification(recipient: str):
    from platform_core.modules.notification.models import Notification

    async with db.get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(Notification).where(
                    Notification.template_key == "password_reset",
                    Notification.recipient == recipient,
                )
            )
        ).all()
        return list(rows)


async def _outbox_payloads():
    from platform_core.modules.event_relay.models import OutboxEvent

    async with db.get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.event_name == "identity.password-reset-requested.v1"
                )
            )
        ).all()
        return [r.payload for r in rows]


async def _reset_token_rows():
    from platform_core.modules.auth.models import PasswordResetToken

    async with db.get_session_factory()() as session:
        return list((await session.scalars(select(PasswordResetToken))).all())


async def test_the_code_reaches_the_reader_and_never_the_outbox(client, provider_guard):
    """The two-sided guard. Both halves, one test, on purpose."""
    recorder = _Capturing()
    provider_guard.register_provider("email", recorder)
    await register_and_login(client, EMAIL)

    r = await client.post("/v1/auth/password-reset/request", json={"email": EMAIL})
    assert r.status_code == 202, r.text
    # The API itself still says nothing — no account oracle, no token.
    assert "token" not in r.text.lower()

    # --- half one: the reader can act on what they were sent ----------------
    delivered = [m for m in recorder.sent if m.recipient == EMAIL]
    assert len(delivered) == 1, "exactly one message, sent once"
    body = delivered[0].body
    assert "Use this code to complete your reset" in body
    assert "Do not share this code with anyone." in body
    # And it no longer promises a link it never contained.
    assert "link" not in body.lower(), f"still promising a link: {body!r}"

    tokens = await _reset_token_rows()
    assert len(tokens) == 1, "one request, one token"

    # Read the code the way its reader would: out of the message.
    code = body.split("complete your reset:", 1)[1].split(".", 1)[0].strip()
    assert code, f"no code in the delivered body: {body!r}"

    # The proof that it is usable, which is the entire point of the work order:
    # the flow can be finished by somebody who has only the email.
    done = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": code, "new_password": "a-brand-new-password-1"},
    )
    assert done.status_code == 204, done.text
    signed_in = await client.post(
        "/v1/auth/token", json={"email": EMAIL, "password": "a-brand-new-password-1"}
    )
    assert signed_in.status_code == 200, "the code from the email opened the account"

    # --- half two: nothing durable holds the live secret --------------------
    stored = await _notification(EMAIL)
    assert len(stored) == 1
    row = stored[0]
    assert row.channel == "email"
    assert row.status == "sent"
    # Cleared once delivered: it existed only to survive a retry.
    assert row.secret_payload is None
    assert code not in (row.rendered_text or ""), "the history kept the live code"

    payloads = await _outbox_payloads()
    assert payloads, "the audit event is still published — it is the record"
    for payload in payloads:
        assert "reset_token" not in payload
        assert code not in str(payload), (
            "the reset code reached `event_outbox`, which is never pruned and "
            "is in every backup — a worse exposure than the one this fixed"
        )
        # The event still carries what a consumer legitimately needs.
        assert payload.get("email") == EMAIL
        assert "expires_hours" in payload

    # And no API hands it back either.
    listing = await client.post(
        "/v1/auth/token", json={"email": EMAIL, "password": "a-brand-new-password-1"}
    )
    admin = {"Authorization": f"Bearer {listing.json()['access_token']}"}
    seen = await client.get("/v1/notifications?limit=50", headers=admin)
    if seen.status_code == 200:
        assert code not in seen.text


async def test_a_second_request_sends_the_second_code_not_the_first(client, provider_guard):
    """Idempotency is keyed on the token, not the person.

    Keyed on the user, a re-request would be suppressed as a duplicate and the
    reader would be left holding a code they had already lost. Keyed on the
    token, each request is its own message — which is what someone who never
    received the first one is trying to achieve.
    """
    recorder = _Capturing()
    provider_guard.register_provider("email", recorder)
    email = "reset-twice@example.com"
    await register_and_login(client, email)

    for _ in range(2):
        assert (
            await client.post("/v1/auth/password-reset/request", json={"email": email})
        ).status_code == 202

    delivered = [m for m in recorder.sent if m.recipient == email]
    assert len(delivered) == 2, "two requests, two messages"
    codes = [m.body.split("complete your reset:", 1)[1].split(".", 1)[0].strip() for m in delivered]
    assert len(set(codes)) == 2, "each message carries its own code"

    # The second code works — which is what somebody who never received the
    # first one is trying to achieve.
    done = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": codes[-1], "new_password": "second-code-works-1"},
    )
    assert done.status_code == 204, done.text


async def test_an_unknown_address_still_says_nothing_and_sends_nothing(client):
    """Enumeration safety, untouched by the delivery fix.

    The 202 is the whole defence, and it would be undone by a delivery change
    that made a real address behave observably differently from a fictional
    one. It does not.
    """
    missing = f"nobody-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post("/v1/auth/password-reset/request", json={"email": missing})
    assert r.status_code == 202
    assert await _notification(missing) == []
