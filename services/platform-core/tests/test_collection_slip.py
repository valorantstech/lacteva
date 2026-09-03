"""The collection slip / parchi (P0-BIZ-003) and differentiated cow/buffalo
pricing (P0-BIZ-001).

The slip is the farmer's copy of the books: every figure on it must be the
STORED value, byte for byte — the tests here compare the slip's JSON strings
against the transaction's own JSON strings, never against arithmetic done in
the test. And the slip number is a document number: sequential per tenant
year, minted exactly once, refused before completion.

P0-BIZ-001's structural answer is proven here end to end: cow and buffalo are
DIFFERENT PRODUCTS (`RAW-COW-MILK` / `RAW-BUFFALO-MILK`) on the same rate
card, so the same FAT reading prices differently by milk type — the shape
every real Indian dual-chart dairy uses.
"""

import re
import uuid

from tests.test_localization import _tenant_admin_for
from tests.test_milk_collection import _engine_fixture
from tests.test_pricing_matrix import _create_matrix, _publish_card
from tests.test_pricing_resolution import _add_bands
from tests.test_rate_cards import _assign_scope, _create_card

SLIP_PATTERN = re.compile(r"^SLP-\d{4}-\d{6}$")


async def _priced_env(client, *, cow_rate=40.0, buffalo_rate=55.0):
    """The engine fixture plus a PUBLISHED card pricing cow and buffalo
    separately on FAT — the dual-chart shape."""
    headers, center, session, supplier = await _engine_fixture(client)
    card = await _create_card(client, headers, code="SLIP-CARD", effective_from="2026-01-01")
    await _assign_scope(client, headers, card["id"], center["id"], product="RAW-COW-MILK")
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/products",
        json={"product_code": "RAW-BUFFALO-MILK"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    cow = await _create_matrix(
        client, headers, card["id"], name="Cow FAT", product_code="RAW-COW-MILK"
    )
    buffalo = await _create_matrix(
        client, headers, card["id"], name="Buffalo FAT", product_code="RAW-BUFFALO-MILK"
    )
    await _add_bands(client, headers, cow["id"], ((3.0, 9.0, cow_rate),))
    await _add_bands(client, headers, buffalo["id"], ((3.0, 9.0, buffalo_rate),))
    await _publish_card(client, headers, card["id"])
    return headers, center, session, supplier


async def _collect(client, headers, session_id, supplier, *, milk_type="cow", fat=4.2):
    """Walk one collection to PRICED; returns the transaction id."""
    tx = (
        await client.post("/v1/milk-transactions", json={"session_id": session_id}, headers=headers)
    ).json()
    tid = tx["id"]
    for step, body in (
        ("identify", {"method": "code", "value": supplier["code"]}),
        (
            "milk",
            {"milk_type": milk_type, "container_type": "can", "container_identifier": "CAN-9"},
        ),
        ("weight", {"source": "manual", "gross": 27.5, "tare": 2.5}),
        ("quality", {"source": "manual", "fat": fat, "snf": 8.6, "clr": 28.5}),
    ):
        r = await client.post(f"/v1/milk-transactions/{tid}/{step}", json=body, headers=headers)
        assert r.status_code == 200, r.text
    return tid


async def _complete(client, headers, tid, *, reject_reason=None):
    if reject_reason:
        r = await client.post(
            f"/v1/milk-transactions/{tid}/reject", json={"reason": reject_reason}, headers=headers
        )
    else:
        r = await client.post(f"/v1/milk-transactions/{tid}/accept", headers=headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/v1/milk-transactions/{tid}/complete", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- the number --------------------------------------------------------------


async def test_completion_mints_a_sequential_slip_number(client):
    headers, _center, session, supplier = await _engine_fixture(client)
    first = await _complete(
        client, headers, await _collect(client, headers, session["id"], supplier)
    )
    second = await _complete(
        client, headers, await _collect(client, headers, session["id"], supplier)
    )

    assert SLIP_PATTERN.match(first["slip_number"]), first["slip_number"]
    assert SLIP_PATTERN.match(second["slip_number"])
    n1 = int(first["slip_number"].rsplit("-", 1)[1])
    n2 = int(second["slip_number"].rsplit("-", 1)[1])
    assert n2 == n1 + 1, "slip numbers must be sequential within the tenant's year"


async def test_no_slip_before_completion(client):
    headers, _center, session, supplier = await _engine_fixture(client)
    tid = await _collect(client, headers, session["id"], supplier)

    tx = (await client.get(f"/v1/milk-transactions/{tid}", headers=headers)).json()
    assert tx["slip_number"] is None, "a number before completion would not be a completion number"
    r = await client.get(f"/v1/milk-transactions/{tid}/slip", headers=headers)
    assert r.status_code == 409, r.text


async def test_cancelled_transaction_has_no_slip(client):
    headers, _center, session, supplier = await _engine_fixture(client)
    tid = await _collect(client, headers, session["id"], supplier)
    r = await client.post(
        f"/v1/milk-transactions/{tid}/cancel", json={"reason": "spilled"}, headers=headers
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"/v1/milk-transactions/{tid}/slip", headers=headers)
    assert r.status_code == 409, r.text


async def test_a_historical_completion_gets_its_number_on_first_read_and_keeps_it(client):
    """History from before slips existed: `slip_number = NULL` on a COMPLETED
    row. The first slip read mints the next number in the series; the second
    read returns the SAME slip, not a fresh number."""
    headers, _center, session, supplier = await _engine_fixture(client)
    tid = await _collect(client, headers, session["id"], supplier)
    await _complete(client, headers, tid)

    from sqlalchemy import update

    from platform_core.core.db import get_session_factory
    from platform_core.modules.milk_collection.models import MilkCollectionTransaction

    async with get_session_factory()() as db:  # simulate the pre-slip row
        await db.execute(
            update(MilkCollectionTransaction)
            .where(MilkCollectionTransaction.id == uuid.UUID(tid))
            .values(slip_number=None)
        )
        await db.commit()

    first = await client.get(f"/v1/milk-transactions/{tid}/slip", headers=headers)
    assert first.status_code == 200, first.text
    minted = first.json()["slip_number"]
    assert SLIP_PATTERN.match(minted)

    again = await client.get(f"/v1/milk-transactions/{tid}/slip", headers=headers)
    assert again.json()["slip_number"] == minted, "a slip number is minted once"


# --- the document ------------------------------------------------------------


async def test_slip_carries_every_parchi_field_and_the_exact_books(client):
    """Every field a real parchi shows — and the money is the transaction's
    OWN JSON, compared string to string, never recomputed."""
    headers, center, session, supplier = await _priced_env(client)
    tid = await _collect(client, headers, session["id"], supplier, fat=4.2)
    await _complete(client, headers, tid)

    tx = (await client.get(f"/v1/milk-transactions/{tid}", headers=headers)).json()
    r = await client.get(f"/v1/milk-transactions/{tid}/slip", headers=headers)
    assert r.status_code == 200, r.text
    slip = r.json()

    assert slip["slip_number"] == tx["slip_number"]
    assert slip["organization_name"]  # the dairy's own name heads the slip
    assert slip["center_name"] == center["name"]
    assert slip["session_label"] == "morning"  # the shift
    assert slip["business_date"]
    assert slip["milk_type"] == "cow"
    # D-21 / WO-70: the unit READ from the record — this Kenyan tenant's is the litre.
    assert slip["quantity"] == 25.0 and slip["weight_unit"] == "litre"
    assert slip["gross_weight"] == 27.5 and slip["tare_weight"] == 2.5
    assert slip["fat"] == 4.2 and slip["snf"] == 8.6 and slip["clr"] == 28.5
    assert slip["supplier_code"] == supplier["code"]
    assert slip["supplier_name"] == supplier["full_name"]
    assert slip["operator_name"]
    assert slip["decision"] == "ACCEPTED"

    # Financial byte-identity: the slip's strings ARE the transaction's.
    assert slip["unit_price"] == tx["unit_price"]
    assert slip["gross_amount"] == tx["gross_amount"]
    assert slip["currency"] == tx["currency"]

    # The shareable text carries the number, the quality and the money.
    assert slip["slip_number"] in slip["text"]
    assert "FAT 4.2" in slip["text"]
    assert str(tx["gross_amount"]) in slip["text"]
    assert supplier["full_name"] in slip["text"]


async def test_morning_and_evening_shifts_are_distinguishable(client):
    """Two sessions on the same day, two shifts — each slip names its own."""
    headers, center, session, supplier = await _engine_fixture(client)
    morning_tid = await _collect(client, headers, session["id"], supplier)
    await _complete(client, headers, morning_tid)
    r = await client.post(f"/v1/collection-sessions/{session['id']}/close", headers=headers)
    assert r.status_code == 200, r.text
    evening = (
        await client.post(
            "/v1/collection-sessions",
            json={"center_id": center["id"], "label": "evening"},
            headers=headers,
        )
    ).json()
    evening_tid = await _collect(client, headers, evening["id"], supplier)
    await _complete(client, headers, evening_tid)

    morning_slip = (
        await client.get(f"/v1/milk-transactions/{morning_tid}/slip", headers=headers)
    ).json()
    evening_slip = (
        await client.get(f"/v1/milk-transactions/{evening_tid}/slip", headers=headers)
    ).json()
    assert morning_slip["session_label"] == "morning"
    assert evening_slip["session_label"] == "evening"


async def test_rejected_milk_still_gets_a_slip_that_says_so(client):
    """Proof of rejection is a document the farmer is owed: numbered like any
    other slip, showing the reason and NO amount."""
    headers, _center, session, supplier = await _engine_fixture(client)
    tid = await _collect(client, headers, session["id"], supplier)
    await _complete(client, headers, tid, reject_reason="adulteration suspected")

    slip = (await client.get(f"/v1/milk-transactions/{tid}/slip", headers=headers)).json()
    assert SLIP_PATTERN.match(slip["slip_number"])
    assert slip["decision"] == "REJECTED"
    assert slip["rejected_reason"] == "adulteration suspected"
    assert slip["unit_price"] is None and slip["gross_amount"] is None
    assert "REJECTED" in slip["text"] and "adulteration suspected" in slip["text"]


async def test_accepted_but_unpriced_milk_says_rate_pending(client):
    """No published rate card covered this milk: the slip must say the rate is
    pending, never print a blank that reads as zero."""
    headers, _center, session, supplier = await _engine_fixture(client)
    tid = await _collect(client, headers, session["id"], supplier)
    await _complete(client, headers, tid)

    slip = (await client.get(f"/v1/milk-transactions/{tid}/slip", headers=headers)).json()
    assert slip["pricing_status"] == "pricing_unavailable"
    assert slip["unit_price"] is None
    assert "Rate pending" in slip["text"]


async def test_a_hindi_dairy_gets_a_bilingual_parchi(client):
    """An organization whose default language is Hindi shares a slip the
    farmer can read: English and Hindi labels side by side."""
    headers, _center, session, supplier = await _priced_env(client)
    tid = await _collect(client, headers, session["id"], supplier, milk_type="buffalo")
    await _complete(client, headers, tid)

    from sqlalchemy import update

    from platform_core.core.db import get_session_factory
    from platform_core.modules.organization.models import Organization

    async with get_session_factory()() as db:
        await db.execute(update(Organization).values(default_locale="hi-IN"))
        await db.commit()

    slip = (await client.get(f"/v1/milk-transactions/{tid}/slip", headers=headers)).json()
    assert "पर्ची" in slip["text"]  # Slip
    assert "किसान" in slip["text"]  # Farmer
    assert "भैंस" in slip["text"]  # buffalo, named in the farmer's language


async def test_every_milk_type_the_platform_knows_has_a_hindi_name(client):
    """WO-55 added `sheep` to the vocabulary, and a farmer handed a parchi in
    Hindi should not be the one person who reads the animal in English.

    `custom` is deliberately absent: its name is whatever the operator typed,
    and the slip prints that rather than a translation of the word "custom".
    """
    from platform_core.core.milk import MILK_TYPES
    from platform_core.modules.milk_collection.service import _SLIP_MILK_HI

    missing = [m for m in MILK_TYPES if m != "custom" and m not in _SLIP_MILK_HI]
    assert not missing, f"no Hindi name on the parchi for: {missing}"


# --- P0-BIZ-001: cow and buffalo price differently ---------------------------


async def test_cow_and_buffalo_price_differently_from_the_same_fat(client):
    """The dual-chart proof: one rate card, two products, same FAT reading —
    and the platform prices them apart, end to end through the collection
    engine, onto two slips that name their milk."""
    headers, _center, session, supplier = await _priced_env(
        client, cow_rate=40.0, buffalo_rate=55.0
    )
    cow_tid = await _collect(client, headers, session["id"], supplier, milk_type="cow", fat=6.5)
    await _complete(client, headers, cow_tid)
    buffalo_tid = await _collect(
        client, headers, session["id"], supplier, milk_type="buffalo", fat=6.5
    )
    await _complete(client, headers, buffalo_tid)

    cow_tx = (await client.get(f"/v1/milk-transactions/{cow_tid}", headers=headers)).json()
    buffalo_tx = (await client.get(f"/v1/milk-transactions/{buffalo_tid}", headers=headers)).json()
    assert cow_tx["pricing_status"] == "priced"
    assert buffalo_tx["pricing_status"] == "priced"
    assert str(cow_tx["unit_price"]) != str(buffalo_tx["unit_price"]), (
        "same FAT, same card — the milk type alone must change the rate"
    )

    cow_slip = (await client.get(f"/v1/milk-transactions/{cow_tid}/slip", headers=headers)).json()
    buffalo_slip = (
        await client.get(f"/v1/milk-transactions/{buffalo_tid}/slip", headers=headers)
    ).json()
    assert cow_slip["milk_type"] == "cow" and buffalo_slip["milk_type"] == "buffalo"
    assert cow_slip["unit_price"] == cow_tx["unit_price"]
    assert buffalo_slip["unit_price"] == buffalo_tx["unit_price"]


# --- security and immutability ----------------------------------------------


async def test_a_slip_is_another_tenants_404(client):
    headers, _center, session, supplier = await _engine_fixture(client)
    tid = await _collect(client, headers, session["id"], supplier)
    await _complete(client, headers, tid)

    _org_b, other = await _tenant_admin_for(
        client, country="KE", slug="slip-iso-b", email="admin@slipiso.example"
    )
    r = await client.get(f"/v1/milk-transactions/{tid}/slip", headers=other)
    assert r.status_code == 404, "another tenant's slip must be indistinguishable from absence"


async def test_a_slip_needs_authentication(client):
    headers, _center, session, supplier = await _engine_fixture(client)
    tid = await _collect(client, headers, session["id"], supplier)
    await _complete(client, headers, tid)

    r = await client.get(f"/v1/milk-transactions/{tid}/slip")
    assert r.status_code == 401


async def test_reading_a_slip_changes_no_financial_byte(client):
    """The mutation check: the whole transaction JSON before and after the
    slip read, compared as strings. The slip renders the books — it must
    never move them."""
    headers, _center, session, supplier = await _priced_env(client)
    tid = await _collect(client, headers, session["id"], supplier)
    await _complete(client, headers, tid)

    before = (await client.get(f"/v1/milk-transactions/{tid}", headers=headers)).text
    for _ in range(3):
        r = await client.get(f"/v1/milk-transactions/{tid}/slip", headers=headers)
        assert r.status_code == 200
    after = (await client.get(f"/v1/milk-transactions/{tid}", headers=headers)).text
    assert before == after
