"""Instrument readings, and the attribution that makes them worth trusting.

WO-49 · LACTEVA-DEVICE-001. The hardware spec (§5) calls this read-assist: an
analyzer or scale pre-fills the operator's capture screen, the operator
confirms, and the reading lands through the SAME endpoint with the same
validation. Only the attribution differs.

Spec §7 is the reason these tests are adversarial rather than happy-path:
provenance "is a security control — it is what makes a fabricated reading
distinguishable after the fact". An instrument source that nobody checks is
worse than no instrument source at all, because it launders an unattributed
number through a word that implies a machine. So every test below is a way of
claiming a device that is not there.
"""

import uuid

import pytest

from tests.test_procurement_e2e import _procurement_env

pytestmark = pytest.mark.asyncio


async def _device(client, headers, center_id, *, category, status="active"):
    """A registered device, walked through the real lifecycle."""
    device = (
        await client.post(
            "/v1/devices",
            json={
                "category": category,
                "serial_number": f"{category}-{uuid.uuid4().hex[:8]}",
                "name": f"Counter {category}",
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/v1/devices/{device['id']}/assign", json={"center_id": str(center_id)}, headers=headers
    )
    if status != "assigned":
        await client.post(
            f"/v1/devices/{device['id']}/status", json={"status": status}, headers=headers
        )
    return device


async def _to_weight_step(client, headers, session_id, supplier):
    tx = (
        await client.post("/v1/milk-transactions", json={"session_id": session_id}, headers=headers)
    ).json()
    qr = (await client.get(f"/v1/suppliers/{supplier['id']}/qr", headers=headers)).json()
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/identify",
        json={"method": "qr", "value": qr["payload"]},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/milk",
        json={
            "milk_type": "cow",
            "container_type": "can",
            "container_identifier": "CAN-DEV-1",
            "temperature_c": 4.0,
        },
        headers=headers,
    )
    return tx


async def test_a_scale_reading_is_accepted_and_says_which_scale(client):
    headers, center, supplier, session = await _procurement_env(client)
    scale = await _device(client, headers, center["id"], category="scale")
    tx = await _to_weight_step(client, headers, session["id"], supplier)

    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={
            "source": "scale",
            "unit": "kg",
            "gross": 32.5,
            "tare": 4.5,
            "device_id": scale["id"],
            "frame_hash": "sha256:" + "a" * 64,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["weight_source"] == "scale"

    # The provenance rides the event, not a new column: spec §14 says the
    # schema does not change for read-assist, and it did not need to.
    events = (await client.get(f"/v1/milk-transactions/{tx['id']}/events", headers=headers)).json()
    rows = events["items"] if isinstance(events, dict) else events
    captured = next(e for e in rows if e["event_type"] == "WeightCaptured")
    assert captured["data"]["source"] == "scale"
    assert captured["data"]["device_id"] == scale["id"]
    assert captured["data"]["frame_hash"].startswith("sha256:")


async def test_an_analyzer_reading_is_accepted_and_says_which_analyzer(client):
    headers, center, supplier, session = await _procurement_env(client)
    analyzer = await _device(client, headers, center["id"], category="milk_analyzer")
    tx = await _to_weight_step(client, headers, session["id"], supplier)
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={"source": "manual", "unit": "kg", "gross": 30.0, "tare": 5.0},
        headers=headers,
    )

    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/quality",
        json={
            "source": "analyzer",
            "fat": 4.2,
            "snf": 8.4,
            "clr": 27.5,
            "device_id": analyzer["id"],
            "frame_hash": "sha256:" + "b" * 64,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["quality_source"] == "analyzer"


# --- every way of claiming a device that is not there ------------------------


async def test_an_instrument_reading_without_a_device_is_refused(client):
    """The whole point. `source=scale` with no device is a hand-typed number
    wearing a machine's name."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _to_weight_step(client, headers, session["id"], supplier)

    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={"source": "scale", "unit": "kg", "gross": 32.5, "tare": 4.5},
        headers=headers,
    )
    assert r.status_code == 409
    assert "device_id" in r.text


async def test_an_unregistered_device_is_refused(client):
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _to_weight_step(client, headers, session["id"], supplier)

    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={
            "source": "scale",
            "unit": "kg",
            "gross": 32.5,
            "tare": 4.5,
            "device_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert r.status_code in (404, 409)


async def test_a_printer_cannot_report_a_weight(client):
    """Category is checked, or `device_id` is just a uuid that exists."""
    headers, center, supplier, session = await _procurement_env(client)
    printer = await _device(client, headers, center["id"], category="printer")
    tx = await _to_weight_step(client, headers, session["id"], supplier)

    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={
            "source": "scale",
            "unit": "kg",
            "gross": 32.5,
            "tare": 4.5,
            "device_id": printer["id"],
        },
        headers=headers,
    )
    assert r.status_code == 409
    assert "printer" in r.text


async def test_a_retired_device_can_no_longer_report(client):
    """Spec §9: retiring a device must kill its access. A number attributed to
    a decommissioned instrument is the clearest possible fabrication."""
    headers, center, supplier, session = await _procurement_env(client)
    scale = await _device(client, headers, center["id"], category="scale")
    await client.post(
        f"/v1/devices/{scale['id']}/status", json={"status": "retired"}, headers=headers
    )
    tx = await _to_weight_step(client, headers, session["id"], supplier)

    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={
            "source": "scale",
            "unit": "kg",
            "gross": 32.5,
            "tare": 4.5,
            "device_id": scale["id"],
        },
        headers=headers,
    )
    assert r.status_code == 409
    assert "retired" in r.text


async def test_manual_capture_is_untouched_and_needs_no_device(client):
    """Spec §26: manual is permanent and first-class. The instrument path must
    not have made the ordinary one harder."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _to_weight_step(client, headers, session["id"], supplier)

    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={"source": "manual", "unit": "kg", "gross": 30.0, "tare": 5.0},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["weight_source"] == "manual"


async def test_a_real_source_never_reuses_a_mock_name(client):
    """Spec §14 and §7: mocks stay production-refused forever, and no real
    adapter takes a `mock_*` name. FINAL-001 is why."""
    from platform_core.modules.milk_collection.models import CAPTURE_SOURCES, INSTRUMENT_SOURCES

    assert set(INSTRUMENT_SOURCES) == {"scale", "analyzer"}
    assert not any(name.startswith("mock_") for name in INSTRUMENT_SOURCES)
    for mock in ("mock_scale", "mock_analyzer"):
        assert mock in CAPTURE_SOURCES, "the mock vocabulary must not be quietly dropped"
