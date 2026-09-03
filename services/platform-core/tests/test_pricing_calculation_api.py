"""Pricing Calculator API (PRC-004): resolve -> calculate flow, policy
configuration, verification of the resolved band, events, permissions."""

import uuid
from decimal import Decimal

from tests.conftest import register_and_login
from tests.test_pricing_resolution import _resolution_env, _resolve


async def _resolved_row(client, headers, center_id, *, value=4.2) -> str:
    r = await _resolve(client, headers, center_id, value=value)
    assert r.status_code == 200, r.text
    return r.json()["row_id"]


async def _calculate(client, headers, row_id, *, quantity=125.5, on="2026-10-15", **extra):
    return await client.post(
        "/v1/pricing/calculate",
        json={
            "row_id": row_id,
            "quantity": quantity,
            "transaction_date": on,
            **extra,
        },
        headers=headers,
    )


def _amount(body: dict, field: str = "gross_amount") -> str:
    return str(body[field]["amount"])


# --- happy path --------------------------------------------------------------


async def test_resolve_then_calculate_flow(client):
    headers, center, card, matrix = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])  # band [4,5) @ 45
    r = await _calculate(client, headers, row_id, quantity=125.5)
    assert r.status_code == 200, r.text
    body = r.json()
    assert _amount(body) == "5647.50"  # 45.00 x 125.5
    assert Decimal(_amount(body, "unit_price")) == Decimal("45")
    assert body["currency"] == "KES"
    assert body["rounding_policy"] == "HALF_UP"
    assert body["calculator_version"] == "1.0.0"
    assert body["calculated_at"]
    assert uuid.UUID(body["calculation_id"])
    res = body["resolution"]
    assert res["rate_card_id"] == card["id"] and res["rate_card_code"] == "RES-CARD"
    assert res["matrix_id"] == matrix["id"] and res["row_id"] == row_id
    assert res["range_from"] == 4.0 and res["range_to"] == 5.0


async def test_price_comes_from_database_not_client(client):
    """The request carries only a row id — there is no way to submit a price."""
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    r = await client.post(
        "/v1/pricing/calculate",
        json={
            "row_id": row_id,
            "quantity": 10,
            "transaction_date": "2026-10-15",
            "unit_price": {"amount": "0.01", "currency": "KES"},  # ignored: unknown field
        },
        headers=headers,
    )
    assert r.status_code == 200
    assert _amount(r.json()) == "450.00"  # DB price 45, not the smuggled 0.01


