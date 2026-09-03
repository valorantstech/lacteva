"""Supplier identification, weight, and quality validation for the engine."""

import uuid

from tests.conftest import invite
from tests.test_milk_collection import _drive_to_priced, _engine_fixture
from tests.test_suppliers import _create_supplier


async def _fresh_tx(client, headers, session_id):
    tx = (
        await client.post("/v1/milk-transactions", json={"session_id": session_id}, headers=headers)
    ).json()
    return tx["id"]


async def _identify(client, headers, tid, method, value=None, supplier_id=None):
    body = {"method": method}
    if value is not None:
        body["value"] = value
    if supplier_id is not None:
        body["supplier_id"] = supplier_id
    return await client.post(f"/v1/milk-transactions/{tid}/identify", json=body, headers=headers)


# --- supplier identification ------------------------------------------------


async def test_identify_by_qr_phone_code_and_manual(client):
    headers, _, session, supplier = await _engine_fixture(client)
    qr = (await client.get(f"/v1/suppliers/{supplier['id']}/qr", headers=headers)).json()

    for method, kwargs in (
        ("qr", {"value": qr["payload"]}),
        ("code", {"value": supplier["code"]}),
        ("phone", {"value": "+254700000001"}),
        ("manual", {"supplier_id": supplier["id"]}),
    ):
        tid = await _fresh_tx(client, headers, session["id"])
        r = await _identify(client, headers, tid, method, **kwargs)
        assert r.status_code == 200, f"{method}: {r.text}"
        assert r.json()["supplier_id"] == supplier["id"]
        await client.post(
            f"/v1/milk-transactions/{tid}/cancel", json={"reason": "test"}, headers=headers
        )


async def test_identify_rejects_bad_inputs(client):
    headers, _, session, _supplier = await _engine_fixture(client)
    tid = await _fresh_tx(client, headers, session["id"])
    assert (await _identify(client, headers, tid, "code", value="NOPE")).status_code == 404
    assert (await _identify(client, headers, tid, "phone", value="+000")).status_code == 404
    assert (await _identify(client, headers, tid, "qr", value="LCT1.junk.sig")).status_code == 400
    assert (await _identify(client, headers, tid, "carrier-pigeon", value="x")).status_code == 409
    assert (await _identify(client, headers, tid, "manual")).status_code == 409
    r = await _identify(client, headers, tid, "manual", supplier_id=str(uuid.uuid4()))
    assert r.status_code == 404


async def test_identify_requires_active_assigned_supplier(client):
    headers, center, session, _ = await _engine_fixture(client)
    # Draft supplier assigned to the center -> refused (not active).
    draft = await _create_supplier(client, headers, name="Draft Dairy")
    await client.post(
        f"/v1/suppliers/{draft['id']}/centers",
        json={"center_id": center["id"]},
        headers=headers,
    )
    tid = await _fresh_tx(client, headers, session["id"])
    r = await _identify(client, headers, tid, "code", value=draft["code"])
    assert r.status_code == 409 and "not active" in r.json()["extra"]

    # Active supplier NOT assigned to this center -> refused.
    other = await _create_supplier(client, headers, name="Elsewhere Farm")
    # Assign to a different center so it can activate.
    branch = (await client.get("/v1/branches", headers=headers)).json()[0]
    center2 = (
        await client.post(
            "/v1/collection-centers",
            json={"branch_id": branch["id"], "name": "Other Center", "code": "OC-1"},
            headers=headers,
        )
    ).json()
    await client.post(
        f"/v1/suppliers/{other['id']}/centers",
        json={"center_id": center2["id"]},
        headers=headers,
    )
    await client.post(
        f"/v1/suppliers/{other['id']}/status", json={"status": "active"}, headers=headers
    )
    r = await _identify(client, headers, tid, "code", value=other["code"])
    assert r.status_code == 409 and "not assigned" in r.json()["extra"]


# --- milk info ---------------------------------------------------------------


async def test_milk_info_validation(client):
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _fresh_tx(client, headers, session["id"])
    await _identify(client, headers, tid, "code", value=supplier["code"])

    r = await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "camel", "container_type": "can", "container_identifier": "C1"},
        headers=headers,
    )
    assert r.status_code == 409  # unknown milk type
    r = await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "custom", "container_type": "can", "container_identifier": "C1"},
        headers=headers,
    )
    assert r.status_code == 409  # custom requires custom label
    r = await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={
            "milk_type": "custom",
            "milk_type_custom": "camel",
            "container_type": "can",
            "container_identifier": "C1",
            "temperature_c": 24.5,
        },
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["state"] == "MILK_RECEIVED"


