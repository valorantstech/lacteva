"""Routes, vehicles, drivers and the daily run, executed (DEMO-034).

The claim this milestone makes is narrow and worth stating exactly:

    **A route says which customers are visited and in what order; a run says
    who took it out, in what, on which of the dairy's own days. Neither knows
    anything about money, and the delivery domain remains the only thing that
    says what was delivered.**

So the tests below drive the real endpoints and then check the two properties
a route layer gets wrong: that it did not become a second source of delivery
truth, and that completing a round moved no money at all.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from platform_core.core import db
from tests.test_localization import _tenant_admin_for
from tests.test_org_structure import _tenant_admin
from tests.test_sales_workflow import _deliver

# --- environment ---------------------------------------------------------------


async def _customer(client, admin, name: str, phone: str = "+254700111222"):
    r = await client.post(
        "/v1/customers",
        json={
            "name": name,
            "customer_type": "household",
            "phone": phone,
            "plan": {
                "product": "RAW-COW-MILK",
                "default_quantity": "2.000",
                "quantity_unit": "L",
                "unit_price": "60.0000",
            },
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _route_env(client, *, stops: int = 3):
    """A dairy with a route, a van, a driver and `stops` customers on the round."""
    _org, admin = await _tenant_admin(client)
    customers = [
        await _customer(client, admin, f"Household {i}", f"+25470011{i:04d}") for i in range(stops)
    ]

    route = (
        await client.post(
            "/v1/routes",
            json={"code": "R-01", "name": "Kilima morning round"},
            headers=admin,
        )
    ).json()
    detail = await client.put(
        f"/v1/routes/{route['id']}/stops",
        json={"customer_ids": [c["id"] for c in customers]},
        headers=admin,
    )
    assert detail.status_code == 200, detail.text

    vehicle = (
        await client.post(
            "/v1/vehicles", json={"registration": "KDA 123X", "label": "Blue van"}, headers=admin
        )
    ).json()
    driver = (
        await client.post(
            "/v1/drivers",
            json={"code": "DRV-1", "full_name": "Joseph Mwangi", "phone": "+254733000111"},
            headers=admin,
        )
    ).json()
    return admin, route, customers, vehicle, driver


async def _run(client, admin, route, vehicle=None, driver=None, **extra):
    body = {"route_id": route["id"], **extra}
    if vehicle:
        body["vehicle_id"] = vehicle["id"]
    if driver:
        body["driver_id"] = driver["id"]
    return await client.post("/v1/delivery-runs", json=body, headers=admin)


# --- the route -----------------------------------------------------------------


async def test_a_route_is_an_ordered_list_of_customers(client):
    admin, route, customers, _v, _d = await _route_env(client)

    detail = (await client.get(f"/v1/routes/{route['id']}", headers=admin)).json()
    assert [s["customer_id"] for s in detail["stops"]] == [c["id"] for c in customers]
    assert [s["position"] for s in detail["stops"]] == [1, 2, 3]
    # The stop carries the customer's own code and name, so a screen showing a
    # round never has to fetch customers separately.
    assert detail["stops"][0]["name"] == "Household 0"
    assert detail["stop_count"] == 3


async def test_reordering_the_stops_is_sending_the_new_order(client):
    """The order IS the payload — which is why this is a PUT of a list."""
    admin, route, customers, _v, _d = await _route_env(client)
    reversed_ids = [c["id"] for c in reversed(customers)]

    r = await client.put(
        f"/v1/routes/{route['id']}/stops", json={"customer_ids": reversed_ids}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert [s["customer_id"] for s in r.json()["stops"]] == reversed_ids
    assert [s["position"] for s in r.json()["stops"]] == [1, 2, 3]


async def test_a_customer_cannot_appear_on_a_route_twice(client):
    """A round that visits the same household twice is a mistake to be seen."""
    admin, route, customers, _v, _d = await _route_env(client)
    duplicated = [customers[0]["id"], customers[1]["id"], customers[0]["id"]]

    r = await client.put(
        f"/v1/routes/{route['id']}/stops", json={"customer_ids": duplicated}, headers=admin
    )
    assert r.status_code == 422, r.text
    assert "more than once" in r.text


async def test_a_stop_must_be_a_customer_of_this_tenant(client):
    """Otherwise a route is a way to name rows in somebody else's dairy."""
    admin, route, _customers, _v, _d = await _route_env(client)

    r = await client.put(
        f"/v1/routes/{route['id']}/stops",
        json={"customer_ids": [str(uuid.uuid4())]},
        headers=admin,
    )
    assert r.status_code == 404, r.text


