"""The round, reported BY ROUTE (DEMO-037).

The claim:

    **An operator can ask which routes ran, what each carried, and what is
    still outstanding on each — and the answer is derived at read time from the
    route membership and the deliveries that already existed.**

Nothing is stored to make this work. `milk_delivery` gained no `route_id` in
DEMO-035 and gains none here, so a stop moved between routes changes the report
the next time it is asked rather than leaving a stale attribution behind. The
test that guards that is `test_moving_a_stop_moves_the_report_with_it`.
"""

import uuid
from datetime import date
from decimal import Decimal

from platform_core.core import db
from tests.test_localization import _tenant_admin_for
from tests.test_logistics import _customer, _route_env
from tests.test_org_structure import _tenant_admin
from tests.test_sales_workflow import _deliver

DAY = date(2026, 8, 17)


# --- helpers -------------------------------------------------------------------


async def _route(client, admin, code: str, customer_ids: list[str], name: str | None = None):
    route = (
        await client.post(
            "/v1/routes", json={"code": code, "name": name or f"Round {code}"}, headers=admin
        )
    ).json()
    r = await client.put(
        f"/v1/routes/{route['id']}/stops",
        json={"customer_ids": customer_ids},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    return route


async def _report(client, admin, day=DAY):
    r = await client.get(
        "/v1/deliveries/report",
        params={"date_from": str(day), "date_to": str(day)},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _run_and_generate(client, admin, route, day=None):
    body = {"route_id": route["id"]}
    if day is not None:
        body["business_date"] = str(day)
    run = await client.post("/v1/delivery-runs", json=body, headers=admin)
    assert run.status_code == 201, run.text
    generated = await client.post(f"/v1/delivery-runs/{run.json()['id']}/generate", headers=admin)
    assert generated.status_code == 201, generated.text
    return run.json(), generated.json()


# --- 1: no routes means no breakdown ---------------------------------------------


async def test_a_dairy_with_no_routes_reports_no_route_breakdown(client):
    """The report a dairy got before DEMO-037, unchanged."""
    _org, admin = await _tenant_admin(client)
    customer = await _customer(client, admin, "Only household")
    r = await _deliver(client, admin, customer["id"], DAY)
    assert r.status_code == 201, r.text

    report = await _report(client, admin)

    assert report["routes"] == 0
    assert report["by_route"] == []
    assert report["unrouted"] == 0, "with no memberships there is nothing to call unrouted"
    # The pre-existing figures are untouched.
    assert report["deliveries"] == 1
    assert report["customers_served"] == 1


# --- 2-3: one route, then several ------------------------------------------------


async def test_one_route_is_reported_with_its_own_totals(client):
    admin, _route, customers, _v, _d = await _route_env(client)
    for customer in customers:
        r = await _deliver(client, admin, customer["id"], DAY)
        assert r.status_code == 201, r.text

    report = await _report(client, admin)

    assert report["routes"] == 1
    assert len(report["by_route"]) == 1
    row = report["by_route"][0]
    assert row["code"] == "R-01"
    assert row["name"] == "Kilima morning round"
    assert row["stops"] == 3
    assert row["stops_with_deliveries"] == 3
    assert row["deliveries"] == 3
    assert row["scheduled"] == 0
    assert Decimal(row["amount"]) > 0


async def test_several_routes_are_reported_separately(client):
    _org, admin = await _tenant_admin(client)
    a = [await _customer(client, admin, f"A{i}", f"+2547010{i:05d}") for i in range(2)]
    b = [await _customer(client, admin, f"B{i}", f"+2547020{i:05d}") for i in range(3)]
    await _route(client, admin, "R-01", [c["id"] for c in a])
    await _route(client, admin, "R-02", [c["id"] for c in b])

    for customer in a + b:
        await _deliver(client, admin, customer["id"], DAY)

    report = await _report(client, admin)

    assert report["routes"] == 2
    rows = {row["code"]: row for row in report["by_route"]}
    assert rows["R-01"]["deliveries"] == 2
    assert rows["R-01"]["stops"] == 2
    assert rows["R-02"]["deliveries"] == 3
    assert rows["R-02"]["stops"] == 3


async def test_the_route_totals_reconcile_with_the_round(client):
    """Overall totals stay consistent — the work order's requirement.

    Routed plus unrouted equals what the report says the round was.
    """
    _org, admin = await _tenant_admin(client)
    routed = [await _customer(client, admin, f"R{i}", f"+2547030{i:05d}") for i in range(2)]
    off_route = await _customer(client, admin, "Off route", "+254704000001")
    await _route(client, admin, "R-01", [c["id"] for c in routed])

    for customer in [*routed, off_route]:
        await _deliver(client, admin, customer["id"], DAY)

    report = await _report(client, admin)

    routed_deliveries = sum(row["deliveries"] for row in report["by_route"])
    assert routed_deliveries == 2
    assert report["unrouted"] == 1
    assert routed_deliveries + report["unrouted"] == report["deliveries"]


# --- 4: route → stop → delivery association --------------------------------------


async def test_a_routes_row_counts_only_its_own_stops_deliveries(client):
    _org, admin = await _tenant_admin(client)
    mine = await _customer(client, admin, "On R-01", "+254705000001")
    theirs = await _customer(client, admin, "On R-02", "+254705000002")
    await _route(client, admin, "R-01", [mine["id"]])
    await _route(client, admin, "R-02", [theirs["id"]])

    await _deliver(client, admin, mine["id"], DAY)

    report = await _report(client, admin)
    rows = {row["code"]: row for row in report["by_route"]}
    assert rows["R-01"]["deliveries"] == 1
    assert rows["R-02"]["deliveries"] == 0
    assert rows["R-02"]["stops_with_deliveries"] == 0
    # A route that was drawn but did not run is reported with zeroes rather
    # than counted as having run.
    assert report["routes"] == 1


async def test_moving_a_stop_moves_the_report_with_it(client):
    """Read-time derivation, asserted rather than described.

    A stored `route_id` on the delivery would keep attributing this household
    to R-01 forever. The report follows the route membership instead, so it is
    right the next time anybody asks.
    """
    _org, admin = await _tenant_admin(client)
    customer = await _customer(client, admin, "Reassigned", "+254706000001")
    route_a = await _route(client, admin, "R-01", [customer["id"]])
    route_b = await _route(client, admin, "R-02", [])

    await _deliver(client, admin, customer["id"], DAY)

    before = {r["code"]: r["deliveries"] for r in (await _report(client, admin))["by_route"]}
    assert before == {"R-01": 1, "R-02": 0}

    # Move the household from one round to the other.
    assert (
        await client.put(
            f"/v1/routes/{route_a['id']}/stops", json={"customer_ids": []}, headers=admin
        )
    ).status_code == 200
    assert (
        await client.put(
            f"/v1/routes/{route_b['id']}/stops",
            json={"customer_ids": [customer["id"]]},
            headers=admin,
        )
    ).status_code == 200

    after = {r["code"]: r["deliveries"] for r in (await _report(client, admin))["by_route"]}
    assert after == {"R-01": 0, "R-02": 1}, after


# --- route-level outcome, from the delivery domain's own statuses -----------------


async def test_a_route_reports_what_is_still_outstanding(client):
    """ "Route-level success/failure where the existing state supports it".

    There is no separate route outcome to invent: a round that went out is
    `deliveries`, one still waiting is `scheduled`, and a household that took
    nothing is `skipped`.
    """
    admin, route, customers, _v, _d = await _route_env(client)
    _run, generated = await _run_and_generate(client, admin, route)
    day = date.fromisoformat(_run["business_date"])
    assert generated["created"] == 3

    # One delivered, one skipped, one left as generated.
    r = await _deliver(client, admin, customers[0]["id"], day)
    assert r.status_code in (200, 201), r.text
    r = await _deliver(client, admin, customers[1]["id"], day, status="skipped")
    assert r.status_code in (200, 201), r.text

    report = await _report(client, admin, day)
    row = report["by_route"][0]
    assert row["deliveries"] == 1
    assert row["skipped"] == 1
    assert row["scheduled"] == 1
    assert row["stops_with_deliveries"] == 3

    # A route's LITRES and MONEY count only what was delivered — DEMO-019's
    # distinction between what a round intended and what it achieved. Counting
    # the two still-outstanding rows here would report a round as having sold
    # milk that is sitting in the van.
    delivered = next(c for c in report["by_customer"] if c["customer_id"] == customers[0]["id"])
    assert Decimal(row["quantity"]) == Decimal(delivered["quantity"]), (
        row["quantity"],
        delivered["quantity"],
    )
    assert Decimal(row["amount"]) == Decimal(delivered["amount"])
    assert Decimal(row["quantity"]) < Decimal(report["planned_quantity"])


# --- 5: tenant isolation ---------------------------------------------------------


async def test_another_dairys_routes_never_appear_in_this_report(client):
    admin_a, _route_a, customers_a, _v, _d = await _route_env(client)
    for c in customers_a:
        await _deliver(client, admin_a, c["id"], DAY)

    _org_b, admin_b = await _tenant_admin_for(
        client, country="KE", slug="report-037-b", email="admin@report037b.example"
    )
    report_b = await _report(client, admin_b)
    assert report_b["by_route"] == []
    assert report_b["routes"] == 0
    assert report_b["deliveries"] == 0

    # And dairy A still sees its own.
    report_a = await _report(client, admin_a)
    assert [r["code"] for r in report_a["by_route"]] == ["R-01"]


async def test_the_report_needs_authentication(client):
    r = await client.get("/v1/deliveries/report")
    assert r.status_code == 401, r.text


# --- 9: ordering -----------------------------------------------------------------


async def test_routes_are_reported_in_code_order(client):
    _org, admin = await _tenant_admin(client)
    c = [await _customer(client, admin, f"C{i}", f"+2547070{i:05d}") for i in range(3)]
    await _route(client, admin, "R-03", [c[2]["id"]])
    await _route(client, admin, "R-01", [c[0]["id"]])
    await _route(client, admin, "R-02", [c[1]["id"]])

    report = await _report(client, admin)
    assert [row["code"] for row in report["by_route"]] == ["R-01", "R-02", "R-03"]


# --- 10-11: nothing else moved ---------------------------------------------------


async def test_the_report_moves_no_money(client):
    from platform_core.modules.billing.models import CustomerInvoice

    admin, _route, customers, _v, _d = await _route_env(client)
    for c in customers:
        await _deliver(client, admin, c["id"], DAY)

    from sqlalchemy import func, select

    async def totals():
        async with db.get_session_factory()() as session:
            invoices = await session.scalar(select(func.count()).select_from(CustomerInvoice))
            return invoices or 0

    before = await totals()
    await _report(client, admin)
    assert await totals() == before, "reading a report changed the books"


async def test_the_existing_report_figures_are_unchanged_by_the_breakdown(client):
    """DEMO-036 behaviour intact: every pre-existing field still answers.

    The route rows are additive. If adding them had changed `deliveries`,
    `planned` or the customer breakdown, this fails.
    """
    admin, route, customers, _v, _d = await _route_env(client)
    _run, _generated = await _run_and_generate(client, admin, route)
    day = date.fromisoformat(_run["business_date"])
    await _deliver(client, admin, customers[0]["id"], day)

    report = await _report(client, admin, day)

    assert report["deliveries"] == 1
    assert report["scheduled"] == 2
    assert report["planned"] == 3
    assert len(report["by_customer"]) == 1
    assert len(report["by_day"]) == 1
    assert report["currency"]
    assert report["quantity_unit"]


async def test_an_inactive_route_is_not_reported(client):
    """Retired rather than deleted — but not part of today's round either."""
    admin, route, customers, _v, _d = await _route_env(client)
    for c in customers:
        await _deliver(client, admin, c["id"], DAY)

    async with db.get_session_factory()() as session:
        from platform_core.modules.logistics.models import Route

        row = await session.get(Route, uuid.UUID(route["id"]))
        row.active = False
        await session.commit()

    report = await _report(client, admin)
    assert report["by_route"] == []
    # The deliveries themselves are untouched — they are the dairy's history.
    assert report["deliveries"] == 3
    assert report["unrouted"] == 0


async def test_the_breakdown_costs_one_extra_query_whatever_the_route_count(client):
    """A query per route would make the report's cost a function of the rounds.

    Asserted by comparing a one-route dairy with a three-route one: the same
    number of statements either way.
    """
    from tests.conftest import count_statements

    _org, admin = await _tenant_admin(client)
    c = [await _customer(client, admin, f"Q{i}", f"+2547080{i:05d}") for i in range(3)]
    await _route(client, admin, "R-01", [c[0]["id"]])
    for customer in c:
        await _deliver(client, admin, customer["id"], DAY)

    _r, one_route = await count_statements(lambda: _report(client, admin))

    await _route(client, admin, "R-02", [c[1]["id"]])
    await _route(client, admin, "R-03", [c[2]["id"]])

    _r, three_routes = await count_statements(lambda: _report(client, admin))

    assert three_routes == one_route, f"{one_route} vs {three_routes} statements"
