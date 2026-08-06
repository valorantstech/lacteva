"""Offline Collection Sync (OFF-001) — the server half.

These tests replay what a dark device would send: a whole collection captured
with LOCAL identifiers, pushed in batches, sometimes twice, sometimes into a
world that moved on. The rule under test throughout is that offline changes
nothing — every operation lands through the same collection service the online
API calls, with the same permissions and the same state machine (BR-0021).
"""

import uuid

from tests.conftest import register_and_login
from tests.test_procurement_e2e import _procurement_env

DEVICE = "device-kilima-01"


def _op(kind, *, seq, target=None, reference=None, payload=None, operation_id=None):
    return {
        "operation_id": str(operation_id or uuid.uuid4()),
        "kind": kind,
        "sequence": seq,
        "client_reference": reference,
        "target_ref": target,
        "payload": payload or {},
        "recorded_at": "2026-08-05T04:30:00+00:00",
    }


async def _push(client, headers, operations, *, device=DEVICE):
    r = await client.post(
        "/v1/sync/collection",
        json={"device_id": device, "operations": operations},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _offline_collection(session_ref, tx_ref, *, supplier_qr, start=1):
    """The operation sequence a device records for one full collection, all of
    it referring to LOCAL ids the server has never seen."""
    return [
        _op("create_transaction", seq=start, target=session_ref, reference=tx_ref),
        _op(
            "identify_supplier",
            seq=start + 1,
            target=tx_ref,
            payload={"method": "qr", "value": supplier_qr},
        ),
        _op(
            "receive_milk",
            seq=start + 2,
            target=tx_ref,
            payload={
                "milk_type": "cow",
                "container_type": "can",
                "container_identifier": "C-OFFLINE",
            },
        ),
        _op(
            "capture_weight",
            seq=start + 3,
            target=tx_ref,
            payload={"source": "manual", "gross": 30.0, "tare": 5.0},
        ),
        _op(
            "capture_quality",
            seq=start + 4,
            target=tx_ref,
            payload={"source": "manual", "fat": 4.2, "snf": 8.5, "clr": 28.0},
        ),
        _op("accept", seq=start + 5, target=tx_ref),
        _op("complete", seq=start + 6, target=tx_ref),
    ]


async def _env(client):
    """Ready center + priced rate card + supplier QR + an open session."""
    headers, center, supplier, session = await _procurement_env(client)
    qr = (await client.get(f"/v1/suppliers/{supplier['id']}/qr", headers=headers)).json()
    return headers, center, supplier, session, qr["payload"]


# --- offline collection replay ------------------------------------------------


async def test_a_whole_collection_captured_offline_lands_intact(client):
    headers, _center, supplier, session, qr = await _env(client)
    ops = _offline_collection(session["id"], "local-tx-1", supplier_qr=qr)
    result = await _push(client, headers, ops)

    assert result["accepted"] == 7 and result["applied"] == 7
    assert result["conflicts"] == 0 and result["failed"] == 0

    # The transaction exists on the platform exactly as an online one would.
    page = (await client.get("/v1/milk-transactions", headers=headers)).json()
    assert page["total"] == 1
    tx = page["items"][0]
    assert tx["state"] == "COMPLETED"
    assert tx["supplier_id"] == supplier["id"]
    assert float(tx["net_weight"]) == 25.0
    assert float(tx["fat"]) == 4.2
    # …including pricing: offline capture is priced by the same engine.
    assert tx["pricing_status"] == "priced"
    assert str(tx["gross_amount"]) == "1125.00"


async def test_offline_session_creation_with_a_local_id(client):
    """A device that opens a session while dark refers to it locally, then
    hangs a whole collection off that local id in the same batch."""
    headers, center, _supplier, session, qr = await _env(client)
    # A center holds ONE open session — close the online one first, exactly as
    # an operator ending a shift would, then let the device open the next.
    assert (
        await client.post(f"/v1/collection-sessions/{session['id']}/close", headers=headers)
    ).status_code == 200
    ops = [
        _op(
            "open_session",
            seq=0,
            reference="local-session-1",
            payload={"center_id": center["id"], "label": "offline shift"},
        ),
        *_offline_collection("local-session-1", "local-tx-1", supplier_qr=qr),
    ]
    result = await _push(client, headers, ops)
    assert result["applied"] == 8 and result["conflicts"] == 0

    session_result = next(r for r in result["results"] if r["kind"] == "open_session")
    assert session_result["client_reference"] == "local-session-1"
    assert session_result["server_id"] is not None
    sessions = (await client.get("/v1/collection-sessions", headers=headers)).json()
    # API-001: this list is paginated now.
    assert any(s["id"] == session_result["server_id"] for s in sessions["items"])


async def test_business_rules_are_identical_offline(client):
    """The state machine is not relaxed for a device: skipping a step fails
    offline exactly as it would online."""
    headers, _center, _supplier, session, _qr = await _env(client)
    ops = [
        _op("create_transaction", seq=1, target=session["id"], reference="local-tx-1"),
        # Weight before the supplier is identified — the engine refuses.
        _op(
            "capture_weight",
            seq=2,
            target="local-tx-1",
            payload={"source": "manual", "gross": 30.0, "tare": 5.0},
        ),
    ]
    result = await _push(client, headers, ops)
    assert result["applied"] == 1 and result["conflicts"] == 1
    weight = next(r for r in result["results"] if r["kind"] == "capture_weight")
    assert weight["status"] == "conflict" and weight["applied"] is False
    assert weight["conflict"]["reason"] == "invalid_state"


# --- idempotency & duplicate replay -------------------------------------------


async def test_replaying_the_same_batch_creates_nothing_twice(client):
    """The device lost its acknowledgement and re-sent. Nothing doubles."""
    headers, _center, _supplier, session, qr = await _env(client)
    ops = _offline_collection(session["id"], "local-tx-1", supplier_qr=qr)

    first = await _push(client, headers, ops)
    second = await _push(client, headers, ops)

    assert first["applied"] == 7
    assert second["applied"] == 0 and second["duplicates"] == 7
    assert (await client.get("/v1/milk-transactions", headers=headers)).json()["total"] == 1
    # The replay hands back the ORIGINAL server ids.
    first_ids = [r["server_id"] for r in first["results"]]
    assert [r["server_id"] for r in second["results"]] == first_ids


async def test_duplicate_operation_ids_within_one_batch_apply_once(client):
    headers, _center, _supplier, session, _qr = await _env(client)
    op_id = uuid.uuid4()
    ops = [
        _op("create_transaction", seq=1, target=session["id"], operation_id=op_id),
        _op("create_transaction", seq=2, target=session["id"], operation_id=op_id),
    ]
    result = await _push(client, headers, ops)
    assert result["applied"] == 1 and result["duplicates"] == 1
    assert (await client.get("/v1/milk-transactions", headers=headers)).json()["total"] == 1


async def test_a_different_operation_id_is_a_different_collection(client):
    """Idempotency is keyed on the operation, not on its shape — two genuine
    collections from the same supplier must both land."""
    headers, _center, _supplier, session, qr = await _env(client)
    await _push(client, headers, _offline_collection(session["id"], "local-tx-1", supplier_qr=qr))
    await _push(client, headers, _offline_collection(session["id"], "local-tx-2", supplier_qr=qr))
    assert (await client.get("/v1/milk-transactions", headers=headers)).json()["total"] == 2


# --- partial sync, interruption, resume ---------------------------------------


async def test_partial_batches_resume_across_pushes(client):
    """Connectivity died mid-sync. The next push refers to a local id created
    in the previous one and is understood."""
    headers, _center, _supplier, session, qr = await _env(client)
    ops = _offline_collection(session["id"], "local-tx-1", supplier_qr=qr)

    first = await _push(client, headers, ops[:3])  # create, identify, milk
    assert first["applied"] == 3
    second = await _push(client, headers, ops[3:])  # weight, quality, accept, complete
    assert second["applied"] == 4 and second["conflicts"] == 0

    tx = (await client.get("/v1/milk-transactions", headers=headers)).json()["items"][0]
    assert tx["state"] == "COMPLETED"


async def test_an_operation_whose_predecessor_never_landed_is_a_conflict(client):
    """No silent invention: a reference to something that never synchronised
    is reported, not guessed at."""
    headers, _center, _supplier, _session, _qr = await _env(client)
    result = await _push(
        client,
        headers,
        [_op("accept", seq=1, target="local-tx-never-synced")],
    )
    assert result["conflicts"] == 1
    conflict = result["results"][0]
    assert conflict["conflict"]["reason"] == "unresolved_reference"
    assert "has not been synchronised" in conflict["conflict"]["detail"]


async def test_out_of_order_operations_are_applied_in_sequence(client):
    """The device numbers its work; the server honours that, not arrival order."""
    headers, _center, _supplier, session, qr = await _env(client)
    ops = _offline_collection(session["id"], "local-tx-1", supplier_qr=qr)
    result = await _push(client, headers, list(reversed(ops)))
    assert result["applied"] == 7 and result["conflicts"] == 0


async def test_batch_upload_of_several_collections(client):
    headers, _center, _supplier, session, qr = await _env(client)
    ops = []
    for index in range(3):
        ops.extend(
            _offline_collection(
                session["id"], f"local-tx-{index}", supplier_qr=qr, start=1 + index * 10
            )
        )
    result = await _push(client, headers, ops)
    assert result["accepted"] == 21 and result["applied"] == 21
    assert (await client.get("/v1/milk-transactions", headers=headers)).json()["total"] == 3


# --- conflicts ----------------------------------------------------------------


async def test_already_completed_transaction_conflicts_on_replay(client):
    """The operator also completed it online. The device's copy does not
    overwrite anything — it is told the world moved on."""
    headers, _center, _supplier, session, qr = await _env(client)
    ops = _offline_collection(session["id"], "local-tx-1", supplier_qr=qr)
    await _push(client, headers, ops)
    server_id = (await client.get("/v1/milk-transactions", headers=headers)).json()["items"][0][
        "id"
    ]

    # A NEW operation id targeting the now-completed server transaction.
    result = await _push(client, headers, [_op("accept", seq=99, target=server_id)])
    assert result["conflicts"] == 1
    assert result["results"][0]["conflict"]["reason"] == "already_accepted"
    assert result["results"][0]["applied"] is False


async def test_archived_supplier_conflicts(client):
    headers, center, supplier, session, qr = await _env(client)
    await client.post(
        f"/v1/suppliers/{supplier['id']}/status", json={"status": "archived"}, headers=headers
    )
    ops = _offline_collection(session["id"], "local-tx-1", supplier_qr=qr)
    result = await _push(client, headers, ops)

    identify = next(r for r in result["results"] if r["kind"] == "identify_supplier")
    assert identify["status"] == "conflict"
    assert identify["conflict"]["reason"] == "supplier_unavailable"
    assert center["id"]


async def test_closed_session_conflicts(client):
    headers, _center, _supplier, session, qr = await _env(client)
    r = await client.post(f"/v1/collection-sessions/{session['id']}/close", headers=headers)
    assert r.status_code == 200, r.text
    result = await _push(
        client, headers, _offline_collection(session["id"], "local-tx-1", supplier_qr=qr)
    )
    create = next(r for r in result["results"] if r["kind"] == "create_transaction")
    assert create["status"] == "conflict"
    assert create["conflict"]["reason"] == "session_closed"


async def test_changed_rate_card_is_flagged_but_the_collection_stands(client):
    """Milk is perishable: pricing that no longer resolves may NOT discard a
    collection (MVP-001). The divergence is surfaced instead."""
    headers, _center, _supplier, session, qr = await _env(client)
    cards = (await client.get("/v1/rate-cards", headers=headers)).json()
    card = next(c for c in cards["items"] if c["code"] == "MVP-CARD")
    assert (
        await client.post(f"/v1/rate-cards/{card['id']}/archive", headers=headers)
    ).status_code == 200

    result = await _push(
        client, headers, _offline_collection(session["id"], "local-tx-1", supplier_qr=qr)
    )
    complete = next(r for r in result["results"] if r["kind"] == "complete")
    assert complete["status"] == "conflict"
    assert complete["conflict"]["reason"] == "rate_card_changed"
    assert complete["applied"] is True  # the collection was NOT discarded
    tx = (await client.get("/v1/milk-transactions", headers=headers)).json()["items"][0]
    assert tx["state"] == "COMPLETED" and tx["pricing_status"] != "priced"


async def test_unknown_operation_kind_fails_without_touching_anything(client):
    headers, _center, _supplier, session, _qr = await _env(client)
    result = await _push(client, headers, [_op("delete_everything", seq=1, target=session["id"])])
    assert result["failed"] == 1
    assert "unknown operation kind" in result["results"][0]["error"]
    assert (await client.get("/v1/milk-transactions", headers=headers)).json()["total"] == 0


# --- retry --------------------------------------------------------------------


async def test_failed_operation_can_be_retried_and_conflicts_cannot(client):
    headers, _center, _supplier, session, _qr = await _env(client)
    bad = _op("delete_everything", seq=1, target=session["id"])
    await _push(client, headers, [bad])

    r = await client.post(f"/v1/sync/operations/{bad['operation_id']}/retry", headers=headers)
    assert r.status_code == 200  # still fails, but the retry is permitted
    assert r.json()["status"] == "failed"

    # A conflict needs a human decision, not a retry.
    conflicted = _op("accept", seq=2, target="local-never-synced")
    await _push(client, headers, [conflicted])
    r = await client.post(
        f"/v1/sync/operations/{conflicted['operation_id']}/retry", headers=headers
    )
    assert r.status_code == 409
    assert "only failed operations can be retried" in r.text


async def test_retry_of_an_unknown_operation_is_404(client):
    headers, _center, _supplier, _session, _qr = await _env(client)
    r = await client.post(f"/v1/sync/operations/{uuid.uuid4()}/retry", headers=headers)
    assert r.status_code == 404


async def test_a_failed_operation_reapplies_successfully_on_retry(client):
    """The classic transient case: the predecessor had not landed yet, the
    device pushed anyway, and a later retry succeeds."""
    headers, _center, _supplier, session, qr = await _env(client)
    ops = _offline_collection(session["id"], "local-tx-1", supplier_qr=qr)
    # Push the identify FIRST — its target does not exist yet.
    early = await _push(client, headers, [ops[1]])
    assert early["conflicts"] == 1

    await _push(client, headers, [ops[0]])  # now create the transaction
    # Re-pushing identify with a NEW operation id now succeeds.
    again = await _push(
        client,
        headers,
        [
            _op(
                "identify_supplier",
                seq=2,
                target="local-tx-1",
                payload={"method": "qr", "value": qr},
            )
        ],
    )
    assert again["applied"] == 1


# --- monitor ------------------------------------------------------------------


async def test_monitor_lists_operations_and_filters(client):
    headers, _center, _supplier, session, qr = await _env(client)
    await _push(client, headers, _offline_collection(session["id"], "local-tx-1", supplier_qr=qr))

    page = (await client.get("/v1/sync/operations", headers=headers)).json()
    assert page["total"] == 7
    applied = (await client.get("/v1/sync/operations?status=applied", headers=headers)).json()
    assert applied["total"] == 7
    by_kind = (await client.get("/v1/sync/operations?kind=complete", headers=headers)).json()
    assert by_kind["total"] == 1
    by_device = (
        await client.get(f"/v1/sync/operations?device_id={DEVICE}", headers=headers)
    ).json()
    assert by_device["total"] == 7


async def test_monitor_paginates(client):
    headers, _center, _supplier, session, qr = await _env(client)
    await _push(client, headers, _offline_collection(session["id"], "local-tx-1", supplier_qr=qr))
    page = (await client.get("/v1/sync/operations?limit=3&offset=0", headers=headers)).json()
    assert page["total"] == 7 and len(page["items"]) == 3
    assert page["limit"] == 3 and page["offset"] == 0


async def test_stats_summarise_devices_and_outcomes(client):
    headers, _center, _supplier, session, qr = await _env(client)
    await _push(client, headers, _offline_collection(session["id"], "local-tx-1", supplier_qr=qr))
    await _push(client, headers, [_op("accept", seq=50, target="local-nope")])

    stats = (await client.get("/v1/sync/stats", headers=headers)).json()
    assert stats["total"] == 8
    assert stats["by_status"]["applied"] == 7
    assert stats["conflicts"] == 1
    assert stats["by_kind"]["capture_quality"] == 1
    assert stats["last_sync_at"] is not None
    device = next(d for d in stats["devices"] if d["device_id"] == DEVICE)
    assert device["operations"] == 8 and device["conflicts"] == 1


# --- authorization ------------------------------------------------------------


async def test_sync_requires_authentication(client):
    r = await client.post("/v1/sync/collection", json={"device_id": "x", "operations": []})
    assert r.status_code in (401, 403)


async def test_offline_never_bypasses_authorization(client):
    """A principal without collection.transaction.record cannot push, however
    it captured the data."""
    headers, _center, _supplier, session, qr = await _env(client)
    _, outsider = await register_and_login(client, "offline-outsider@example.com")
    r = await client.post(
        "/v1/sync/collection",
        json={
            "device_id": DEVICE,
            "operations": _offline_collection(session["id"], "local-tx-1", supplier_qr=qr),
        },
        headers=outsider,
    )
    assert r.status_code == 403
    assert (await client.get("/v1/sync/operations", headers=outsider)).status_code == 403
    assert (await client.get("/v1/sync/stats", headers=outsider)).status_code == 403
    assert headers


async def test_monitor_is_readable_by_a_viewer_but_push_is_not(client):
    from platform_core.modules.authz.permissions import SYSTEM_ROLES

    assert "sync.read" in SYSTEM_ROLES["tenant-viewer"]
    assert "collection.transaction.record" not in SYSTEM_ROLES["tenant-viewer"]


# --- tenant isolation ---------------------------------------------------------


async def test_sync_operations_are_invisible_across_tenants(client):
    headers, _center, _supplier, session, qr = await _env(client)
    await _push(client, headers, _offline_collection(session["id"], "local-tx-1", supplier_qr=qr))

    from tests.test_payments import _second_tenant

    other = await _second_tenant(client)
    assert (await client.get("/v1/sync/operations", headers=other)).json()["total"] == 0
    assert (await client.get("/v1/sync/stats", headers=other)).json()["total"] == 0


async def test_a_local_reference_cannot_cross_tenants(client):
    """Local ids are device-scoped strings; one tenant's reference must never
    resolve inside another's data."""
    headers, _center, _supplier, session, qr = await _env(client)
    await _push(client, headers, _offline_collection(session["id"], "local-tx-1", supplier_qr=qr))

    from tests.test_payments import _second_tenant

    other = await _second_tenant(client)
    r = await client.post(
        "/v1/sync/collection",
        json={"device_id": DEVICE, "operations": [_op("accept", seq=1, target="local-tx-1")]},
        headers=other,
    )
    # The other tenant lacks the record permission entirely; even with it, the
    # reference lookup is tenant-scoped.
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        assert r.json()["results"][0]["conflict"]["reason"] == "unresolved_reference"
