"""Pricing Resolution Engine (PRC-003): exactly-one selection, structured
failures, boundaries, integrity, permissions, and query-count bounds."""

import uuid

from sqlalchemy import update

from tests.conftest import count_statements, register_and_login
from tests.test_collection_centers import _center_fixture
from tests.test_pricing_matrix import _create_matrix, _publish_card
from tests.test_rate_cards import PRODUCT, _assign_scope, _create_card

BANDS = ((3.0, 4.0, 40.0), (4.0, 5.0, 45.0), (5.0, 6.0, 50.0))


async def _add_bands(client, headers, matrix_id, bands):
    for from_value, to_value, price in bands:
        r = await client.post(
            f"/v1/pricing-matrices/{matrix_id}/rows",
            json={"from_value": from_value, "to_value": to_value, "unit_price": price},
            headers=headers,
        )
        assert r.status_code == 201, r.text


async def _resolution_env(client, *, bands=BANDS, effective_until="2027-08-31", publish=True):
    """Center + published RES-CARD (KES, from 2026-09-01) + FAT matrix with bands."""
    headers, _branch, center = await _center_fixture(client)
    card = await _create_card(client, headers, code="RES-CARD", effective_until=effective_until)
    await _assign_scope(client, headers, card["id"], center["id"])
    matrix = await _create_matrix(client, headers, card["id"], name="FAT Bands")
    await _add_bands(client, headers, matrix["id"], bands)
    if publish:
        await _publish_card(client, headers, card["id"])
    return headers, center, card, matrix


async def _resolve(
    client,
    headers,
    center_id,
    *,
    product=PRODUCT,
    on="2026-10-15",
    dimension="FAT",
    value=4.2,
):
    return await client.post(
        "/v1/pricing/resolve",
        json={
            "center_id": center_id,
            "product_code": product,
            "transaction_date": on,
            "dimension_code": dimension,
            "value": value,
        },
        headers=headers,
    )


def _price(body: dict) -> float:
    return float(str(body["unit_price"]["amount"]))


# --- correct resolution ------------------------------------------------------


async def test_resolves_matching_band(client):
    headers, center, card, matrix = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], value=4.2)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rate_card_id"] == card["id"]
    assert body["rate_card_code"] == "RES-CARD" and body["rate_card_version"] == 1
    assert body["matrix_id"] == matrix["id"] and body["matrix_name"] == "FAT Bands"
    assert body["matching_range"] == {"from_value": 4.0, "to_value": 5.0}
    assert _price(body) == 45.0
    assert body["unit_price"]["currency"] == "KES"


async def test_resolves_first_band(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], value=3.5)
    assert r.status_code == 200 and _price(r.json()) == 40.0


async def test_resolves_third_band(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], value=5.5)
    assert r.status_code == 200 and _price(r.json()) == 50.0


async def test_lower_boundary_inclusive(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], value=3.0)
    assert r.status_code == 200 and _price(r.json()) == 40.0


async def test_shared_boundary_belongs_to_upper_band(client):
    """Half-open [from, to): the value 4.0 is NOT in [3,4) but IS in [4,5)."""
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], value=4.0)
    assert r.status_code == 200 and _price(r.json()) == 45.0


async def test_upper_boundary_exclusive(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], value=6.0)
    assert r.status_code == 422
    assert r.json()["extra"]["stage"] == "band"


async def test_value_below_all_bands(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], value=2.0)
    assert r.status_code == 422 and r.json()["extra"]["stage"] == "band"


async def test_value_near_boundary_stays_in_lower_band(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], value=3.9999)
    assert r.status_code == 200 and _price(r.json()) == 40.0


async def test_value_at_dimension_minimum(client):
    headers, center, _, _ = await _resolution_env(client, bands=((0.0, 1.0, 10.0),))
    r = await _resolve(client, headers, center["id"], value=0.0)
    assert r.status_code == 200 and _price(r.json()) == 10.0


async def test_effective_from_date_inclusive(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], on="2026-09-01")
    assert r.status_code == 200


async def test_effective_until_date_inclusive(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], on="2027-08-31")
    assert r.status_code == 200


async def test_open_ended_card_matches_far_future(client):
    headers, center, _, _ = await _resolution_env(client, effective_until=None)
    r = await _resolve(client, headers, center["id"], on="2031-01-01")
    assert r.status_code == 200


