"""DEMO-002 — the dashboard's aggregates.

DEMO-001 recorded that the reporting layer had a settlement summary and no
payment summary, so "pending payments" could only have been counted in a
browser. These are the server-side answers, and the tests below check the
NUMBERS rather than that the endpoint responds: an aggregate that returns 200
with the wrong total is worse than one that fails.

Money is asserted as `Decimal`, never as a float, for the same reason the
platform stores it that way.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from tests.conftest import count_statements
from tests.test_payments import _action, _pay, _payable, _second_tenant
from tests.test_procurement_e2e import _accept_complete, _procurement_env, _run_collection


async def _get(client, headers, path):
    r = await client.get(path, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _complete(client, headers, payment):
    for step, body in (("submit", {}), ("execute", {}), ("complete", {"reference": "REF-1"})):
        r = await _action(client, headers, payment["id"], step, body)
        assert r.status_code == 200, r.text


async def _fail(client, headers, payment):
    for step in ("submit", "execute"):
        assert (await _action(client, headers, payment["id"], step, {})).status_code == 200
    r = await _action(client, headers, payment["id"], "fail", {"reason": "wallet unreachable"})
    assert r.status_code == 200, r.text


# --- payment summary ---------------------------------------------------------


async def test_payment_summary_counts_and_sums_each_status(client):
    """The aggregate DEMO-001 said was missing, checked against known amounts."""
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    expected = Decimal(str(payment["amount"]))
    await _complete(client, headers, payment)

    body = await _get(client, headers, "/v1/reports/payments")
    assert body["total_payments"] == 1
    assert body["completed_count"] == 1
    assert body["failed_count"] == 0
    assert Decimal(body["completed_amount"]) == expected
    assert Decimal(body["outstanding_amount"]) == Decimal("0")
    assert body["total_by_currency"] == {"KES": str(expected)}

    rows = {r["status"]: r for r in body["by_status"]}
    assert rows["completed"]["count"] == 1
    assert Decimal(rows["completed"]["amount"]) == expected
    assert rows["completed"]["currency"] == "KES"


async def test_payment_summary_separates_failed_from_outstanding(client):
    """A failed payment is money that did NOT move — it must not be counted as
    completed, and must not be hidden inside 'outstanding' either."""
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    amount = Decimal(str(payment["amount"]))
    await _fail(client, headers, payment)

    body = await _get(client, headers, "/v1/reports/payments")
    assert body["failed_count"] == 1
    assert body["completed_count"] == 0
    assert Decimal(body["failed_amount"]) == amount
    assert Decimal(body["completed_amount"]) == Decimal("0")
    assert Decimal(body["outstanding_amount"]) == Decimal("0")


async def test_payment_summary_counts_money_still_in_flight(client):
    """A payment submitted but not completed is outstanding: the supplier has
    not been paid, and a dashboard that showed nothing here would be lying."""
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    amount = Decimal(str(payment["amount"]))
    assert (await _action(client, headers, payment["id"], "submit", {})).status_code == 200

    body = await _get(client, headers, "/v1/reports/payments")
    assert body["pending_count"] == 1
    assert Decimal(body["outstanding_amount"]) == amount
    assert Decimal(body["completed_amount"]) == Decimal("0")


async def test_payment_summary_is_empty_and_exact_with_no_payments(client):
    headers, _center, _supplier, _session = await _procurement_env(client)
    body = await _get(client, headers, "/v1/reports/payments")
    assert body["total_payments"] == 0
    assert body["by_status"] == []
    assert Decimal(body["completed_amount"]) == Decimal("0")
    assert body["total_by_currency"] == {}


# --- collection trend --------------------------------------------------------


async def test_trend_returns_one_point_per_day_including_empty_days(client):
    """A day with no collection is a zero, not a missing point: a chart that
    closes the gap would show a supply failure as normal trading."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])

    today = date.today()
    start = today - timedelta(days=6)
    body = await _get(
        client,
        headers,
        f"/v1/reports/collection/trend?date_from={start}&date_to={today}",
    )
    assert len(body["points"]) == 7
    assert [p["day"] for p in body["points"]] == [
        (start + timedelta(days=i)).isoformat() for i in range(7)
    ]
    empty = body["points"][0]
    assert empty["transactions"] == 0
    assert Decimal(empty["payable_amount"]) == Decimal("0")
    # Today carries the collection: 25kg @ 45 = 1125.00.
    last = body["points"][-1]
    assert last["accepted"] == 1
    assert Decimal(last["payable_amount"]) == Decimal("1125.00")
    assert last["total_net_weight_kg"] == 25.0


async def test_trend_is_one_query_not_one_per_day(client):
    """Thirty days must not cost thirty round trips."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])
    today = date.today()
    start = today - timedelta(days=29)

    path = f"/v1/reports/collection/trend?date_from={start}&date_to={today}"
    response, statements = await count_statements(lambda: client.get(path, headers=headers))
    assert response.status_code == 200, response.text
    # Session and permission lookups dominate; the report itself is ONE grouped
    # query, so the total cannot scale with the number of days requested.
    assert statements < 12, statements


# --- rate distribution -------------------------------------------------------


async def test_rate_distribution_groups_by_the_price_actually_resolved(client):
    """Two quality bands, two rates, each with its own quantity and value."""
    headers, _center, supplier, session = await _procurement_env(client)
    a = await _run_collection(client, headers, session["id"], supplier)  # 25kg @ 45
    await _accept_complete(client, headers, a["id"])
    b = await _run_collection(
        client, headers, session["id"], supplier, fat=3.5, gross=20.0, tare=5.0
    )  # 15kg @ 40
    await _accept_complete(client, headers, b["id"])

    rows = await _get(client, headers, "/v1/reports/collection/by-rate")
    by_price = {Decimal(r["unit_price"]): r for r in rows}
    assert set(by_price) == {Decimal("40.0000"), Decimal("45.0000")}
    assert Decimal(by_price[Decimal("45.0000")]["payable_amount"]) == Decimal("1125.00")
    assert by_price[Decimal("45.0000")]["total_net_weight_kg"] == 25.0
    assert Decimal(by_price[Decimal("40.0000")]["payable_amount"]) == Decimal("600.00")
    assert by_price[Decimal("40.0000")]["total_net_weight_kg"] == 15.0


async def test_rate_distribution_excludes_rejected_milk(client):
    """Rejected milk was not bought, so it belongs to no rate band."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/reject", json={"reason": "spoiled"}, headers=headers
    )
    assert r.status_code == 200
    await client.post(f"/v1/milk-transactions/{tx['id']}/complete", headers=headers)

    assert await _get(client, headers, "/v1/reports/collection/by-rate") == []


