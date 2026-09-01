"""Milk reported by the animal it came from (WO-55 · LACTEVA-REPORT-001).

`milk_type` has been on every transaction since the beginning, and the pricing
engine has always resolved a rate per type — a buffalo litre and a cow litre
are different money. Nothing REPORTED by type, so a dairy taking both could
see what it paid in total and never what it paid for which. These pin the
breakdown, and the two ways it could mislead: inventing a category out of
free text, and adding two currencies together.
"""

import pytest

from tests.test_procurement_e2e import _procurement_env, _run_collection

pytestmark = pytest.mark.asyncio


async def _daily(client, headers, center_id):
    r = await client.get(
        "/v1/reports/collection/daily", params={"center_id": center_id}, headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _collect(client, headers, session_id, supplier, *, milk_type, gross, fat=4.2):
    """One collection of a named kind, walked through the real state machine."""
    tx = (
        await client.post("/v1/milk-transactions", json={"session_id": session_id}, headers=headers)
    ).json()
    qr = (await client.get(f"/v1/suppliers/{supplier['id']}/qr", headers=headers)).json()
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/identify",
        json={"method": "qr", "value": qr["payload"]},
        headers=headers,
    )
    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/milk",
        json={
            "milk_type": milk_type,
            "container_type": "can",
            "container_identifier": f"CAN-{milk_type}",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={"source": "manual", "gross": gross, "tare": 5.0},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/quality",
        json={"source": "manual", "fat": fat, "snf": 8.5, "clr": 28.0},
        headers=headers,
    )
    await client.post(f"/v1/milk-transactions/{tx['id']}/accept", headers=headers)
    return tx


async def test_sheep_is_a_milk_type_the_platform_accepts(client):
    """It was the one common Indian dairy animal the vocabulary omitted, so a
    dairy taking sheep milk had to record it as `custom` — which prices and
    reports as "custom" rather than as itself."""
    from platform_core.modules.milk_collection.models import MILK_TYPES

    assert "sheep" in MILK_TYPES
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _collect(client, headers, session["id"], supplier, milk_type="sheep", gross=25.0)
    assert tx is not None


async def test_the_daily_report_splits_the_day_by_animal(client):
    headers, center, supplier, session = await _procurement_env(client)
    await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=35.0)
    await _collect(client, headers, session["id"], supplier, milk_type="buffalo", gross=25.0)

    report = await _daily(client, headers, center["id"])
    rows = {row["milk_type"]: row for row in report["by_milk_type"]}

    assert set(rows) == {"cow", "buffalo"}
    assert rows["cow"]["net_weight_kg"] == 30.0  # 35 gross - 5 tare
    assert rows["buffalo"]["net_weight_kg"] == 20.0
    # The parts add up to the whole, or one of the two numbers is wrong.
    assert sum(r["net_weight_kg"] for r in rows.values()) == report["total_net_weight_kg"]


async def test_the_heaviest_kind_is_listed_first(client):
    """A dairy reads the top row and expects its main line of business."""
    headers, center, supplier, session = await _procurement_env(client)
    await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=15.0)
    await _collect(client, headers, session["id"], supplier, milk_type="buffalo", gross=45.0)

    report = await _daily(client, headers, center["id"])
    assert [row["milk_type"] for row in report["by_milk_type"]] == ["buffalo", "cow"]


async def test_a_custom_type_reports_as_custom_and_invents_no_category(client):
    """Grouping on the free-text name would invent a category per spelling —
    "Camel", "camel" and "camel milk" would be three lines about one animal."""
    headers, center, supplier, session = await _procurement_env(client)
    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
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
            "milk_type": "custom",
            "milk_type_custom": "Camel",
            "container_type": "can",
            "container_identifier": "CAN-C",
        },
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={"source": "manual", "gross": 20.0, "tare": 5.0},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/quality",
        json={"source": "manual", "fat": 4.0, "snf": 8.5, "clr": 28.0},
        headers=headers,
    )
    await client.post(f"/v1/milk-transactions/{tx['id']}/accept", headers=headers)

    report = await _daily(client, headers, center["id"])
    kinds = [row["milk_type"] for row in report["by_milk_type"]]
    assert kinds == ["custom"]
    assert "Camel" not in kinds, "free text became a reporting category"


async def test_a_rejected_collection_is_in_no_type_row(client):
    """The breakdown is of milk the dairy TOOK. Rejected milk was not."""
    headers, center, supplier, session = await _procurement_env(client)
    await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=35.0)

    tx = (
        await client.post(
            "/v1/milk-transactions", json={"session_id": session["id"]}, headers=headers
        )
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
            "milk_type": "buffalo",
            "container_type": "can",
            "container_identifier": "CAN-R",
        },
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/weight",
        json={"source": "manual", "gross": 30.0, "tare": 5.0},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/quality",
        json={"source": "manual", "fat": 4.0, "snf": 8.5, "clr": 28.0},
        headers=headers,
    )
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/reject",
        json={"reason": "sour on arrival"},
        headers=headers,
    )

    report = await _daily(client, headers, center["id"])
    assert [row["milk_type"] for row in report["by_milk_type"]] == ["cow"]


async def test_a_single_type_dairy_still_gets_its_one_row(client):
    """The breakdown appears when there is something to break down, and one
    kind is still something — a dairy should not have to wonder why the
    section is missing."""
    headers, center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    # Accepted, because the breakdown is of milk the dairy TOOK — a priced but
    # undecided collection is not yet that.
    await client.post(f"/v1/milk-transactions/{tx['id']}/accept", headers=headers)
    report = await _daily(client, headers, center["id"])
    assert len(report["by_milk_type"]) == 1
    assert report["by_milk_type"][0]["milk_type"] == "cow"