# --- weight ------------------------------------------------------------------


async def test_weight_validation_rules(client):
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _fresh_tx(client, headers, session["id"])
    await _identify(client, headers, tid, "code", value=supplier["code"])
    await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "cow", "container_type": "can", "container_identifier": "W1"},
        headers=headers,
    )
    cases = [
        ({"source": "manual", "gross": 0, "tare": 0}, "gross must be > 0"),
        ({"source": "manual", "gross": 10, "tare": -1}, "tare >= 0"),
        ({"source": "manual", "gross": 250, "tare": 2}, "exceeds"),
        ({"source": "manual", "gross": 5, "tare": 5}, "tare must be less"),
        ({"source": "manual", "gross": 5}, "requires gross and tare"),
        ({"source": "telepathy", "gross": 5, "tare": 1}, "source must be"),
        # D-21 / WO-70: the refusal is now relative to the TENANT, not to a
        # constant — and it is still a refusal. This organisation (Kenya)
        # measures in litres, so a reading claimed in kilograms is refused as
        # firmly as pounds are; "accept anything" is exactly what this must
        # not have become.
        ({"source": "manual", "gross": 5, "tare": 1, "unit": "lb"}, "unknown quantity unit"),
        ({"source": "manual", "gross": 5, "tare": 1, "unit": "kg"}, "this organisation measures"),
    ]
    for body, fragment in cases:
        r = await client.post(f"/v1/milk-transactions/{tid}/weight", json=body, headers=headers)
        assert r.status_code == 409, body
        assert fragment.split()[0].lower() in r.json()["extra"].lower(), body
    # Valid manual weight computes net.
    r = await client.post(
        f"/v1/milk-transactions/{tid}/weight",
        json={"source": "manual", "gross": 31.25, "tare": 2.75},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["net_weight"] == 28.5
    assert r.json()["state"] == "QUALITY_PENDING"


async def test_mock_scale_adapter_fills_weights(client):
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _fresh_tx(client, headers, session["id"])
    await _identify(client, headers, tid, "code", value=supplier["code"])
    await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "buffalo", "container_type": "can", "container_identifier": "MS-1"},
        headers=headers,
    )
    r = await client.post(
        f"/v1/milk-transactions/{tid}/weight", json={"source": "mock_scale"}, headers=headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["gross_weight"] > body["tare_weight"] > 0
    assert body["net_weight"] == round(body["gross_weight"] - body["tare_weight"], 3)


# --- quality -----------------------------------------------------------------


async def test_quality_validation_rules(client):
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _fresh_tx(client, headers, session["id"])
    await _identify(client, headers, tid, "code", value=supplier["code"])
    await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "cow", "container_type": "can", "container_identifier": "Q1"},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tid}/weight",
        json={"source": "manual", "gross": 20, "tare": 2},
        headers=headers,
    )
    for body in (
        {"source": "manual", "fat": 20, "snf": 8, "clr": 28},  # fat out of range
        {"source": "manual", "fat": 4, "snf": 8, "clr": 55},  # clr out of range
        {"source": "manual", "fat": 4, "snf": 8},  # missing clr
        {"source": "guesswork", "fat": 4, "snf": 8, "clr": 28},  # bad source
        {"source": "manual", "fat": 4, "snf": 8, "clr": 28, "density": 2.0},  # density
    ):
        r = await client.post(f"/v1/milk-transactions/{tid}/quality", json=body, headers=headers)
        assert r.status_code == 409, body
    r = await client.post(
        f"/v1/milk-transactions/{tid}/quality",
        json={"source": "manual", "fat": 4.1, "snf": 8.4, "clr": 27.0, "remarks": "fresh"},
        headers=headers,
    )
    assert r.status_code == 200 and r.json()["state"] == "PRICED"


