"""WO-82 · LACTEVA-MOBILE-015 — the delivery boy's round, as it actually happens.

Three things the driver app could not do and a shop cannot run without:

  1. the run tells the driver what to pour — each stop carries its standing
     product(s), name, quantity and unit, resolved server-side from the
     plan; a household with two milks (WO-81) lists two, and an outcome
     must say which;
  2. an item at the doorstep goes through the item endpoint a DRIVER already
     holds (`sales.item.record`, WO-81) — nothing new on the platform;
  3. today's round, without the owner: a route with `auto_plan` and a default
     driver has its run at 00:31 IST the next day, created, assigned and
     generated through the same three calls the office uses, idempotent at
     the database, and skipped on a non-working day.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from platform_core.modules.delivery.scheduler import Tenant, run_for_tenant
from platform_core.modules.logistics.service import plan_auto_routes_for_scheduler
from tests.test_driver_execution import _driver_env
from tests.test_logistics import _route_env
from tests.test_org_structure import add_milk_product

HOUR = 0  # the generation hour, local: 00:30 IST is the scheduler's own


# --- 1. the quantity, at the doorstep ------------------------------------------


async def test_a_run_stop_carries_its_standing_orders(client):
    admin, route, customers, vehicle, driver = await _route_env(client, stops=2)
    # The second household takes cow AND buffalo milk on the same mornings.
    await add_milk_product(client, admin, code="RAW-BUFFALO-MILK", name="Raw buffalo milk")
    r = await client.post(
        f"/v1/customers/{customers[1]['id']}/plan",
        json={
            "product": "RAW-BUFFALO-MILK",
            "default_quantity": "0.500",
            "quantity_unit": "L",
            "unit_price": "56.0000",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    run = (
        await client.post(
            "/v1/delivery-runs",
            json={"route_id": route["id"], "vehicle_id": vehicle["id"], "driver_id": driver["id"]},
            headers=admin,
        )
    ).json()
    view = (await client.get(f"/v1/delivery-runs/{run['id']}", headers=admin)).json()
    by_customer = {s["customer_id"]: s for s in view["stops"]}

    one = by_customer[customers[0]["id"]]["orders"]
    assert [(o["product"], o["product_name"], o["quantity"], o["quantity_unit"]) for o in one] == [
        ("RAW-COW-MILK", "Raw Cow Milk", "2.000", "L")
    ]
    assert one[0]["delivery_status"] is None  # nothing recorded yet

    two = by_customer[customers[1]["id"]]["orders"]
    assert sorted(o["product"] for o in two) == ["RAW-BUFFALO-MILK", "RAW-COW-MILK"]
    assert {o["product_name"] for o in two} == {"Raw buffalo milk", "Raw Cow Milk"}


async def test_the_driver_names_the_product_when_there_are_two_and_sends_the_quantity(client):
    env = await _driver_env(client)
    driver, run, customers, admin = env["headers"], env["run"], env["customers"], env["admin"]
    household = customers[0]
    await add_milk_product(client, admin, code="RAW-BUFFALO-MILK", name="Raw buffalo milk")
    r = await client.post(
        f"/v1/customers/{household['id']}/plan",
        json={
            "product": "RAW-BUFFALO-MILK",
            "default_quantity": "0.500",
            "quantity_unit": "L",
            "unit_price": "56.0000",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    await client.post(f"/v1/delivery-runs/{run['id']}/start", headers=driver)

    # Two standing orders, none named: refused, and the refusal names both.
    r = await client.post(
        f"/v1/delivery-runs/{run['id']}/stops/{household['id']}/outcome",
        json={"status": "delivered"},
        headers=driver,
    )
    assert r.status_code == 409, r.text
    assert "RAW-BUFFALO-MILK" in r.text and "RAW-COW-MILK" in r.text

    # Named, with a changed quantity: the delivery is that product at that
    # quantity, priced by ITS plan.
    r = await client.post(
        f"/v1/delivery-runs/{run['id']}/stops/{household['id']}/outcome",
        json={"status": "delivered", "product": "RAW-COW-MILK", "quantity": "1.500"},
        headers=driver,
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        f"/v1/delivery-runs/{run['id']}/stops/{household['id']}/outcome",
        json={"status": "delivered", "product": "RAW-BUFFALO-MILK"},
        headers=driver,
    )
    assert r.status_code == 201, r.text
    view = (await client.get(f"/v1/delivery-runs/{run['id']}", headers=admin)).json()
    stop = next(s for s in view["stops"] if s["customer_id"] == household["id"])
    assert {o["product"]: o["delivery_status"] for o in stop["orders"]} == {
        "RAW-COW-MILK": "delivered",
        "RAW-BUFFALO-MILK": "delivered",
    }
    page = (
        await client.get(
            "/v1/deliveries",
            params={
                "customer_id": household["id"],
                "date_from": run["business_date"],
                "date_to": run["business_date"],
            },
            headers=admin,
        )
    ).json()
    by_product = {d["product"]: d for d in page["items"]}
    assert Decimal(by_product["RAW-COW-MILK"]["quantity"]) == Decimal("1.500")
    assert Decimal(by_product["RAW-BUFFALO-MILK"]["quantity"]) == Decimal("0.500")
    assert Decimal(by_product["RAW-BUFFALO-MILK"]["unit_price"]) == Decimal("56.0000")

    # A household with ONE standing order still needs no product named —
    # exactly as before this work order.
    other = customers[1]
    r = await client.post(
        f"/v1/delivery-runs/{run['id']}/stops/{other['id']}/outcome",
        json={"status": "delivered"},
        headers=driver,
    )
    assert r.status_code == 201, r.text


# --- 2. items, at the doorstep ---------------------------------------------------


async def test_the_driver_adds_an_item_at_the_doorstep_and_a_replay_is_the_same_item(client):
    env = await _driver_env(client)
    driver, run, customers, admin = env["headers"], env["run"], env["customers"], env["admin"]
    r = await client.post(
        "/v1/products",
        json={"code": "DAHI-500G", "name": "Dahi 500 g", "unit": "pc", "default_price": "40.00"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    household = customers[0]
    body = {
        "sale_date": run["business_date"],
        "product_code": "DAHI-500G",
        "quantity": "1",
        "idempotency_key": "phone-op-1",
        "recorded_via": "mobile",
    }
    first = await client.post(f"/v1/customers/{household['id']}/items", json=body, headers=driver)
    assert first.status_code == 201, first.text
    assert Decimal(first.json()["amount"]) == Decimal("40.00")
    again = await client.post(f"/v1/customers/{household['id']}/items", json=body, headers=driver)
    assert again.json()["id"] == first.json()["id"]
    # The catalogue is readable by the driver, for the phone's cache.
    assert (await client.get("/v1/products", headers=driver)).status_code == 200


# --- 3. today's round, without the owner -------------------------------------------


async def _planned_route(client, *, auto_plan=True, with_driver=True):
    admin, route, customers, vehicle, driver = await _route_env(client)
    body = {"auto_plan": auto_plan, "default_vehicle_id": vehicle["id"]}
    if with_driver:
        body["default_driver_id"] = driver["id"]
    r = await client.patch(f"/v1/routes/{route['id']}", json=body, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["auto_plan"] is auto_plan
    org = (await client.get("/v1/auth/me", headers=admin)).json()
    return admin, route, customers, vehicle, driver, org


def _tenant(org) -> Tenant:
    return Tenant(
        id=uuid.UUID(org["tenant_id"]), slug="test", timezone=org["organization"]["timezone"]
    )


async def test_a_route_with_auto_plan_has_its_run_at_the_generation_hour(client):
    admin, route, customers, vehicle, driver, org = await _planned_route(client)
    # 00:31 in the dairy's own zone, tomorrow: past the generation hour.
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(org["organization"]["timezone"])
    tomorrow = (datetime.now(zone) + timedelta(days=1)).date()
    at = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 31, tzinfo=zone).astimezone(UTC)

    run = await run_for_tenant(
        _tenant(org),
        now=at,
        generation_hour=HOUR,
        force_date=tomorrow,
        route_planner=plan_auto_routes_for_scheduler,
    )
    assert run is not None and run.status == "success"

    runs = (
        await client.get(
            "/v1/delivery-runs", params={"business_date": str(tomorrow)}, headers=admin
        )
    ).json()
    mine = [r for r in runs if r["route_id"] == route["id"]]
    assert len(mine) == 1, runs
    planned = mine[0]
    assert planned["driver_id"] == driver["id"]
    assert planned["vehicle_id"] == vehicle["id"]
    assert planned["status"] == "planned"
    assert planned["business_date"] == str(tomorrow)
    # Generated: every stop has its scheduled delivery.
    assert all(s["delivery_status"] == "scheduled" for s in planned["stops"])

    # Idempotent: a second pass at the same clock creates nothing more.
    await run_for_tenant(
        _tenant(org),
        now=at,
        generation_hour=HOUR,
        force_date=tomorrow,
        route_planner=plan_auto_routes_for_scheduler,
    )
    runs = (
        await client.get(
            "/v1/delivery-runs", params={"business_date": str(tomorrow)}, headers=admin
        )
    ).json()
    assert len([r for r in runs if r["route_id"] == route["id"]]) == 1


async def test_a_route_with_a_default_driver_but_auto_plan_off_gets_no_run(client):
    admin, route, customers, vehicle, driver, org = await _planned_route(client, auto_plan=False)
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(org["organization"]["timezone"])
    tomorrow = (datetime.now(zone) + timedelta(days=1)).date()
    await run_for_tenant(
        _tenant(org),
        now=datetime.now(UTC),
        generation_hour=HOUR,
        force_date=tomorrow,
        route_planner=plan_auto_routes_for_scheduler,
    )
    runs = (
        await client.get(
            "/v1/delivery-runs", params={"business_date": str(tomorrow)}, headers=admin
        )
    ).json()
    assert [r for r in runs if r["route_id"] == route["id"]] == []


async def test_a_route_with_auto_plan_but_no_default_driver_gets_no_run(client):
    admin, route, customers, vehicle, driver, org = await _planned_route(client, with_driver=False)
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(org["organization"]["timezone"])
    tomorrow = (datetime.now(zone) + timedelta(days=1)).date()
    await run_for_tenant(
        _tenant(org),
        now=datetime.now(UTC),
        generation_hour=HOUR,
        force_date=tomorrow,
        route_planner=plan_auto_routes_for_scheduler,
    )
    runs = (
        await client.get(
            "/v1/delivery-runs", params={"business_date": str(tomorrow)}, headers=admin
        )
    ).json()
    assert [r for r in runs if r["route_id"] == route["id"]] == []


async def test_a_non_working_day_plans_nothing(client):
    admin, route, customers, vehicle, driver, org = await _planned_route(client)
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(org["organization"]["timezone"])
    holiday = (datetime.now(zone) + timedelta(days=2)).date()
    r = await client.put(
        "/v1/organization/calendar/days",
        json={"day": str(holiday), "working": False, "kind": "holiday", "name": "Diwali"},
        headers=admin,
    )
    assert r.status_code in (200, 201), r.text
    await run_for_tenant(
        _tenant(org),
        now=datetime.now(UTC),
        generation_hour=HOUR,
        force_date=holiday,
        route_planner=plan_auto_routes_for_scheduler,
    )
    runs = (
        await client.get("/v1/delivery-runs", params={"business_date": str(holiday)}, headers=admin)
    ).json()
    assert [r for r in runs if r["route_id"] == route["id"]] == []


async def test_the_route_defaults_are_validated_and_clearable(client):
    admin, route, customers, vehicle, driver = await _route_env(client)
    r = await client.patch(
        f"/v1/routes/{route['id']}",
        json={"default_driver_id": str(uuid.uuid4())},
        headers=admin,
    )
    assert r.status_code in (404, 409, 422), r.text
    r = await client.patch(
        f"/v1/routes/{route['id']}",
        json={"default_driver_id": driver["id"], "auto_plan": True},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["default_driver_id"] == driver["id"]
    r = await client.patch(
        f"/v1/routes/{route['id']}", json={"clear_default_driver": True}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["default_driver_id"] is None
    assert r.json()["auto_plan"] is True
    listed = (await client.get("/v1/routes", headers=admin)).json()
    assert next(x for x in listed if x["id"] == route["id"])["auto_plan"] is True
