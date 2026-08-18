"""Supplier FAT/SNF deviation flag (P0-PILOT-003 — the one AI MVP).

Statistics against the supplier's OWN recent baseline, surfaced as a
non-blocking `QualityDeviationFlagged` event in the transaction's trail.
Nothing is refused, nothing reaches the parchi, no vendor is involved — and
these tests pin the honesty rules: a new farmer is never flagged for lacking
a past, a consistent reading is never flagged, and one milk type's baseline
says nothing about another's.
"""

from tests.test_collection_slip import _collect, _complete
from tests.test_milk_collection import _engine_fixture


async def _events(client, headers, tid):
    r = await client.get(f"/v1/milk-transactions/{tid}/events", headers=headers)
    return [e["event_type"] for e in r.json()], r.json()


async def _baseline(client, headers, session_id, supplier, *, n=5, fat=4.1, milk_type="cow"):
    for _ in range(n):
        tid = await _collect(client, headers, session_id, supplier, milk_type=milk_type, fat=fat)
        await _complete(client, headers, tid)


async def test_a_reading_far_from_the_suppliers_own_baseline_is_flagged(client):
    headers, _center, session, supplier = await _engine_fixture(client)
    await _baseline(client, headers, session["id"], supplier, fat=4.1)

    tid = await _collect(client, headers, session["id"], supplier, fat=6.8)
    types, events = await _events(client, headers, tid)
    assert "QualityDeviationFlagged" in types

    flag = next(e for e in events if e["event_type"] == "QualityDeviationFlagged")
    assert "fat" in flag["data"]["metrics"]
    fat = flag["data"]["metrics"]["fat"]
    assert fat["value"] == 6.8
    assert fat["baseline_n"] == 5
    # The reading was NOT blocked: the transaction priced/proceeded as ever.
    tx = (await client.get(f"/v1/milk-transactions/{tid}", headers=headers)).json()
    assert tx["state"] in ("PRICED", "QUALITY_CAPTURED", "PRICING_PENDING")


async def test_a_consistent_reading_is_never_flagged(client):
    headers, _center, session, supplier = await _engine_fixture(client)
    await _baseline(client, headers, session["id"], supplier, fat=4.1)

    tid = await _collect(client, headers, session["id"], supplier, fat=4.2)
    types, _ = await _events(client, headers, tid)
    assert "QualityDeviationFlagged" not in types


async def test_a_new_farmer_is_never_flagged_for_lacking_a_past(client):
    headers, _center, session, supplier = await _engine_fixture(client)
    tid = await _collect(client, headers, session["id"], supplier, fat=9.5)
    types, _ = await _events(client, headers, tid)
    assert "QualityDeviationFlagged" not in types


async def test_one_milk_types_baseline_says_nothing_about_another(client):
    """Five cow collections at 4.1 FAT must not flag buffalo milk at 6.8 —
    6.8 is a perfectly ordinary buffalo reading."""
    headers, _center, session, supplier = await _engine_fixture(client)
    await _baseline(client, headers, session["id"], supplier, fat=4.1, milk_type="cow")

    tid = await _collect(client, headers, session["id"], supplier, milk_type="buffalo", fat=6.8)
    types, _ = await _events(client, headers, tid)
    assert "QualityDeviationFlagged" not in types


async def test_the_flag_never_reaches_the_parchi(client):
    """The farmer's slip must not accuse; the operator's trail may inform."""
    headers, _center, session, supplier = await _engine_fixture(client)
    await _baseline(client, headers, session["id"], supplier, fat=4.1)

    tid = await _collect(client, headers, session["id"], supplier, fat=6.8)
    await _complete(client, headers, tid)
    slip = (await client.get(f"/v1/milk-transactions/{tid}/slip", headers=headers)).json()
    assert "eviation" not in slip["text"]
    assert "flag" not in slip["text"].lower()
