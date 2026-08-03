"""Milk Collection Transaction Engine: sessions, lifecycle, validation, immutability."""

import asyncio
import uuid

from tests.test_collection_centers import _center_fixture
from tests.test_suppliers import _create_supplier


async def _ready_center(client, headers, center):
    """Make a center READY: hours + active + operator + active scale."""
    cid = center["id"]
    await client.put(
        f"/v1/collection-centers/{cid}/operating-hours",
        json={"windows": [{"day_of_week": 0, "opens": "06:00", "closes": "20:00"}]},
        headers=headers,
    )
    await client.post(
        f"/v1/collection-centers/{cid}/status", json={"status": "active"}, headers=headers
    )
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    await client.post(
        f"/v1/collection-centers/{cid}/operators",
        json={"user_id": me["user"]["id"]},
        headers=headers,
    )
    scale = (
        await client.post(
            "/v1/devices",
            json={"category": "scale", "serial_number": f"SC-{cid[:8]}", "name": "Scale"},
            headers=headers,
        )
    ).json()
    await client.post(f"/v1/devices/{scale['id']}/assign", json={"center_id": cid}, headers=headers)
    await client.post(
        f"/v1/devices/{scale['id']}/status", json={"status": "active"}, headers=headers
    )


async def _engine_fixture(client):
    """Ready center + open session + active assigned supplier."""
    headers, _branch, center = await _center_fixture(client)
    await _ready_center(client, headers, center)
    session = (
        await client.post(
            "/v1/collection-sessions",
            json={"center_id": center["id"], "label": "morning"},
            headers=headers,
        )
    ).json()
    supplier = await _create_supplier(client, headers)
    await client.post(
        f"/v1/suppliers/{supplier['id']}/centers",
        json={"center_id": center["id"]},
        headers=headers,
    )
    await client.post(
        f"/v1/suppliers/{supplier['id']}/status", json={"status": "active"}, headers=headers
    )
    return headers, center, session, supplier