async def test_metadata_and_reading(client):
    headers, center, _, _ = await _resolution_env(client)
    body = (await _resolve(client, headers, center["id"], value=4.2)).json()
    meta = body["metadata"]
    assert meta["strategy"] == "single-query"
    assert meta["effective_from"] == "2026-09-01"
    assert meta["effective_until"] == "2027-08-31"
    assert meta["dimension_code"] == "FAT" and meta["dimension_name"] == "Fat"
    assert meta["product_code"] == PRODUCT
    assert meta["center_id"] == center["id"]
    assert "resolved_at" in meta
    assert body["reading"] == {"value": 4.2, "unit": "%", "precision": 2}


async def test_money_value_object_fields(client):
    headers, center, _, _ = await _resolution_env(client)
    price = (await _resolve(client, headers, center["id"], value=4.2)).json()["unit_price"]
    assert price["currency"] == "KES"
    assert price["precision"] == 2
    assert price["rounding_policy"] == "unspecified"  # PRC-004 defines the policy


async def test_row_identity_fields(client):
    headers, center, _, matrix = await _resolution_env(client)
    body = (await _resolve(client, headers, center["id"], value=4.2)).json()
    detail = (await client.get(f"/v1/pricing-matrices/{matrix['id']}", headers=headers)).json()
    matched = next(r for r in detail["rows"] if r["from_value"] == 4.0)
    assert body["row_id"] == matched["id"]
    assert body["row_sequence"] == matched["sequence"]


async def test_resolution_is_deterministic(client):
    headers, center, _, _ = await _resolution_env(client)
    first = (await _resolve(client, headers, center["id"], value=4.2)).json()
    second = (await _resolve(client, headers, center["id"], value=4.2)).json()
    assert first["row_id"] == second["row_id"]
    assert _price(first) == _price(second)


async def test_resolution_emits_no_events(client, bus):
    headers, center, _, _ = await _resolution_env(client)
    before = len(bus.published)
    assert (await _resolve(client, headers, center["id"], value=4.2)).status_code == 200
    assert (await _resolve(client, headers, center["id"], value=99.0)).status_code == 422
    assert len(bus.published) == before  # read-side only: no events, ever


# --- structured no-match failures --------------------------------------------


async def test_unknown_center_fails_at_rate_card_stage(client):
    headers, _, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, str(uuid.uuid4()))
    assert r.status_code == 422
    assert r.json()["extra"]["stage"] == "rate_card"


async def test_unassigned_product_fails_at_rate_card_stage(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], product="GOAT-MILK")
    assert r.status_code == 422 and r.json()["extra"]["stage"] == "rate_card"


async def test_date_before_window(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], on="2026-08-15")
    assert r.status_code == 422 and r.json()["extra"]["stage"] == "rate_card"


async def test_date_after_window(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], on="2027-09-15")
    assert r.status_code == 422 and r.json()["extra"]["stage"] == "rate_card"


async def test_unpublished_card_never_matches(client):
    headers, center, _, _ = await _resolution_env(client, publish=False)
    r = await _resolve(client, headers, center["id"])
    assert r.status_code == 422 and r.json()["extra"]["stage"] == "rate_card"


async def test_archived_card_never_matches(client):
    headers, center, card, _ = await _resolution_env(client)
    assert (
        await client.post(f"/v1/rate-cards/{card['id']}/archive", headers=headers)
    ).status_code == 200
    r = await _resolve(client, headers, center["id"])
    assert r.status_code == 422 and r.json()["extra"]["stage"] == "rate_card"


async def test_unknown_dimension_stage(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], dimension="VIBES")
    assert r.status_code == 422 and r.json()["extra"]["stage"] == "dimension"


async def test_dimension_without_matrix_stage(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], dimension="SNF", value=8.0)
    assert r.status_code == 422
    extra = r.json()["extra"]
    assert extra["stage"] == "matrix"
    assert "RES-CARD" in extra["reason"]


async def test_second_product_without_matrix_fails_at_matrix_stage(client):
    headers, _branch, center = await _center_fixture(client)
    card = await _create_card(client, headers, code="TWO-PROD")
    await _assign_scope(client, headers, card["id"], center["id"])
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/products",
        json={"product_code": "GOAT-MILK"},
        headers=headers,
    )
    assert r.status_code == 201
    matrix = await _create_matrix(client, headers, card["id"])
    await _add_bands(client, headers, matrix["id"], BANDS)
    await _publish_card(client, headers, card["id"])
    r = await _resolve(client, headers, center["id"], product="GOAT-MILK", value=3.5)
    assert r.status_code == 422 and r.json()["extra"]["stage"] == "matrix"


