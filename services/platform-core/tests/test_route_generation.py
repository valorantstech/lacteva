"""Route-driven delivery generation, executed (DEMO-035).

The claim this milestone makes:

    **A configured route with ordered stops can produce the day's deliveries
    for its own households — through the existing generator, with the existing
    rules, and without becoming a second delivery domain.**

So the tests below check the two things a scoped generator gets wrong. That it
generates the RIGHT rows — this route's households, this run's slot, nobody
else's — and that it generates them ONCE, by the constraint that already
existed rather than by a check in Python.

The most valuable test in the file is
`test_two_routes_on_the_same_day_both_generate`: routing this through
`record_run` would have made the second route of the day silently produce
nothing while reporting success, because that function claims the tenant's DATE.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from platform_core.core import db
from tests.test_localization import _tenant_admin_for
from tests.test_logistics import _customer, _route_env
from tests.test_org_structure import _tenant_admin

# --- helpers -------------------------------------------------------------------


async def _run(client, admin, route, vehicle=None, driver=None, **extra):
    body = {"route_id": route["id"], **extra}
    if vehicle:
        body["vehicle_id"] = vehicle["id"]
    if driver:
        body["driver_id"] = driver["id"]
    return await client.post("/v1/delivery-runs", json=body, headers=admin)


async def _generate(client, admin, run_id):
    return await client.post(f"/v1/delivery-runs/{run_id}/generate", headers=admin)


async def _deliveries_on(client, admin, day, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/v1/deliveries?date_from={day}&date_to={day}"
    return (await client.get(f"{url}&{query}" if query else url, headers=admin)).json()


# --- the normal case -------------------------------------------------------------


async def test_a_route_generates_the_round_for_its_own_households(client):
    admin, route, customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()

    r = await _generate(client, admin, run["id"])
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["stops"] == 3
    assert body["created"] == 3, body
    assert body["already_present"] == 0
    assert body["route_code"] == route["code"]
    assert body["business_date"] == run["business_date"]
    assert body["slot"] == "morning"

    # The deliveries are ORDINARY deliveries, readable through the delivery
    # endpoints — the generator's own guarantee, not a new one.
    page = await _deliveries_on(client, admin, run["business_date"])
    assert page["total"] == 3
    assert {d["status"] for d in page["items"]} == {"scheduled"}
    assert {d["customer_id"] for d in page["items"]} == {c["id"] for c in customers}


async def test_the_generated_round_appears_on_the_run_in_route_order(client):
    """The whole point of the milestone, end to end.

    The run's stops carry the delivery domain's own status once generation has
    run — no route reference was added to `milk_delivery` to make this work.
    """
    admin, route, customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()

    before = (await client.get(f"/v1/delivery-runs/{run['id']}", headers=admin)).json()
    assert [s["delivery_status"] for s in before["stops"]] == [None, None, None]

    await _generate(client, admin, run["id"])

    after = (await client.get(f"/v1/delivery-runs/{run['id']}", headers=admin)).json()
    assert [s["position"] for s in after["stops"]] == [1, 2, 3]
    assert [s["delivery_status"] for s in after["stops"]] == ["scheduled"] * 3
    assert [s["customer_id"] for s in after["stops"]] == [c["id"] for c in customers]


async def test_only_the_customers_on_the_route_are_generated_for(client):
    """A household off the route is not part of this round.

    The narrowing is the feature: before DEMO-035 the only generator produced
    the whole tenant's round, so "generate this route" had no meaning.
    """
    admin, route, _customers, vehicle, driver = await _route_env(client)
    off_route = await _customer(client, admin, "Not on the round", "+254700999888")

    run = (await _run(client, admin, route, vehicle, driver)).json()
    r = await _generate(client, admin, run["id"])
    assert r.json()["created"] == 3

    page = await _deliveries_on(client, admin, run["business_date"])
    assert off_route["id"] not in {d["customer_id"] for d in page["items"]}
    assert page["total"] == 3


async def test_a_morning_run_does_not_generate_an_evening_plan(client):
    """A plan carries its own slot, and a morning van must not deliver it.

    Without the slot narrowing this generated the evening round too, and the
    evening run would then have reported `created: 0` — a whole slot delivered
    on paper by the wrong van.
    """
    admin, route, customers, vehicle, driver = await _route_env(client)

    # Give the first household a SECOND plan, for the evening.
    r = await client.post(
        f"/v1/customers/{customers[0]['id']}/plan",
        json={
            "product": "RAW-COW-MILK",
            "default_quantity": "1.000",
            "quantity_unit": "L",
            "unit_price": "60.0000",
            "slot": "evening",
        },
        headers=admin,
    )
    assert r.status_code in (200, 201), r.text

    morning = (await _run(client, admin, route, vehicle, driver)).json()
    assert (await _generate(client, admin, morning["id"])).json()["created"] == 3

    evening = (await _run(client, admin, route, vehicle, driver, slot="evening")).json()
    generated = (await _generate(client, admin, evening["id"])).json()
    assert generated["created"] == 1, "the evening plan was generated by the morning run"
    assert generated["slot"] == "evening"


# --- idempotency and concurrency -------------------------------------------------


async def test_generating_twice_creates_the_round_once(client):
    """§7. Decided by `uq_delivery_customer_date_slot`, not by a Python check."""
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()

    first = (await _generate(client, admin, run["id"])).json()
    second = (await _generate(client, admin, run["id"])).json()

    assert first["created"] == 3
    assert second["created"] == 0, "a second generation duplicated the round"
    assert second["already_present"] == 3

    page = await _deliveries_on(client, admin, run["business_date"])
    assert page["total"] == 3


async def test_two_routes_on_the_same_day_both_generate(client):
    """The defect this milestone would have shipped.

    `record_run` claims the tenant's DATE — `uq_generation_run_tenant_date` —
    and hands whoever loses the claim a `created: 0`. Correct for the scheduler,
    where a day has one whole-tenant round. Routed through it, the FIRST route
    of the day would claim the date and every later route would silently
    generate nothing while reporting success.

    So route generation goes to `generate_for_day` directly, and this test is
    what says so.
    """
    admin, route_a, _customers_a, vehicle, driver = await _route_env(client)
    extra = [
        await _customer(client, admin, f"Second round {i}", f"+25470088{i:04d}") for i in range(2)
    ]

    route_b = (
        await client.post(
            "/v1/routes", json={"code": "R-02", "name": "Second round"}, headers=admin
        )
    ).json()
    r = await client.put(
        f"/v1/routes/{route_b['id']}/stops",
        json={"customer_ids": [c["id"] for c in extra]},
        headers=admin,
    )
    assert r.status_code == 200, r.text

    run_a = (await _run(client, admin, route_a, vehicle, driver)).json()
    run_b = (await _run(client, admin, route_b, vehicle, driver)).json()

    generated_a = (await _generate(client, admin, run_a["id"])).json()
    generated_b = (await _generate(client, admin, run_b["id"])).json()

    assert generated_a["created"] == 3, generated_a
    assert generated_b["created"] == 2, (
        f"the second route of the day generated {generated_b['created']} — the "
        "tenant-day claim swallowed it"
    )

    page = await _deliveries_on(client, admin, run_a["business_date"])
    assert page["total"] == 5


async def test_the_whole_tenant_generator_still_sees_the_route_round(client):
    """Existing delivery compatibility.

    The scheduler's whole-tenant round and a route round write the same table
    with the same constraint, so running both is safe in either order.
    """
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()
    assert (await _generate(client, admin, run["id"])).json()["created"] == 3

    r = await client.post(
        "/v1/deliveries/generate",
        json={"for_date": run["business_date"]},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 0, "the tenant-wide run duplicated the route round"

    page = await _deliveries_on(client, admin, run["business_date"])
    assert page["total"] == 3


# --- refusals -------------------------------------------------------------------


async def test_a_route_with_no_stops_is_refused_rather_than_reporting_success(client):
    """ "generated 0 of 0" reads like success to whoever is waiting for a van."""
    _org, admin = await _tenant_admin(client)
    route = (
        await client.post(
            "/v1/routes", json={"code": "EMPTY", "name": "No stops yet"}, headers=admin
        )
    ).json()
    vehicle = (
        await client.post("/v1/vehicles", json={"registration": "KDA 9Z"}, headers=admin)
    ).json()
    driver = (
        await client.post("/v1/drivers", json={"code": "D-9", "full_name": "Nobody"}, headers=admin)
    ).json()
    run = (await _run(client, admin, route, vehicle, driver)).json()

    r = await _generate(client, admin, run["id"])
    assert r.status_code == 409, r.text
    assert "no stops" in r.text


async def test_an_inactive_route_generates_nothing(client):
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()

    async with db.get_session_factory()() as session:
        from platform_core.modules.logistics.models import Route

        row = await session.get(Route, uuid.UUID(route["id"]))
        row.active = False
        await session.commit()

    r = await _generate(client, admin, run["id"])
    assert r.status_code == 409, r.text
    assert "not active" in r.text


async def test_a_nonexistent_run_is_a_404(client):
    _org, admin = await _tenant_admin(client)
    r = await _generate(client, admin, str(uuid.uuid4()))
    assert r.status_code == 404, r.text


async def test_another_dairys_run_cannot_be_generated_and_is_a_404(client):
    """§ tenant isolation. Never a 403: a probe must not learn it exists."""
    admin_a, route_a, _c, vehicle, driver = await _route_env(client)
    run_a = (await _run(client, admin_a, route_a, vehicle, driver)).json()

    _org_b, admin_b = await _tenant_admin_for(
        client, country="KE", slug="other-dairy-035", email="admin@other035.example"
    )
    r = await _generate(client, admin_b, run_a["id"])
    assert r.status_code == 404, r.text

    # And nothing was generated in either dairy by the attempt.
    page = await _deliveries_on(client, admin_a, run_a["business_date"])
    assert page["total"] == 0


async def test_nothing_generates_on_a_day_the_dairy_does_not_work(client):
    """Checked AGAIN at generation, not only at run creation.

    A holiday can be declared between planning a round and generating it.
    """
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()

    r = await client.put(
        "/v1/organization/calendar/days",
        json={
            "day": run["business_date"],
            "working": False,
            "kind": "holiday",
            "name": "Declared after the run was planned",
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text

    refused = await _generate(client, admin, run["id"])
    assert refused.status_code == 409, refused.text
    assert "not a working day" in refused.text

    page = await _deliveries_on(client, admin, run["business_date"])
    assert page["total"] == 0, "a holiday round was generated anyway"


@pytest.mark.parametrize("status", ["completed", "cancelled"])
async def test_a_closed_run_cannot_generate(client, status):
    """Adding work to a day somebody has already signed off."""
    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()

    if status == "completed":
        await client.post(
            f"/v1/delivery-runs/{run['id']}/status",
            json={"status": "in_progress"},
            headers=admin,
        )
    await client.post(
        f"/v1/delivery-runs/{run['id']}/status", json={"status": status}, headers=admin
    )

    r = await _generate(client, admin, run["id"])
    assert r.status_code == 409, r.text
    assert status in r.text


async def test_generation_needs_the_run_grant(client):
    """A read-only role cannot send a round out."""
    from platform_core.modules.authz.permissions import NAMED_ROLES

    assert "logistics.run.manage" not in NAMED_ROLES["AUDITOR"]
    assert "logistics.run.manage" in NAMED_ROLES["SALES_OFFICER"]


async def test_generation_refuses_an_anonymous_caller(client):
    r = await client.post(f"/v1/delivery-runs/{uuid.uuid4()}/generate", json={})
    assert r.status_code == 401, r.text


# --- the delivery domain keeps its rules ----------------------------------------


async def test_an_inactive_customer_on_a_route_is_skipped_not_delivered(client):
    """A suspended household keeps their plan and stops receiving milk.

    The rule is the delivery domain's; this asserts the route path did not
    bypass it.
    """
    admin, route, customers, vehicle, driver = await _route_env(client)
    r = await client.post(
        f"/v1/customers/{customers[0]['id']}/status",
        json={"status": "suspended"},
        headers=admin,
    )
    assert r.status_code == 200, r.text

    run = (await _run(client, admin, route, vehicle, driver)).json()
    body = (await _generate(client, admin, run["id"])).json()

    assert body["created"] == 2
    assert body["inactive_customers"] == 1


async def test_a_plan_not_due_today_is_reported_as_not_due(client):
    """A weekday mask still narrows the round."""
    admin, route, customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()
    day = date.fromisoformat(run["business_date"])

    # A mask that excludes exactly today, set by superseding the plan.
    mask = "".join("0" if i == day.weekday() else "1" for i in range(7))
    r = await client.post(
        f"/v1/customers/{customers[0]['id']}/plan",
        json={
            "product": "RAW-COW-MILK",
            "default_quantity": "2.000",
            "quantity_unit": "L",
            "unit_price": "60.0000",
            "weekdays": mask,
        },
        headers=admin,
    )
    assert r.status_code in (200, 201), r.text

    body = (await _generate(client, admin, run["id"])).json()
    assert body["created"] == 2
    assert body["not_due"] == 1


async def test_the_generated_round_is_worth_nothing_until_somebody_says_so(client):
    """§ financial safety. `scheduled` is not billable, and the amount is 0.00.

    A generator that produced billable rows would invoice a dairy's whole round
    every morning whether the milk arrived or not.
    """
    from platform_core.modules.billing.models import CustomerInvoice
    from platform_core.modules.delivery.models import MilkDelivery

    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()

    async with db.get_session_factory()() as session:
        invoices_before = await session.scalar(select(func.count()).select_from(CustomerInvoice))

    await _generate(client, admin, run["id"])

    async with db.get_session_factory()() as session:
        invoices_after = await session.scalar(select(func.count()).select_from(CustomerInvoice))
        billed = await session.scalar(select(func.coalesce(func.sum(MilkDelivery.amount), 0)))
        statuses = set((await session.scalars(select(MilkDelivery.status))).all())

    assert invoices_after == invoices_before, "generating a round created an invoice"
    assert Decimal(billed or 0) == Decimal("0.00"), "a generated round carried money"
    assert statuses == {"scheduled"}


async def test_no_route_reference_was_added_to_the_delivery_table(client):
    """The architectural gap, recorded as a test rather than as prose.

    `milk_delivery` has no place for a route, and DEMO-035 deliberately did not
    add one: the run view already joins stops to deliveries on (customer, date,
    slot), which is unique, and a `route_id` column would be a second answer to
    "which route served this delivery" that could disagree with `route_stop`.
    """
    from platform_core.modules.delivery.models import MilkDelivery

    names = {c.name for c in MilkDelivery.__table__.columns}
    for invented in ("route_id", "run_id", "stop_id", "position", "vehicle_id", "driver_id"):
        assert invented not in names, f"milk_delivery gained {invented}"


async def test_generation_is_one_insert_batch_not_one_per_stop(client):
    """A round of forty households must not be forty statements.

    The generator already batched; this asserts the route path did not undo it
    by looping per stop.
    """
    from tests.conftest import count_statements

    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()

    _result, statements = await count_statements(
        lambda: _generate(client, admin, run["id"]), selects_only=False
    )
    assert statements < 40, f"{statements} statements for a three-stop round"


async def test_a_future_dated_run_generates_for_that_day_only(client):
    """Planning tomorrow's round is legitimate and must not touch today."""
    admin, route, _customers, vehicle, driver = await _route_env(client)
    tomorrow = date.today() + timedelta(days=1)

    run = await _run(client, admin, route, vehicle, driver, business_date=str(tomorrow))
    assert run.status_code == 201, run.text
    body = (await _generate(client, admin, run.json()["id"])).json()
    assert body["business_date"] == str(tomorrow)
    assert body["created"] == 3

    today_page = await _deliveries_on(client, admin, date.today().isoformat())
    assert today_page["total"] == 0, "tomorrow's round generated into today"


async def test_an_empty_customer_set_generates_nothing_not_everything(client):
    """The generator's own claim, tested where the API cannot reach it.

    `if not stops` refuses an empty route before this can happen, so nothing
    above exercises it — and a mutation turning `customer_ids is not None` into
    `customer_ids` therefore survived the whole file. An empty set has to mean
    "no households", because the alternative is that a route with no stops
    generates the WHOLE DAIRY's round.
    """
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.delivery.generation import generate_for_day

    admin, route, _customers, vehicle, driver = await _route_env(client)
    run = (await _run(client, admin, route, vehicle, driver)).json()
    day = date.fromisoformat(run["business_date"])

    async with db.get_session_factory()() as session:
        from platform_core.modules.logistics.models import DeliveryRun

        row = await session.get(DeliveryRun, uuid.UUID(run["id"]))
        tenant_id = row.tenant_id
        set_current_tenant(tenant_id)
        result = await generate_for_day(
            session,
            tenant_id=tenant_id,
            day=day,
            actor_id=None,
            customer_ids=set(),
            slot="morning",
        )
        await session.commit()

    assert result.due == 0, "an empty customer set generated a round"
    assert result.created == 0

    page = await _deliveries_on(client, admin, run["business_date"])
    assert page["total"] == 0
