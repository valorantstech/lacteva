"""Transaction operations, executed (DEMO-007).

The operational transaction screen makes three claims that only a running
platform can settle:

* it can show, per row, where a collection has reached financially — and it
  does so in a FIXED number of queries, not one per row. `operational_status`
  is that promise, and the tests below drive it with real collections that are
  settled, paid and receipted;
* the capture SOURCE of every reading is visible, because a hand-entered weight
  must never be mistaken for an instrument's;
* the audit trail can be searched by the database rather than by the browser.

Everything here uses the platform's own vocabulary. No status is invented, and
the absence of a settlement is asserted as an absence rather than as a zero.
"""

import uuid
from decimal import Decimal

from tests.test_payments import _action, _pay, _second_tenant
from tests.test_procurement_e2e import _procurement_env, _run_collection


async def _completed(client, headers, session_id, supplier, **kwargs):
    """One collection driven all the way to COMPLETED."""
    tx = await _run_collection(client, headers, session_id, supplier, **kwargs)
    assert (
        await client.post(f"/v1/milk-transactions/{tx['id']}/accept", json={}, headers=headers)
    ).status_code == 200
    r = await client.post(f"/v1/milk-transactions/{tx['id']}/complete", json={}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _settled_and_paid(client):
    """A completed collection, settled, finalized, paid and receipted."""
    headers, center, supplier, session = await _procurement_env(client)
    tx = await _completed(client, headers, session["id"], supplier)

    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "period_from": "2026-08-01",
                "period_to": "2026-08-31",
                "currency": "KES",
            },
            headers=headers,
        )
    ).json()
    assert (
        await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    ).status_code == 200
    assert (
        await client.post(f"/v1/settlements/{settlement['id']}/calculate", headers=headers)
    ).status_code == 200
    r = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    assert r.status_code == 200, r.text
    settlement = r.json()

    payment = await _pay(client, headers, settlement)
    assert (await _action(client, headers, payment["id"], "submit")).status_code == 200
    assert (await _action(client, headers, payment["id"], "execute")).status_code == 200
    r = await _action(client, headers, payment["id"], "complete", {"reference": "BNK-DEMO7"})
    assert r.status_code == 200, r.text
    return headers, center, supplier, tx, settlement, r.json()


async def _status(client, headers, ids):
    query = "&".join(f"transaction_ids={i}" for i in ids)
    r = await client.get(f"/v1/reports/collection/operational-status?{query}", headers=headers)
    assert r.status_code == 200, r.text
    return {item["transaction_id"]: item for item in r.json()["items"]}


# --- the operational status the transaction list is built on ------------------


async def test_operational_status_follows_a_collection_to_its_receipt(client):
    headers, _center, _supplier, tx, settlement, payment = await _settled_and_paid(client)

    by_id = await _status(client, headers, [tx["id"]])
    row = by_id[tx["id"]]

    assert row["settlement_id"] == settlement["id"]
    assert row["settlement_number"] == settlement["settlement_number"]
    assert row["settlement_status"] == "finalized"
    assert row["payment_id"] == payment["id"]
    assert row["payment_status"] == "completed"
    # What THIS collection contributed, not the settlement total.
    assert Decimal(str(row["settled_amount"])) == Decimal(str(tx["gross_amount"]))
    # The last thing that happened to it, from its own event log.
    assert row["last_event_type"] == "TransactionCompleted"
    assert row["last_event_at"] is not None