async def test_zero_quantity(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    r = await _calculate(client, headers, row_id, quantity=0)
    assert r.status_code == 200
    assert _amount(r.json()) == "0.00"


async def test_negative_quantity_rejected(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    r = await _calculate(client, headers, row_id, quantity=-5)
    assert r.status_code == 422


async def test_large_quantity(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    r = await _calculate(client, headers, row_id, quantity=1_000_000_000)
    assert r.status_code == 200
    assert _amount(r.json()) == "45000000000.00"


async def test_quantity_unit_default_and_custom(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    # D-21 / WO-70: an absent unit is the ORGANISATION'S — this Kenyan tenant
    # trades in litres — never a kilogram constant. A stated unit is honoured.
    body = (await _calculate(client, headers, row_id)).json()
    assert body["quantity"]["unit"] == "litre"
    body = (await _calculate(client, headers, row_id, quantity_unit="kg")).json()
    assert body["quantity"]["unit"] == "kg"


async def test_deterministic_via_api(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    first = (await _calculate(client, headers, row_id, quantity=33.33)).json()
    second = (await _calculate(client, headers, row_id, quantity=33.33)).json()
    assert _amount(first) == _amount(second)
    assert first["trace"] == second["trace"]
    assert first["calculation_id"] != second["calculation_id"]  # identity differs, money doesn't


async def test_currency_flows_from_rate_card(client):
    from tests.test_collection_centers import _center_fixture
    from tests.test_pricing_matrix import _create_matrix, _publish_card
    from tests.test_pricing_resolution import _add_bands
    from tests.test_rate_cards import _assign_scope, _create_card

    headers, _branch, center = await _center_fixture(client)
    card = await _create_card(client, headers, code="USD-CARD", currency="USD")
    await _assign_scope(client, headers, card["id"], center["id"])
    matrix = await _create_matrix(client, headers, card["id"], name="USD FAT")
    await _add_bands(client, headers, matrix["id"], ((3.0, 4.0, 0.31),))
    await _publish_card(client, headers, card["id"])
    row_id = await _resolved_row(client, headers, center["id"], value=3.5)
    body = (await _calculate(client, headers, row_id, quantity=100)).json()
    assert body["currency"] == "USD"
    assert body["gross_amount"]["currency"] == "USD"
    assert _amount(body) == "31.00"


async def test_repeating_decimal_quantity(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    # 45 x 33.333 = 1499.985 — a tie the policy must decide, not float luck.
    body = (await _calculate(client, headers, row_id, quantity=33.333)).json()
    assert _amount(body) == "1499.99"  # HALF_UP default


# --- trace -------------------------------------------------------------------


async def test_trace_via_api(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    body = (await _calculate(client, headers, row_id, quantity=125.75)).json()
    trace = body["trace"]
    assert [s["operation"] for s in trace] == ["inputs", "normalize", "multiply", "round"]
    # The price now carries its stored scale (NUMERIC(12,4)), so the trace
    # shows the exact value used rather than a shortened float rendering.
    assert trace[2]["values"]["expression"] == "45.0000 x 125.75"
    # The RAW amount is the exact product, shown before rounding by design
    # (PRC-004). Decimal multiplication adds the scales, so a price stored at
    # NUMERIC(12,4) times a 2dp quantity gives 6 decimals — more precision on
    # the intermediate, and the rounded result below is unchanged.
    assert trace[2]["values"]["raw_amount"] == "5658.750000"
    assert trace[3]["values"]["rounded_amount"] == "5658.75"
    assert trace[3]["values"]["policy"] == "HALF_UP"


# --- rounding policy resolution ----------------------------------------------


async def test_default_policy_is_half_up(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    # 45 x 0.099 = 4.455 — tie at 2dp: HALF_UP -> 4.46
    body = (await _calculate(client, headers, row_id, quantity=0.099)).json()
    assert body["rounding_policy"] == "HALF_UP"
    assert _amount(body) == "4.46"


async def test_explicit_policy_override(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    body = (
        await _calculate(client, headers, row_id, quantity=0.099, rounding_policy="HALF_EVEN")
    ).json()
    assert body["rounding_policy"] == "HALF_EVEN"
    assert _amount(body) == "4.46"  # 4.455 -> even neighbour is 4.46
    body = (
        await _calculate(client, headers, row_id, quantity=0.099, rounding_policy="DOWN")
    ).json()
    assert body["rounding_policy"] == "DOWN"
    assert _amount(body) == "4.45"


async def test_unknown_policy_rejected(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    r = await _calculate(client, headers, row_id, rounding_policy="CEILING")
    assert r.status_code == 422


async def test_tenant_configured_policy_applies(client):
    headers, center, _, _ = await _resolution_env(client)
    r = await client.put(
        "/v1/config/pricing.rounding_policy",
        json={"value": "DOWN", "scope": "tenant"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    row_id = await _resolved_row(client, headers, center["id"])
    body = (await _calculate(client, headers, row_id, quantity=0.099)).json()
    assert body["rounding_policy"] == "DOWN"
    assert _amount(body) == "4.45"


async def test_invalid_configured_policy_is_surfaced(client):
    headers, center, _, _ = await _resolution_env(client)
    await client.put(
        "/v1/config/pricing.rounding_policy",
        json={"value": "VIBES", "scope": "tenant"},
        headers=headers,
    )
    row_id = await _resolved_row(client, headers, center["id"])
    r = await _calculate(client, headers, row_id)
    assert r.status_code == 422
    assert "not a supported rounding policy" in r.json()["extra"]["reason"]


async def test_request_override_beats_tenant_config(client):
    headers, center, _, _ = await _resolution_env(client)
    await client.put(
        "/v1/config/pricing.rounding_policy",
        json={"value": "DOWN", "scope": "tenant"},
        headers=headers,
    )
    row_id = await _resolved_row(client, headers, center["id"])
    body = (
        await _calculate(client, headers, row_id, quantity=0.099, rounding_policy="HALF_UP")
    ).json()
    assert body["rounding_policy"] == "HALF_UP" and _amount(body) == "4.46"


# --- verification of the resolved band ---------------------------------------


async def test_unknown_row_404(client):
    headers, _, _, _ = await _resolution_env(client)
    r = await _calculate(client, headers, str(uuid.uuid4()))
    assert r.status_code == 404


async def test_date_outside_card_window_rejected(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    r = await _calculate(client, headers, row_id, on="2030-01-01")
    assert r.status_code == 422
    assert "effective window" in r.json()["extra"]["reason"]


async def test_archived_card_rejected(client):
    headers, center, card, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    assert (
        await client.post(f"/v1/rate-cards/{card['id']}/archive", headers=headers)
    ).status_code == 200
    r = await _calculate(client, headers, row_id)
    assert r.status_code == 422
    assert "no longer published" in r.json()["extra"]["reason"]


async def test_deactivated_row_rejected(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    from platform_core.core import db
    from platform_core.modules.pricing.models import PricingMatrixRow

    async with db.get_session_factory()() as session:
        row = await session.get(PricingMatrixRow, uuid.UUID(row_id))
        row.active = False
        await session.commit()
    r = await _calculate(client, headers, row_id)
    assert r.status_code == 422
    assert "inactive" in r.json()["extra"]["reason"]


async def test_unpublished_card_row_rejected(client):
    """A band of a draft card must not be calculable even if its id leaks."""
    headers, _center, _, _ = await _resolution_env(client, publish=False)
    page = (await client.get("/v1/pricing-matrices", headers=headers)).json()
    detail = (
        await client.get(f"/v1/pricing-matrices/{page['items'][0]['id']}", headers=headers)
    ).json()
    row_id = detail["rows"][0]["id"]
    r = await _calculate(client, headers, row_id)
    assert r.status_code == 422


# --- events ------------------------------------------------------------------


async def test_calculated_event_emitted(client, bus):
    headers, center, card, matrix = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    body = (await _calculate(client, headers, row_id, quantity=125.5)).json()
    events = [e for e in bus.published if e.type == "pricing.calculated.v1"]
    assert len(events) == 1
    e = events[0]
    assert e.aggregate_type == "pricing_calculation"
    assert str(e.aggregate_id) == body["calculation_id"]
    assert e.data["gross_amount"] == "5647.50"
    assert Decimal(e.data["unit_price"]) == Decimal("45")
    assert e.data["quantity"] == "125.5"
    assert e.data["currency"] == "KES"
    assert e.data["rounding_policy"] == "HALF_UP"
    assert e.data["calculator_version"] == "1.0.0"
    assert e.data["rate_card_id"] == card["id"] and e.data["matrix_id"] == matrix["id"]


async def test_one_event_per_calculation(client, bus):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    await _calculate(client, headers, row_id)
    await _calculate(client, headers, row_id)
    assert len([e for e in bus.published if e.type == "pricing.calculated.v1"]) == 2


async def test_no_event_on_failed_calculation(client, bus):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    before = len([e for e in bus.published if e.type == "pricing.calculated.v1"])
    assert (await _calculate(client, headers, row_id, on="2030-01-01")).status_code == 422
    assert (await _calculate(client, headers, row_id, quantity=-1)).status_code == 422
    after = len([e for e in bus.published if e.type == "pricing.calculated.v1"])
    assert after == before


# --- API validation & permissions --------------------------------------------


async def test_calculate_requires_authentication(client):
    r = await client.post(
        "/v1/pricing/calculate",
        json={"row_id": str(uuid.uuid4()), "quantity": 1, "transaction_date": "2026-10-15"},
    )
    assert r.status_code == 401


async def test_calculate_requires_permission(client):
    await _resolution_env(client)
    _, nobody = await register_and_login(client, "calcnoperm@example.com")
    r = await client.post(
        "/v1/pricing/calculate",
        json={"row_id": str(uuid.uuid4()), "quantity": 1, "transaction_date": "2026-10-15"},
        headers=nobody,
    )
    assert r.status_code == 403


async def test_missing_fields_rejected(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    for missing in ("row_id", "quantity", "transaction_date"):
        payload = {"row_id": row_id, "quantity": 1, "transaction_date": "2026-10-15"}
        del payload[missing]
        r = await client.post("/v1/pricing/calculate", json=payload, headers=headers)
        assert r.status_code == 422, missing


async def test_non_numeric_quantity_rejected(client):
    headers, center, _, _ = await _resolution_env(client)
    row_id = await _resolved_row(client, headers, center["id"])
    r = await _calculate(client, headers, row_id, quantity="a lot")
    assert r.status_code == 422
