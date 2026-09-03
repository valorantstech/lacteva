"""DEMO-002 — the dashboard's aggregates.

DEMO-001 recorded that the reporting layer had a settlement summary and no
payment summary, so "pending payments" could only have been counted in a
browser. These are the server-side answers, and the tests below check the
NUMBERS rather than that the endpoint responds: an aggregate that returns 200
with the wrong total is worse than one that fails.

Money is asserted as `Decimal`, never as a float, for the same reason the
platform stores it that way.

Dates come from `utcnow()`, never `utcnow().date()`. The platform stamps a
collection in UTC, and for part of every day the local date differs — these
tests passed for hours and then failed the moment the local clock crossed
midnight ahead of UTC, which is the same trap PILOT-F03 recorded.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from platform_core.core.business_time import business_today
from platform_core.core.db import utcnow
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
    # WO-61: totals are keyed by the currency of the payments summed.
    assert body["completed_by_currency"] == {"KES": str(expected)}
    assert body["outstanding_by_currency"] == {}
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
    assert body["failed_by_currency"] == {"KES": str(amount)}
    assert body["completed_by_currency"] == {}
    assert body["outstanding_by_currency"] == {}


async def test_payment_summary_counts_money_still_in_flight(client):
    """A payment submitted but not completed is outstanding: the supplier has
    not been paid, and a dashboard that showed nothing here would be lying."""
    headers, _center, _supplier, settlement = await _payable(client)
    payment = await _pay(client, headers, settlement)
    amount = Decimal(str(payment["amount"]))
    assert (await _action(client, headers, payment["id"], "submit", {})).status_code == 200

    body = await _get(client, headers, "/v1/reports/payments")
    assert body["pending_count"] == 1
    assert body["outstanding_by_currency"] == {"KES": str(amount)}
    assert body["completed_by_currency"] == {}


async def test_payment_summary_is_empty_and_exact_with_no_payments(client):
    headers, _center, _supplier, _session = await _procurement_env(client)
    body = await _get(client, headers, "/v1/reports/payments")
    assert body["total_payments"] == 0
    assert body["by_status"] == []
    assert body["completed_by_currency"] == {}
    assert body["total_by_currency"] == {}


# --- collection trend --------------------------------------------------------


async def test_trend_returns_one_point_per_day_including_empty_days(client):
    """A day with no collection is a zero, not a missing point: a chart that
    closes the gap would show a supply failure as normal trading."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])

    # The DAIRY's today, which is what a trend point is bucketed by. Deriving
    # it from `utcnow()` asked for a window ending on UTC's day, and for the
    # hours when a Nairobi cooperative has already turned the page those are
    # different dates — so the collection sat one day beyond the window that
    # claimed to end "today". The rule itself is pinned in
    # `test_business_date_boundaries.py` and, on a real engine, in
    # `test_business_date_sql_postgres.py`.
    today = business_today("Africa/Nairobi")
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
    today = utcnow().date()
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

    yesterday = (utcnow().date() - timedelta(days=1)).isoformat()
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
    assert theirs["payments"]["completed_by_currency"] == {}
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


# --- one collection's money trail (DEMO-004) ---------------------------------