async def test_value_in_gap_fails_at_band_stage(client):
    headers, center, _, _ = await _resolution_env(
        client, bands=((3.0, 4.0, 40.0), (5.0, 6.0, 50.0))
    )
    r = await _resolve(client, headers, center["id"], value=4.5)
    assert r.status_code == 422
    extra = r.json()["extra"]
    assert extra["stage"] == "band"
    assert "FAT Bands" in extra["reason"] and "4.5" in extra["reason"]


async def test_inactive_band_never_matches(client):
    headers, _branch, center = await _center_fixture(client)
    card = await _create_card(client, headers, code="INACTIVE")
    await _assign_scope(client, headers, card["id"], center["id"])
    matrix = await _create_matrix(client, headers, card["id"])
    r = await client.post(
        f"/v1/pricing-matrices/{matrix['id']}/rows",
        json={"from_value": 3.0, "to_value": 4.0, "unit_price": 40.0, "active": False},
        headers=headers,
    )
    assert r.status_code == 201
    await _publish_card(client, headers, card["id"])
    r = await _resolve(client, headers, center["id"], value=3.5)
    assert r.status_code == 422 and r.json()["extra"]["stage"] == "band"


async def test_no_match_error_shape(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], product="goat-milk", value=9.9)
    assert r.status_code == 422
    body = r.json()
    assert body["title"] == "pricing_no_match"
    assert body["detail"] == "No applicable pricing was found for this transaction."
    extra = body["extra"]
    assert set(extra) == {"stage", "reason", "inputs"}
    # Inputs are echoed back normalized (uppercased codes, ISO date).
    assert extra["inputs"]["product_code"] == "GOAT-MILK"
    assert extra["inputs"]["transaction_date"] == "2026-10-15"
    assert extra["inputs"]["value"] == 9.9


# --- integrity (multiple matches) --------------------------------------------


async def test_overlapping_bands_raise_integrity(client):
    """Force an overlapping active band directly in the DB (the API forbids
    it) — the engine must refuse to choose."""
    headers, center, _, matrix = await _resolution_env(client)
    from platform_core.core import db
    from platform_core.modules.pricing.models import PricingMatrixRow

    async with db.get_session_factory()() as session:
        # SEC-002: bands are tenant-owned, so a row built outside the service
        # still has to name its tenant — taken from the matrix it belongs to.
        from platform_core.modules.pricing.models import PricingMatrix

        parent = await session.get(PricingMatrix, uuid.UUID(matrix["id"]))
        session.add(
            PricingMatrixRow(
                tenant_id=parent.tenant_id,
                matrix_id=uuid.UUID(matrix["id"]),
                sequence=99,
                from_value=3.5,
                to_value=4.5,
                unit_price=99.0,
                active=True,
            )
        )
        await session.commit()
    r = await _resolve(client, headers, center["id"], value=4.2)
    assert r.status_code == 409
    body = r.json()
    assert body["title"] == "pricing_integrity"
    extra = body["extra"]
    assert extra["stage"] == "band"
    assert len(extra["candidates"]) == 2
    assert extra["inputs"]["value"] == 4.2


async def test_duplicate_published_cards_raise_integrity(client):
    """Force a second published card over the same scope (bypassing the CAS
    publish gate) — exactly-one applies to the rate card stage too."""
    headers, center, _, _ = await _resolution_env(client)
    second = await _create_card(client, headers, code="RES-DUP", effective_until="2027-08-31")
    await _assign_scope(client, headers, second["id"], center["id"])
    from platform_core.core import db
    from platform_core.modules.pricing.models import RateCard

    async with db.get_session_factory()() as session:
        await session.execute(
            update(RateCard)
            .where(RateCard.id == uuid.UUID(second["id"]))
            .values(status="published")
        )
        await session.commit()
    r = await _resolve(client, headers, center["id"], value=4.2)
    assert r.status_code == 409
    extra = r.json()["extra"]
    assert extra["stage"] == "rate_card"
    assert len(extra["candidates"]) == 2


# --- multi-scope correctness -------------------------------------------------


