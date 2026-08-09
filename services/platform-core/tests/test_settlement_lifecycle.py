"""Settlement lifecycle (SET-001): totals, finalize, cancel, immutability,
events, permissions."""

import uuid
from decimal import Decimal

from tests.conftest import invite, register_and_login
from tests.test_org_structure import _tenant_admin
from tests.test_settlements import (
    _add_calculation,
    _calculation_id,
    _create_settlement,
    _settlement_env,
)


async def _with_lines(client, quantities=(125.5, 50.0)):
    headers, center, supplier, settlement = await _settlement_env(client)
    for quantity in quantities:
        calc_id = await _calculation_id(client, headers, center["id"], quantity=quantity)
        r = await _add_calculation(client, headers, settlement["id"], calc_id)
        assert r.status_code == 201, r.text
    return headers, center, supplier, settlement


async def _post(client, headers, settlement_id, action, body=None):
    return await client.post(
        f"/v1/settlements/{settlement_id}/{action}",
        json=body if body is not None else {},
        headers=headers,
    )


# --- totals (BR-0011) --------------------------------------------------------


async def test_calculate_totals_sums_lines_exactly(client):
    headers, _, _, settlement = await _with_lines(client)  # 5647.50 + 2250.00
    r = await _post(client, headers, settlement["id"], "calculate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "calculated"
    assert Decimal(str(body["gross_amount"])) == Decimal("7897.50")
    assert Decimal(str(body["adjustments_amount"])) == Decimal("0.00")  # placeholder
    assert Decimal(str(body["net_amount"])) == Decimal("7897.50")


async def test_totals_precision_many_small_lines(client):
    # 3 x (45 x 0.001 = 0.045 -> HALF_UP 0.05): exact decimal sum = 0.15
    headers, _, _, settlement = await _with_lines(client, quantities=(0.001, 0.002, 0.003))
    body = (await _post(client, headers, settlement["id"], "calculate")).json()
    lines = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()[
        "lines"
    ]
    expected = sum(Decimal(str(line["gross_amount"])) for line in lines)
    assert Decimal(str(body["gross_amount"])) == expected


async def test_calculate_empty_settlement_gives_zero(client):
    headers, _, _, settlement = await _settlement_env(client)
    body = (await _post(client, headers, settlement["id"], "calculate")).json()
    assert body["status"] == "calculated"
    assert Decimal(str(body["gross_amount"])) == 0


async def test_calculate_totals_idempotent(client):
    headers, _, _, settlement = await _with_lines(client)
    first = (await _post(client, headers, settlement["id"], "calculate")).json()
    second = (await _post(client, headers, settlement["id"], "calculate")).json()
    assert first["gross_amount"] == second["gross_amount"]


async def test_line_change_reverts_to_draft(client):
    headers, center, _, settlement = await _with_lines(client)
    assert (await _post(client, headers, settlement["id"], "calculate")).status_code == 200
    calc_id = await _calculation_id(client, headers, center["id"], quantity=10.0)
    await _add_calculation(client, headers, settlement["id"], calc_id)
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    assert detail["settlement"]["status"] == "draft"  # totals stale -> recalculate


async def test_remove_line_reverts_to_draft(client):
    headers, _, _, settlement = await _with_lines(client)
    await _post(client, headers, settlement["id"], "calculate")
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    line_id = detail["lines"][0]["id"]
    await client.delete(f"/v1/settlements/{settlement['id']}/lines/{line_id}", headers=headers)
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    assert detail["settlement"]["status"] == "draft"


async def test_detail_reports_totals_match(client):
    headers, _, _, settlement = await _with_lines(client)
    await _post(client, headers, settlement["id"], "calculate")
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    assert detail["totals_match_lines"] is True


async def test_net_equals_gross_while_adjustments_placeholder(client):
    headers, _, _, settlement = await _with_lines(client)
    body = (await _post(client, headers, settlement["id"], "calculate")).json()
    assert body["net_amount"] == body["gross_amount"]
    assert Decimal(str(body["adjustments_amount"])) == 0


async def test_large_amounts_sum_exactly(client):
    headers, _, _, settlement = await _with_lines(client, quantities=(1_000_000_000.0,))
    body = (await _post(client, headers, settlement["id"], "calculate")).json()
    assert Decimal(str(body["gross_amount"])) == Decimal("45000000000.00")


async def test_zero_quantity_line_included(client):
    headers, _, _, settlement = await _with_lines(client, quantities=(0.0, 10.0))
    body = (await _post(client, headers, settlement["id"], "calculate")).json()
    assert Decimal(str(body["gross_amount"])) == Decimal("450.00")  # 0.00 + 450.00


async def test_detail_flags_totals_mismatch_after_tamper(client):
    headers, _, _, settlement = await _with_lines(client)
    await _post(client, headers, settlement["id"], "calculate")
    from platform_core.core import db
    from platform_core.modules.settlement.models import SettlementLine

    async with db.get_session_factory()() as session:
        from sqlalchemy import select

        line = (
            await session.scalars(
                select(SettlementLine).where(
                    SettlementLine.settlement_id == uuid.UUID(settlement["id"])
                )
            )
        ).first()
        line.gross_amount = Decimal("123456.78")
        await session.commit()
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    assert detail["totals_match_lines"] is False  # review screens surface this


# --- finalize ----------------------------------------------------------------


async def test_finalize_happy_path(client, bus):
    headers, _, _, settlement = await _with_lines(client)
    await _post(client, headers, settlement["id"], "calculate")
    r = await _post(client, headers, settlement["id"], "finalize")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "finalized"
    assert body["finalized_at"] is not None
    events = [e for e in bus.published if e.type == "settlement.finalized.v1"]
    assert len(events) == 1
    assert events[0].data["gross_amount"] == "7897.50"
    assert events[0].data["line_count"] == 2


async def test_finalize_requires_calculated(client):
    headers, _, _, settlement = await _with_lines(client)
    r = await _post(client, headers, settlement["id"], "finalize")
    assert r.status_code == 409  # still draft — calculate first


async def test_finalize_requires_lines(client):
    headers, _, _, settlement = await _settlement_env(client)
    await _post(client, headers, settlement["id"], "calculate")
    r = await _post(client, headers, settlement["id"], "finalize")
    assert r.status_code == 409
    assert "no lines" in r.json()["extra"]


async def test_finalize_integrity_gate_detects_tampered_lines(client):
    """BR-0011 is re-verified at finalize: stored totals must equal lines."""
    headers, _, _, settlement = await _with_lines(client)
    await _post(client, headers, settlement["id"], "calculate")
    from platform_core.core import db
    from platform_core.modules.settlement.models import SettlementLine

    async with db.get_session_factory()() as session:
        from sqlalchemy import select

        line = (
            await session.scalars(
                select(SettlementLine).where(
                    SettlementLine.settlement_id == uuid.UUID(settlement["id"])
                )
            )
        ).first()
        line.gross_amount = Decimal("999999.99")
        await session.commit()
    r = await _post(client, headers, settlement["id"], "finalize")
    assert r.status_code == 409
    assert "no longer match" in r.json()["extra"]


# --- BR-0010: finalized is immutable -----------------------------------------


async def test_finalized_settlement_is_immutable(client):
    headers, center, _, settlement = await _with_lines(client)
    await _post(client, headers, settlement["id"], "calculate")
    assert (await _post(client, headers, settlement["id"], "finalize")).status_code == 200

    calc_id = await _calculation_id(client, headers, center["id"], quantity=1.0)
    assert (await _add_calculation(client, headers, settlement["id"], calc_id)).status_code == 409
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    line_id = detail["lines"][0]["id"]
    r = await client.delete(f"/v1/settlements/{settlement['id']}/lines/{line_id}", headers=headers)
    assert r.status_code == 409
    assert (await _post(client, headers, settlement["id"], "calculate")).status_code == 409
    assert (await _post(client, headers, settlement["id"], "finalize")).status_code == 409
    assert (await _post(client, headers, settlement["id"], "cancel")).status_code == 409


async def test_finalized_calculation_stays_settled(client):
    """Finalization locks the calculation permanently (only cancel releases)."""
    headers, center, _, settlement = await _with_lines(client, quantities=(10.0,))
    await _post(client, headers, settlement["id"], "calculate")
    await _post(client, headers, settlement["id"], "finalize")
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    calc_id = detail["lines"][0]["calculation_id"]
    from tests.test_suppliers import _create_supplier

    other = await _create_supplier(client, headers, name="Other")
    second = await _create_settlement(client, headers, other["id"], center["id"])
    r = await _add_calculation(client, headers, second["id"], calc_id)
    assert r.status_code == 409


async def test_finalized_status_searchable(client):
    headers, _, _, settlement = await _with_lines(client, quantities=(10.0,))
    await _post(client, headers, settlement["id"], "calculate")
    await _post(client, headers, settlement["id"], "finalize")
    hits = (await client.get("/v1/settlements?status=finalized", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["id"] == settlement["id"]


# --- cancel ------------------------------------------------------------------


async def test_cancel_preserves_history(client, bus):
    headers, _, _, settlement = await _with_lines(client)
    r = await _post(client, headers, settlement["id"], "cancel", {"reason": "wrong period"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "cancelled" and body["cancelled_at"] is not None
    # History preserved: lines still visible, settlement still searchable.
    detail = (await client.get(f"/v1/settlements/{settlement['id']}", headers=headers)).json()
    assert len(detail["lines"]) == 2
    hits = (await client.get("/v1/settlements?status=cancelled", headers=headers)).json()
    assert hits["total"] == 1
    event = next(e for e in bus.published if e.type == "settlement.cancelled.v1")
    assert event.data["reason"] == "wrong period"


async def test_cancel_calculated_settlement(client):
    headers, _, _, settlement = await _with_lines(client)
    await _post(client, headers, settlement["id"], "calculate")
    assert (await _post(client, headers, settlement["id"], "cancel")).status_code == 200


async def test_cancel_twice_rejected(client):
    headers, _, _, settlement = await _settlement_env(client)
    assert (await _post(client, headers, settlement["id"], "cancel")).status_code == 200
    assert (await _post(client, headers, settlement["id"], "cancel")).status_code == 409


async def test_cancelled_settlement_rejects_lines(client):
    headers, center, _, settlement = await _settlement_env(client)
    await _post(client, headers, settlement["id"], "cancel")
    calc_id = await _calculation_id(client, headers, center["id"])
    r = await _add_calculation(client, headers, settlement["id"], calc_id)
    assert r.status_code == 409


# --- events ------------------------------------------------------------------


async def test_lifecycle_events_emitted(client, bus):
    headers, _, _, settlement = await _with_lines(client, quantities=(10.0,))
    await _post(client, headers, settlement["id"], "calculate")
    await _post(client, headers, settlement["id"], "finalize")
    types = [e.type for e in bus.published]
    assert "settlement.created.v1" in types
    assert "settlement.updated.v1" in types  # line adds + totals
    assert "settlement.finalized.v1" in types
    created = next(e for e in bus.published if e.type == "settlement.created.v1")
    assert created.aggregate_type == "settlement"
    assert str(created.aggregate_id) == settlement["id"]
    assert created.data["settlement_number"] == settlement["settlement_number"]


async def test_no_finalize_event_on_failure(client, bus):
    headers, _, _, settlement = await _with_lines(client)
    assert (await _post(client, headers, settlement["id"], "finalize")).status_code == 409
    assert "settlement.finalized.v1" not in [e.type for e in bus.published]


async def test_updated_event_on_totals(client, bus):
    headers, _, _, settlement = await _with_lines(client, quantities=(10.0,))
    await _post(client, headers, settlement["id"], "calculate")
    updated = [e for e in bus.published if e.type == "settlement.updated.v1"]
    totals_events = [e for e in updated if e.data.get("totals_calculated")]
    assert len(totals_events) == 1
    assert totals_events[0].data["gross_amount"] == "450.00"


# --- permissions & validation ------------------------------------------------


async def test_requires_authentication(client):
    assert (await client.get("/v1/settlements")).status_code == 401


async def test_requires_permission(client):
    await _settlement_env(client)
    _, nobody = await register_and_login(client, "setnoperm@example.com")
    assert (await client.get("/v1/settlements", headers=nobody)).status_code == 403


async def test_viewer_reads_but_cannot_manage_or_finalize(client):
    org, headers = await _tenant_admin(client)
    _inv, inv_token = await invite(
        client,
        headers,
        email="viewer@kilima.example",
        role_name="tenant-viewer",
    )
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
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
    assert (await client.get("/v1/settlements", headers=viewer)).status_code == 200
    r = await client.post(
        "/v1/settlements",
        json={
            "supplier_id": str(uuid.uuid4()),
            "center_id": str(uuid.uuid4()),
            "currency": "KES",
            "period_from": "2026-10-01",
            "period_to": "2026-10-31",
        },
        headers=viewer,
    )
    assert r.status_code == 403
    r = await client.post(f"/v1/settlements/{uuid.uuid4()}/finalize", headers=viewer)
    assert r.status_code == 403


async def test_missing_fields_rejected(client):
    headers, center, supplier, _ = await _settlement_env(client)
    for missing in ("supplier_id", "center_id", "period_from", "period_to", "currency"):
        payload = {
            "supplier_id": supplier["id"],
            "center_id": center["id"],
            "currency": "KES",
            "period_from": "2026-12-01",
            "period_to": "2026-12-31",
        }
        del payload[missing]
        r = await client.post("/v1/settlements", json=payload, headers=headers)
        assert r.status_code == 422, missing