async def test_a_route_code_is_unique_within_the_dairy(client):
    admin, _route, _customers, _v, _d = await _route_env(client)
    r = await client.post(
        "/v1/routes", json={"code": "R-01", "name": "Another round"}, headers=admin
    )
    assert r.status_code == 409, r.text


# --- the run -------------------------------------------------------------------


async def test_a_run_defaults_to_the_dairys_own_today(client):
    """Not UTC's, and not the caller's (DEMO-013).

    The client sends no date at all, and the platform answers with the
    organization's business date — the same machinery generation already uses.
    """
    admin, route, _customers, vehicle, driver = await _route_env(client)

    r = await _run(client, admin, route, vehicle, driver)
    assert r.status_code == 201, r.text

    from platform_core.core.business_time import business_today

    locale = (await client.get("/v1/organizations/settings/locale", headers=admin)).json()
    assert r.json()["business_date"] == business_today(locale["timezone"]).isoformat()


async def test_the_same_route_cannot_go_out_twice_in_one_slot(client):
    """`uq_delivery_run_route_date_slot` — the guard, in the database."""
    admin, route, _customers, vehicle, driver = await _route_env(client)
    first = await _run(client, admin, route, vehicle, driver)
    assert first.status_code == 201, first.text

    second = await _run(client, admin, route, vehicle, driver)
    assert second.status_code == 409, second.text
    assert "already exists" in second.text


async def test_the_same_route_goes_out_again_in_the_evening(client):
    """A dairy delivering twice a day runs the same route twice, and those are
    two rounds — which is why `slot` is part of the constraint."""
    admin, route, _customers, vehicle, driver = await _route_env(client)
    assert (await _run(client, admin, route, vehicle, driver)).status_code == 201
    evening = await _run(client, admin, route, vehicle, driver, slot="evening")
    assert evening.status_code == 201, evening.text
    assert evening.json()["slot"] == "evening"


async def test_a_run_cannot_start_without_a_driver_and_a_vehicle(client):
    """BR-0028, and the reason there is no `assigned` STATUS.

    Assignment is two columns. Starting is what checks them.
    """
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route)).json()
    assert run["status"] == "planned"

    r = await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": "in_progress"}, headers=admin
    )
    assert r.status_code == 409, r.text
    assert "driver and a vehicle" in r.text

    # Assign both, and the same call now succeeds.
    assigned = await client.post(
        f"/v1/delivery-runs/{run['id']}/assignment",
        json={"vehicle_id": vehicle["id"], "driver_id": driver["id"]},
        headers=admin,
    )
    assert assigned.status_code == 200, assigned.text
    started = await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": "in_progress"}, headers=admin
    )
    assert started.status_code == 200, started.text
    assert started.json()["started_at"] is not None


async def test_a_run_walks_planned_to_in_progress_to_completed(client):
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()

    for status in ("in_progress", "completed"):
        r = await client.post(
            f"/v1/delivery-runs/{run['id']}/status", json={"status": status}, headers=admin
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == status
    assert r.json()["finished_at"] is not None


@pytest.mark.parametrize("target", ["in_progress", "completed", "cancelled"])
async def test_a_completed_run_is_terminal(client, target):
    """Reopening a closed round would let this module disagree with the
    deliveries it describes."""
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()
    await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": "in_progress"}, headers=admin
    )
    await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": "completed"}, headers=admin
    )

    r = await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": target}, headers=admin
    )
    assert r.status_code == 409, r.text
    assert "terminal" in r.text


async def test_an_unknown_status_is_refused_rather_than_stored(client):
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()
    r = await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": "finished"}, headers=admin
    )
    assert r.status_code == 422, r.text


async def test_a_retired_van_cannot_be_assigned(client):
    """Discovered in the evening beats discovered at six the next morning."""
    admin, route, _customers, vehicle, driver = await _route_env(client)

    async with db.get_session_factory()() as session:
        from platform_core.modules.logistics.models import Vehicle

        v = await session.get(Vehicle, uuid.UUID(vehicle["id"]))
        v.active = False
        await session.commit()

    r = await _run(client, admin, route, vehicle, driver)
    assert r.status_code == 409, r.text
    assert "not active" in r.text