async def test_multi_center_card_resolves_from_both_centers(client):
    headers, _branch, center = await _center_fixture(client)
    center2 = (
        await client.post(
            "/v1/collection-centers",
            json={"branch_id": _branch["id"], "name": "Second", "code": "KH-C2"},
            headers=headers,
        )
    ).json()
    card = await _create_card(client, headers, code="BOTH")
    for c in (center, center2):
        r = await client.post(
            f"/v1/rate-cards/{card['id']}/centers", json={"center_id": c["id"]}, headers=headers
        )
        assert r.status_code == 201
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/products", json={"product_code": PRODUCT}, headers=headers
    )
    assert r.status_code == 201
    matrix = await _create_matrix(client, headers, card["id"])
    await _add_bands(client, headers, matrix["id"], BANDS)
    await _publish_card(client, headers, card["id"])
    a = (await _resolve(client, headers, center["id"], value=3.5)).json()
    b = (await _resolve(client, headers, center2["id"], value=3.5)).json()
    assert a["row_id"] == b["row_id"] and _price(a) == 40.0


async def test_multi_product_card_resolves_per_product(client):
    headers, center, card, _ = await _resolution_env(client, publish=False)
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/products",
        json={"product_code": "GOAT-MILK"},
        headers=headers,
    )
    assert r.status_code == 201
    goat = await _create_matrix(
        client, headers, card["id"], product_code="GOAT-MILK", name="Goat FAT"
    )
    await _add_bands(client, headers, goat["id"], ((3.0, 4.0, 99.0),))
    await _publish_card(client, headers, card["id"])
    cow = (await _resolve(client, headers, center["id"], value=3.5)).json()
    goat_hit = (
        await _resolve(client, headers, center["id"], product="GOAT-MILK", value=3.5)
    ).json()
    assert _price(cow) == 40.0 and _price(goat_hit) == 99.0
    assert cow["matrix_id"] != goat_hit["matrix_id"]


async def test_two_dimensions_resolve_independently(client):
    headers, center, card, _ = await _resolution_env(client, publish=False)
    snf = await _create_matrix(client, headers, card["id"], dimension_code="SNF", name="SNF Bands")
    await _add_bands(client, headers, snf["id"], ((7.0, 9.0, 20.0),))
    await _publish_card(client, headers, card["id"])
    fat = (await _resolve(client, headers, center["id"], dimension="FAT", value=3.5)).json()
    snf_hit = (await _resolve(client, headers, center["id"], dimension="SNF", value=8.0)).json()
    assert _price(fat) == 40.0 and _price(snf_hit) == 20.0
    assert fat["matrix_id"] != snf_hit["matrix_id"]


async def test_other_center_card_does_not_interfere(client):
    headers, _branch, center = await _center_fixture(client)
    center2 = (
        await client.post(
            "/v1/collection-centers",
            json={"branch_id": _branch["id"], "name": "South", "code": "KH-C2"},
            headers=headers,
        )
    ).json()
    for code, target, price in (("NORTH-C", center, 40.0), ("SOUTH-C", center2, 77.0)):
        card = await _create_card(client, headers, code=code)
        await _assign_scope(client, headers, card["id"], target["id"])
        matrix = await _create_matrix(client, headers, card["id"], name=f"{code} bands")
        await _add_bands(client, headers, matrix["id"], ((3.0, 4.0, price),))
        await _publish_card(client, headers, card["id"])
    north = (await _resolve(client, headers, center["id"], value=3.5)).json()
    south = (await _resolve(client, headers, center2["id"], value=3.5)).json()
    assert _price(north) == 40.0 and _price(south) == 77.0


