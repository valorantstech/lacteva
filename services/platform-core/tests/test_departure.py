"""WO-88 — somebody leaves, and the round still belongs to them.

The revocation half already worked (suspension is immediate, deactivation
revokes sessions, history keeps the person's name). This pins the hand-over
half that did not exist:

  1. a driver (and a vehicle) can be RETIRED — the refusal `_assert_assignable`
     has carried since DEMO-034 finally has a way to be reached; past runs are
     untouched;
  2. the last administrator cannot be suspended, deactivated or stripped of
     the role — with the remedy in the message — and can be the moment a
     second admin exists;
  3. a pending staff invitation can be listed and withdrawn;
  4. a reinstated member is the same user, not a new one.
"""

import uuid

from tests.conftest import invite
from tests.test_access_revocation import _member
from tests.test_logistics import _route_env, _run
from tests.test_org_structure import _tenant_admin

LAST_ADMIN = "only administrator"


# --- 1. retiring ---------------------------------------------------------------


async def test_a_retired_driver_is_refused_by_assert_assignable(client):
    """The test that could not have passed before: nothing could set
    `Driver.active` false, so the refusal was unreachable."""
    admin, route, _customers, vehicle, driver = await _route_env(client)
    r = await client.post(
        f"/v1/drivers/{driver['id']}/status", json={"active": False}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    # A run for tomorrow, with him: refused, not silently planned.
    r = await _run(client, admin, route, vehicle, driver)
    assert r.status_code == 409, r.text
    assert "driver is not active" in r.text
    # Naming him as a route's default is refused the same way.
    r = await client.patch(
        f"/v1/routes/{route['id']}", json={"default_driver_id": driver["id"]}, headers=admin
    )
    assert r.status_code == 409, r.text
    # He is out of the active list, and brought back the same way.
    active = (await client.get("/v1/drivers?active=true", headers=admin)).json()
    assert all(d["id"] != driver["id"] for d in active)
    r = await client.post(
        f"/v1/drivers/{driver['id']}/status", json={"active": True}, headers=admin
    )
    assert r.json()["active"] is True
    assert (await _run(client, admin, route, vehicle, driver)).status_code == 201


async def test_retiring_a_driver_leaves_his_past_runs_untouched(client):
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()
    assert run["driver_name"] == "Joseph Mwangi"
    r = await client.post(
        f"/v1/drivers/{driver['id']}/status", json={"active": False}, headers=admin
    )
    assert r.status_code == 200
    # The run still names him; retiring is not reattribution.
    after = (await client.get(f"/v1/delivery-runs/{run['id']}", headers=admin)).json()
    assert after["driver_id"] == driver["id"]
    assert after["driver_name"] == "Joseph Mwangi"
    # Retiring twice is not an error (an end state, not a verb).
    r = await client.post(
        f"/v1/drivers/{driver['id']}/status", json={"active": False}, headers=admin
    )
    assert r.status_code == 200


async def test_the_routes_that_would_still_be_planned_for_him_are_listed(client):
    admin, route, _customers, vehicle, driver = await _route_env(client)
    r = await client.patch(
        f"/v1/routes/{route['id']}",
        json={
            "default_driver_id": driver["id"],
            "default_vehicle_id": vehicle["id"],
            "auto_plan": True,
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    listed = (await client.get(f"/v1/drivers/{driver['id']}/default-routes", headers=admin)).json()
    assert [x["id"] for x in listed] == [route["id"]]
    assert listed[0]["auto_plan"] is True
    # Hand the route over (clear the default) and the list is empty.
    r = await client.patch(
        f"/v1/routes/{route['id']}", json={"clear_default_driver": True}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert (
        await client.get(f"/v1/drivers/{driver['id']}/default-routes", headers=admin)
    ).json() == []


async def test_a_vehicle_is_retired_the_same_way(client):
    admin, route, _customers, vehicle, driver = await _route_env(client)
    r = await client.post(
        f"/v1/vehicles/{vehicle['id']}/status", json={"active": False}, headers=admin
    )
    assert r.status_code == 200 and r.json()["active"] is False
    r = await _run(client, admin, route, vehicle, driver)
    assert r.status_code == 409 and "vehicle is not active" in r.text


async def test_retiring_needs_its_own_grant(client):
    admin, _route, _customers, vehicle, driver = await _route_env(client)
    org = (await client.get("/v1/auth/me", headers=admin)).json()
    _uid, viewer, _refresh = await _member(
        client,
        admin,
        email="viewer@kilima.example",
        role="tenant-viewer",
        tenant_id=org["tenant_id"],
    )
    r = await client.post(
        f"/v1/drivers/{driver['id']}/status", json={"active": False}, headers=viewer
    )
    assert r.status_code == 403
    r = await client.post(
        f"/v1/vehicles/{vehicle['id']}/status", json={"active": False}, headers=viewer
    )
    assert r.status_code == 403
    assert (await client.get("/v1/drivers?active=true", headers=admin)).json()[0]["active"] is True


# --- 2. the last administrator --------------------------------------------------------


async def _admin_user_id(client, admin) -> str:
    return (await client.get("/v1/auth/me", headers=admin)).json()["user"]["id"]


async def test_the_only_administrator_cannot_be_suspended_deactivated_or_demoted(client):
    _org, admin = await _tenant_admin(client)
    me = await _admin_user_id(client, admin)
    r = await client.post(f"/v1/members/{me}/status", json={"status": "suspended"}, headers=admin)
    assert r.status_code == 409, r.text
    assert LAST_ADMIN in r.text and "invite another administrator first" in r.text
    r = await client.post(
        f"/v1/identity/users/{me}/status", json={"is_active": False}, headers=admin
    )
    assert r.status_code == 409, r.text
    assert LAST_ADMIN in r.text
    r = await client.delete(
        "/v1/authz/assignments",
        params={"user_id": me, "role_name": "tenant-admin"},
        headers=admin,
    )
    assert r.status_code == 409, r.text
    assert LAST_ADMIN in r.text
    # Nothing was written: still an active admin who can still act.
    assert (await client.get("/v1/members", headers=admin)).status_code == 200
    row = next(
        m for m in (await client.get("/v1/members", headers=admin)).json() if m["user_id"] == me
    )
    assert row["status"] == "active"


async def test_with_a_second_administrator_the_first_may_leave(client):
    _org, admin = await _tenant_admin(client)
    me = await _admin_user_id(client, admin)
    org = (await client.get("/v1/auth/me", headers=admin)).json()
    second_id, second, _refresh = await _member(
        client,
        admin,
        email="second@kilima.example",
        role="tenant-admin",
        tenant_id=org["tenant_id"],
    )
    # Now the first admin can be suspended by the second …
    r = await client.post(f"/v1/members/{me}/status", json={"status": "suspended"}, headers=second)
    assert r.status_code == 200, r.text
    # … and the second, now the only one, is protected in turn.
    r = await client.post(
        f"/v1/members/{second_id}/status", json={"status": "suspended"}, headers=second
    )
    assert r.status_code == 409 and LAST_ADMIN in r.text
    # Reinstating the first brings the count back to two.
    r = await client.post(f"/v1/members/{me}/status", json={"status": "active"}, headers=second)
    assert r.status_code == 200
    r = await client.post(
        f"/v1/members/{second_id}/status", json={"status": "suspended"}, headers=second
    )
    assert r.status_code == 200


async def test_a_suspended_second_admin_does_not_count(client):
    """Counted as ACTIVE users with an ACTIVE membership, not as role holders."""
    _org, admin = await _tenant_admin(client)
    me = await _admin_user_id(client, admin)
    org = (await client.get("/v1/auth/me", headers=admin)).json()
    second_id, _second, _refresh = await _member(
        client,
        admin,
        email="second@kilima.example",
        role="tenant-admin",
        tenant_id=org["tenant_id"],
    )
    r = await client.post(
        f"/v1/members/{second_id}/status", json={"status": "suspended"}, headers=admin
    )
    assert r.status_code == 200
    r = await client.post(
        f"/v1/identity/users/{me}/status", json={"is_active": False}, headers=admin
    )
    assert r.status_code == 409 and LAST_ADMIN in r.text


# --- 3. pending invitations ------------------------------------------------------------


async def test_a_pending_staff_invitation_is_listed_and_withdrawn(client):
    _org, admin = await _tenant_admin(client)
    body, token = await invite(client, admin, email="late@kilima.example", role_name="DRIVER")
    listed = (await client.get("/v1/invitations?email=late@kilima.example", headers=admin)).json()
    assert [row["id"] for row in listed] == [body["id"]]
    assert "token" not in str(listed) and token not in str(listed)
    r = await client.delete(f"/v1/invitations/{body['id']}", headers=admin)
    assert r.status_code == 204, r.text
    assert (
        await client.get("/v1/invitations?email=late@kilima.example", headers=admin)
    ).json() == []
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "late-password-11", "full_name": "Too Late"},
    )
    assert r.status_code == 400
    assert (
        await client.delete(f"/v1/invitations/{uuid.uuid4()}", headers=admin)
    ).status_code == 404


# --- 4. re-joining -------------------------------------------------------------------------


async def test_a_reinstated_member_is_the_same_user(client):
    _org, admin = await _tenant_admin(client)
    org = (await client.get("/v1/auth/me", headers=admin)).json()
    user_id, headers, _refresh = await _member(
        client, admin, email="back@kilima.example", role="DRIVER", tenant_id=org["tenant_id"]
    )
    r = await client.post(
        f"/v1/members/{user_id}/status", json={"status": "suspended"}, headers=admin
    )
    assert r.status_code == 200
    # Immediate: the very next request with the session they hold is refused.
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 401
    r = await client.post(f"/v1/members/{user_id}/status", json={"status": "active"}, headers=admin)
    assert r.status_code == 200
    pair = await client.post(
        "/v1/auth/token",
        json={
            "email": "back@kilima.example",
            "password": "member-password-1",
            "tenant_id": org["tenant_id"],
        },
    )
    assert pair.status_code == 200, pair.text
    me = (
        await client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {pair.json()['access_token']}"}
        )
    ).json()
    assert me["user"]["id"] == user_id, "re-joining split one person into two logins"
    # Inviting the same address again is refused: the account exists.
    r = await client.post(
        "/v1/invitations",
        json={"email": "back@kilima.example", "role_name": "DRIVER"},
        headers=admin,
    )
    assert r.status_code in (400, 409), r.text
