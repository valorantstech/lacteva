"""The delivery driver, as a person (P0-MOB-001 / P0-MOB-002).

The claim this milestone makes:

    **A driver logs in, sees the runs assigned to their own driver profile for
    the dairy's today, starts the run, records what happened at each stop, and
    closes the round — and can touch nothing else.**

Two properties carry the security story and both are tested to refuse:

* **`logistics.run.execute` is its own key**, held by the DRIVER role and by
  nobody else. The audit found the mobile experience keyed on the sales
  operator's grant, which would have collapsed the personas — so the operator
  roles must NOT hold the driver key, and the driver must not hold theirs.
* **Own-run scoping resolves the driver from the LOGIN, never from the
  client.** Another driver's run — same dairy, valid id — is a 404, exactly as
  another tenant's is, because a probe must not learn the run exists.
"""

import uuid

from tests.conftest import invite
from tests.test_localization import _tenant_admin_for
from tests.test_logistics import _route_env

DRIVER_PASSWORD = "driver-password-1"


# --- environment ---------------------------------------------------------------


async def _driver_login(client, admin, org_id, email, *, full_name="Joseph Mwangi"):
    """A login holding ONLY the DRIVER role, the way a dairy would create one."""
    _inv, token = await invite(
        client,
        {**admin, "X-Tenant-ID": org_id} if "X-Tenant-ID" not in admin else admin,
        email=email,
        role_name="DRIVER",
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": DRIVER_PASSWORD, "full_name": full_name},
    )
    assert r.status_code == 201, r.text
    tokens = (
        await client.post("/v1/auth/token", json={"email": email, "password": DRIVER_PASSWORD})
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    return headers, me["user"]["id"]


async def _driver_env(client, *, linked=True):
    """A dairy with a route, a run assigned to a driver — and the driver's login."""
    admin, route, customers, vehicle, driver = await _route_env(client)
    org_id = (await client.get("/v1/auth/me", headers=admin)).json()["tenant_id"]

    headers, user_id = await _driver_login(client, admin, org_id, "driver@kilima.example")
    if linked:
        r = await client.post(
            f"/v1/drivers/{driver['id']}/user", json={"user_id": user_id}, headers=admin
        )
        assert r.status_code == 200, r.text

    run = await client.post(
        "/v1/delivery-runs",
        json={"route_id": route["id"], "vehicle_id": vehicle["id"], "driver_id": driver["id"]},
        headers=admin,
    )
    assert run.status_code == 201, run.text
    return {
        "admin": admin,
        "org_id": org_id,
        "route": route,
        "customers": customers,
        "vehicle": vehicle,
        "driver": driver,
        "headers": headers,
        "user_id": user_id,
        "run": run.json(),
    }


# --- the driver's own view -------------------------------------------------------


async def test_a_driver_sees_their_own_run_with_ordered_reachable_stops(client):
    env = await _driver_env(client)

    r = await client.get("/v1/delivery-runs/mine", headers=env["headers"])
    assert r.status_code == 200, r.text
    runs = r.json()
    assert len(runs) == 1
    run = runs[0]
    assert run["id"] == env["run"]["id"]
    assert run["driver_name"] == "Joseph Mwangi"
    assert [s["position"] for s in run["stops"]] == [1, 2, 3]
    # A driver at a gate needs to find and reach the household — phone and
    # address ride on the stop, read through the customer module's own batch.
    assert all(s["phone"].startswith("+254") for s in run["stops"])
    assert run["stops"][0]["name"] == "Household 0"


async def test_my_profile_answers_and_an_unlinked_login_is_told_clearly(client):
    env = await _driver_env(client)
    me = await client.get("/v1/drivers/me", headers=env["headers"])
    assert me.status_code == 200, me.text
    assert me.json()["code"] == "DRV-1"

    # A second DRIVER login with no linked profile: the app needs "not set up
    # yet" (404 on /drivers/me) to be distinguishable from "no run today"
    # (200 with an empty list on /mine).
    other, _uid = await _driver_login(
        client, env["admin"], env["org_id"], "unlinked@kilima.example", full_name="New Hire"
    )
    assert (await client.get("/v1/drivers/me", headers=other)).status_code == 404
    r = await client.get("/v1/delivery-runs/mine", headers=other)
    assert r.status_code == 200
    assert r.json() == []


# --- isolation: own runs only ----------------------------------------------------


async def test_a_driver_cannot_see_or_touch_another_drivers_run(client):
    env = await _driver_env(client)

    # A second driver in the SAME dairy, with their own login and run.
    admin = env["admin"]
    second = (
        await client.post(
            "/v1/drivers",
            json={"code": "DRV-2", "full_name": "Peter Otieno"},
            headers=admin,
        )
    ).json()
    other_headers, other_user = await _driver_login(
        client, admin, env["org_id"], "second@kilima.example", full_name="Peter Otieno"
    )
    r = await client.post(
        f"/v1/drivers/{second['id']}/user", json={"user_id": other_user}, headers=admin
    )
    assert r.status_code == 200, r.text

    # Driver 2 sees an empty day — driver 1's run is not theirs.
    assert (await client.get("/v1/delivery-runs/mine", headers=other_headers)).json() == []

    # And driver 1's run id, probed directly by driver 2, is a 404 on every
    # verb — never a 403, because a probe must not learn the run exists.
    run_id = env["run"]["id"]
    customer_id = env["customers"][0]["id"]
    for path, body in (
        (f"/v1/delivery-runs/{run_id}/start", None),
        (f"/v1/delivery-runs/{run_id}/complete", None),
        (
            f"/v1/delivery-runs/{run_id}/stops/{customer_id}/outcome",
            {"status": "delivered"},
        ),
    ):
        r = await client.post(path, json=body, headers=other_headers)
        assert r.status_code == 404, f"{path} -> {r.status_code}: {r.text}"


async def test_another_tenants_driver_run_is_a_404(client):
    env = await _driver_env(client)

    org_b, admin_b = await _tenant_admin_for(
        client, country="KE", slug="driver-iso-b", email="admin@driveriso.example"
    )
    driver_b = (
        await client.post(
            "/v1/drivers", json={"code": "DRV-B", "full_name": "Grace"}, headers=admin_b
        )
    ).json()
    headers_b, user_b = await _driver_login(
        client, admin_b, org_b["id"], "driver@other-dairy.example", full_name="Grace"
    )
    r = await client.post(
        f"/v1/drivers/{driver_b['id']}/user", json={"user_id": user_b}, headers=admin_b
    )
    assert r.status_code == 200, r.text

    r = await client.post(f"/v1/delivery-runs/{env['run']['id']}/start", headers=headers_b)
    assert r.status_code == 404, r.text


# --- persona separation ----------------------------------------------------------


async def test_the_driver_key_is_held_by_no_operator_role(client):
    """The audit's conflation risk, closed at the registry.

    A collection operator must not wander into the driver experience, a sales
    officer must not silently become a driver, and a driver must not inherit
    either operator's surface.
    """
    from platform_core.modules.authz.permissions import ALL_SYSTEM_ROLES

    holders = [name for name, perms in ALL_SYSTEM_ROLES.items() if "logistics.run.execute" in perms]
    assert holders == ["DRIVER"], holders

    driver_grants = set(ALL_SYSTEM_ROLES["DRIVER"])
    assert "sales.delivery.record" not in driver_grants
    assert "collection.transaction.record" not in driver_grants
    assert "logistics.route.manage" not in driver_grants
    assert "logistics.run.manage" not in driver_grants


async def test_an_operator_without_the_key_is_refused_the_driver_surface(client):
    """403 for a real staff login, not merely a registry assertion."""
    env = await _driver_env(client)
    # The tenant ADMIN runs the whole dairy — and still is not a driver.
    r = await client.get("/v1/delivery-runs/mine", headers=env["admin"])
    assert r.status_code == 403, r.text


async def test_a_driver_cannot_use_the_operator_surfaces(client):
    env = await _driver_env(client)
    h = env["headers"]
    assert (await client.get("/v1/routes", headers=h)).status_code == 403
    assert (await client.post("/v1/deliveries", json={}, headers=h)).status_code == 403
    assert (await client.get("/v1/suppliers", headers=h)).status_code == 403
    assert (
        await client.post(
            f"/v1/delivery-runs/{env['run']['id']}/status",
            json={"status": "in_progress"},
            headers=h,
        )
    ).status_code == 403, "the office status endpoint leaked to a driver"


async def test_every_driver_endpoint_refuses_an_anonymous_caller(client):
    rid, cid = uuid.uuid4(), uuid.uuid4()
    for method, path in (
        ("get", "/v1/drivers/me"),
        ("get", "/v1/delivery-runs/mine"),
        ("post", f"/v1/delivery-runs/{rid}/start"),
        ("post", f"/v1/delivery-runs/{rid}/complete"),
        ("post", f"/v1/delivery-runs/{rid}/stops/{cid}/outcome"),
    ):
        r = await client.post(path, json={}) if method == "post" else await client.get(path)
        assert r.status_code == 401, f"{path} -> {r.status_code}"


# --- the day itself --------------------------------------------------------------


async def test_the_driver_walks_the_day_start_outcomes_complete(client):
    env = await _driver_env(client)
    h, run_id = env["headers"], env["run"]["id"]
    customers = env["customers"]

    started = await client.post(f"/v1/delivery-runs/{run_id}/start", headers=h)
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"

    # Delivered with the plan's standing quantity — the driver types nothing
    # and the platform prices it, exactly as the operator round works.
    first = await client.post(
        f"/v1/delivery-runs/{run_id}/stops/{customers[0]['id']}/outcome",
        json={"status": "delivered"},
        headers=h,
    )
    assert first.status_code == 201, first.text
    assert first.json()["delivery_status"] == "delivered"

    skipped = await client.post(
        f"/v1/delivery-runs/{run_id}/stops/{customers[1]['id']}/outcome",
        json={"status": "skipped", "notes": "gate locked"},
        headers=h,
    )
    assert skipped.status_code == 201, skipped.text

    done = await client.post(f"/v1/delivery-runs/{run_id}/complete", headers=h)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"

    # The run view now carries the delivery domain's own answers per stop.
    mine = (await client.get("/v1/delivery-runs/mine", headers=h)).json()
    outcomes = [s["delivery_status"] for s in mine[0]["stops"]]
    assert outcomes == ["delivered", "skipped", None]

    # And the deliveries are ORDINARY deliveries in the book, priced by the
    # platform from the plan — visible to the office exactly as always.
    page = (
        await client.get(
            "/v1/deliveries",
            params={
                "date_from": env["run"]["business_date"],
                "date_to": env["run"]["business_date"],
            },
            headers=env["admin"],
        )
    ).json()
    delivered = [d for d in page["items"] if d["status"] == "delivered"]
    assert len(delivered) == 1
    assert delivered[0]["quantity"] == "2.000", "the plan's standing quantity"


async def test_an_outcome_fills_the_generated_row_rather_than_colliding(client):
    """The round was generated in the office; the driver fills it in."""
    env = await _driver_env(client)
    h, run_id = env["headers"], env["run"]["id"]

    generated = await client.post(f"/v1/delivery-runs/{run_id}/generate", headers=env["admin"])
    assert generated.status_code == 201, generated.text
    assert generated.json()["created"] == 3

    r = await client.post(
        f"/v1/delivery-runs/{run_id}/stops/{env['customers'][0]['id']}/outcome",
        json={"status": "delivered"},
        headers=h,
    )
    assert r.status_code == 201, r.text

    page = (
        await client.get(
            "/v1/deliveries",
            params={
                "date_from": env["run"]["business_date"],
                "date_to": env["run"]["business_date"],
            },
            headers=env["admin"],
        )
    ).json()
    assert page["total"] == 3, "the outcome collided with the generated row"
    statuses = sorted(d["status"] for d in page["items"])
    assert statuses == ["delivered", "scheduled", "scheduled"]


async def test_the_same_outcome_replayed_with_the_same_key_lands_once(client):
    """The offline queue's contract: replay is safe because this router is an
    IdempotentRoute and the queue sends the captured operation id as the key."""
    env = await _driver_env(client)
    h, run_id = env["headers"], env["run"]["id"]
    customer_id = env["customers"][0]["id"]
    key = str(uuid.uuid4())

    first = await client.post(
        f"/v1/delivery-runs/{run_id}/stops/{customer_id}/outcome",
        json={"status": "delivered"},
        headers={**h, "Idempotency-Key": key},
    )
    assert first.status_code == 201, first.text
    replay = await client.post(
        f"/v1/delivery-runs/{run_id}/stops/{customer_id}/outcome",
        json={"status": "delivered"},
        headers={**h, "Idempotency-Key": key},
    )
    assert replay.status_code in (200, 201), replay.text
    assert replay.json() == first.json()

    page = (
        await client.get(
            "/v1/deliveries",
            params={
                "date_from": env["run"]["business_date"],
                "date_to": env["run"]["business_date"],
            },
            headers=env["admin"],
        )
    ).json()
    assert page["total"] == 1, "the replay recorded a second delivery"


# --- guards ---------------------------------------------------------------------


async def test_an_outcome_for_a_customer_not_on_the_route_is_refused(client):
    from tests.test_logistics import _customer

    env = await _driver_env(client)
    off_route = await _customer(client, env["admin"], "Not on round", "+254700999777")

    r = await client.post(
        f"/v1/delivery-runs/{env['run']['id']}/stops/{off_route['id']}/outcome",
        json={"status": "delivered"},
        headers=env["headers"],
    )
    assert r.status_code == 404, r.text


async def test_a_closed_run_records_no_more_outcomes(client):
    env = await _driver_env(client)
    h, run_id = env["headers"], env["run"]["id"]
    await client.post(f"/v1/delivery-runs/{run_id}/start", headers=h)
    await client.post(f"/v1/delivery-runs/{run_id}/complete", headers=h)

    r = await client.post(
        f"/v1/delivery-runs/{run_id}/stops/{env['customers'][0]['id']}/outcome",
        json={"status": "delivered"},
        headers=h,
    )
    assert r.status_code == 409, r.text


async def test_cancelled_is_not_a_doorstep_outcome(client):
    """ "Recorded in error" is an office correction, not something a driver
    declares at a gate."""
    env = await _driver_env(client)
    r = await client.post(
        f"/v1/delivery-runs/{env['run']['id']}/stops/{env['customers'][0]['id']}/outcome",
        json={"status": "cancelled"},
        headers=env["headers"],
    )
    assert r.status_code == 422, r.text


async def test_the_start_guard_still_requires_a_vehicle(client):
    """BR-0028 holds through the driver path — composition, not a bypass."""
    env = await _driver_env(client)
    run = await client.post(
        "/v1/delivery-runs",
        json={
            "route_id": env["route"]["id"],
            "slot": "evening",
            "driver_id": env["driver"]["id"],
        },
        headers=env["admin"],
    )
    assert run.status_code == 201, run.text

    r = await client.post(f"/v1/delivery-runs/{run.json()['id']}/start", headers=env["headers"])
    assert r.status_code == 409, r.text
    assert "vehicle" in r.text


async def test_completing_before_starting_is_refused(client):
    env = await _driver_env(client)
    r = await client.post(f"/v1/delivery-runs/{env['run']['id']}/complete", headers=env["headers"])
    assert r.status_code == 409, r.text


# --- linkage --------------------------------------------------------------------


async def test_one_login_drives_at_most_one_driver(client):
    env = await _driver_env(client)
    second = (
        await client.post(
            "/v1/drivers", json={"code": "DRV-9", "full_name": "Duplicate"}, headers=env["admin"]
        )
    ).json()

    r = await client.post(
        f"/v1/drivers/{second['id']}/user",
        json={"user_id": env["user_id"]},
        headers=env["admin"],
    )
    assert r.status_code == 409, r.text
    assert "DRV-1" in r.text, "the refusal names the driver the login already is"


async def test_unlinking_takes_the_runs_away_but_keeps_the_record(client):
    env = await _driver_env(client)
    r = await client.post(
        f"/v1/drivers/{env['driver']['id']}/user", json={"user_id": None}, headers=env["admin"]
    )
    assert r.status_code == 200, r.text

    assert (await client.get("/v1/drivers/me", headers=env["headers"])).status_code == 404
    assert (await client.get("/v1/delivery-runs/mine", headers=env["headers"])).json() == []
    # The driver RECORD survives — a person who left is history, not a deletion.
    drivers = (await client.get("/v1/drivers", headers=env["admin"])).json()
    assert any(d["code"] == "DRV-1" for d in drivers)


async def test_linking_needs_the_fleet_grant_not_the_driver_one(client):
    env = await _driver_env(client)
    r = await client.post(
        f"/v1/drivers/{env['driver']['id']}/user",
        json={"user_id": env["user_id"]},
        headers=env["headers"],
    )
    assert r.status_code == 403, r.text


async def test_the_link_is_audited_without_leaking_the_phone(client):
    env = await _driver_env(client)
    entries = (await client.get("/v1/audit?limit=100", headers=env["admin"])).json()
    linked = [e for e in entries["items"] if e["action"] == "logistics.driver_user_linked"]
    assert linked, "the link left no audit trail"
    assert "+254" not in str(linked[0]["detail"])


async def test_a_retired_driver_login_loses_the_runs_but_not_the_history(client):
    """`driver_for_user` counts only ACTIVE profiles.

    Found by a surviving mutation: nothing retired a driver and asserted the
    phone went dark. A dairy that marks a departed driver inactive must not
    leave their old login able to see — or start — a round.
    """
    from platform_core.core import db

    env = await _driver_env(client)
    async with db.get_session_factory()() as session:
        from platform_core.modules.logistics.models import Driver

        row = await session.get(Driver, __import__("uuid").UUID(env["driver"]["id"]))
        row.active = False
        await session.commit()

    assert (await client.get("/v1/drivers/me", headers=env["headers"])).status_code == 404
    assert (await client.get("/v1/delivery-runs/mine", headers=env["headers"])).json() == []
    r = await client.post(f"/v1/delivery-runs/{env['run']['id']}/start", headers=env["headers"])
    assert r.status_code == 404, r.text