async def test_new_version_resolves_with_updated_price(client):
    headers, center, card, _ = await _resolution_env(client)
    assert (
        await client.post(f"/v1/rate-cards/{card['id']}/archive", headers=headers)
    ).status_code == 200
    v2 = (await client.post(f"/v1/rate-cards/{card['id']}/versions", headers=headers)).json()
    page = (
        await client.get(f"/v1/pricing-matrices?rate_card_id={v2['id']}", headers=headers)
    ).json()
    matrix_v2 = page["items"][0]
    detail = (await client.get(f"/v1/pricing-matrices/{matrix_v2['id']}", headers=headers)).json()
    first_band = next(r for r in detail["rows"] if r["from_value"] == 3.0)
    r = await client.put(
        f"/v1/pricing-matrices/{matrix_v2['id']}/rows/{first_band['id']}",
        json={"from_value": 3.0, "to_value": 4.0, "unit_price": 42.0},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    await _publish_card(client, headers, v2["id"])
    body = (await _resolve(client, headers, center["id"], value=3.5)).json()
    assert body["rate_card_version"] == 2 and _price(body) == 42.0


async def test_case_insensitive_codes(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(
        client, headers, center["id"], product="raw-cow-milk", dimension="fat", value=3.5
    )
    assert r.status_code == 200 and _price(r.json()) == 40.0


# --- API validation & permissions --------------------------------------------


async def test_resolve_requires_authentication(client):
    r = await client.post(
        "/v1/pricing/resolve",
        json={
            "center_id": str(uuid.uuid4()),
            "product_code": PRODUCT,
            "transaction_date": "2026-10-15",
            "dimension_code": "FAT",
            "value": 4.0,
        },
    )
    assert r.status_code == 401


async def test_resolve_requires_read_permission(client):
    await _resolution_env(client)
    _, nobody = await register_and_login(client, "noperm@example.com")
    r = await client.post(
        "/v1/pricing/resolve",
        json={
            "center_id": str(uuid.uuid4()),
            "product_code": PRODUCT,
            "transaction_date": "2026-10-15",
            "dimension_code": "FAT",
            "value": 4.0,
        },
        headers=nobody,
    )
    assert r.status_code == 403


async def test_missing_fields_rejected(client):
    headers, center, _, _ = await _resolution_env(client)
    for missing in ("center_id", "product_code", "transaction_date", "dimension_code", "value"):
        payload = {
            "center_id": center["id"],
            "product_code": PRODUCT,
            "transaction_date": "2026-10-15",
            "dimension_code": "FAT",
            "value": 4.0,
        }
        del payload[missing]
        r = await client.post("/v1/pricing/resolve", json=payload, headers=headers)
        assert r.status_code == 422, missing


async def test_invalid_date_format_rejected(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], on="15/10/2026")
    assert r.status_code == 422


async def test_non_numeric_value_rejected(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await _resolve(client, headers, center["id"], value="high")
    assert r.status_code == 422


# --- repository reuse & performance ------------------------------------------


async def _tenant_id(client, headers) -> uuid.UUID:
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    return uuid.UUID(me["tenant_id"])


async def test_repository_applicable_cards_direct(client):
    """The repository is directly reusable (PRC-004 contract)."""
    import datetime

    headers, center, card, _ = await _resolution_env(client)
    tenant = await _tenant_id(client, headers)
    from platform_core.core import db
    from platform_core.modules.pricing.resolution import PricingResolutionRepository

    async with db.get_session_factory()() as session:
        repo = PricingResolutionRepository(session)
        hit = await repo.applicable_cards(
            tenant, uuid.UUID(center["id"]), PRODUCT, datetime.date(2026, 10, 15)
        )
        assert [str(c.id) for c in hit] == [card["id"]]
        miss = await repo.applicable_cards(
            tenant, uuid.UUID(center["id"]), PRODUCT, datetime.date(2030, 1, 1)
        )
        assert miss == []


async def test_repository_matching_rows_direct(client):
    _headers, _, _, matrix = await _resolution_env(client)
    from platform_core.core import db
    from platform_core.modules.pricing.resolution import PricingResolutionRepository

    async with db.get_session_factory()() as session:
        repo = PricingResolutionRepository(session)
        rows = await repo.matching_rows(uuid.UUID(matrix["id"]), 4.0)
        assert len(rows) == 1 and rows[0].unit_price == 45.0  # half-open boundary
        assert await repo.matching_rows(uuid.UUID(matrix["id"]), 6.0) == []


MANY_BANDS = tuple((i * 0.5, (i + 1) * 0.5, 10.0 + i) for i in range(30))


async def _count_selects(client, headers, center_id, *, value):
    return await count_statements(lambda: _resolve(client, headers, center_id, value=value))


async def test_query_count_bounded_regardless_of_band_count(client):
    """30 bands must cost the same queries as 3 — no N+1. The bound covers
    auth/session/permission lookups plus the 3 fixed resolution queries."""
    headers, center, _, _ = await _resolution_env(client, bands=MANY_BANDS)
    response, selects = await _count_selects(client, headers, center["id"], value=7.2)
    assert response.status_code == 200 and _price(response.json()) == 24.0
    assert selects <= 12, f"expected a fixed query budget, saw {selects} SELECTs"


async def test_failure_path_query_count_bounded(client):
    headers, center, _, _ = await _resolution_env(client, bands=MANY_BANDS)
    response, selects = await _count_selects(client, headers, center["id"], value=99.0)
    assert response.status_code == 422
    assert selects <= 13, f"diagnosis must stay bounded, saw {selects} SELECTs"
