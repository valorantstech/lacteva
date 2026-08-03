"""Pricing Matrix rows: range validation, overlap rule, continuity, events."""

import uuid

from tests.test_pricing_matrix import _card_env, _create_matrix, _publish_card


async def _matrix_env(client):
    headers, card, _ = await _card_env(client)
    matrix = await _create_matrix(client, headers, card["id"])
    return headers, card, matrix


async def _add_row(client, headers, matrix_id, from_value, to_value, price, **extra):
    r = await client.post(
        f"/v1/pricing-matrices/{matrix_id}/rows",
        json={"from_value": from_value, "to_value": to_value, "unit_price": price, **extra},
        headers=headers,
    )
    return r


# --- creation & validation ---------------------------------------------------


async def test_create_row(client, bus):
    headers, _, matrix = await _matrix_env(client)
    r = await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["sequence"] == 1 and row["active"] is True
    assert "pricing.pricing-matrix-row-created.v1" in [e.type for e in bus.published]


async def test_row_sequence_auto_increments_and_explicit_respected(client):
    headers, _, matrix = await _matrix_env(client)
    first = (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).json()
    second = (await _add_row(client, headers, matrix["id"], 4.0, 5.0, 45.0)).json()
    assert (first["sequence"], second["sequence"]) == (1, 2)
    explicit = (await _add_row(client, headers, matrix["id"], 5.0, 6.0, 50.0, sequence=10)).json()
    assert explicit["sequence"] == 10


async def test_row_invalid_range_rejected(client):
    headers, _, matrix = await _matrix_env(client)
    for from_v, to_v in ((4.0, 4.0), (5.0, 4.0)):  # empty and inverted
        r = await _add_row(client, headers, matrix["id"], from_v, to_v, 40.0)
        assert r.status_code == 422, (from_v, to_v)


async def test_row_invalid_price_rejected(client):
    headers, _, matrix = await _matrix_env(client)
    for price in (0, -5):
        r = await _add_row(client, headers, matrix["id"], 3.0, 4.0, price)
        assert r.status_code == 422, price


async def test_row_must_be_within_dimension_bounds(client):
    headers, _, matrix = await _matrix_env(client)  # FAT: 0..15
    r = await _add_row(client, headers, matrix["id"], -1.0, 4.0, 40.0)
    assert r.status_code == 409
    assert "minimum" in r.json()["extra"]
    r = await _add_row(client, headers, matrix["id"], 14.0, 16.0, 40.0)
    assert r.status_code == 409
    assert "maximum" in r.json()["extra"]


# --- overlap rule ------------------------------------------------------------


async def test_duplicate_range_rejected(client):
    headers, _, matrix = await _matrix_env(client)
    assert (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).status_code == 201
    r = await _add_row(client, headers, matrix["id"], 3.0, 4.0, 42.0)
    assert r.status_code == 409
    assert "overlaps" in r.json()["extra"]


async def test_partial_and_containing_overlaps_rejected(client):
    headers, _, matrix = await _matrix_env(client)
    assert (await _add_row(client, headers, matrix["id"], 3.0, 5.0, 40.0)).status_code == 201
    for from_v, to_v in (
        (2.0, 3.5),  # overlaps left edge
        (4.5, 6.0),  # overlaps right edge
        (2.0, 6.0),  # contains existing
        (3.5, 4.5),  # contained in existing
    ):
        r = await _add_row(client, headers, matrix["id"], from_v, to_v, 41.0)
        assert r.status_code == 409, (from_v, to_v)


async def test_adjacent_ranges_allowed_half_open(client):
    headers, _, matrix = await _matrix_env(client)
    assert (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).status_code == 201
    # [3,4) and [4,5) share the boundary value 4.0 without overlapping.
    assert (await _add_row(client, headers, matrix["id"], 4.0, 5.0, 45.0)).status_code == 201
    assert (await _add_row(client, headers, matrix["id"], 2.0, 3.0, 35.0)).status_code == 201


async def test_inactive_rows_do_not_block(client):
    headers, _, matrix = await _matrix_env(client)
    r = await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0, active=False)
    assert r.status_code == 201
    # Same range is fine because the existing row is inactive (parked data).
    assert (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 42.0)).status_code == 201


# --- update / delete ---------------------------------------------------------


async def test_update_row(client, bus):
    headers, _, matrix = await _matrix_env(client)
    row = (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).json()
    r = await client.put(
        f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}",
        json={"from_value": 3.0, "to_value": 4.5, "unit_price": 41.5, "active": True},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["to_value"] == 4.5 and r.json()["unit_price"] == 41.5
    assert "pricing.pricing-matrix-row-updated.v1" in [e.type for e in bus.published]


async def test_update_row_overlap_rejected_but_self_ok(client):
    headers, _, matrix = await _matrix_env(client)
    row = (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).json()
    assert (await _add_row(client, headers, matrix["id"], 4.0, 5.0, 45.0)).status_code == 201
    # Growing into the neighbour is rejected...
    r = await client.put(
        f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}",
        json={"from_value": 3.0, "to_value": 4.5, "unit_price": 40.0},
        headers=headers,
    )
    assert r.status_code == 409
    # ...but re-saving the same range is not blocked by itself.
    r = await client.put(
        f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}",
        json={"from_value": 3.0, "to_value": 4.0, "unit_price": 43.0},
        headers=headers,
    )
    assert r.status_code == 200


