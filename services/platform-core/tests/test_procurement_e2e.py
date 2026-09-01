"""MVP-001 — end-to-end procurement integration.

The complete journey: login -> org -> branch -> center (ready) -> session
-> supplier identification (QR) -> milk collection -> automatic pricing
(resolution + calculator) -> accept -> complete -> settlement -> collect
period -> totals -> finalize — with the audit trail and event chain
verified across every module boundary.
"""

import uuid
from decimal import Decimal

from tests.clock import month_end, month_start
from tests.test_milk_collection import _engine_fixture
from tests.test_pricing_matrix import _create_matrix, _publish_card
from tests.test_pricing_resolution import _add_bands
from tests.test_rate_cards import _assign_scope, _create_card

# WO-58. This was `THIS_MONTH = {"period_from": "2026-08-01", ...}` — named for
# one month, holding another's dates, with a comment saying it was chosen to
# "cover today". It covered today for exactly as long as today was in August.
# The period a settlement collects into must contain the collections it
# settles, and those happen on the reference date.
THIS_MONTH = {
    "period_from": month_start().isoformat(),
    "period_to": month_end().isoformat(),
}


async def _procurement_env(client, *, with_pricing=True):
    """Ready center + active supplier with QR (from the milk engine fixture),
    plus (optionally) a published rate card with FAT bands for RAW-COW-MILK."""
    headers, center, session, supplier = await _engine_fixture(client)
    if with_pricing:
        card = await _create_card(
            client, headers, code="MVP-CARD", effective_from="2026-01-01", effective_until=None
        )
        await _assign_scope(client, headers, card["id"], center["id"])  # RAW-COW-MILK
        matrix = await _create_matrix(client, headers, card["id"], name="MVP FAT Bands")
        await _add_bands(
            client, headers, matrix["id"], ((3.0, 4.0, 40.0), (4.0, 5.0, 45.0), (5.0, 6.0, 50.0))
        )
        await _publish_card(client, headers, card["id"])
    return headers, center, supplier, session


async def _run_collection(client, headers, session_id, supplier, *, fat=4.2, gross=30.0, tare=5.0):
    """Drive one transaction: create -> identify (QR) -> milk -> weight ->
    quality (triggers pricing) -> returns the priced transaction body."""
    tx = (
        await client.post("/v1/milk-transactions", json={"session_id": session_id}, headers=headers)
    ).json()
    tid = tx["id"]
    qr = (await client.get(f"/v1/suppliers/{supplier['id']}/qr", headers=headers)).json()
    r = await client.post(
        f"/v1/milk-transactions/{tid}/identify",
        json={"method": "qr", "value": qr["payload"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "cow", "container_type": "can", "container_identifier": "C-1"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/v1/milk-transactions/{tid}/weight",
        json={"source": "manual", "gross": gross, "tare": tare},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/v1/milk-transactions/{tid}/quality",
        json={"source": "manual", "fat": fat, "snf": 8.5, "clr": 28.0},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _accept_complete(client, headers, tid):
    assert (
        await client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers)
    ).status_code == 200
    r = await client.post(f"/v1/milk-transactions/{tid}/complete", headers=headers)
    assert r.status_code == 200
    return r.json()


# --- the full journey --------------------------------------------------------


async def test_full_procurement_journey(client, bus):
    headers, center, supplier, session = await _procurement_env(client)

    # Collection: fat 4.2 hits band [4,5) @ 45; net = 25kg -> 1125.00 KES.
    tx = await _run_collection(client, headers, session["id"], supplier)
    assert tx["state"] == "PRICED"
    assert tx["pricing_status"] == "priced"
    assert Decimal(str(tx["unit_price"])) == Decimal("45")
    assert Decimal(str(tx["gross_amount"])) == Decimal("1125.00")
    assert tx["currency"] == "KES"
    assert tx["calculation_id"] is not None
    assert "MVP-CARD" in tx["pricing_detail"]

    tx = await _accept_complete(client, headers, tx["id"])
    assert tx["state"] == "COMPLETED"

    # Settlement: create for the supplier + center + current period, collect.
    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "currency": "KES",
                **THIS_MONTH,
            },
            headers=headers,
        )
    ).json()
    r = await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"added": 1, "skipped": 0}

    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    line = detail["lines"][0]
    assert line["transaction_id"] == tx["id"]
    assert line["calculation_id"] == tx["calculation_id"]
    assert Decimal(str(line["gross_amount"])) == Decimal("1125.00")

    # Totals + finalize.
    r = await client.post(f"/v1/settlements/{settlement['id']}/calculate", headers=headers)
    assert Decimal(str(r.json()["net_amount"])) == Decimal("1125.00")
    r = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "finalized"

    # Event chain across all module boundaries, in one durable stream.
    types = [e.type for e in bus.published]
    for expected in (
        "collection.transaction-created.v1",
        "collection.supplier-identified.v1",
        "collection.quality-captured.v1",
        "collection.pricing-completed.v1",
        "pricing.calculated.v1",
        "collection.transaction-accepted.v1",
        "collection.transaction-completed.v1",
        "settlement.created.v1",
        "settlement.updated.v1",
        "settlement.finalized.v1",
    ):
        assert expected in types, expected

    # Audit trail persisted for every stage of the journey.
    records = (await client.get("/v1/audit?limit=200", headers=headers)).json()
    actions = {r["action"] for r in records["items"]}
    for expected in (
        "collection.session.opened",
        "collection.transaction.TransactionCreated",
        "collection.transaction.PricingCompleted",
        "collection.transaction.TransactionCompleted",
        "pricing.rate_card_published",
        "settlement.created",
        "settlement.updated",
        "settlement.finalized",
    ):
        assert expected in actions, (expected, sorted(actions))