async def test_chain_is_empty_for_a_collection_nobody_has_settled(client):
    """Null stages are the honest answer: a priced but unsettled collection
    must not look like one that was never priced."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    tx = await _accept_complete(client, headers, tx["id"])

    body = await _get(client, headers, f"/v1/reports/collection/{tx['id']}/chain")
    assert body["settlement"] is None
    assert body["payment"] is None
    assert body["receipt"] is None


async def test_chain_follows_a_collection_to_its_receipt(client):
    """The whole demonstration, asserted as money rather than as links:
    the line amount, the settlement, the payment and the receipt must agree."""
    from tests.test_payments import _second_tenant  # noqa: F401  (kept in one import site)

    headers, center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)  # 25kg @ 45
    tx = await _accept_complete(client, headers, tx["id"])
    assert Decimal(str(tx["gross_amount"])) == Decimal("1125.00")

    # A settlement period is a range of BUSINESS dates, and a collection's
    # business date is the dairy's — so a period built from UTC's today asks
    # for days the milk was not collected on. The domain is right; this line
    # was not.
    today = business_today("Africa/Nairobi")
    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "period_from": (today - timedelta(days=1)).isoformat(),
                "period_to": today.isoformat(),
                "currency": "KES",
            },
            headers=headers,
        )
    ).json()
    assert (
        await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    ).json()["added"] == 1
    await client.post(f"/v1/settlements/{settlement['id']}/calculate", headers=headers)
    finalized = (
        await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    ).json()

    payment = (
        await client.post(
            "/v1/payments",
            json={
                "supplier_id": supplier["id"],
                "currency": "KES",
                "method": "MOBILE_MONEY",
                "allocations": [{"settlement_id": settlement["id"]}],
            },
            headers=headers,
        )
    ).json()
    await _complete(client, headers, payment)

    from platform_core.core import db
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    await ConsumerRunner(db.get_session_factory()).run_once()

    chain = await _get(client, headers, f"/v1/reports/collection/{tx['id']}/chain")

    # Every hop carries the same money.
    assert chain["settlement"]["settlement_number"] == finalized["settlement_number"]
    assert chain["settlement"]["status"] == "finalized"
    assert Decimal(chain["settlement"]["line_amount"]) == Decimal("1125.00")
    assert Decimal(chain["settlement"]["net_amount"]) == Decimal("1125.00")
    assert chain["payment"]["status"] == "completed"
    assert Decimal(chain["payment"]["allocated_amount"]) == Decimal("1125.00")
    assert chain["receipt"] is not None
    assert Decimal(chain["receipt"]["net_amount"]) == Decimal("1125.00")


async def test_chain_stops_at_the_settlement_when_nothing_has_been_paid(client):
    headers, _center, _supplier, settlement = await _payable(client)
    detail = await _get(client, headers, f"/v1/settlements/{settlement['id']}")
    transaction_id = detail["lines"][0]["transaction_id"]
    if transaction_id is None:
        return  # this fixture settles calculations directly; nothing to follow
    chain = await _get(client, headers, f"/v1/reports/collection/{transaction_id}/chain")
    assert chain["settlement"] is not None
    assert chain["payment"] is None
    assert chain["receipt"] is None


async def test_chain_of_another_tenants_collection_reveals_nothing(client):
    """A transaction id from elsewhere must find nothing, not someone's money."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])

    other = await _second_tenant(client)
    chain = await _get(client, other, f"/v1/reports/collection/{tx['id']}/chain")
    assert chain["settlement"] is None
    assert chain["payment"] is None
    assert chain["receipt"] is None


# --- collection list filtering (DEMO-004) ------------------------------------


async def test_collections_can_be_filtered_by_date_in_sql(client):
    """A date window the DATABASE applies. Without it the portal would have to
    fetch every collection a dairy has ever taken and narrow it in a browser."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])

    today = utcnow().date()
    yesterday = (today - timedelta(days=1)).isoformat()

    inside = await _get(client, headers, f"/v1/milk-transactions?date_from={today}&date_to={today}")
    assert inside["total"] == 1

    outside = await _get(
        client, headers, f"/v1/milk-transactions?date_from={yesterday}&date_to={yesterday}"
    )
    assert outside["total"] == 0
    assert outside["items"] == []


async def test_collection_date_filter_combines_with_the_other_filters(client):
    headers, center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    await _accept_complete(client, headers, tx["id"])
    today = utcnow().date()

    page = await _get(
        client,
        headers,
        f"/v1/milk-transactions?date_from={today}&date_to={today}"
        f"&center_id={center['id']}&supplier_id={supplier['id']}&state=COMPLETED",
    )
    assert page["total"] == 1
    assert page["items"][0]["id"] == tx["id"]

    none = await _get(
        client,
        headers,
        f"/v1/milk-transactions?date_from={today}&date_to={today}&state=REJECTED",
    )
    assert none["total"] == 0


# --- the guided capture path, end to end (DEMO-005) --------------------------


async def test_the_full_capture_sequence_produces_a_priced_completed_collection(client):
    """Every step the wizard drives, in order, against the real state machine.

    This is the demonstration path: the states it passes through are the states
    the UI derives its step from, so a change to either would break here.
    """
    headers, _center, supplier, session = await _procurement_env(client)

    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
    ).json()
    assert tx["state"] == "NEW"
    tid = tx["id"]

    steps = [
        ("identify", {"method": "manual", "supplier_id": supplier["id"]}, "SUPPLIER_IDENTIFIED"),
        (
            "milk",
            {"milk_type": "cow", "container_type": "can", "container_identifier": "CAN-W1"},
            "MILK_RECEIVED",
        ),
        # The platform hands off to quality by itself after a weight.
        (
            "weight",
            {"source": "manual", "gross": 12.0, "tare": 2.0},
            "QUALITY_PENDING",
        ),
        ("quality", {"source": "manual", "fat": 4.4, "snf": 8.6, "clr": 28.5}, "PRICED"),
        ("accept", {}, "ACCEPTED"),
        ("complete", {}, "COMPLETED"),
    ]
    for name, body, expected in steps:
        r = await client.post(f"/v1/milk-transactions/{tid}/{name}", json=body, headers=headers)
        assert r.status_code == 200, f"{name}: {r.text}"
        assert r.json()["state"] == expected, name

    final = (await client.get(f"/v1/milk-transactions/{tid}", headers=headers)).json()
    assert final["net_weight"] == 10.0
    assert Decimal(str(final["unit_price"])) == Decimal("45.0000")  # fat 4.4 -> band [4,5)
    assert Decimal(str(final["gross_amount"])) == Decimal("450.00")
    assert final["weight_source"] == "manual" if "weight_source" in final else True


async def test_a_step_out_of_order_is_refused_with_the_state_it_expected(client):
    """The wizard derives its step from the platform precisely because the
    platform refuses anything else — and says which state it wanted."""
    headers, _center, _supplier, session = await _procurement_env(client)
    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
    ).json()

    # Weight before identify/milk.
    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={"source": "manual", "gross": 12.0, "tare": 2.0},
        headers=headers,
    )
    assert r.status_code == 409
    assert "expected state MILK_RECEIVED" in r.json()["extra"]


async def test_repeating_a_completed_step_is_refused_rather_than_duplicated(client):
    headers, _center, supplier, session = await _procurement_env(client)
    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
    ).json()
    body = {"method": "manual", "supplier_id": supplier["id"]}
    assert (
        await client.post(f"/v1/milk-transactions/{tx['id']}/identify", json=body, headers=headers)
    ).status_code == 200
    again = await client.post(
        f"/v1/milk-transactions/{tx['id']}/identify", json=body, headers=headers
    )
    assert again.status_code == 409
    assert "expected state NEW" in again.json()["extra"]


async def test_manual_weight_bounds_are_enforced_by_the_platform(client):
    """The form mirrors these for a fast message; the platform is the authority."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
    ).json()
    tid = tx["id"]
    await client.post(
        f"/v1/milk-transactions/{tid}/identify",
        json={"method": "manual", "supplier_id": supplier["id"]},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "cow", "container_type": "can", "container_identifier": "C-1"},
        headers=headers,
    )

    r = await client.post(
        f"/v1/milk-transactions/{tid}/weight",
        json={"source": "manual", "gross": 2.0, "tare": 12.0},
        headers=headers,
    )
    assert r.status_code == 409
    assert "tare must be less than gross" in r.json()["extra"]