async def test_an_unsettled_collection_reports_absence_not_zero(client):
    """A collection that has not been settled must look different from one
    settled for nothing. The portal renders these as "not settled"/"not paid",
    and it can only do that because the platform sends null."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _completed(client, headers, session["id"], supplier)

    row = (await _status(client, headers, [tx["id"]]))[tx["id"]]
    assert row["settlement_id"] is None
    assert row["settlement_status"] is None
    assert row["settled_amount"] is None
    assert row["payment_id"] is None
    assert row["receipt_id"] is None
    # It still has a history.
    assert row["last_event_type"] == "TransactionCompleted"


async def test_status_for_a_page_costs_a_fixed_number_of_queries(client):
    """The reason this endpoint exists. Ten collections must not cost ten
    round trips, and must not cost ten times the SQL either."""
    from tests.conftest import count_statements

    headers, _center, supplier, session = await _procurement_env(client)
    ids = [
        (await _completed(client, headers, session["id"], supplier, gross=20.0 + n))["id"]
        for n in range(4)
    ]

    async def one():
        return await _status(client, headers, ids[:1])

    async def four():
        return await _status(client, headers, ids)

    _r1, one_count = await count_statements(one)
    _r4, four_count = await count_statements(four)
    # Four times the rows must not mean four times the queries.
    assert four_count == one_count, (one_count, four_count)


async def test_unknown_and_foreign_ids_come_back_empty_rather_than_erroring(client):
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _completed(client, headers, session["id"], supplier)
    stranger = uuid.uuid4()

    by_id = await _status(client, headers, [tx["id"], stranger])
    assert by_id[str(stranger)]["last_event_type"] is None
    assert by_id[str(stranger)]["settlement_id"] is None
    # And the real one is unaffected by the company it kept.
    assert by_id[tx["id"]]["last_event_type"] == "TransactionCompleted"


async def test_operational_status_is_tenant_scoped(client):
    """Another organization asking about this organization's collection is told
    nothing — not 403, which would confirm the id exists."""
    headers, _center, _supplier, tx, _settlement, _payment = await _settled_and_paid(client)
    other = await _second_tenant(client)

    row = (await _status(client, other, [tx["id"]]))[tx["id"]]
    assert row["settlement_id"] is None
    assert row["payment_id"] is None
    assert row["last_event_type"] is None
    # ...while its own tenant still sees it.
    assert (await _status(client, headers, [tx["id"]]))[tx["id"]][
        "settlement_status"
    ] == "finalized"


async def test_a_cancelled_settlement_does_not_count_as_settled(client):
    """A cancelled settlement settled nothing. Reporting it on a list would be
    the same lie as reporting it on a detail page, told faster."""
    headers, center, supplier, session = await _procurement_env(client)
    tx = await _completed(client, headers, session["id"], supplier)
    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "period_from": "2026-08-01",
                "period_to": "2026-08-31",
                "currency": "KES",
            },
            headers=headers,
        )
    ).json()
    await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    r = await client.post(
        f"/v1/settlements/{settlement['id']}/cancel",
        json={"reason": "wrong period"},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    row = (await _status(client, headers, [tx["id"]]))[tx["id"]]
    assert row["settlement_id"] is None, "a cancelled settlement must not read as settled"


async def test_the_id_list_is_bounded(client):
    headers, _center, _supplier, _session = await _procurement_env(client)
    too_many = "&".join(f"transaction_ids={uuid.uuid4()}" for _ in range(101))
    r = await client.get(f"/v1/reports/collection/operational-status?{too_many}", headers=headers)
    assert r.status_code == 422


# --- capture source, finally visible ------------------------------------------


async def test_the_transaction_view_reports_how_each_reading_was_obtained(client):
    """DEMO-005 built the wizard on the rule that the UI must never imply a
    device supplied a value it did not. This is the field that makes the claim
    checkable from outside the platform."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _completed(client, headers, session["id"], supplier)

    assert tx["weight_source"] == "manual"
    assert tx["quality_source"] == "manual"
    # And the decision is attributed.
    assert tx["decided_at"] is not None
    assert tx["decided_by"] is not None

    # The same fields survive the list endpoint, which the table reads.
    page = (await client.get("/v1/milk-transactions?limit=50", headers=headers)).json()
    listed = next(t for t in page["items"] if t["id"] == tx["id"])
    assert listed["weight_source"] == "manual"
    assert listed["quality_source"] == "manual"


# --- audit search -------------------------------------------------------------


async def test_audit_is_searchable_by_the_database(client):
    """The trail used to be "the newest 100 records", filtered in a browser.
    An operations question needs the database to do the narrowing."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _completed(client, headers, session["id"], supplier)

    everything = (await client.get("/v1/audit?limit=200", headers=headers)).json()
    assert everything["total"] >= len(everything["items"])

    only_weight = (
        await client.get("/v1/audit?action=WeightCaptured&limit=50", headers=headers)
    ).json()
    assert only_weight["total"] >= 1
    assert all("WeightCaptured" in r["action"] for r in only_weight["items"])

    by_resource = (
        await client.get(
            f"/v1/audit?resource_type=milk_collection_transaction&q={tx['id']}&limit=50",
            headers=headers,
        )
    ).json()
    assert by_resource["total"] >= 1
    assert all(r["resource_id"] == tx["id"] for r in by_resource["items"])


async def test_audit_pages_rather_than_truncating(client):
    headers, _center, supplier, session = await _procurement_env(client)
    await _completed(client, headers, session["id"], supplier)

    first = (await client.get("/v1/audit?limit=5&offset=0", headers=headers)).json()
    second = (await client.get("/v1/audit?limit=5&offset=5", headers=headers)).json()
    assert first["total"] == second["total"] > 5
    assert len(first["items"]) == 5
    # Different pages, not the same five records again.
    assert {r["id"] for r in first["items"]}.isdisjoint({r["id"] for r in second["items"]})


async def test_audit_action_vocabulary_comes_from_what_happened(client):
    headers, _center, supplier, session = await _procurement_env(client)
    await _completed(client, headers, session["id"], supplier)

    actions = (await client.get("/v1/audit/actions", headers=headers)).json()
    assert "collection.transaction.WeightCaptured" in actions
    assert actions == sorted(actions)
    assert len(actions) == len(set(actions))


async def test_audit_is_tenant_scoped(client):
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _completed(client, headers, session["id"], supplier)
    other = await _second_tenant(client)

    mine = (await client.get(f"/v1/audit?q={tx['id']}&limit=50", headers=headers)).json()
    assert mine["total"] >= 1
    theirs = (await client.get(f"/v1/audit?q={tx['id']}&limit=50", headers=other)).json()
    assert theirs["total"] == 0


async def test_audit_requires_permission(client):
    from tests.conftest import register_and_login

    _, outsider = await register_and_login(client, "nobody@example.com")
    assert (await client.get("/v1/audit", headers=outsider)).status_code == 403
    assert (await client.get("/v1/audit/actions", headers=outsider)).status_code == 403