async def test_transaction_event_log_records_pricing(client):
    headers, _, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    events = (await client.get(f"/v1/milk-transactions/{tx['id']}/events", headers=headers)).json()
    types = [e["event_type"] for e in events]
    assert "PricingRequested" in types and "PricingCompleted" in types
    completed = next(e for e in events if e["event_type"] == "PricingCompleted")
    assert completed["data"]["gross_amount"] == "1125.00"
    assert completed["data"]["calculation_id"] == tx["calculation_id"]


async def test_pricing_unavailable_never_blocks_collection(client, bus):
    headers, center, supplier, session = await _procurement_env(client, with_pricing=False)
    tx = await _run_collection(client, headers, session["id"], supplier)
    assert tx["state"] == "PRICED"
    assert tx["pricing_status"] == "pricing_unavailable"
    assert tx["unit_price"] is None and tx["calculation_id"] is None
    # The structured reason names the failing stage (here: the tenant has
    # never touched pricing, so even the dimension registry is empty).
    assert tx["pricing_detail"]
    tx = await _accept_complete(client, headers, tx["id"])
    assert tx["state"] == "COMPLETED"  # milk is perishable; the flow never blocks
    assert "collection.pricing-unavailable.v1" in [e.type for e in bus.published]

    # Unpriced transactions are not silently settled.
    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "currency": "KES",
                **THIS_MONTH,
            },
            headers=headers,
        )
    ).json()
    r = await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    assert r.json() == {"added": 0, "skipped": 0}


async def test_value_outside_bands_degrades_gracefully(client):
    headers, _, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier, fat=7.5)
    assert tx["pricing_status"] == "pricing_unavailable"
    assert "band" in tx["pricing_detail"] or "no active price band" in tx["pricing_detail"]


async def test_rejected_milk_is_never_settled(client):
    headers, center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    assert tx["pricing_status"] == "priced"
    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/reject",
        json={"reason": "adulteration suspected"},
        headers=headers,
    )
    assert r.status_code == 200
    assert (
        await client.post(f"/v1/milk-transactions/{tx['id']}/complete", headers=headers)
    ).status_code == 200

    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "currency": "KES",
                **THIS_MONTH,
            },
            headers=headers,
        )
    ).json()
    assert (
        await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    ).json() == {"added": 0, "skipped": 0}
    r = await client.post(
        f"/v1/settlements/{settlement['id']}/transactions",
        json={"transaction_id": tx["id"]},
        headers=headers,
    )
    assert r.status_code == 409
    assert "rejected" in r.json()["extra"]


async def test_add_single_transaction_and_guards(client):
    headers, center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "currency": "KES",
                **THIS_MONTH,
            },
            headers=headers,
        )
    ).json()
    # Not yet completed -> rejected with the reason.
    r = await client.post(
        f"/v1/settlements/{settlement['id']}/transactions",
        json={"transaction_id": tx["id"]},
        headers=headers,
    )
    assert r.status_code == 409 and "not COMPLETED" in r.json()["extra"]

    tx = await _accept_complete(client, headers, tx["id"])
    r = await client.post(
        f"/v1/settlements/{settlement['id']}/transactions",
        json={"transaction_id": tx["id"]},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["transaction_id"] == tx["id"]

    # Unknown transaction 404.
    r = await client.post(
        f"/v1/settlements/{settlement['id']}/transactions",
        json={"transaction_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert r.status_code == 404


async def test_collect_period_is_idempotent(client):
    headers, center, supplier, session = await _procurement_env(client)
    for _ in range(2):
        tx = await _run_collection(client, headers, session["id"], supplier)
        await _accept_complete(client, headers, tx["id"])
    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "currency": "KES",
                **THIS_MONTH,
            },
            headers=headers,
        )
    ).json()
    first = (
        await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    ).json()
    assert first == {"added": 2, "skipped": 0}
    second = (
        await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    ).json()
    assert second == {"added": 0, "skipped": 2}
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    assert len(detail["lines"]) == 2


async def test_snapshot_freezes_pricing(client):
    headers, _, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    tx = await _accept_complete(client, headers, tx["id"])
    from platform_core.core import db
    from platform_core.modules.milk_collection.models import TransactionSnapshot

    async with db.get_session_factory()() as s:
        from sqlalchemy import select

        snapshot = await s.scalar(
            select(TransactionSnapshot).where(
                TransactionSnapshot.transaction_id == uuid.UUID(tx["id"])
            )
        )
        assert snapshot.data["pricing"]["status"] == "priced"
        assert snapshot.data["pricing"]["gross_amount"] == "1125.00"
        assert snapshot.data["pricing"]["calculation_id"] == tx["calculation_id"]
