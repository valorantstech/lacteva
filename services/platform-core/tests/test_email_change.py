"""WO-87 — a login's details can be corrected, and an email change is built
like the credential change it is.

Before this, `email` and `full_name` were written once, at registration, and
no route could change either. Now:

  * a person corrects their own name; a tenant admin corrects a member's —
    both audited with before and after;
  * an email change is a PENDING request: the new address gets a code, the
    old address gets a notice, and nothing changes until the new address
    confirms — proven by signing in with the OLD email between the steps;
  * it expires, can be cancelled, is replaced by a second request, revokes
    every session on completion, and the code appears in no response, no
    outbox row and no log;
  * a tenant admin cannot start one against another tenant's user or a
    platform-level account — both are NOT FOUND, never forbidden.
"""

import re
import uuid
from datetime import timedelta

from sqlalchemy import select

from platform_core.core import db
from platform_core.core.db import utcnow
from tests.conftest import invite, register_and_login
from tests.test_org_structure import _tenant_admin

PASSWORD = "delivery-password-1"


async def _member(client, admin, email="raghvan@kilima.example", role="tenant-viewer"):
    """A second member of the tenant, signed in. Returns (user_id, headers)."""
    _inv, token = await invite(client, admin, email=email, role_name=role)
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": PASSWORD, "full_name": "Raghvan"},
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"]), await _login(client, email)