async def test_deactivated_row_frees_its_range(client):
    headers, _, matrix = await _matrix_env(client)
    row = (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).json()
    r = await client.put(
        f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}",
        json={"from_value": 3.0, "to_value": 4.0, "unit_price": 40.0, "active": False},
        headers=headers,
    )
    assert r.status_code == 200
    assert (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 42.0)).status_code == 201


async def test_delete_row(client, bus):
    headers, _, matrix = await _matrix_env(client)
    row = (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).json()
    r = await client.delete(
        f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}", headers=headers
    )
    assert r.status_code == 204
    assert "pricing.pricing-matrix-row-deleted.v1" in [e.type for e in bus.published]
    r = await client.delete(
        f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}", headers=headers
    )
    assert r.status_code == 404


async def test_row_unknown_matrix_404(client):
    headers, _, _ = await _matrix_env(client)
    r = await client.post(
        f"/v1/pricing-matrices/{uuid.uuid4()}/rows",
        json={"from_value": 3.0, "to_value": 4.0, "unit_price": 40.0},
        headers=headers,
    )
    assert r.status_code == 404


async def test_row_id_must_belong_to_matrix(client):
    headers, card, matrix = await _matrix_env(client)
    other = await _create_matrix(
        client, headers, card["id"], dimension_code="SNF", name="SNF Bands"
    )
    row = (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).json()
    r = await client.put(
        f"/v1/pricing-matrices/{other['id']}/rows/{row['id']}",
        json={"from_value": 3.0, "to_value": 4.0, "unit_price": 40.0},
        headers=headers,
    )
    assert r.status_code == 404


async def test_rows_immutable_once_card_published(client):
    headers, card, matrix = await _matrix_env(client)
    row = (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).json()
    await _publish_card(client, headers, card["id"])
    assert (await _add_row(client, headers, matrix["id"], 4.0, 5.0, 45.0)).status_code == 409
    r = await client.put(
        f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}",
        json={"from_value": 3.0, "to_value": 4.0, "unit_price": 99.0},
        headers=headers,
    )
    assert r.status_code == 409
    r = await client.delete(
        f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}", headers=headers
    )
    assert r.status_code == 409


async def test_update_row_invalid_payload_rejected(client):
    headers, _, matrix = await _matrix_env(client)
    row = (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).json()
    for body in (
        {"from_value": 4.0, "to_value": 4.0, "unit_price": 40.0},  # empty range
        {"from_value": 3.0, "to_value": 4.0, "unit_price": 0},  # non-positive price
    ):
        r = await client.put(
            f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}",
            json=body,
            headers=headers,
        )
        assert r.status_code == 422, body


# --- detail: ordering, gaps (continuity), events -----------------------------


async def test_matrix_detail_unknown_404(client):
    headers, _, _ = await _matrix_env(client)
    r = await client.get(f"/v1/pricing-matrices/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404


async def test_detail_rows_sorted_and_gaps_reported(client):
    headers, _, matrix = await _matrix_env(client)
    await _add_row(client, headers, matrix["id"], 5.0, 6.0, 50.0)
    await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)  # gap [4,5)
    await _add_row(client, headers, matrix["id"], 6.0, 7.0, 55.0)  # contiguous with [5,6)
    detail = (await client.get(f"/v1/pricing-matrices/{matrix['id']}", headers=headers)).json()
    assert [r["from_value"] for r in detail["rows"]] == [3.0, 5.0, 6.0]
    assert detail["gaps"] == [{"from_value": 4.0, "to_value": 5.0}]
    assert detail["editable"] is True
    assert detail["dimension"]["code"] == "FAT"


async def test_gaps_ignore_inactive_rows(client):
    headers, _, matrix = await _matrix_env(client)
    await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)
    await _add_row(client, headers, matrix["id"], 4.0, 5.0, 45.0, active=False)
    await _add_row(client, headers, matrix["id"], 5.0, 6.0, 50.0)
    detail = (await client.get(f"/v1/pricing-matrices/{matrix['id']}", headers=headers)).json()
    # The inactive [4,5) band does not close the hole between active bands.
    assert detail["gaps"] == [{"from_value": 4.0, "to_value": 5.0}]


async def test_full_matrix_lifecycle_emits_all_events(client, bus):
    headers, card, matrix = await _matrix_env(client)
    row = (await _add_row(client, headers, matrix["id"], 3.0, 4.0, 40.0)).json()
    await client.put(
        f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}",
        json={"from_value": 3.0, "to_value": 4.2, "unit_price": 41.0},
        headers=headers,
    )
    await client.delete(f"/v1/pricing-matrices/{matrix['id']}/rows/{row['id']}", headers=headers)
    await client.put(
        f"/v1/pricing-matrices/{matrix['id']}",
        json={"name": "Renamed", "product_code": matrix["product_code"], "dimension_code": "FAT"},
        headers=headers,
    )
    await client.delete(f"/v1/pricing-matrices/{matrix['id']}", headers=headers)
    types = {e.type for e in bus.published}
    assert {
        "pricing.pricing-matrix-created.v1",
        "pricing.pricing-matrix-updated.v1",
        "pricing.pricing-matrix-archived.v1",
        "pricing.pricing-matrix-row-created.v1",
        "pricing.pricing-matrix-row-updated.v1",
        "pricing.pricing-matrix-row-deleted.v1",
    } <= types
    created = next(e for e in bus.published if e.type == "pricing.pricing-matrix-created.v1")
    assert created.aggregate_type == "pricing_matrix"
    assert str(created.aggregate_id) == matrix["id"]
    assert created.data["rate_card_id"] == card["id"]