async def _drive_to_priced(client, headers, session_id, supplier):
    """Create a transaction and walk it to PRICED; returns the transaction id."""
    tx = (
        await client.post("/v1/milk-transactions", json={"session_id": session_id}, headers=headers)
    ).json()
    tid = tx["id"]
    r = await client.post(
        f"/v1/milk-transactions/{tid}/identify",
        json={"method": "code", "value": supplier["code"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "cow", "container_type": "can", "container_identifier": "CAN-7"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/v1/milk-transactions/{tid}/weight",
        json={"source": "manual", "gross": 27.5, "tare": 2.5},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/v1/milk-transactions/{tid}/quality",
        json={"source": "manual", "fat": 4.2, "snf": 8.6, "clr": 28.5},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "PRICED"
    return tid


# --- sessions ---------------------------------------------------------------


async def test_session_requires_active_ready_center(client):
    headers, _, center = await _center_fixture(client)
    # Inactive center -> conflict.
    r = await client.post(
        "/v1/collection-sessions", json={"center_id": center["id"]}, headers=headers
    )
    assert r.status_code == 409
    # Unknown center -> 404.
    r = await client.post(
        "/v1/collection-sessions", json={"center_id": str(uuid.uuid4())}, headers=headers
    )
    assert r.status_code == 404


async def test_session_blocked_when_not_ready(client):
    headers, _, center = await _center_fixture(client)
    # Active but no operator/scale -> NOT_READY -> blocked.
    await client.put(
        f"/v1/collection-centers/{center['id']}/operating-hours",
        json={"windows": [{"day_of_week": 0, "opens": "06:00", "closes": "20:00"}]},
        headers=headers,
    )
    await client.post(
        f"/v1/collection-centers/{center['id']}/status",
        json={"status": "active"},
        headers=headers,
    )
    r = await client.post(
        "/v1/collection-sessions", json={"center_id": center["id"]}, headers=headers
    )
    assert r.status_code == 409
    assert "NOT_READY" in r.json()["extra"]


async def test_one_open_session_per_center(client):
    headers, center, session, _ = await _engine_fixture(client)
    r = await client.post(
        "/v1/collection-sessions", json={"center_id": center["id"]}, headers=headers
    )
    assert r.status_code == 409
    # Close, then a new one may open.
    r = await client.post(f"/v1/collection-sessions/{session['id']}/close", headers=headers)
    assert r.status_code == 200
    r = await client.post(
        "/v1/collection-sessions", json={"center_id": center["id"]}, headers=headers
    )
    assert r.status_code == 201


async def test_session_close_blocked_by_inflight_transactions(client):
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _drive_to_priced(client, headers, session["id"], supplier)
    r = await client.post(f"/v1/collection-sessions/{session['id']}/close", headers=headers)
    assert r.status_code == 409
    # Finish the transaction; close succeeds.
    await client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers)
    await client.post(f"/v1/milk-transactions/{tid}/complete", headers=headers)
    r = await client.post(f"/v1/collection-sessions/{session['id']}/close", headers=headers)
    assert r.status_code == 200


# --- happy path -------------------------------------------------------------


async def test_full_lifecycle_accept_complete(client, bus):
    headers, _center, session, supplier = await _engine_fixture(client)
    tid = await _drive_to_priced(client, headers, session["id"], supplier)

    r = await client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers)
    assert r.status_code == 200 and r.json()["state"] == "ACCEPTED"
    r = await client.post(f"/v1/milk-transactions/{tid}/complete", headers=headers)
    assert r.status_code == 200 and r.json()["state"] == "COMPLETED"
    assert r.json()["completed_at"] is not None

    detail = (await client.get(f"/v1/milk-transactions/{tid}", headers=headers)).json()
    assert detail["net_weight"] == 25.0
    assert detail["supplier_id"] == supplier["id"]
    # MVP-001: pricing runs inline; without a rate card it degrades gracefully.
    assert detail["pricing_status"] == "pricing_unavailable"

    # Ordered event log covers every mandated business event.
    events = (await client.get(f"/v1/milk-transactions/{tid}/events", headers=headers)).json()
    types = [e["event_type"] for e in events]
    assert types == [
        "TransactionCreated",
        "SupplierIdentified",
        "MilkReceived",
        "WeightCaptured",
        "QualityCaptured",
        "PricingRequested",
        "PricingUnavailable",
        "TransactionAccepted",
        "TransactionCompleted",
    ]
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))

    # Bus envelopes emitted for the same steps.
    bus_types = [e.type for e in bus.published]
    for expected in (
        "collection.transaction-created.v1",
        "collection.supplier-identified.v1",
        "collection.weight-captured.v1",
        "collection.quality-captured.v1",
        "collection.pricing-requested.v1",
        "collection.transaction-accepted.v1",
        "collection.transaction-completed.v1",
    ):
        assert expected in bus_types


async def test_snapshot_and_metrics_written_at_completion(client):
    headers, _center, session, supplier = await _engine_fixture(client)
    tid = await _drive_to_priced(client, headers, session["id"], supplier)
    await client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers)
    await client.post(f"/v1/milk-transactions/{tid}/complete", headers=headers)

    from sqlalchemy import select

    from platform_core.core.db import get_session_factory
    from platform_core.modules.milk_collection.models import (
        TransactionMetrics,
        TransactionSnapshot,
    )

    async with get_session_factory()() as db:
        snapshot = await db.scalar(
            select(TransactionSnapshot).where(TransactionSnapshot.transaction_id == uuid.UUID(tid))
        )
        metrics = await db.scalar(
            select(TransactionMetrics).where(TransactionMetrics.transaction_id == uuid.UUID(tid))
        )
    assert snapshot is not None
    assert snapshot.data["decision"] == "ACCEPTED"
    assert snapshot.data["weight"]["net"] == 25.0
    assert snapshot.data["quality"]["fat"] == 4.2
    assert metrics is not None
    assert metrics.final_state == "ACCEPTED"
    assert metrics.duration_seconds >= 0
    assert str(metrics.operator_id)  # operator captured