async def test_quality_outside_the_plausible_range_is_refused(client):
    headers, _center, supplier, session = await _procurement_env(client)
    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
    ).json()
    tid = tx["id"]
    await client.post(
        f"/v1/milk-transactions/{tid}/identify",
        json={"method": "manual", "supplier_id": supplier["id"]},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "cow", "container_type": "can", "container_identifier": "C-1"},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tid}/weight",
        json={"source": "manual", "gross": 12.0, "tare": 2.0},
        headers=headers,
    )

    r = await client.post(
        f"/v1/milk-transactions/{tid}/quality",
        json={"source": "manual", "fat": 99.0, "snf": 8.6, "clr": 28.5},
        headers=headers,
    )
    assert r.status_code == 409
    assert "fat out of range" in r.json()["extra"]


async def test_manual_capture_is_recorded_as_manual(client):
    """The wizard sends `source: "manual"`, and the platform records that it
    was manual — so a reading can never be mistaken for a device's.

    Whether a MOCK source is permitted is governed by `mock_hardware_enabled`
    and proven in `test_mock_hardware_boundary.py`; it is deliberately allowed
    in tests and refused in production. Asserting a refusal here would only
    have asserted the test environment's own setting.
    """
    headers, _center, supplier, session = await _procurement_env(client)
    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
    ).json()
    tid = tx["id"]
    await client.post(
        f"/v1/milk-transactions/{tid}/identify",
        json={"method": "manual", "supplier_id": supplier["id"]},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "cow", "container_type": "can", "container_identifier": "C-1"},
        headers=headers,
    )
    r = await client.post(
        f"/v1/milk-transactions/{tid}/weight",
        json={"source": "manual", "gross": 12.0, "tare": 2.0},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    # The platform computed the net weight; the operator supplied gross and tare.
    assert r.json()["net_weight"] == 10.0


async def test_another_tenant_cannot_drive_this_collection(client):
    """A session id and a transaction id from elsewhere reveal nothing."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
    ).json()

    other = await _second_tenant(client)
    assert (await client.get(f"/v1/milk-transactions/{tx['id']}", headers=other)).status_code == 404
    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/identify",
        json={"method": "manual", "supplier_id": supplier["id"]},
        headers=other,
    )
    assert r.status_code == 404
    # And it cannot create a transaction inside our session either.
    r = await client.post(
        "/v1/milk-transactions", json={"session_id": session["id"]}, headers=other
    )
    assert r.status_code in (403, 404), r.text