async def test_mock_analyzer_adapter_fills_quality(client):
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _fresh_tx(client, headers, session["id"])
    await _identify(client, headers, tid, "code", value=supplier["code"])
    await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "cow", "container_type": "can", "container_identifier": "MA-1"},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tid}/weight", json={"source": "mock_scale"}, headers=headers
    )
    r = await client.post(
        f"/v1/milk-transactions/{tid}/quality", json={"source": "mock_analyzer"}, headers=headers
    )
    assert r.status_code == 200
    body = r.json()
    assert 3.0 <= body["fat"] <= 6.5
    assert 7.5 <= body["snf"] <= 9.5
    assert body["pricing_status"] == "pricing_unavailable"  # no rate card in fixture


# --- list & audit ------------------------------------------------------------


async def test_list_filters_and_audit_trail(client):
    headers, center, session, supplier = await _engine_fixture(client)
    tid = await _drive_to_priced(client, headers, session["id"], supplier)
    await client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers)
    await client.post(f"/v1/milk-transactions/{tid}/complete", headers=headers)
    cancelled = await _fresh_tx(client, headers, session["id"])
    await client.post(
        f"/v1/milk-transactions/{cancelled}/cancel", json={"reason": "x"}, headers=headers
    )

    page = (await client.get("/v1/milk-transactions", headers=headers)).json()
    assert page["total"] == 2
    page = (await client.get("/v1/milk-transactions?state=COMPLETED", headers=headers)).json()
    assert page["total"] == 1 and page["items"][0]["id"] == tid
    page = (
        await client.get(f"/v1/milk-transactions?supplier_id={supplier['id']}", headers=headers)
    ).json()
    assert page["total"] == 1
    page = (
        await client.get(f"/v1/milk-transactions?center_id={center['id']}", headers=headers)
    ).json()
    assert page["total"] == 2

    # Full audit trail: every engine step is in the tenant audit log.
    audit = (await client.get("/v1/audit?limit=200", headers=headers)).json()
    actions = [a["action"] for a in audit["items"]]
    for expected in (
        "collection.transaction.TransactionCreated",
        "collection.transaction.WeightCaptured",
        "collection.transaction.QualityCaptured",
        "collection.transaction.TransactionAccepted",
        "collection.transaction.TransactionCompleted",
    ):
        assert expected in actions


async def test_create_on_closed_session_rejected(client):
    headers, _, session, _ = await _engine_fixture(client)
    await client.post(f"/v1/collection-sessions/{session['id']}/close", headers=headers)
    r = await client.post(
        "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
    )
    assert r.status_code == 409
    r = await client.post(
        "/v1/milk-transactions", json={"session_id": str(uuid.uuid4())}, headers=headers
    )
    assert r.status_code == 404


async def test_cancelled_transaction_is_immutable(client):
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _fresh_tx(client, headers, session["id"])
    await client.post(
        f"/v1/milk-transactions/{tid}/cancel", json={"reason": "left"}, headers=headers
    )
    r = await _identify(client, headers, tid, "code", value=supplier["code"])
    assert r.status_code == 409 and "immutable" in r.json()["extra"]


async def test_viewer_can_read_but_not_record(client):
    headers, _, session, _ = await _engine_fixture(client)
    _inv, inv_token = await invite(
        client,
        headers,
        email="txviewer@kilima.example",
        role_name="tenant-viewer",
    )
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
            "password": "viewer-password-1",
            "full_name": "Tx Viewer",
        },
    )
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "txviewer@kilima.example",
                "password": "viewer-password-1",
                "tenant_id": me["tenant_id"],
            },
        )
    ).json()
    viewer = {"Authorization": f"Bearer {pair['access_token']}"}
    assert (await client.get("/v1/milk-transactions", headers=viewer)).status_code == 200
    r = await client.post(
        "/v1/milk-transactions", json={"session_id": session["id"]}, headers=viewer
    )
    assert r.status_code == 403


async def test_events_endpoint_unknown_transaction(client):
    headers, _, _, _ = await _engine_fixture(client)
    r = await client.get(f"/v1/milk-transactions/{uuid.uuid4()}/events", headers=headers)
    assert r.status_code == 404


async def test_transaction_pagination(client):
    headers, _, session, _supplier = await _engine_fixture(client)
    for _ in range(3):
        tid = await _fresh_tx(client, headers, session["id"])
        await client.post(
            f"/v1/milk-transactions/{tid}/cancel", json={"reason": "x"}, headers=headers
        )
    page = (await client.get("/v1/milk-transactions?limit=2&offset=0", headers=headers)).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    page = (await client.get("/v1/milk-transactions?limit=2&offset=2", headers=headers)).json()
    assert len(page["items"]) == 1
