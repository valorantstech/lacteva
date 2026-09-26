"""The owner can give his delivery boy a round (WO-108 · LACTEVA-LOGISTICS-003).

The portal created routes, vehicles and drivers but nothing linked a driver
profile to a login, so a delivery boy invited as a Driver signed in to the
app and was told "You are not set up as a driver". The whole chain, on the
platform, as one proof:

invite a delivery boy → he accepts → he is a LINKED driver → a round with two
customers, him as default driver, "every morning" on → the scheduler creates
tomorrow's run assigned to him → his own runs show it → and because a shop's
delivery boy walks, the run starts without a vehicle.
"""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from platform_core.modules.delivery.scheduler import Tenant, run_for_tenant
from platform_core.modules.logistics.service import plan_auto_routes_for_scheduler
from tests.conftest import invite
from tests.test_wo107_first_customer import _fresh_shop

HOUR = 0  # the generation hour, local — as test_wo82_round.py runs it


async def _delivery_boy(client, owner, org_id, *, email, full_name):
    """Staff → Invite → role Delivery boy (DRIVER), accepted, signed in."""
    _inv, token = await invite(client, owner, email=email, role_name="DRIVER")
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "delivery-password-1", "full_name": full_name},
    )
    assert r.status_code == 201, r.text
    pair = (
        await client.post(
            "/v1/auth/token",
            json={"email": email, "password": "delivery-password-1", "tenant_id": org_id},
        )
    ).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}


async def _customer(client, owner, name):
    r = await client.post(
        "/v1/customers",
        json={
            "name": name,
            "plan": {"product": "COW-MILK", "default_quantity": "1", "unit_price": "50"},
        },
        headers=owner,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_the_whole_chain_from_invitation_to_his_own_run(client):
    org, owner = await _fresh_shop(client, slug="patel-rounds")

    # 1. Staff → Invite → Delivery boy. On acceptance he IS a linked driver:
    #    a profile from his name, code spelled by the platform, his login on it.
    boy = await _delivery_boy(
        client, owner, org["id"], email="ramesh@patel.example", full_name="Ramesh Pawar"
    )
    drivers = (await client.get("/v1/drivers", headers=owner)).json()
    assert len(drivers) == 1, drivers
    ramesh = drivers[0]
    assert ramesh["full_name"] == "Ramesh Pawar" and ramesh["code"] == "RAMESH-PAWAR"
    assert ramesh["user_id"] is not None, "linked to his login — no driver screen needed"
    me = await client.get("/v1/drivers/me", headers=boy)
    assert me.status_code == 200 and me.json()["id"] == ramesh["id"]

    # 2. Delivery rounds: a round by NAME (code generated), on foot, two
    #    customers in delivery order, him as default delivery boy, every morning.
    flat = await _customer(client, owner, "Flat C-1603")
    temple = await _customer(client, owner, "Shri Ganesh Mandir")
    r = await client.post(
        "/v1/routes", json={"name": "Morning round", "transport": "on foot"}, headers=owner
    )
    assert r.status_code == 201, r.text
    route = r.json()
    assert route["code"] == "MORNING-ROUND" and route["transport"] == "on_foot"
    r = await client.put(
        f"/v1/routes/{route['id']}/stops",
        json={"customer_ids": [temple["id"], flat["id"]]},
        headers=owner,
    )
    assert r.status_code == 200, r.text
    assert [s["customer_id"] for s in r.json()["stops"]] == [temple["id"], flat["id"]]
    r = await client.patch(
        f"/v1/routes/{route['id']}",
        json={"default_driver_id": ramesh["id"], "auto_plan": True},
        headers=owner,
    )
    assert r.status_code == 200, r.text
    assert r.json()["default_driver_id"] == ramesh["id"] and r.json()["auto_plan"] is True

    # 3. The scheduler creates the day's run at its generation hour, assigned
    #    to him — no vehicle, because the round goes out on foot. It runs at
    #    00:30 on the business day itself, so "tomorrow's run" is the run of
    #    the day the delivery boy looks at his phone; here that day is the
    #    shop's today, which is what his own list shows.
    me_org = (await client.get("/v1/auth/me", headers=owner)).json()
    zone = ZoneInfo(me_org["organization"]["timezone"])
    tomorrow = datetime.now(zone).date()
    at = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 31, tzinfo=zone).astimezone(UTC)
    tenant = Tenant(
        id=uuid.UUID(org["id"]), slug="patel-rounds", timezone=me_org["organization"]["timezone"]
    )
    generation = await run_for_tenant(
        tenant,
        now=at,
        generation_hour=HOUR,
        force_date=tomorrow,
        route_planner=plan_auto_routes_for_scheduler,
    )
    assert generation is not None and generation.status == "success", generation

    # 4. His own runs show it: two stops, in order, him as the driver.
    mine = (await client.get("/v1/delivery-runs/mine", headers=boy)).json()
    assert len(mine) == 1, mine
    run = mine[0]
    assert run["route_id"] == route["id"] and run["business_date"] == str(tomorrow)
    assert run["driver_id"] == ramesh["id"] and run["vehicle_id"] is None
    assert run["transport"] == "on_foot"
    assert [s["customer_id"] for s in run["stops"]] == [temple["id"], flat["id"]]
    assert all(s["delivery_status"] == "scheduled" for s in run["stops"])

    # 5. And he can start it without a vehicle — the round goes out on foot.
    r = await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": "in_progress"}, headers=owner
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"


