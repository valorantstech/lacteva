"""SEC-003 / F-04 — the invitation token belongs to the invitee alone.

FINAL-001: `POST /v1/invitations` returned `invitation_token` in its response
body, so whoever issued an invitation could accept it themselves — creating an
account bound to the invitee's email address, inside the invitee's tenant,
carrying the role they were being offered. The comment above it said
"FOUNDATION ONLY: token in the response until real delivery lands (M2)".
Delivery had landed two work orders earlier.

The fix has three parts, and all three are load-bearing:

  1. the response carries metadata only;
  2. the token reaches the invitee through the notification channel;
  3. it is stored as a SECRET on the way — not in the outbox payload, not in
     `Notification.payload`, not in `rendered_text`, and not in a log line —
     because a token that merely moves from the HTTP response to the
     notification history is still readable by the inviter.
"""

import uuid

from sqlalchemy import select

from platform_core.core import db
from tests.conftest import invite
from tests.test_org_structure import _tenant_admin


async def _invitation_row(email: str):
    """By EMAIL, not `.first()` — `_tenant_admin` already issued one invitation
    to bootstrap the tenant, so the first row is never the one under test."""
    from platform_core.modules.organization.models import Invitation

    async with db.get_session_factory()() as session:
        return (await session.scalars(select(Invitation).where(Invitation.email == email))).one()


async def _notification_row(template_key: str = "invitation", *, recipient: str | None = None):
    from platform_core.modules.notification.models import Notification

    async with db.get_session_factory()() as session:
        stmt = select(Notification).where(Notification.template_key == template_key)
        if recipient is not None:
            stmt = stmt.where(Notification.recipient == recipient)
        return (await session.scalars(stmt)).first()


# --- 1. the response --------------------------------------------------------


async def test_the_invite_response_carries_no_secret(client):
    _org, admin = await _tenant_admin(client)
    r = await client.post(
        "/v1/invitations",
        json={"email": "newcomer@kilima.example", "role_name": "tenant-viewer"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "invitation_token" not in body
    assert "token" not in body
    # Requirement 4: id, status, expiry and other non-secret metadata are fine.
    assert set(body) == {"id", "email", "role_name", "status", "expires_at"}
    uuid.UUID(body["id"])
    assert body["status"] == "pending"


async def test_no_value_in_the_response_can_be_used_as_a_token(client):
    """The sharp version of requirement 9: not merely 'the field is gone', but
    'nothing the inviter is handed works'."""
    _org, admin = await _tenant_admin(client)
    body = (
        await client.post(
            "/v1/invitations",
            json={"email": "target@kilima.example", "role_name": "tenant-admin"},
            headers=admin,
        )
    ).json()

    for value in body.values():
        r = await client.post(
            "/v1/invitations/accept",
            json={
                "token": str(value),
                "password": "stolen-password-1",
                "full_name": "Impostor",
            },
        )
        assert r.status_code == 400, f"{value!r} was accepted as an invitation token"


async def test_the_inviter_cannot_create_the_invitees_account(client):
    """F-04 stated as the attack it enables, end to end."""
    _org, admin = await _tenant_admin(client)
    await client.post(
        "/v1/invitations",
        json={"email": "victim@kilima.example", "role_name": "tenant-admin"},
        headers=admin,
    )
    # Everything the inviter can see about the invitation they just issued.
    listed = await client.get("/v1/invitations", headers=admin)
    visible = listed.text if listed.status_code == 200 else ""
    history = await client.get("/v1/notifications?limit=50", headers=admin)
    visible += history.text if history.status_code == 200 else ""

    row = await _notification_row(recipient="victim@kilima.example")
    assert row is not None, "no invitation notification was created"

    # The token is nowhere in anything the inviter can read.
    invitation = await _invitation_row("victim@kilima.example")
    assert invitation.token_hash not in visible
    assert (row.rendered_text or "") not in visible or "[redacted]" in (row.rendered_text or "")


# --- 2. delivery ------------------------------------------------------------


async def test_the_token_is_delivered_through_the_notification_channel(client):
    """Requirement 3. `invite()` captures the outbound provider message, which
    is the only place the real token ever appears."""
    _org, admin = await _tenant_admin(client)
    _body, token = await invite(
        client, admin, email="delivered@kilima.example", role_name="tenant-viewer"
    )
    assert len(token) > 20, token

    accepted = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "delivered-password-1", "full_name": "Delivered"},
    )
    assert accepted.status_code == 201, accepted.text