# --- the boundary: a run composes deliveries, it does not restate them ---------


async def test_a_stop_shows_what_the_DELIVERY_domain_says_happened(client):
    """The whole design in one test.

    No delivery outcome is stored on a run. The run is created first, the
    delivery is recorded afterwards through the delivery domain's own
    endpoint, and the run reports it the next time anybody looks.
    """
    admin, route, customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()
    day = date.fromisoformat(run["business_date"])

    before = (await client.get(f"/v1/delivery-runs/{run['id']}", headers=admin)).json()
    assert [s["delivery_status"] for s in before["stops"]] == [None, None, None]

    r = await _deliver(client, admin, customers[0]["id"], day)
    assert r.status_code == 201, r.text
    r = await _deliver(client, admin, customers[1]["id"], day, status="skipped")
    assert r.status_code == 201, r.text

    after = (await client.get(f"/v1/delivery-runs/{run['id']}", headers=admin)).json()
    assert [s["delivery_status"] for s in after["stops"]] == ["delivered", "skipped", None]


async def test_the_run_carries_no_milk_and_no_money(client):
    """A route is an operational concept. Asserted against the schema itself,
    so a future column called `total_amount` fails here rather than in a
    reconciliation six months later."""
    from platform_core.modules.logistics.models import DeliveryRun, Route, RouteStop

    financial = ("amount", "quantity", "unit_price", "currency", "total", "balance", "invoice")
    for model in (DeliveryRun, Route, RouteStop):
        for column in model.__table__.columns:
            assert not any(word in column.name for word in financial), (
                f"{model.__tablename__}.{column.name} looks financial; "
                "a run is an execution record, not a document"
            )


async def test_completing_a_round_moves_no_money(client):
    """The §11 property, executed end to end."""
    from platform_core.modules.billing.models import CustomerInvoice
    from platform_core.modules.delivery.models import MilkDelivery

    admin, route, customers, vehicle, driver = await _route_env(client)

    async def totals():
        async with db.get_session_factory()() as session:
            invoices = await session.scalar(select(func.count()).select_from(CustomerInvoice))
            billed = await session.scalar(select(func.coalesce(func.sum(MilkDelivery.amount), 0)))
            return invoices or 0, Decimal(billed or 0)

    run = (await _run(client, admin, route, vehicle, driver)).json()
    day = date.fromisoformat(run["business_date"])
    await _deliver(client, admin, customers[0]["id"], day)
    before = await totals()

    for status in ("in_progress", "completed"):
        r = await client.post(
            f"/v1/delivery-runs/{run['id']}/status", json={"status": status}, headers=admin
        )
        assert r.status_code == 200, r.text

    assert await totals() == before, "completing a run changed a financial total"