async def test_a_round_by_vehicle_still_needs_one_and_says_how_to_change_that(client):
    """BR-0028 is unchanged for a round that goes out by vehicle — the default,
    and every round that existed before this work order."""
    org, owner = await _fresh_shop(client, slug="patel-van")
    boy = await _delivery_boy(
        client, owner, org["id"], email="van@patel.example", full_name="Suresh"
    )
    driver = (await client.get("/v1/drivers/me", headers=boy)).json()
    flat = await _customer(client, owner, "Flat A-1")
    route = (await client.post("/v1/routes", json={"name": "Van round"}, headers=owner)).json()
    assert route["transport"] == "vehicle"
    await client.put(
        f"/v1/routes/{route['id']}/stops", json={"customer_ids": [flat["id"]]}, headers=owner
    )
    run = (
        await client.post(
            "/v1/delivery-runs",
            json={"route_id": route["id"], "driver_id": driver["id"]},
            headers=owner,
        )
    ).json()
    r = await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": "in_progress"}, headers=owner
    )
    assert r.status_code == 409, r.text
    assert "driver and a vehicle" in r.text and "on foot or by bicycle" in r.text
    # Mark the round as going out by bicycle and the same run starts.
    r = await client.patch(
        f"/v1/routes/{route['id']}", json={"transport": "bicycle"}, headers=owner
    )
    assert r.status_code == 200 and r.json()["transport"] == "bicycle"
    r = await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": "in_progress"}, headers=owner
    )
    assert r.status_code == 200, r.text
    # A driver is never optional.
    unassigned = (
        await client.post(
            "/v1/delivery-runs", json={"route_id": route["id"], "slot": "evening"}, headers=owner
        )
    ).json()
    r = await client.post(
        f"/v1/delivery-runs/{unassigned['id']}/status",
        json={"status": "in_progress"},
        headers=owner,
    )
    assert r.status_code == 409 and "needs a driver" in r.text
    # And only the three ways of going out exist.
    r = await client.post(
        "/v1/routes", json={"name": "Odd", "transport": "helicopter"}, headers=owner
    )
    assert r.status_code == 422


async def test_an_existing_unlinked_profile_with_his_name_is_offered_not_duplicated(client):
    """The escape hatch for profiles made before this work order: the owner
    made "Ramesh Pawar" by hand; when Ramesh joins, that profile is offered
    for linking from the rounds page — not duplicated, not silently taken."""
    org, owner = await _fresh_shop(client, slug="patel-offered")
    r = await client.post("/v1/drivers", json={"full_name": "Ramesh  Pawar"}, headers=owner)
    assert r.status_code == 201, r.text
    handmade = r.json()
    boy = await _delivery_boy(
        client, owner, org["id"], email="ramesh2@patel.example", full_name="ramesh pawar"
    )
    drivers = (await client.get("/v1/drivers", headers=owner)).json()
    assert len(drivers) == 1 and drivers[0]["id"] == handmade["id"]
    assert drivers[0]["user_id"] is None, "offered, not taken over"
    assert (await client.get("/v1/drivers/me", headers=boy)).status_code == 404
    # The owner links it from the select — the platform's existing link —
    # and the app answers.
    me = (await client.get("/v1/auth/me", headers=boy)).json()
    r = await client.post(
        f"/v1/drivers/{handmade['id']}/user", json={"user_id": me["user"]["id"]}, headers=owner
    )
    assert r.status_code == 200, r.text
    assert (await client.get("/v1/drivers/me", headers=boy)).json()["id"] == handmade["id"]