async def test_rejection_records_reason_operator_timestamp(client, bus):
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _drive_to_priced(client, headers, session["id"], supplier)
    # Reason is mandatory.
    r = await client.post(
        f"/v1/milk-transactions/{tid}/reject", json={"reason": ""}, headers=headers
    )
    assert r.status_code == 422
    r = await client.post(
        f"/v1/milk-transactions/{tid}/reject",
        json={"reason": "curdled on arrival"},
        headers=headers,
    )
    assert r.status_code == 200 and r.json()["state"] == "REJECTED"
    detail = (await client.get(f"/v1/milk-transactions/{tid}", headers=headers)).json()
    assert detail["rejected_reason"] == "curdled on arrival"
    r = await client.post(f"/v1/milk-transactions/{tid}/complete", headers=headers)
    assert r.status_code == 200
    assert "collection.transaction-rejected.v1" in [e.type for e in bus.published]


# --- state machine violations ----------------------------------------------


async def test_state_preconditions_enforced(client):
    headers, _, session, supplier = await _engine_fixture(client)
    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
    ).json()
    tid = tx["id"]
    # Weight before identification/milk -> 409; quality before weight -> 409.
    r = await client.post(
        f"/v1/milk-transactions/{tid}/weight",
        json={"source": "manual", "gross": 20, "tare": 2},
        headers=headers,
    )
    assert r.status_code == 409
    r = await client.post(
        f"/v1/milk-transactions/{tid}/quality",
        json={"source": "manual", "fat": 4, "snf": 8, "clr": 28},
        headers=headers,
    )
    assert r.status_code == 409
    # Accept/complete before priced/decided -> 409.
    assert (
        await client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers)
    ).status_code == 409
    assert (
        await client.post(f"/v1/milk-transactions/{tid}/complete", headers=headers)
    ).status_code == 409
    # Identify twice -> 409 (second expects NEW).
    r = await client.post(
        f"/v1/milk-transactions/{tid}/identify",
        json={"method": "code", "value": supplier["code"]},
        headers=headers,
    )
    assert r.status_code == 200
    r = await client.post(
        f"/v1/milk-transactions/{tid}/identify",
        json={"method": "code", "value": supplier["code"]},
        headers=headers,
    )
    assert r.status_code == 409


async def test_completed_transactions_are_immutable(client):
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _drive_to_priced(client, headers, session["id"], supplier)
    await client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers)
    await client.post(f"/v1/milk-transactions/{tid}/complete", headers=headers)
    # Every mutating step is refused on a completed transaction.
    for path, body in (
        ("identify", {"method": "code", "value": supplier["code"]}),
        ("milk", {"milk_type": "cow", "container_type": "can", "container_identifier": "X"}),
        ("weight", {"source": "manual", "gross": 20, "tare": 2}),
        ("quality", {"source": "manual", "fat": 4, "snf": 8, "clr": 28}),
        ("accept", None),
        ("reject", {"reason": "too late"}),
        ("complete", None),
        ("cancel", {"reason": "nope"}),
    ):
        r = await client.post(
            f"/v1/milk-transactions/{tid}/{path}",
            json=body if body is not None else {},
            headers=headers,
        )
        assert r.status_code == 409, f"{path} should be blocked, got {r.status_code}"


async def test_cancellation_rules(client, bus):
    headers, _, session, supplier = await _engine_fixture(client)
    # Cancellable at NEW.
    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
    ).json()
    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/cancel",
        json={"reason": "supplier left"},
        headers=headers,
    )
    assert r.status_code == 200 and r.json()["state"] == "CANCELLED"
    # Cancellable at PRICED (before decision)...
    tid = await _drive_to_priced(client, headers, session["id"], supplier)
    r = await client.post(
        f"/v1/milk-transactions/{tid}/cancel", json={"reason": "changed mind"}, headers=headers
    )
    assert r.status_code == 200
    # ...but not after a decision.
    tid = await _drive_to_priced(client, headers, session["id"], supplier)
    await client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers)
    r = await client.post(
        f"/v1/milk-transactions/{tid}/cancel", json={"reason": "too late"}, headers=headers
    )
    assert r.status_code == 409
    assert "collection.transaction-cancelled.v1" in [e.type for e in bus.published]


async def test_concurrent_accept_only_one_wins(client):
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _drive_to_priced(client, headers, session["id"], supplier)
    r1, r2 = await asyncio.gather(
        client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers),
        client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers),
    )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 409]
