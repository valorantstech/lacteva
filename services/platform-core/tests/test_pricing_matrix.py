"""Pricing Matrix Foundation: dimensions, matrix lifecycle, search, authz."""

import uuid
from decimal import Decimal

from tests.test_collection_centers import _center_fixture
from tests.test_org_structure import _tenant_admin
from tests.test_rate_cards import PRODUCT, _assign_scope, _create_card

DIMENSION = "FAT"


async def _card_env(client):
    """Tenant admin + center + a draft rate card with one product assigned."""
    headers, _branch, center = await _center_fixture(client)
    card = await _create_card(client, headers, code="MATRIX-CARD")
    await _assign_scope(client, headers, card["id"], center["id"])
    return headers, card, center


async def _create_matrix(client, headers, card_id, **overrides):
    body = {
        "rate_card_id": card_id,
        "name": "Cow Milk FAT Bands",
        "product_code": PRODUCT,
        "dimension_code": DIMENSION,
        **overrides,
    }
    r = await client.post("/v1/pricing-matrices", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# --- quality dimensions (configurable business data) -------------------------


async def test_dimensions_seeded_per_tenant(client):
    headers, _, _ = await _card_env(client)
    dims = (await client.get("/v1/quality-dimensions", headers=headers)).json()
    codes = {d["code"] for d in dims}
    assert {"FAT", "SNF", "CLR", "DENSITY", "PROTEIN", "MOISTURE", "ACIDITY"} <= codes
    fat = next(d for d in dims if d["code"] == "FAT")
    assert fat["min_value"] == 0.0 and fat["max_value"] == 15.0 and fat["unit"] == "%"


async def test_create_custom_dimension_and_duplicate_rejected(client):
    headers, _, _ = await _card_env(client)
    r = await client.post(
        "/v1/quality-dimensions",
        json={"code": "lactose", "name": "Lactose", "unit": "%", "min_value": 0, "max_value": 8},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "LACTOSE"  # normalized
    r = await client.post(
        "/v1/quality-dimensions",
        json={"code": "LACTOSE", "name": "Duplicate"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_dimension_invalid_bounds_rejected(client):
    headers, _, _ = await _card_env(client)
    r = await client.post(
        "/v1/quality-dimensions",
        json={"code": "BAD", "name": "Bad Bounds", "min_value": 5, "max_value": 5},
        headers=headers,
    )
    assert r.status_code == 422


async def test_custom_dimension_usable_in_matrix(client):
    headers, card, _ = await _card_env(client)
    await client.post(
        "/v1/quality-dimensions",
        json={"code": "LACTOSE", "name": "Lactose", "min_value": 0, "max_value": 8},
        headers=headers,
    )
    matrix = await _create_matrix(
        client, headers, card["id"], dimension_code="LACTOSE", name="Lactose Bands"
    )
    assert matrix["dimension_code"] == "LACTOSE"


# --- matrix creation ---------------------------------------------------------


async def test_create_matrix_on_draft_card(client, bus):
    headers, card, _ = await _card_env(client)
    matrix = await _create_matrix(client, headers, card["id"])
    assert matrix["status"] == "draft"
    assert matrix["version"] == card["version"]
    assert matrix["rate_card_code"] == "MATRIX-CARD"
    assert matrix["row_count"] == 0
    assert "pricing.pricing-matrix-created.v1" in [e.type for e in bus.published]


async def test_create_matrix_unknown_card(client):
    headers, _, _ = await _card_env(client)
    r = await client.post(
        "/v1/pricing-matrices",
        json={
            "rate_card_id": str(uuid.uuid4()),
            "name": "Orphan",
            "product_code": PRODUCT,
            "dimension_code": DIMENSION,
        },
        headers=headers,
    )
    assert r.status_code == 404


async def test_create_matrix_product_must_be_in_card_scope(client):
    headers, card, _ = await _card_env(client)
    r = await client.post(
        "/v1/pricing-matrices",
        json={
            "rate_card_id": card["id"],
            "name": "Unscoped Product",
            "product_code": "CAMEL-MILK",
            "dimension_code": DIMENSION,
        },
        headers=headers,
    )
    assert r.status_code == 409
    assert "not assigned" in r.json()["extra"]


async def test_create_matrix_unknown_dimension(client):
    headers, card, _ = await _card_env(client)
    r = await client.post(
        "/v1/pricing-matrices",
        json={
            "rate_card_id": card["id"],
            "name": "No Such Dimension",
            "product_code": PRODUCT,
            "dimension_code": "VIBES",
        },
        headers=headers,
    )
    assert r.status_code == 404


async def test_duplicate_matrix_same_product_dimension_rejected(client):
    headers, card, _ = await _card_env(client)
    await _create_matrix(client, headers, card["id"])
    r = await client.post(
        "/v1/pricing-matrices",
        json={
            "rate_card_id": card["id"],
            "name": "Duplicate",
            "product_code": PRODUCT,
            "dimension_code": DIMENSION,
        },
        headers=headers,
    )
    assert r.status_code == 409


async def test_same_product_different_dimension_allowed(client):
    headers, card, _ = await _card_env(client)
    await _create_matrix(client, headers, card["id"])
    second = await _create_matrix(
        client, headers, card["id"], dimension_code="SNF", name="SNF Bands"
    )
    assert second["dimension_code"] == "SNF"


async def test_create_matrix_blocked_when_card_not_draft(client):
    headers, card, _ = await _card_env(client)
    await client.post(f"/v1/rate-cards/{card['id']}/submit", headers=headers)
    r = await client.post(
        "/v1/pricing-matrices",
        json={
            "rate_card_id": card["id"],
            "name": "Too Late",
            "product_code": PRODUCT,
            "dimension_code": DIMENSION,
        },
        headers=headers,
    )
    assert r.status_code == 409


# --- matrix editing ----------------------------------------------------------


async def test_update_draft_matrix(client, bus):
    headers, card, _ = await _card_env(client)
    matrix = await _create_matrix(client, headers, card["id"])
    r = await client.put(
        f"/v1/pricing-matrices/{matrix['id']}",
        json={
            "name": "Renamed Bands",
            "product_code": PRODUCT,
            "product_name": "Raw Cow Milk",
            "dimension_code": DIMENSION,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed Bands"
    assert r.json()["product_name"] == "Raw Cow Milk"
    assert "pricing.pricing-matrix-updated.v1" in [e.type for e in bus.published]


async def test_update_dimension_change_blocked_with_rows(client):
    headers, card, _ = await _card_env(client)
    matrix = await _create_matrix(client, headers, card["id"])
    r = await client.post(
        f"/v1/pricing-matrices/{matrix['id']}/rows",
        json={"from_value": 3.0, "to_value": 4.0, "unit_price": 40.0},
        headers=headers,
    )
    assert r.status_code == 201
    r = await client.put(
        f"/v1/pricing-matrices/{matrix['id']}",
        json={"name": "Switch", "product_code": PRODUCT, "dimension_code": "SNF"},
        headers=headers,
    )
    assert r.status_code == 409
    assert "delete the rows first" in r.json()["extra"]


async def test_update_dimension_change_allowed_without_rows(client):
    headers, card, _ = await _card_env(client)
    matrix = await _create_matrix(client, headers, card["id"])
    r = await client.put(
        f"/v1/pricing-matrices/{matrix['id']}",
        json={"name": "Now SNF", "product_code": PRODUCT, "dimension_code": "SNF"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["dimension_code"] == "SNF"


async def test_update_to_duplicate_scope_rejected(client):
    headers, card, _ = await _card_env(client)
    await _create_matrix(client, headers, card["id"])  # FAT
    snf = await _create_matrix(client, headers, card["id"], dimension_code="SNF", name="SNF")
    r = await client.put(
        f"/v1/pricing-matrices/{snf['id']}",
        json={"name": "Collide", "product_code": PRODUCT, "dimension_code": DIMENSION},
        headers=headers,
    )
    assert r.status_code == 409


async def test_delete_draft_matrix(client, bus):
    headers, card, _ = await _card_env(client)
    matrix = await _create_matrix(client, headers, card["id"])
    await client.post(
        f"/v1/pricing-matrices/{matrix['id']}/rows",
        json={"from_value": 3.0, "to_value": 4.0, "unit_price": 40.0},
        headers=headers,
    )
    r = await client.delete(f"/v1/pricing-matrices/{matrix['id']}", headers=headers)
    assert r.status_code == 204
    r = await client.get(f"/v1/pricing-matrices/{matrix['id']}", headers=headers)
    assert r.status_code == 404
    assert "pricing.pricing-matrix-archived.v1" in [e.type for e in bus.published]


async def test_matrix_immutable_once_card_submitted(client):
    headers, card, _ = await _card_env(client)
    matrix = await _create_matrix(client, headers, card["id"])
    await client.post(f"/v1/rate-cards/{card['id']}/submit", headers=headers)
    r = await client.put(
        f"/v1/pricing-matrices/{matrix['id']}",
        json={"name": "Nope", "product_code": PRODUCT, "dimension_code": DIMENSION},
        headers=headers,
    )
    assert r.status_code == 409
    r = await client.delete(f"/v1/pricing-matrices/{matrix['id']}", headers=headers)
    assert r.status_code == 409


# --- lifecycle follows the rate card ----------------------------------------


async def _publish_card(client, headers, card_id):
    assert (
        await client.post(f"/v1/rate-cards/{card_id}/submit", headers=headers)
    ).status_code == 200
    assert (
        await client.post(f"/v1/rate-cards/{card_id}/approve", headers=headers)
    ).status_code == 200
    r = await client.post(f"/v1/rate-cards/{card_id}/publish", headers=headers)
    assert r.status_code == 200, r.text


async def test_matrix_becomes_active_on_card_publish(client, bus):
    headers, card, _ = await _card_env(client)
    matrix = await _create_matrix(client, headers, card["id"])
    await _publish_card(client, headers, card["id"])
    detail = (await client.get(f"/v1/pricing-matrices/{matrix['id']}", headers=headers)).json()
    assert detail["matrix"]["status"] == "active"
    assert detail["editable"] is False


async def test_matrix_archived_with_card(client, bus):
    headers, card, _ = await _card_env(client)
    matrix = await _create_matrix(client, headers, card["id"])
    await _publish_card(client, headers, card["id"])
    await client.post(f"/v1/rate-cards/{card['id']}/archive", headers=headers)
    detail = (await client.get(f"/v1/pricing-matrices/{matrix['id']}", headers=headers)).json()
    assert detail["matrix"]["status"] == "archived"
    assert "pricing.pricing-matrix-archived.v1" in [e.type for e in bus.published]


async def test_new_card_version_copies_matrices(client):
    headers, card, _ = await _card_env(client)
    matrix = await _create_matrix(client, headers, card["id"])
    for band in (
        {"from_value": 3.0, "to_value": 4.0, "unit_price": 40.0},
        {"from_value": 4.0, "to_value": 5.0, "unit_price": 45.0},
    ):
        r = await client.post(
            f"/v1/pricing-matrices/{matrix['id']}/rows", json=band, headers=headers
        )
        assert r.status_code == 201
    await _publish_card(client, headers, card["id"])
    v2 = (await client.post(f"/v1/rate-cards/{card['id']}/versions", headers=headers)).json()

    page = (
        await client.get(f"/v1/pricing-matrices?rate_card_id={v2['id']}", headers=headers)
    ).json()
    assert page["total"] == 1
    copy = page["items"][0]
    assert copy["status"] == "draft" and copy["version"] == 2 and copy["row_count"] == 2
    # The copy is editable; the original is untouched and still active.
    detail = (await client.get(f"/v1/pricing-matrices/{copy['id']}", headers=headers)).json()
    assert detail["editable"] is True
    assert [Decimal(r["unit_price"]) for r in detail["rows"]] == [Decimal("40"), Decimal("45")]
    original = (await client.get(f"/v1/pricing-matrices/{matrix['id']}", headers=headers)).json()
    assert original["matrix"]["status"] == "active" and original["matrix"]["row_count"] == 2


# --- search / pagination -----------------------------------------------------


async def test_search_and_filters(client):
    headers, card, _ = await _card_env(client)
    await _create_matrix(client, headers, card["id"], name="Fat Bands Cow")
    await _create_matrix(client, headers, card["id"], dimension_code="SNF", name="Snf Bands Cow")
    hits = (await client.get("/v1/pricing-matrices?q=fat", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["dimension_code"] == "FAT"
    hits = (await client.get("/v1/pricing-matrices?dimension_code=snf", headers=headers)).json()
    assert hits["total"] == 1
    hits = (
        await client.get(f"/v1/pricing-matrices?product_code={PRODUCT}", headers=headers)
    ).json()
    assert hits["total"] == 2
    hits = (await client.get("/v1/pricing-matrices?status=draft", headers=headers)).json()
    assert hits["total"] == 2
    hits = (
        await client.get(f"/v1/pricing-matrices?rate_card_id={card['id']}", headers=headers)
    ).json()
    assert hits["total"] == 2


async def test_search_by_product_name(client):
    headers, card, _ = await _card_env(client)
    await _create_matrix(client, headers, card["id"], product_name="Fresh Cow Milk", name="Bands")
    hits = (await client.get("/v1/pricing-matrices?q=fresh", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["product_name"] == "Fresh Cow Milk"


async def test_matrix_pagination(client):
    headers, card, _ = await _card_env(client)
    for dim in ("FAT", "SNF", "CLR"):
        await _create_matrix(client, headers, card["id"], dimension_code=dim, name=f"{dim} Bands")
    page = (await client.get("/v1/pricing-matrices?limit=2&offset=0", headers=headers)).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    page = (await client.get("/v1/pricing-matrices?limit=2&offset=2", headers=headers)).json()
    assert page["total"] == 3 and len(page["items"]) == 1


# --- authorization -----------------------------------------------------------


async def test_matrix_requires_authentication(client):
    r = await client.get("/v1/pricing-matrices")
    assert r.status_code == 401


async def test_viewer_reads_but_cannot_manage_matrices(client):
    org, headers = await _tenant_admin(client)
    inv = (
        await client.post(
            "/v1/invitations",
            json={"email": "viewer@kilima.example", "role_name": "tenant-viewer"},
            headers=headers,
        )
    ).json()
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv["invitation_token"],
            "password": "viewer-password-1",
            "full_name": "Read Only",
        },
    )
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "viewer@kilima.example",
                "password": "viewer-password-1",
                "tenant_id": org["id"],
            },
        )
    ).json()
    viewer = {"Authorization": f"Bearer {pair['access_token']}"}
    assert (await client.get("/v1/pricing-matrices", headers=viewer)).status_code == 200
    assert (await client.get("/v1/quality-dimensions", headers=viewer)).status_code == 200
    r = await client.post(
        "/v1/pricing-matrices",
        json={
            "rate_card_id": str(uuid.uuid4()),
            "name": "Nope",
            "product_code": PRODUCT,
            "dimension_code": DIMENSION,
        },
        headers=viewer,
    )
    assert r.status_code == 403
    r = await client.post(
        "/v1/quality-dimensions", json={"code": "X9", "name": "Nope"}, headers=viewer
    )
    assert r.status_code == 403