# --- the dashboard block -----------------------------------------------------


async def test_dashboard_composes_every_block_in_one_request(client):
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])

    body = await _get(client, headers, "/v1/reports/dashboard")
    for block in ("collection", "settlements", "payments", "rate_bands", "attention"):
        assert block in body, block
    assert body["collection"]["accepted"] == 1
    assert Decimal(body["collection"]["payable_by_currency"]["KES"]) == Decimal("1125.00")
    assert body["active_suppliers"] == 1
    assert body["active_centers"] == 1
    assert body["payments"]["total_payments"] == 0


async def test_dashboard_reports_nothing_to_attend_to_when_all_is_well(client):
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])

    body = await _get(client, headers, "/v1/reports/dashboard")
    assert body["attention"] == []


async def test_dashboard_raises_real_states_and_never_invents_one(client):
    """Every attention item must correspond to a real count. A rejected
    collection produces one; nothing else does."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/reject", json={"reason": "spoiled"}, headers=headers
    )
    await client.post(f"/v1/milk-transactions/{tx['id']}/complete", headers=headers)

    body = await _get(client, headers, "/v1/reports/dashboard")
    keys = {item["key"] for item in body["attention"]}
    assert "rejected_collections" in keys
    item = next(i for i in body["attention"] if i["key"] == "rejected_collections")
    assert item["count"] == 1
    assert item["href"] == "/transactions"
    assert item["severity"] in {"warning", "critical"}
    # Nothing failed and nothing is unpriced, so those must be absent entirely
    # rather than present with a count of zero.
    assert "failed_payments" not in keys
    assert "unpriced" not in keys


async def test_dashboard_surfaces_failed_payments_as_critical(client):
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _fail(client, headers, payment)

    body = await _get(client, headers, "/v1/reports/dashboard")
    item = next(i for i in body["attention"] if i["key"] == "failed_payments")
    assert item["count"] == 1
    assert item["severity"] == "critical"
    assert item["href"] == "/payments"


# --- date range --------------------------------------------------------------


async def test_dashboard_honours_the_requested_date_range(client):
    """Yesterday's window must not contain today's collection."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    body = await _get(
        client, headers, f"/v1/reports/dashboard?date_from={yesterday}&date_to={yesterday}"
    )
    assert body["collection"]["transactions"] == 0
    assert body["rate_bands"] == []
    # Counts that are not date-bounded stay truthful.
    assert body["active_suppliers"] == 1


# --- tenant isolation --------------------------------------------------------


async def test_every_dashboard_aggregate_is_scoped_to_the_signed_in_tenant(client):
    """The critical one. Another organization's money must be invisible, and
    the tenant comes from the PRINCIPAL — a header cannot change it."""
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _complete(client, headers, payment)

    other = await _second_tenant(client)

    mine = await _get(client, headers, "/v1/reports/dashboard")
    theirs = await _get(client, other, "/v1/reports/dashboard")

    assert mine["payments"]["total_payments"] == 1
    assert theirs["payments"]["total_payments"] == 0
    assert Decimal(theirs["payments"]["completed_amount"]) == Decimal("0")
    assert theirs["collection"]["transactions"] == 0
    assert theirs["active_suppliers"] == 0
    assert theirs["rate_bands"] == []
    assert theirs["attention"] == []

    for path in (
        "/v1/reports/payments",
        "/v1/reports/collection/trend",
        "/v1/reports/collection/by-rate",
    ):
        body = await _get(client, other, path)
        if path.endswith("payments"):
            assert body["total_payments"] == 0
            assert body["total_by_currency"] == {}
        elif path.endswith("by-rate"):
            assert body == []
        else:
            assert all(p["transactions"] == 0 for p in body["points"])


async def test_a_forged_tenant_header_cannot_reach_another_organizations_totals(client):
    """A tenant-scoped token is authoritative; the header is decoration."""
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    await _complete(client, headers, payment)

    other = await _second_tenant(client)
    forged = {**other, "X-Tenant-ID": str(uuid.uuid4())}
    body = await _get(client, forged, "/v1/reports/payments")
    assert body["total_payments"] == 0


async def test_the_new_reports_require_the_reporting_permission(client):
    """PERM: a session without `reporting.read` is refused, not served a blank
    dashboard it might mistake for an empty business."""
    headers, _center, _supplier, _session = await _procurement_env(client)
    viewer = await _second_tenant(client)  # tenant-admin elsewhere, still scoped
    assert (await client.get("/v1/reports/dashboard")).status_code == 401
    assert (await client.get("/v1/reports/payments")).status_code == 401
    # A legitimate session with the permission is served.
    assert (await client.get("/v1/reports/dashboard", headers=headers)).status_code == 200
    assert (await client.get("/v1/reports/dashboard", headers=viewer)).status_code == 200
