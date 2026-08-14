"""Device registry, operator assignment, and the readiness engine."""

import uuid

from tests.test_collection_centers import _center_fixture


async def _register(client, headers, category, serial, name=None):
    r = await client.post(
        "/v1/devices",
        json={"category": category, "serial_number": serial, "name": name or serial},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _activate_device(client, headers, device_id, center_id):
    r = await client.post(
        f"/v1/devices/{device_id}/assign", json={"center_id": center_id}, headers=headers
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/v1/devices/{device_id}/status", json={"status": "active"}, headers=headers
    )
    assert r.status_code == 200, r.text


async def test_device_lifecycle_and_serial_uniqueness(client, bus):
    headers, _, center = await _center_fixture(client)
    device = await _register(client, headers, "scale", "SC-001")
    assert device["status"] == "registered" and device["center_id"] is None

    # Duplicate serial and unknown category are rejected.
    r = await client.post(
        "/v1/devices",
        json={"category": "scale", "serial_number": "SC-001", "name": "Dup"},
        headers=headers,
    )
    assert r.status_code == 409
    r = await client.post(
        "/v1/devices",
        json={"category": "teleporter", "serial_number": "T-1", "name": "Nope"},
        headers=headers,
    )
    assert r.status_code == 422

    # registered -> active directly is illegal; assignment is its own step.
    r = await client.post(
        f"/v1/devices/{device['id']}/status", json={"status": "active"}, headers=headers
    )
    assert r.status_code == 409

    await _activate_device(client, headers, device["id"], center["id"])
    # active -> maintenance -> active -> retired; retired is terminal.
    for target, expected in (
        ("maintenance", 200),
        ("active", 200),
        ("retired", 200),
        ("active", 409),
    ):
        r = await client.post(
            f"/v1/devices/{device['id']}/status", json={"status": target}, headers=headers
        )
        assert r.status_code == expected, f"{target}: {r.text}"
    assert "operations.device-status-changed.v1" in [e.type for e in bus.published]


async def test_device_assignment_requires_center_in_tenant(client):
    headers, _, _ = await _center_fixture(client)
    device = await _register(client, headers, "printer", "PR-001")
    r = await client.post(
        f"/v1/devices/{device['id']}/assign",
        json={"center_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert r.status_code == 404


async def test_health_reporting(client):
    headers, _, center = await _center_fixture(client)
    device = await _register(client, headers, "scale", "SC-010")
    await _activate_device(client, headers, device["id"], center["id"])

    r = await client.post(
        f"/v1/devices/{device['id']}/health",
        json={"state": "failed", "note": "drifting readings"},
        headers=headers,
    )
    assert r.status_code == 201
    detail = (await client.get(f"/v1/devices/{device['id']}", headers=headers)).json()
    assert detail["latest_health"] == "failed"
    assert detail["health_note"] == "drifting readings"
    # Unknown state rejected.
    r = await client.post(
        f"/v1/devices/{device['id']}/health", json={"state": "meh"}, headers=headers
    )
    assert r.status_code == 409


async def test_operator_assignment_rules(client):
    headers, _, center = await _center_fixture(client)
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    user_id = me["user"]["id"]
    cid = center["id"]

    r = await client.post(
        f"/v1/collection-centers/{cid}/operators",
        json={"user_id": user_id, "role_label": "operator"},
        headers=headers,
    )
    assert r.status_code == 201
    # Duplicate assignment and unknown user rejected.
    r = await client.post(
        f"/v1/collection-centers/{cid}/operators",
        json={"user_id": user_id},
        headers=headers,
    )
    assert r.status_code == 409
    r = await client.post(
        f"/v1/collection-centers/{cid}/operators",
        json={"user_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert r.status_code == 404

    ops = (await client.get(f"/v1/collection-centers/{cid}/operators", headers=headers)).json()
    assert len(ops) == 1 and ops[0]["role_label"] == "operator"
    r = await client.delete(f"/v1/collection-centers/{cid}/operators/{user_id}", headers=headers)
    assert r.status_code == 204


async def test_readiness_walkthrough(client):
    """The definition-of-done path: NOT_READY -> WARNING -> READY."""
    headers, _, center = await _center_fixture(client)
    cid = center["id"]

    async def readiness():
        r = await client.get(f"/v1/collection-centers/{cid}/readiness", headers=headers)
        assert r.status_code == 200, r.text
        return r.json()

    # Fresh center: inactive, no operator, no devices -> NOT_READY.
    result = await readiness()
    assert result["status"] == "NOT_READY"
    failed_blocking = {c["rule"] for c in result["checks"] if not c["passed"]}
    assert {"center.active", "operator.assigned", "device.scale"} <= failed_blocking

    # Activate the center (needs operating hours first).
    await client.put(
        f"/v1/collection-centers/{cid}/operating-hours",
        json={"windows": [{"day_of_week": 0, "opens": "06:00", "closes": "10:00"}]},
        headers=headers,
    )
    await client.post(
        f"/v1/collection-centers/{cid}/status", json={"status": "active"}, headers=headers
    )
    # Assign an operator.
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    await client.post(
        f"/v1/collection-centers/{cid}/operators",
        json={"user_id": me["user"]["id"]},
        headers=headers,
    )
    # Active scale present.
    scale = await _register(client, headers, "scale", "SC-100")
    await _activate_device(client, headers, scale["id"], cid)

    # Blocking rules now pass; analyzer/printer missing -> WARNING.
    result = await readiness()
    assert result["status"] == "WARNING"
    warn_rules = {c["rule"] for c in result["checks"] if not c["passed"]}
    assert warn_rules == {"device.milk_analyzer", "device.printer"}

    # Add analyzer and printer -> READY.
    for cat, serial in (("milk_analyzer", "MA-1"), ("printer", "PR-9")):
        device = await _register(client, headers, cat, serial)
        await _activate_device(client, headers, device["id"], cid)
    result = await readiness()
    assert result["status"] == "READY"
    assert all(c["passed"] for c in result["checks"])

    # A failed scale drops readiness back to NOT_READY.
    await client.post(
        f"/v1/devices/{scale['id']}/health", json={"state": "failed"}, headers=headers
    )
    result = await readiness()
    assert result["status"] == "NOT_READY"
    scale_check = next(c for c in result["checks"] if c["rule"] == "device.scale")
    assert not scale_check["passed"]


async def test_calendar_closure_blocks_readiness(client):
    from platform_core.core.business_time import business_today

    headers, _, center = await _center_fixture(client)
    cid = center["id"]
    # DEMO-019: the CENTRE's today, not UTC's. Readiness evaluates a closure
    # against the dairy's own calendar day — correctly, since a centre is shut
    # on its own Tuesday — and this test closed it on UTC's day instead. For a
    # Nairobi cooperative after local midnight those are different dates, so
    # the closure landed on a day nobody asked about and readiness passed.
    today = business_today("Africa/Nairobi").isoformat()
    r = await client.post(
        f"/v1/collection-centers/{cid}/calendar",
        json={"day": today, "kind": "closure", "note": "Stocktaking"},
        headers=headers,
    )
    assert r.status_code == 201
    result = (await client.get(f"/v1/collection-centers/{cid}/readiness", headers=headers)).json()
    cal = next(c for c in result["checks"] if c["rule"] == "center.calendar")
    assert not cal["passed"] and cal["severity"] == "blocking"
    assert result["status"] == "NOT_READY"


async def test_rules_and_categories_listing(client):
    headers, _, _ = await _center_fixture(client)
    rules = (await client.get("/v1/readiness/rules", headers=headers)).json()
    assert rules["device.scale"]["severity"] == "blocking"
    assert rules["device.printer"]["severity"] == "warning"
    cats = (await client.get("/v1/device-categories", headers=headers)).json()
    assert set(cats) == {"scale", "milk_analyzer", "printer", "qr_scanner", "rfid_reader", "camera"}


async def test_device_list_filters(client):
    headers, _, center = await _center_fixture(client)
    scale = await _register(client, headers, "scale", "F-SC1")
    await _register(client, headers, "printer", "F-PR1")
    await _activate_device(client, headers, scale["id"], center["id"])

    page = (await client.get("/v1/devices", headers=headers)).json()
    assert page["total"] == 2
    page = (await client.get("/v1/devices?category=scale", headers=headers)).json()
    assert page["total"] == 1 and page["items"][0]["serial_number"] == "F-SC1"
    page = (await client.get(f"/v1/devices?center_id={center['id']}", headers=headers)).json()
    assert page["total"] == 1
    page = (await client.get("/v1/devices?status=registered", headers=headers)).json()
    assert page["total"] == 1 and page["items"][0]["category"] == "printer"