async def test_the_logistics_module_never_reads_the_delivery_or_customer_TABLES(client):
    """The boundary DEMO-030 was caught crossing.

    A module owns one concept and asks another module's SERVICE for the rest.
    This is an AST check rather than a naming convention, so an import added
    in six months fails here.
    """
    import ast
    import pathlib

    from platform_core.modules import logistics

    banned = {"MilkDelivery", "Customer", "DeliveryPlan", "CustomerInvoice"}
    offenders = []
    for path in sorted(pathlib.Path(logistics.__file__).parent.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and ".models" in node.module:
                if node.module.startswith("platform_core.modules.logistics"):
                    continue
                for alias in node.names:
                    if alias.name in banned:
                        offenders.append(f"{path.name}: {node.module}.{alias.name}")
    assert not offenders, f"logistics imports another module's models: {offenders}"


# --- business date, in two countries -------------------------------------------


@pytest.mark.parametrize(
    ("timezone", "country"),
    [("Asia/Kolkata", "India"), ("Africa/Nairobi", "Kenya")],
)
async def test_the_run_date_is_the_dairys_date_in_any_country(client, timezone, country):
    """§3. One business-date abstraction, no country branch.

    The organization's timezone decides, and the test asserts the run agrees
    with `business_today` for that zone rather than with the machine's clock.
    """
    from platform_core.core.business_time import business_today

    admin, route, _customers, vehicle, driver = await _route_env(client)

    r = await client.put(
        "/v1/organizations/settings/locale", json={"timezone": timezone}, headers=admin
    )
    assert r.status_code == 200, r.text

    run = await _run(client, admin, route, vehicle, driver)
    assert run.status_code == 201, run.text
    assert run.json()["business_date"] == business_today(timezone).isoformat(), country


async def test_a_run_is_refused_on_a_day_the_dairy_does_not_work(client):
    """The one working-day answer (DEMO-022), reused rather than re-derived.

    Generation already skips a non-working day; a run that could be planned on
    one would disagree with the round it describes.
    """
    admin, route, _customers, vehicle, driver = await _route_env(client)
    tomorrow = date.today() + timedelta(days=1)

    r = await client.put(
        "/v1/organization/calendar/days",
        json={
            "day": str(tomorrow),
            "working": False,
            "kind": "holiday",
            "name": "Public holiday",
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text

    refused = await _run(client, admin, route, vehicle, driver, business_date=str(tomorrow))
    assert refused.status_code == 409, refused.text
    assert "not a working day" in refused.text


# --- security -------------------------------------------------------------------


async def test_every_logistics_endpoint_refuses_an_anonymous_caller(client):
    for method, path in (
        ("get", "/v1/routes"),
        ("post", "/v1/routes"),
        ("get", "/v1/vehicles"),
        ("post", "/v1/vehicles"),
        ("get", "/v1/drivers"),
        ("post", "/v1/drivers"),
        ("get", "/v1/delivery-runs"),
        ("post", "/v1/delivery-runs"),
    ):
        r = await client.post(path, json={}) if method == "post" else await client.get(path)
        assert r.status_code == 401, f"{method.upper()} {path} answered {r.status_code}"


async def test_another_dairys_route_is_a_404_and_never_a_403(client):
    """The platform's rule: a probe must not learn that a thing exists."""
    _admin_a, route_a, _c, _v, _d = await _route_env(client)
    # A SECOND, genuinely separate dairy — same platform, different tenant.
    _org_b, admin_b = await _tenant_admin_for(
        client, country="KE", slug="second-dairy", email="admin@second.example"
    )

    r = await client.get(f"/v1/routes/{route_a['id']}", headers=admin_b)
    assert r.status_code == 404, r.text

    listing = (await client.get("/v1/routes", headers=admin_b)).json()
    assert listing == [], "another dairy's routes were visible"


async def test_a_driver_cannot_redraw_tomorrows_route(client):
    """`run.manage` deliberately does not imply `route.manage`."""
    from platform_core.modules.authz.permissions import NAMED_ROLES

    officer = set(NAMED_ROLES["SALES_OFFICER"])
    assert "logistics.run.manage" in officer
    assert "logistics.route.manage" not in officer
    assert "logistics.fleet.manage" not in officer


async def test_no_tenant_role_can_reach_another_dairys_fleet(client):
    """Every logistics permission is tenant-scoped; none is platform-wide."""
    from platform_core.modules.authz.permissions import PERMISSIONS

    keys = [k for k in PERMISSIONS if k.startswith("logistics.")]
    assert len(keys) == 6
    assert all(k.count(".") == 2 for k in keys)


# --- audit ----------------------------------------------------------------------


async def test_every_operational_change_is_audited(client):
    """§10. One audit mechanism, reused."""
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()
    await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": "in_progress"}, headers=admin
    )

    entries = (await client.get("/v1/audit?limit=100", headers=admin)).json()
    actions = {e["action"] for e in entries["items"]}
    for expected in (
        "logistics.route_created",
        "logistics.route_stops_set",
        "logistics.vehicle_created",
        "logistics.driver_created",
        "logistics.run_created",
        "logistics.run_status_changed",
    ):
        assert expected in actions, f"{expected} was not audited"


async def test_a_status_change_records_where_it_came_from_and_went_to(client):
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()
    await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": "in_progress"}, headers=admin
    )

    entries = (await client.get("/v1/audit?limit=100", headers=admin)).json()
    change = next(e for e in entries["items"] if e["action"] == "logistics.run_status_changed")
    assert change["detail"] == {"from": "planned", "to": "in_progress"}


async def test_a_drivers_phone_is_not_copied_into_the_audit_trail(client):
    """An audit trail is read by more people than the record it describes."""
    admin, _route, _customers, _v, _d = await _route_env(client)
    entries = (await client.get("/v1/audit?limit=100", headers=admin)).json()
    created = next(e for e in entries["items"] if e["action"] == "logistics.driver_created")
    assert "+254733000111" not in str(created["detail"])