async def test_an_expired_invitation_is_refused(client):
    from datetime import timedelta

    from platform_core.core.db import utcnow
    from platform_core.modules.organization.models import Invitation

    _org, admin = await _tenant_admin(client)
    _body, token = await invite(
        client, admin, email="late@kilima.example", role_name="tenant-viewer"
    )

    async with db.get_session_factory()() as session:
        invitation = (
            await session.scalars(
                select(Invitation).where(Invitation.email == "late@kilima.example")
            )
        ).one()
        invitation.expires_at = utcnow() - timedelta(days=1)
        await session.commit()

    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "late-password-11", "full_name": "Too Late"},
    )
    assert r.status_code == 400


async def test_a_bogus_invitation_token_is_refused(client):
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": "not-a-real-token", "password": "bogus-password-1", "full_name": "Nobody"},
    )
    assert r.status_code == 400


async def test_an_invitation_cannot_be_accepted_twice(client):
    _org, admin = await _tenant_admin(client)
    _body, token = await invite(
        client, admin, email="once@kilima.example", role_name="tenant-viewer"
    )
    first = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "once-password-111", "full_name": "First"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "again-password-11", "full_name": "Second"},
    )
    assert second.status_code == 400


# --- 3. the token at rest ---------------------------------------------------


async def test_only_the_hash_is_stored_on_the_invitation(client):

    _org, admin = await _tenant_admin(client)
    _body, token = await invite(
        client, admin, email="hashed@kilima.example", role_name="tenant-viewer"
    )
    invitation = await _invitation_row("hashed@kilima.example")
    assert invitation.token_hash != token
    assert len(invitation.token_hash) == 64  # sha256 hex


async def test_the_token_never_enters_the_durable_event_log(client, bus):
    """The reason `InvitationService` sends this one message itself.

    `event_outbox` is classified critical, is never pruned, and is in every
    backup. A consumer can only read what the payload carries, so routing the
    invitation email through the consumer would have required putting a live
    one-time secret there permanently.
    """
    _org, admin = await _tenant_admin(client)
    _body, token = await invite(
        client, admin, email="outbox@kilima.example", role_name="tenant-viewer"
    )

    from platform_core.modules.event_relay.models import OutboxEvent

    async with db.get_session_factory()() as session:
        rows = (await session.scalars(select(OutboxEvent))).all()
        payloads = " ".join(str(row.payload) for row in rows)
    assert token not in payloads, "the invitation token is in the durable event log"

    issued = [e for e in bus.published if e.type == "organization.invitation-issued.v1"]
    assert issued, "the invitation event is still published"
    assert token not in str(issued[0].data)


async def test_the_stored_notification_redacts_the_token(client):
    """`NotificationView` exposes `payload` and `rendered_text` over the API,
    so a token in either would simply move the exposure to anyone holding
    `notification.read` — including the inviter."""
    _org, admin = await _tenant_admin(client)
    _body, token = await invite(
        client, admin, email="stored@kilima.example", role_name="tenant-viewer"
    )
    row = await _notification_row(recipient="stored@kilima.example")
    assert row is not None
    assert token not in str(row.payload)
    assert token not in (row.rendered_text or "")
    assert "[redacted]" in (row.rendered_text or ""), row.rendered_text


async def test_the_secret_is_cleared_once_the_message_is_delivered(client):
    """It exists only to survive a retry. Once the message is out, keeping it
    would leave a live credential in the database and in tonight's backup."""
    _org, admin = await _tenant_admin(client)
    await invite(client, admin, email="cleared@kilima.example", role_name="tenant-viewer")
    row = await _notification_row(recipient="cleared@kilima.example")
    assert row.status == "sent"
    assert row.secret_payload is None


async def test_the_notification_api_never_exposes_the_secret_column(client):
    _org, admin = await _tenant_admin(client)
    _body, token = await invite(
        client, admin, email="api@kilima.example", role_name="tenant-viewer"
    )
    r = await client.get("/v1/notifications?limit=50", headers=admin)
    assert r.status_code == 200, r.text
    assert "secret_payload" not in r.text
    assert token not in r.text


async def test_the_token_is_not_logged(client, caplog, capsys):
    """Requirement 10. The SMS provider already masks phone numbers; the same
    standard applies to a credential."""
    _org, admin = await _tenant_admin(client)
    _body, token = await invite(
        client, admin, email="quiet@kilima.example", role_name="tenant-viewer"
    )
    captured = capsys.readouterr()
    assert token not in captured.out
    assert token not in captured.err
    assert token not in caplog.text
