"""Settlement Foundation (SET-001): creation, overlap rule, lines from
verified calculations, totals, search. Lifecycle deep-dive in
test_settlement_lifecycle.py."""

import uuid
from decimal import Decimal

from tests.test_pricing_resolution import _resolution_env, _resolve
from tests.test_suppliers import _create_supplier

PERIOD = {"period_from": "2026-10-01", "period_to": "2026-10-31"}


async def _settlement_env(client):
    """Published KES card + FAT bands (via _resolution_env) + a supplier +
    one draft settlement for October 2026."""
    headers, center, _card, _matrix = await _resolution_env(client)
    supplier = await _create_supplier(client, headers)
    settlement = await _create_settlement(client, headers, supplier["id"], center["id"])
    return headers, center, supplier, settlement


async def _create_settlement(client, headers, supplier_id, center_id, **overrides):
    body = {
        "supplier_id": supplier_id,
        "center_id": center_id,
        "currency": "KES",
        **PERIOD,
        **overrides,
    }
    r = await client.post("/v1/settlements", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _calculation_id(client, headers, center_id, *, quantity=100.0, on="2026-10-15"):
    """Run resolve -> calculate and return the calculation id."""
    r = await _resolve(client, headers, center_id, value=4.2, on=on)
    assert r.status_code == 200, r.text
    row_id = r.json()["row_id"]
    r = await client.post(
        "/v1/pricing/calculate",
        json={"row_id": row_id, "quantity": quantity, "transaction_date": on},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["calculation_id"]


async def _add_calculation(client, headers, settlement_id, calculation_id, **extra):
    return await client.post(
        f"/v1/settlements/{settlement_id}/calculations",
        json={"calculation_id": calculation_id, **extra},
        headers=headers,
    )


# --- creation ---------------------------------------------------------------


async def test_create_draft_settlement(client, bus):
    _headers, center, supplier, settlement = await _settlement_env(client)
    assert settlement["status"] == "draft"
    assert settlement["settlement_number"].startswith("STL-")
    assert settlement["currency"] == "KES"
    assert settlement["supplier_id"] == supplier["id"]
    assert settlement["center_id"] == center["id"]
    assert Decimal(str(settlement["gross_amount"])) == 0
    assert Decimal(str(settlement["net_amount"])) == 0
    assert settlement["line_count"] == 0
    assert "settlement.created.v1" in [e.type for e in bus.published]


async def test_create_unknown_supplier(client):
    headers, center, _, _ = await _settlement_env(client)
    r = await client.post(
        "/v1/settlements",
        json={
            "supplier_id": str(uuid.uuid4()),
            "center_id": center["id"],
            "currency": "KES",
            **PERIOD,
        },
        headers=headers,
    )
    assert r.status_code == 404


async def test_create_unknown_center(client):
    headers, _, supplier, _ = await _settlement_env(client)
    r = await client.post(
        "/v1/settlements",
        json={
            "supplier_id": supplier["id"],
            "center_id": str(uuid.uuid4()),
            "currency": "KES",
            **PERIOD,
        },
        headers=headers,
    )
    assert r.status_code == 404


async def test_invalid_period_rejected(client):
    headers, center, supplier, _ = await _settlement_env(client)
    r = await client.post(
        "/v1/settlements",
        json={
            "supplier_id": supplier["id"],
            "center_id": center["id"],
            "currency": "KES",
            "period_from": "2026-12-10",
            "period_to": "2026-12-01",
        },
        headers=headers,
    )
    assert r.status_code == 422


async def test_single_day_period_allowed(client):
    headers, center, supplier, _ = await _settlement_env(client)
    s = await _create_settlement(
        client,
        headers,
        supplier["id"],
        center["id"],
        period_from="2026-12-01",
        period_to="2026-12-01",
    )
    assert s["period_from"] == s["period_to"] == "2026-12-01"


async def test_invalid_currency_rejected(client):
    headers, center, supplier, _ = await _settlement_env(client)
    r = await client.post(
        "/v1/settlements",
        json={
            "supplier_id": supplier["id"],
            "center_id": center["id"],
            "currency": "K3S",
            "period_from": "2026-12-01",
            "period_to": "2026-12-31",
        },
        headers=headers,
    )
    assert r.status_code == 422


# --- BR-0009: supplier period overlap ----------------------------------------


async def test_overlapping_period_same_supplier_rejected(client):
    headers, center, supplier, settlement = await _settlement_env(client)
    r = await client.post(
        "/v1/settlements",
        json={
            "supplier_id": supplier["id"],
            "center_id": center["id"],
            "currency": "KES",
            "period_from": "2026-10-20",
            "period_to": "2026-11-20",
        },
        headers=headers,
    )
    assert r.status_code == 409
    assert settlement["settlement_number"] in r.json()["extra"]


async def test_shared_boundary_day_overlaps(client):
    """Closed periods: a settlement starting the day another ends overlaps."""
    headers, center, supplier, _ = await _settlement_env(client)  # ends 10-31
    r = await client.post(
        "/v1/settlements",
        json={
            "supplier_id": supplier["id"],
            "center_id": center["id"],
            "currency": "KES",
            "period_from": "2026-10-31",
            "period_to": "2026-11-30",
        },
        headers=headers,
    )
    assert r.status_code == 409


async def test_adjacent_period_allowed(client):
    headers, center, supplier, _ = await _settlement_env(client)
    s = await _create_settlement(
        client,
        headers,
        supplier["id"],
        center["id"],
        period_from="2026-11-01",
        period_to="2026-11-30",
    )
    assert s["status"] == "draft"


async def test_same_period_different_supplier_allowed(client):
    headers, center, _, _ = await _settlement_env(client)
    other = await _create_supplier(client, headers, name="Baraka Otieno")
    s = await _create_settlement(client, headers, other["id"], center["id"])
    assert s["status"] == "draft"


async def test_cancelled_settlement_releases_period(client):
    headers, center, supplier, settlement = await _settlement_env(client)
    r = await client.post(f"/v1/settlements/{settlement['id']}/cancel", json={}, headers=headers)
    assert r.status_code == 200
    replacement = await _create_settlement(client, headers, supplier["id"], center["id"])
    assert replacement["status"] == "draft"


# --- lines from verified calculations ----------------------------------------


async def test_add_calculation_builds_line_from_record(client, bus):
    headers, center, _, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"], quantity=125.5)
    r = await _add_calculation(client, headers, settlement["id"], calc_id)
    assert r.status_code == 201, r.text
    line = r.json()
    assert line["calculation_id"] == calc_id
    assert Decimal(str(line["quantity"])) == Decimal("125.5")
    assert Decimal(str(line["unit_price"])) == Decimal("45")
    assert Decimal(str(line["gross_amount"])) == Decimal("5647.50")
    assert line["transaction_date"] == "2026-10-15"
    # Trace reference = the id of the durable pricing.calculated.v1 event.
    event = next(
        e
        for e in bus.published
        if e.type == "pricing.calculated.v1" and str(e.aggregate_id) == calc_id
    )
    assert line["trace_reference"] == str(event.id)


async def test_add_unknown_calculation_404(client):
    headers, _, _, settlement = await _settlement_env(client)
    r = await _add_calculation(client, headers, settlement["id"], str(uuid.uuid4()))
    assert r.status_code == 404


async def test_add_calculation_to_unknown_settlement_404(client):
    headers, center, _, _ = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"])
    r = await _add_calculation(client, headers, str(uuid.uuid4()), calc_id)
    assert r.status_code == 404


async def test_same_calculation_twice_in_settlement_rejected(client):
    headers, center, _, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"])
    assert (await _add_calculation(client, headers, settlement["id"], calc_id)).status_code == 201
    r = await _add_calculation(client, headers, settlement["id"], calc_id)
    assert r.status_code == 409
    assert "already settled" in r.json()["extra"]


async def test_calculation_settled_elsewhere_rejected(client):
    """BR-0008: one live settlement per calculation."""
    headers, center, _supplier, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"])
    assert (await _add_calculation(client, headers, settlement["id"], calc_id)).status_code == 201
    other = await _create_supplier(client, headers, name="Other Supplier")
    second = await _create_settlement(client, headers, other["id"], center["id"])
    r = await _add_calculation(client, headers, second["id"], calc_id)
    assert r.status_code == 409


async def test_cancel_releases_calculations(client):
    headers, center, supplier, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"])
    await _add_calculation(client, headers, settlement["id"], calc_id)
    await client.post(f"/v1/settlements/{settlement['id']}/cancel", json={}, headers=headers)
    replacement = await _create_settlement(client, headers, supplier["id"], center["id"])
    r = await _add_calculation(client, headers, replacement["id"], calc_id)
    assert r.status_code == 201


async def test_currency_mismatch_rejected(client):
    headers, center, supplier, _ = await _settlement_env(client)
    usd = await _create_settlement(
        client,
        headers,
        supplier["id"],
        center["id"],
        currency="USD",
        period_from="2026-12-01",
        period_to="2026-12-31",
    )
    calc_id = await _calculation_id(client, headers, center["id"], on="2026-12-10")
    r = await _add_calculation(client, headers, usd["id"], calc_id)
    assert r.status_code == 409
    assert "currency" in r.json()["extra"]


async def test_transaction_date_outside_period_rejected(client):
    headers, center, _, settlement = await _settlement_env(client)  # October
    calc_id = await _calculation_id(client, headers, center["id"], on="2026-11-15")
    r = await _add_calculation(client, headers, settlement["id"], calc_id)
    assert r.status_code == 409
    assert "outside" in r.json()["extra"]


async def test_duplicate_transaction_reference_rejected(client):
    """BR-0012: a collection transaction settles at most once."""
    headers, center, _, settlement = await _settlement_env(client)
    tx = str(uuid.uuid4())
    first = await _calculation_id(client, headers, center["id"])
    second = await _calculation_id(client, headers, center["id"], quantity=50.0)
    assert (
        await _add_calculation(client, headers, settlement["id"], first, transaction_id=tx)
    ).status_code == 201
    r = await _add_calculation(client, headers, settlement["id"], second, transaction_id=tx)
    assert r.status_code == 409
    assert "transaction" in r.json()["extra"]


async def test_duplicate_transaction_across_settlements_rejected(client):
    headers, center, _, settlement = await _settlement_env(client)
    tx = str(uuid.uuid4())
    first = await _calculation_id(client, headers, center["id"])
    await _add_calculation(client, headers, settlement["id"], first, transaction_id=tx)
    other_supplier = await _create_supplier(client, headers, name="Other")
    second_settlement = await _create_settlement(
        client, headers, other_supplier["id"], center["id"]
    )
    second_calc = await _calculation_id(client, headers, center["id"], quantity=50.0)
    r = await _add_calculation(
        client, headers, second_settlement["id"], second_calc, transaction_id=tx
    )
    assert r.status_code == 409


async def test_lines_without_transaction_ids_can_coexist(client):
    headers, center, _, settlement = await _settlement_env(client)
    a = await _calculation_id(client, headers, center["id"])
    b = await _calculation_id(client, headers, center["id"], quantity=50.0)
    assert (await _add_calculation(client, headers, settlement["id"], a)).status_code == 201
    assert (await _add_calculation(client, headers, settlement["id"], b)).status_code == 201


async def test_remove_line(client):
    headers, center, _, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"])
    line = (await _add_calculation(client, headers, settlement["id"], calc_id)).json()
    r = await client.delete(
        f"/v1/settlements/{settlement['id']}/lines/{line['id']}", headers=headers
    )
    assert r.status_code == 204
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    assert detail["lines"] == []
    r = await client.delete(
        f"/v1/settlements/{settlement['id']}/lines/{line['id']}", headers=headers
    )
    assert r.status_code == 404


async def test_detail_lists_lines_ordered_by_date(client):
    headers, center, _, settlement = await _settlement_env(client)
    late = await _calculation_id(client, headers, center["id"], on="2026-10-20")
    early = await _calculation_id(client, headers, center["id"], on="2026-10-05", quantity=50.0)
    await _add_calculation(client, headers, settlement["id"], late)
    await _add_calculation(client, headers, settlement["id"], early)
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    assert [line["transaction_date"] for line in detail["lines"]] == [
        "2026-10-05",
        "2026-10-20",
    ]
    assert detail["settlement"]["line_count"] == 2


async def test_new_settlement_has_zero_adjustments_placeholder(client):
    _, _, _, settlement = await _settlement_env(client)
    assert Decimal(str(settlement["adjustments_amount"])) == 0
    assert settlement["period_from"] == "2026-10-01"
    assert settlement["period_to"] == "2026-10-31"
    assert settlement["finalized_at"] is None and settlement["cancelled_at"] is None


async def test_settlement_numbers_are_unique(client):
    headers, center, supplier, first = await _settlement_env(client)
    second = await _create_settlement(
        client,
        headers,
        supplier["id"],
        center["id"],
        period_from="2026-11-01",
        period_to="2026-11-30",
    )
    assert first["settlement_number"] != second["settlement_number"]


async def test_line_quantity_unit_propagates_from_calculation(client):
    headers, center, _, settlement = await _settlement_env(client)
    r = await _resolve(client, headers, center["id"], value=4.2, on="2026-10-15")
    row_id = r.json()["row_id"]
    r = await client.post(
        "/v1/pricing/calculate",
        json={
            "row_id": row_id,
            "quantity": 40,
            "quantity_unit": "litre",
            "transaction_date": "2026-10-15",
        },
        headers=headers,
    )
    calc_id = r.json()["calculation_id"]
    line = (await _add_calculation(client, headers, settlement["id"], calc_id)).json()
    assert line["quantity_unit"] == "litre"


async def test_transaction_id_stored_on_line(client):
    headers, center, _, settlement = await _settlement_env(client)
    tx = str(uuid.uuid4())
    calc_id = await _calculation_id(client, headers, center["id"])
    line = (
        await _add_calculation(client, headers, settlement["id"], calc_id, transaction_id=tx)
    ).json()
    assert line["transaction_id"] == tx


async def test_overlap_rule_is_supplier_wide_across_centers(client):
    """BR-0009 keys on supplier + period — a different center does not help."""
    headers, _branch_center, supplier, _ = await _settlement_env(client)
    centers = (await client.get("/v1/collection-centers", headers=headers)).json()["items"]
    branch_id = centers[0]["branch_id"]
    center2 = (
        await client.post(
            "/v1/collection-centers",
            json={"branch_id": branch_id, "name": "Second", "code": "KH-C9"},
            headers=headers,
        )
    ).json()
    r = await client.post(
        "/v1/settlements",
        json={
            "supplier_id": supplier["id"],
            "center_id": center2["id"],
            "currency": "KES",
            **PERIOD,
        },
        headers=headers,
    )
    assert r.status_code == 409


async def test_remove_line_of_other_settlement_404(client):
    headers, center, _supplier, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"])
    line = (await _add_calculation(client, headers, settlement["id"], calc_id)).json()
    other_supplier = await _create_supplier(client, headers, name="Other")
    other = await _create_settlement(client, headers, other_supplier["id"], center["id"])
    r = await client.delete(f"/v1/settlements/{other['id']}/lines/{line['id']}", headers=headers)
    assert r.status_code == 404


# --- search / pagination -----------------------------------------------------


async def test_search_filters(client):
    headers, center, supplier, settlement = await _settlement_env(client)
    other = await _create_supplier(client, headers, name="Baraka Otieno")
    await _create_settlement(client, headers, other["id"], center["id"])

    page = (await client.get("/v1/settlements", headers=headers)).json()
    assert page["total"] == 2
    hits = (
        await client.get(f"/v1/settlements?supplier_id={supplier['id']}", headers=headers)
    ).json()
    assert hits["total"] == 1 and hits["items"][0]["id"] == settlement["id"]
    hits = (await client.get(f"/v1/settlements?center_id={center['id']}", headers=headers)).json()
    assert hits["total"] == 2
    hits = (await client.get("/v1/settlements?status=draft", headers=headers)).json()
    assert hits["total"] == 2
    number = settlement["settlement_number"].lower()
    hits = (await client.get(f"/v1/settlements?q={number}", headers=headers)).json()
    assert hits["total"] == 1


async def test_search_by_period_date(client):
    headers, center, supplier, _ = await _settlement_env(client)  # October
    await _create_settlement(
        client,
        headers,
        supplier["id"],
        center["id"],
        period_from="2026-11-01",
        period_to="2026-11-30",
    )
    hits = (await client.get("/v1/settlements?overlapping_on=2026-10-15", headers=headers)).json()
    assert hits["total"] == 1
    hits = (await client.get("/v1/settlements?overlapping_on=2026-12-15", headers=headers)).json()
    assert hits["total"] == 0


async def test_pagination(client):
    headers, center, supplier, _ = await _settlement_env(client)
    for month in ("11", "12"):
        await _create_settlement(
            client,
            headers,
            supplier["id"],
            center["id"],
            period_from=f"2026-{month}-01",
            period_to=f"2026-{month}-28",
        )
    page = (await client.get("/v1/settlements?limit=2&offset=0", headers=headers)).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    page = (await client.get("/v1/settlements?limit=2&offset=2", headers=headers)).json()
    assert page["total"] == 3 and len(page["items"]) == 1


async def test_line_count_in_search_results(client):
    headers, center, _, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"])
    await _add_calculation(client, headers, settlement["id"], calc_id)
    page = (await client.get("/v1/settlements", headers=headers)).json()
    assert page["items"][0]["line_count"] == 1


async def test_detail_unknown_404(client):
    headers, _, _, _ = await _settlement_env(client)
    r = await client.get(f"/v1/settlements/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404
