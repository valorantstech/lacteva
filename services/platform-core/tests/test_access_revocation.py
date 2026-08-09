"""SEC-003 / F-02 — access must be revocable, not only grantable.

FINAL-001 found `User.is_active` enforced in five places and settable in none,
and `assign_role` with no inverse anywhere in the platform. An employee who
left kept working credentials; a permission granted by mistake was permanent.
Logout was the only lever, and it ends the session the user is holding — they
log in again.

Two mechanisms, tested separately and then together:

  * deactivation — the flag, plus the session revocation that stops the
    refresh path minting fresh access tokens from a session nobody re-checked;
  * role revocation — deleting the assignment, which the permission engine
    resolves from on every request.
"""

import uuid

import pytest

from tests.conftest import invite, register_and_login
from tests.test_org_structure import _tenant_admin


async def _member(client, admin_headers, *, email: str, role: str, tenant_id: str):
    """A real second user in the admin's tenant, via the real invitation flow."""
    _inv, token = await invite(client, admin_headers, email=email, role_name=role)
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "member-password-1", "full_name": "A Member"},
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    pair = await client.post(
        "/v1/auth/token",
        json={"email": email, "password": "member-password-1", "tenant_id": tenant_id},
    )
    assert pair.status_code == 200, pair.text
    body = pair.json()
    return user_id, {"Authorization": f"Bearer {body['access_token']}"}, body["refresh_token"]


# --- deactivation -----------------------------------------------------------