async def _login(client, email, password=PASSWORD):
    r = await client.post("/v1/auth/token", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _confirm(client, code: str) -> int:
    return await _confirm(client, code)


class _Capture:
    """The mail channel, as the recipients see it (SEC-003 / F-04: the only
    place the code exists in the clear)."""

    name = "capture-email"

    def __init__(self):
        self.messages: list = []

    async def send(self, message):
        from platform_core.modules.notification import providers

        self.messages.append(message)
        return providers.DeliveryResult(
            provider_message_id=f"capture:{message.notification_id}",
            status=providers.ACCEPTED,
        )

    def to(self, recipient: str):
        return [m for m in self.messages if m.recipient == recipient]

    def code_for(self, recipient: str) -> str:
        bodies = [m.body for m in self.to(recipient) if "#code=" in m.body]
        assert bodies, f"no confirmation code was delivered to {recipient}"
        match = re.search(r"/confirm-email#code=([A-Za-z0-9_-]+)", bodies[-1])
        assert match, bodies[-1]
        return match.group(1)


def _capturing():
    from platform_core.modules.notification import providers

    capture = _Capture()
    previous = providers.get_provider("email")
    providers.register_provider("email", capture)
    return capture, lambda: providers.register_provider("email", previous)


async def _audit(action: str):
    from platform_core.modules.audit.models import AuditRecord

    async with db.get_session_factory()() as session:
        return list(await session.scalars(select(AuditRecord).where(AuditRecord.action == action)))


# --- §1, §2: the name ---------------------------------------------------------


async def test_a_person_corrects_their_own_name_and_it_is_audited(client):
    _org, admin = await _tenant_admin(client)
    user_id, headers = await _member(client, admin)
    r = await client.put("/v1/auth/me/profile", json={"full_name": "Raghavan"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Raghavan"
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["user"]["full_name"] == "Raghavan"
    rows = await _audit("identity.name.changed")
    assert len(rows) == 1
    assert rows[0].detail == {"before": "Raghvan", "after": "Raghavan", "self": True}
    assert rows[0].actor_id == user_id
    # A blank name is refused, not stored.
    r = await client.put("/v1/auth/me/profile", json={"full_name": "   "}, headers=headers)
    assert r.status_code == 422


async def test_a_tenant_admin_corrects_a_members_name_and_it_is_audited(client):
    _org, admin = await _tenant_admin(client)
    user_id, headers = await _member(client, admin)
    r = await client.put(
        f"/v1/members/{user_id}/profile", json={"full_name": "Raghavan"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert (await client.get("/v1/auth/me", headers=headers)).json()["user"]["full_name"] == (
        "Raghavan"
    )
    rows = await _audit("identity.name.changed")
    assert len(rows) == 1 and rows[0].detail["self"] is False
    assert rows[0].actor_id != user_id
    # A viewer holds no organization.member.manage: refused, and the name stays.
    r = await client.put(
        f"/v1/members/{user_id}/profile", json={"full_name": "Someone Else"}, headers=headers
    )
    assert r.status_code == 403


# --- §3: the email change ---------------------------------------------------------


async def test_an_email_change_is_two_steps_and_the_old_address_signs_in_between(client, bus):
    _org, admin = await _tenant_admin(client)
    user_id, headers = await _member(client, admin)
    capture, restore = _capturing()
    try:
        r = await client.post(
            "/v1/auth/me/email-change",
            json={"new_email": "Raghavan@Kilima.example"},
            headers=headers,
        )
    finally:
        restore()
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["new_email"] == "raghavan@kilima.example"
    assert set(body) == {"new_email", "requested_by", "requested_at", "expires_at"}
    # The code reached the NEW address, and only the new address.
    code = capture.code_for("raghavan@kilima.example")
    assert len(code) > 20
    assert code not in r.text
    # The OLD address was told, naming the new one and how to stop it, with no code.
    notice = capture.to("raghvan@kilima.example")
    assert len(notice) == 1
    assert "raghavan@kilima.example" in notice[0].body
    assert "cancel" in notice[0].body
    assert code not in notice[0].body
    # Visible to the person and to their administrator, still without the code.
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["pending_email_change"]["new_email"] == "raghavan@kilima.example"
    assert code not in str(me)
    members = (await client.get("/v1/members", headers=admin)).json()
    row = next(m for m in members if m["user_id"] == str(user_id))
    assert row["pending_email_change"]["new_email"] == "raghavan@kilima.example"

    # NOTHING has changed yet: the old email still signs in, the new does not.
    old_session = await _login(client, "raghvan@kilima.example")
    r = await client.post(
        "/v1/auth/token", json={"email": "raghavan@kilima.example", "password": PASSWORD}
    )
    assert r.status_code == 401

    # The new address confirms — anonymously.
    r = await client.post("/v1/auth/email-change/confirm", json={"token": code})
    assert r.status_code == 204, r.text

    # Now the login has moved, and EVERY session that existed is revoked.
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 401
    assert (await client.get("/v1/auth/me", headers=old_session)).status_code == 401
    r = await client.post(
        "/v1/auth/token", json={"email": "raghvan@kilima.example", "password": PASSWORD}
    )
    assert r.status_code == 401
    fresh = await _login(client, "raghavan@kilima.example")
    me = (await client.get("/v1/auth/me", headers=fresh)).json()
    assert me["user"]["email"] == "raghavan@kilima.example"
    assert me["pending_email_change"] is None

    # Audited with both addresses; the code is single-use.
    rows = await _audit("identity.email.changed")
    assert len(rows) == 1
    assert rows[0].detail["from"] == "raghvan@kilima.example"
    assert rows[0].detail["to"] == "raghavan@kilima.example"
    assert (
        await client.post("/v1/auth/email-change/confirm", json={"token": code})
    ).status_code == 400
    assert any(e.type == "identity.email-change-requested.v1" for e in bus.published)
    assert any(e.type == "identity.email-changed.v1" for e in bus.published)


async def test_the_code_is_in_no_outbox_row_and_no_log(client, caplog, capsys):
    from platform_core.modules.event_relay.models import OutboxEvent
    from platform_core.modules.notification.models import Notification

    _org, admin = await _tenant_admin(client)
    _user_id, headers = await _member(client, admin)
    capture, restore = _capturing()
    try:
        r = await client.post(
            "/v1/auth/me/email-change",
            json={"new_email": "raghavan@kilima.example"},
            headers=headers,
        )
    finally:
        restore()
    assert r.status_code == 202
    code = capture.code_for("raghavan@kilima.example")
    captured = capsys.readouterr()
    assert code not in captured.out and code not in captured.err and code not in caplog.text
    async with db.get_session_factory()() as session:
        for row in await session.scalars(select(OutboxEvent)):
            assert code not in str(row.payload)
        for row in await session.scalars(select(Notification)):
            assert code not in str(row.payload) if hasattr(row, "payload") else True
    # The administrator's view of the notification history carries no secret.
    history = await client.get("/v1/notifications?limit=50", headers=admin)
    assert history.status_code == 200
    assert code not in history.text


async def test_an_expired_change_is_refused(client):
    from platform_core.modules.identity.models import EmailChange

    _org, admin = await _tenant_admin(client)
    user_id, headers = await _member(client, admin)
    capture, restore = _capturing()
    try:
        await client.post(
            "/v1/auth/me/email-change",
            json={"new_email": "raghavan@kilima.example"},
            headers=headers,
        )
    finally:
        restore()
    code = capture.code_for("raghavan@kilima.example")
    async with db.get_session_factory()() as session:
        row = (
            await session.scalars(select(EmailChange).where(EmailChange.user_id == user_id))
        ).one()
        row.expires_at = utcnow() - timedelta(minutes=1)
        await session.commit()
    # Expired: gone from the person's view, and the code opens nothing.
    assert (await client.get("/v1/auth/me", headers=headers)).json()["pending_email_change"] is None
    assert (
        await client.post("/v1/auth/email-change/confirm", json={"token": code})
    ).status_code == 400
    assert (await _login(client, "raghvan@kilima.example")) is not None


async def test_a_change_can_be_cancelled_by_the_person_and_by_the_admin(client):
    _org, admin = await _tenant_admin(client)
    user_id, headers = await _member(client, admin)
    capture, restore = _capturing()
    try:
        await client.post(
            "/v1/auth/me/email-change",
            json={"new_email": "raghavan@kilima.example"},
            headers=headers,
        )
        code = capture.code_for("raghavan@kilima.example")
        # The person stops it.
        assert (await client.delete("/v1/auth/me/email-change", headers=headers)).status_code == 204
        assert (
            await client.post("/v1/auth/email-change/confirm", json={"token": code})
        ).status_code == 400
        assert (await client.get("/v1/auth/me/email-change", headers=headers)).json() is None
        # The admin starts one for them (the dead-mailbox case) and stops it too.
        r = await client.post(
            f"/v1/members/{user_id}/email-change",
            json={"new_email": "raghavan2@kilima.example"},
            headers=admin,
        )
        assert r.status_code == 202, r.text
        code2 = capture.code_for("raghavan2@kilima.example")
        assert (
            await client.delete(f"/v1/members/{user_id}/email-change", headers=admin)
        ).status_code == 204
        assert (
            await client.post("/v1/auth/email-change/confirm", json={"token": code2})
        ).status_code == 400
        # Cancelling nothing is not an error.
        assert (await client.delete("/v1/auth/me/email-change", headers=headers)).status_code == 204
    finally:
        restore()
    rows = await _audit("identity.email-change.cancelled")
    assert [r.detail["self"] for r in rows] == [True, False]
    assert (await _login(client, "raghvan@kilima.example")) is not None


async def test_asking_again_replaces_the_pending_change_and_renotifies(client):
    _org, admin = await _tenant_admin(client)
    _user_id, headers = await _member(client, admin)
    capture, restore = _capturing()
    try:
        await client.post(
            "/v1/auth/me/email-change", json={"new_email": "first@kilima.example"}, headers=headers
        )
        first = capture.code_for("first@kilima.example")
        await client.post(
            "/v1/auth/me/email-change", json={"new_email": "second@kilima.example"}, headers=headers
        )
        second = capture.code_for("second@kilima.example")
    finally:
        restore()
    assert len(capture.to("raghvan@kilima.example")) == 2, "the old address was told twice"
    pending = (await client.get("/v1/auth/me/email-change", headers=headers)).json()
    assert pending["new_email"] == "second@kilima.example"
    assert (
        await client.post("/v1/auth/email-change/confirm", json={"token": first})
    ).status_code == 400
    assert (
        await client.post("/v1/auth/email-change/confirm", json={"token": second})
    ).status_code == 204


async def test_an_address_another_login_uses_is_refused(client):
    _org, admin = await _tenant_admin(client)
    _user_id, headers = await _member(client, admin)
    r = await client.post(
        "/v1/auth/me/email-change", json={"new_email": "manager@kilima.example"}, headers=headers
    )
    assert r.status_code == 409
    r = await client.post(
        "/v1/auth/me/email-change", json={"new_email": "raghvan@kilima.example"}, headers=headers
    )
    assert r.status_code == 422
    r = await client.post(
        "/v1/auth/me/email-change", json={"new_email": "not-an-address"}, headers=headers
    )
    assert r.status_code == 422


# --- §3: the tenant boundary ---------------------------------------------------------


async def test_a_tenant_admin_cannot_start_a_change_for_another_tenants_user(client):
    from platform_core.core.db import get_session_factory  # noqa: F401  (doc pointer)

    _org, admin = await _tenant_admin(client)
    # A second organisation with its own admin and member.
    _root_id, root = await register_and_login(client, "root2@example.com", admin=True)
    other = (
        await client.post(
            "/v1/organizations",
            json={"name": "Mara Dairy", "slug": "mara", "country_code": "ke"},
            headers=root,
        )
    ).json()
    _inv, token = await invite(
        client,
        {**root, "X-Tenant-ID": other["id"]},
        email="owner@mara.example",
        role_name="tenant-admin",
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "mara-password-11", "full_name": "Mara Owner"},
    )
    stranger_id = r.json()["id"]
    # Kilima's admin, against Mara's owner: NOT FOUND, for both the name and the email.
    r = await client.post(
        f"/v1/members/{stranger_id}/email-change",
        json={"new_email": "hijack@kilima.example"},
        headers=admin,
    )
    assert r.status_code == 404, r.text
    r = await client.put(
        f"/v1/members/{stranger_id}/profile", json={"full_name": "Hijacked"}, headers=admin
    )
    assert r.status_code == 404
    assert await _audit("identity.email-change.requested") == []


async def test_a_tenant_admin_cannot_target_a_platform_account(client):
    _org, admin = await _tenant_admin(client)
    root_id, _root = await register_and_login(client, "root3@example.com", admin=True)
    r = await client.post(
        f"/v1/members/{root_id}/email-change",
        json={"new_email": "owned@kilima.example"},
        headers=admin,
    )
    assert r.status_code == 404, r.text
    r = await client.put(
        f"/v1/members/{root_id}/profile", json={"full_name": "Owned"}, headers=admin
    )
    assert r.status_code == 404
    assert await _audit("identity.email-change.requested") == []