async def test_an_active_user_can_authenticate(client):
    org, admin = await _tenant_admin(client)
    _user_id, headers, _refresh = await _member(
        client, admin, email="active@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    me = await client.get("/v1/auth/me", headers=headers)
    assert me.status_code == 200


async def test_a_deactivated_user_cannot_authenticate(client):
    org, admin = await _tenant_admin(client)
    user_id, _headers, _refresh = await _member(
        client, admin, email="leaver@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )

    r = await client.post(
        f"/v1/identity/users/{user_id}/status",
        json={"is_active": False, "reason": "left the cooperative"},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False

    again = await client.post(
        "/v1/auth/token",
        json={
            "email": "leaver@kilima.example",
            "password": "member-password-1",
            "tenant_id": org["id"],
        },
    )
    assert again.status_code == 401, "a deactivated user logged back in"


async def test_the_live_access_token_of_a_deactivated_user_stops_working(client):
    """The token was minted while the account was good. It must die at its
    next use, not at its expiry — 15 minutes of valid access after an
    offboarding is 15 minutes too many."""
    org, admin = await _tenant_admin(client)
    user_id, headers, _refresh = await _member(
        client, admin, email="live@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 200

    await client.post(
        f"/v1/identity/users/{user_id}/status", json={"is_active": False}, headers=admin
    )

    after = await client.get("/v1/auth/me", headers=headers)
    assert after.status_code == 401, "a revoked user's access token still worked"


async def test_the_refresh_token_of_a_deactivated_user_stops_working(client):
    """The half that the `is_active` check alone does NOT cover.

    `get_current_principal` re-reads `is_active`, so the access token dies by
    itself. The refresh endpoint is a different path — it takes an opaque
    secret and mints a new pair. Without revoking the session, an offboarded
    user holding a refresh token keeps rolling it forward.
    """
    org, admin = await _tenant_admin(client)
    user_id, _headers, refresh = await _member(
        client, admin, email="refresher@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )

    await client.post(
        f"/v1/identity/users/{user_id}/status", json={"is_active": False}, headers=admin
    )

    r = await client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401, "a deactivated user refreshed their session"


async def test_a_user_can_be_reactivated(client):
    org, admin = await _tenant_admin(client)
    user_id, _headers, _refresh = await _member(
        client, admin, email="returner@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    await client.post(
        f"/v1/identity/users/{user_id}/status", json={"is_active": False}, headers=admin
    )

    r = await client.post(
        f"/v1/identity/users/{user_id}/status", json={"is_active": True}, headers=admin
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is True

    pair = await client.post(
        "/v1/auth/token",
        json={
            "email": "returner@kilima.example",
            "password": "member-password-1",
            "tenant_id": org["id"],
        },
    )
    assert pair.status_code == 200, "a reactivated user could not log back in"


async def test_reactivation_does_not_resurrect_the_old_sessions(client):
    """They were revoked. Handing one back would make the revoke reason a lie
    and would restore a refresh token that may have been captured in the
    meantime — the user logs in again instead."""
    org, admin = await _tenant_admin(client)
    user_id, _headers, refresh = await _member(
        client, admin, email="resurrect@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    await client.post(
        f"/v1/identity/users/{user_id}/status", json={"is_active": False}, headers=admin
    )
    await client.post(
        f"/v1/identity/users/{user_id}/status", json={"is_active": True}, headers=admin
    )

    r = await client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


async def test_deactivating_twice_is_not_an_error(client):
    """The request names an end state. An administrator who clicks twice, or
    a retried request, has not made a mistake."""
    org, admin = await _tenant_admin(client)
    user_id, _h, _r = await _member(
        client, admin, email="twice@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    for _ in range(2):
        r = await client.post(
            f"/v1/identity/users/{user_id}/status", json={"is_active": False}, headers=admin
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is False


# --- role revocation --------------------------------------------------------


async def test_a_role_can_be_granted_and_the_permission_works(client):
    org, admin = await _tenant_admin(client)
    user_id, headers, _r = await _member(
        client, admin, email="grantee@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )

    denied = await client.post(
        "/v1/collection-centers",
        json={"name": "Nyeri", "code": "NYR", "branch_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert denied.status_code == 403

    r = await client.post(
        "/v1/authz/assignments",
        json={"user_id": user_id, "role_name": "tenant-admin"},
        headers=admin,
    )
    assert r.status_code == 201, r.text

    me = await client.get("/v1/auth/me", headers=headers)
    assert "organization.structure.manage" in me.json()["permissions"]


async def test_a_revoked_role_stops_granting_its_permissions(client):
    """The assertion F-02 exists for: after the revoke, the permission the
    role carried is gone from the very next authorization decision."""
    org, admin = await _tenant_admin(client)
    user_id, headers, _r = await _member(
        client, admin, email="revokee@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    await client.post(
        "/v1/authz/assignments",
        json={"user_id": user_id, "role_name": "tenant-admin"},
        headers=admin,
    )
    before = await client.get("/v1/auth/me", headers=headers)
    assert "organization.structure.manage" in before.json()["permissions"]

    r = await client.delete(
        f"/v1/authz/assignments?user_id={user_id}&role_name=tenant-admin", headers=admin
    )
    assert r.status_code == 204, r.text

    after = await client.get("/v1/auth/me", headers=headers)
    assert "organization.structure.manage" not in after.json()["permissions"], (
        "the revoked role still grants its permissions"
    )


async def test_a_revoked_role_actually_refuses_the_action(client):
    """Not just absent from the permission list — refused at the endpoint."""
    org, admin = await _tenant_admin(client)
    user_id, headers, _r = await _member(
        client, admin, email="doer@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    await client.post(
        "/v1/authz/assignments",
        json={"user_id": user_id, "role_name": "tenant-admin"},
        headers=admin,
    )
    ws = await client.post("/v1/workspaces", json={"name": "Ops", "slug": "ops"}, headers=headers)
    assert ws.status_code == 201, ws.text

    await client.delete(
        f"/v1/authz/assignments?user_id={user_id}&role_name=tenant-admin", headers=admin
    )

    denied = await client.post(
        "/v1/workspaces", json={"name": "Ops 2", "slug": "ops-2"}, headers=headers
    )
    assert denied.status_code == 403


async def test_revoking_a_role_the_user_never_had_is_not_an_error(client):
    org, admin = await _tenant_admin(client)
    user_id, _h, _r = await _member(
        client, admin, email="never@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    r = await client.delete(
        f"/v1/authz/assignments?user_id={user_id}&role_name=tenant-admin", headers=admin
    )
    assert r.status_code == 204


async def test_revoking_an_unknown_role_is_a_404(client):
    _org, admin = await _tenant_admin(client)
    r = await client.delete(
        f"/v1/authz/assignments?user_id={uuid.uuid4()}&role_name=does-not-exist", headers=admin
    )
    assert r.status_code == 404


# --- tenant isolation and authorization -------------------------------------


async def test_one_tenant_cannot_deactivate_another_tenants_user(client):
    """The isolation assertion. A 404, never a 403 — telling the caller the
    account exists somewhere else is itself a disclosure."""
    org_a, admin_a = await _tenant_admin(client)
    victim_id, _h, _r = await _member(
        client, admin_a, email="victim@kilima.example", role="tenant-viewer", tenant_id=org_a["id"]
    )

    _uid, platform_admin = await register_and_login(client, "root2@example.com", admin=True)
    org_b = (
        await client.post(
            "/v1/organizations",
            json={"name": "Rival Dairy", "slug": "rival", "country_code": "ke"},
            headers=platform_admin,
        )
    ).json()
    _inv, token = await invite(
        client,
        {**platform_admin, "X-Tenant-ID": org_b["id"]},
        email="boss@rival.example",
        role_name="tenant-admin",
    )
    await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "rival-password-1", "full_name": "Rival Boss"},
    )
    rival = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "boss@rival.example",
                "password": "rival-password-1",
                "tenant_id": org_b["id"],
            },
        )
    ).json()
    rival_headers = {"Authorization": f"Bearer {rival['access_token']}"}

    r = await client.post(
        f"/v1/identity/users/{victim_id}/status", json={"is_active": False}, headers=rival_headers
    )
    assert r.status_code == 404, r.text

    # And the victim is untouched.
    still = await client.post(
        "/v1/auth/token",
        json={
            "email": "victim@kilima.example",
            "password": "member-password-1",
            "tenant_id": org_a["id"],
        },
    )
    assert still.status_code == 200


async def test_deactivation_requires_the_manage_permission(client):
    org, admin = await _tenant_admin(client)
    user_id, viewer_headers, _r = await _member(
        client, admin, email="nosy@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    r = await client.post(
        f"/v1/identity/users/{user_id}/status", json={"is_active": False}, headers=viewer_headers
    )
    assert r.status_code == 403


async def test_role_revocation_requires_the_manage_permission(client):
    org, admin = await _tenant_admin(client)
    user_id, viewer_headers, _r = await _member(
        client, admin, email="climber@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    r = await client.delete(
        f"/v1/authz/assignments?user_id={user_id}&role_name=tenant-viewer",
        headers=viewer_headers,
    )
    assert r.status_code == 403


# --- audit ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("active", "expected"),
    [(False, "identity.user.deactivated"), (True, "identity.user.reactivated")],
)
async def test_deactivation_and_reactivation_are_audited(client, active, expected):
    org, admin = await _tenant_admin(client)
    user_id, _h, _r = await _member(
        client,
        admin,
        email=f"audited-{int(active)}@kilima.example",
        role="tenant-viewer",
        tenant_id=org["id"],
    )
    if active:  # reactivation needs something to reactivate
        await client.post(
            f"/v1/identity/users/{user_id}/status", json={"is_active": False}, headers=admin
        )
    await client.post(
        f"/v1/identity/users/{user_id}/status", json={"is_active": active}, headers=admin
    )

    entries = (await client.get("/v1/audit?limit=100", headers=admin)).json()
    actions = [e["action"] for e in (entries["items"] if isinstance(entries, dict) else entries)]
    assert expected in actions, actions


async def test_granting_and_revoking_a_role_are_both_audited(client):
    """An access review reads exactly these two entries. A grant that is
    recorded and a revocation that is not would make the trail read as though
    the permission is still held."""
    org, admin = await _tenant_admin(client)
    user_id, _h, _r = await _member(
        client, admin, email="trail@kilima.example", role="tenant-viewer", tenant_id=org["id"]
    )
    await client.post(
        "/v1/authz/assignments",
        json={"user_id": user_id, "role_name": "tenant-admin"},
        headers=admin,
    )
    await client.delete(
        f"/v1/authz/assignments?user_id={user_id}&role_name=tenant-admin", headers=admin
    )

    entries = (await client.get("/v1/audit?limit=100", headers=admin)).json()
    actions = [e["action"] for e in (entries["items"] if isinstance(entries, dict) else entries)]
    assert "authz.role.granted" in actions, actions
    assert "authz.role.revoked" in actions, actions
