"""Pricing a collection the platform could not price at the time
(LACTEVA-BACKEND-001; D-3).

Two correct refusals used to add up to a permanent loss. Capture will not
invent a price when no rate card covers the milk — right, because a guessed
rate is worse than none. Settlement will not touch a transaction with no
calculation — also right, because you cannot pay from a number nobody
computed. Between them the collection was stranded forever: the milk was
taken, the parchi said "Rate pending", and no route existed to finish the
sentence once the missing card was published. The first physical handset run
met this on day one.

What these tests defend is that closing that gap did not open a worse one:

  * the rate is the one effective for the TRANSACTION's own day, never
    today's — proven with two non-overlapping cards, where the wrong answer
    is the one a naive implementation would give;
  * a transaction that already has a price is refused, so this can never
    become a quiet recalculation of money somebody has been paid;
  * a foreign tenant's transaction is a 404, and a principal without the
    pricing grant is a 403;
  * and the whole point: a repriced collection actually settles.
"""

import uuid
from decimal import Decimal

from tests.test_milk_collection import _engine_fixture
from tests.test_pricing_matrix import _create_matrix, _publish_card
from tests.test_pricing_resolution import _add_bands
from tests.test_procurement_e2e import _accept_complete, _run_collection
from tests.test_rate_cards import _assign_scope, _create_card


async def _card(client, headers, *, code, bands, effective_from, effective_until=None):
    """A published card scoped to the engine fixture's centre and RAW-COW-MILK."""
    card = await _create_card(
        client,
        headers,
        code=code,
        name=f"Card {code}",
        effective_from=effective_from,
        effective_until=effective_until,
    )
    await _assign_scope(client, headers, card["id"], _card.center_id)
    matrix = await _create_matrix(client, headers, card["id"], name=f"{code} FAT")
    await _add_bands(client, headers, matrix["id"], bands)
    await _publish_card(client, headers, card["id"])
    return card


async def _stranded(client):
    """A COMPLETED collection with no rate card anywhere: rate-pending."""
    headers, center, session, supplier = await _engine_fixture(client)
    _card.center_id = center["id"]
    tx = await _run_collection(client, headers, session["id"], supplier)
    assert tx["pricing_status"] == "pricing_unavailable", tx
    assert tx["calculation_id"] is None
    tx = await _accept_complete(client, headers, tx["id"])
    assert tx["state"] == "COMPLETED"
    return headers, center, supplier, tx


async def _backdate(tx_id: str, when: str) -> None:
    """Move a capture into the past, so 'the transaction's day' and 'today'
    stop being the same day — which is the only way to tell the two apart."""
    from datetime import datetime

    from platform_core.core.db import get_session_factory
    from platform_core.modules.milk_collection.models import MilkCollectionTransaction

    async with get_session_factory()() as db:
        tx = await db.get(MilkCollectionTransaction, uuid.UUID(tx_id))
        tx.created_at = datetime.fromisoformat(when)
        await db.commit()


async def test_reprice_uses_the_rate_effective_on_the_collection_s_own_day(client):
    """The assertion that matters: publishing a card today must not retro-price
    yesterday's milk at today's rate.

    Two cards, no overlap. One covers the day the milk was actually poured; the
    other starts afterwards and runs to today. A implementation that resolved
    against `date.today()` would pick the second and pay the farmer 99 — which
    is exactly the bug this test exists to make impossible.
    """
    headers, _center, _supplier, tx = await _stranded(client)
    await _backdate(tx["id"], "2026-06-15T06:00:00+00:00")

    await _card(
        client,
        headers,
        code="THEN",
        bands=((4.0, 5.0, 40.0),),
        effective_from="2026-01-01",
        effective_until="2026-06-30",
    )
    await _card(
        client,
        headers,
        code="NOW",
        bands=((4.0, 5.0, 99.0),),
        effective_from="2026-07-01",
    )

    r = await client.post(f"/v1/milk-transactions/{tx['id']}/reprice", headers=headers)
    assert r.status_code == 200, r.text
    priced = r.json()

    assert priced["pricing_status"] == "priced"
    assert priced["calculation_id"] is not None
    # 40, the June rate — not 99, the rate in force the day it was resolved.
    assert Decimal(str(priced["unit_price"])) == Decimal("40")
    assert "THEN" in priced["pricing_detail"]
    # Nothing about the collection itself moved.
    assert priced["state"] == "COMPLETED"
    assert Decimal(str(priced["net_weight"])) == Decimal(str(tx["net_weight"]))


async def test_reprice_publishes_the_fact_and_writes_the_audit_trail(client, bus):
    headers, _center, _supplier, tx = await _stranded(client)
    await _card(
        client, headers, code="LATE", bands=((4.0, 5.0, 45.0),), effective_from="2026-01-01"
    )

    r = await client.post(f"/v1/milk-transactions/{tx['id']}/reprice", headers=headers)
    assert r.status_code == 200, r.text

    assert "collection.transaction-repriced.v1" in [e.type for e in bus.published]
    events = (await client.get(f"/v1/milk-transactions/{tx['id']}/events", headers=headers)).json()
    kinds = [e["event_type"] for e in events]
    assert "Repriced" in kinds
    # The one that could not be priced is still in the log: the record says
    # what happened, not what we wish had happened.
    assert "PricingUnavailable" in kinds


async def test_a_repriced_collection_becomes_settleable(client):
    """The whole point. Before this route the farmer could never be paid."""
    headers, center, supplier, tx = await _stranded(client)
    await _card(
        client, headers, code="LATE", bands=((4.0, 5.0, 45.0),), effective_from="2026-01-01"
    )

    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "period_from": "2026-08-01",
                "period_to": "2026-12-31",
            },
            headers=headers,
        )
    ).json()

    # Still stranded: settlement refuses a transaction with no calculation.
    before = (
        await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    ).json()
    assert before["added"] == 0

    assert (
        await client.post(f"/v1/milk-transactions/{tx['id']}/reprice", headers=headers)
    ).status_code == 200

    after = (
        await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    ).json()
    assert after["added"] == 1, after


async def test_repricing_an_already_priced_collection_is_a_conflict(client):
    """Immutability is not renegotiated here: a price that exists is corrected
    by an adjustment, never by quietly recalculating it.

    This also covers the settled case. A settlement line requires a
    calculation_id, so anything settled is priced — and priced is refused.
    """
    from tests.test_procurement_e2e import _procurement_env

    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _run_collection(client, headers, session["id"], supplier)
    assert tx["pricing_status"] == "priced"
    tx = await _accept_complete(client, headers, tx["id"])

    r = await client.post(f"/v1/milk-transactions/{tx['id']}/reprice", headers=headers)
    assert r.status_code == 409, r.text
    assert "priced" in r.json()["extra"]


async def test_rejected_milk_is_not_repriced(client):
    headers, center, session, supplier = await _engine_fixture(client)
    _card.center_id = center["id"]
    tx = await _run_collection(client, headers, session["id"], supplier)
    assert (
        await client.post(
            f"/v1/milk-transactions/{tx['id']}/reject",
            json={"reason": "sour on arrival"},
            headers=headers,
        )
    ).status_code == 200
    assert (
        await client.post(f"/v1/milk-transactions/{tx['id']}/complete", headers=headers)
    ).status_code == 200
    await _card(
        client, headers, code="LATE", bands=((4.0, 5.0, 45.0),), effective_from="2026-01-01"
    )

    r = await client.post(f"/v1/milk-transactions/{tx['id']}/reprice", headers=headers)
    assert r.status_code == 409, r.text
    assert "rejected milk is not payable" in r.json()["extra"]


async def test_an_incomplete_collection_is_not_repriced(client):
    """Reprice finishes a record; it does not reach into one still being made."""
    headers, center, session, supplier = await _engine_fixture(client)
    _card.center_id = center["id"]
    tx = await _run_collection(client, headers, session["id"], supplier)  # PRICED, not COMPLETED

    r = await client.post(f"/v1/milk-transactions/{tx['id']}/reprice", headers=headers)
    assert r.status_code == 409, r.text
    assert "not COMPLETED" in r.json()["extra"]


async def test_still_no_applicable_rate_refuses_and_changes_nothing(client):
    """The honest failure: no card covers this collection, so it stays
    rate-pending and says why."""
    headers, _center, _supplier, tx = await _stranded(client)

    r = await client.post(f"/v1/milk-transactions/{tx['id']}/reprice", headers=headers)
    assert r.status_code == 409, r.text

    after = (await client.get(f"/v1/milk-transactions/{tx['id']}", headers=headers)).json()
    assert after["pricing_status"] == "pricing_unavailable"
    assert after["calculation_id"] is None
    assert after["unit_price"] is None


async def test_another_tenant_s_collection_is_a_404_not_a_403(client):
    """A foreign resource does not exist, as far as this dairy is concerned."""
    from tests.test_localization import _tenant_admin_for

    _headers, _center, _supplier, tx = await _stranded(client)
    _org_b, other = await _tenant_admin_for(
        client, country="KE", slug="reprice-iso-b", email="admin@repriceiso.example"
    )

    r = await client.post(f"/v1/milk-transactions/{tx['id']}/reprice", headers=other)
    assert r.status_code == 404, r.text


async def test_without_the_pricing_grant_it_is_a_403(client):
    """Recording milk and deciding what it is worth are different authorities:
    the operator who captured this collection may not price it."""
    from tests.test_access_revocation import _member

    headers, _center, _supplier, tx = await _stranded(client)
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    _uid, operator, _refresh = await _member(
        client,
        headers,
        email=f"operator-{uuid.uuid4().hex[:8]}@dairy.example",
        role="COLLECTION_OPERATOR",
        tenant_id=me["organization"]["id"],
    )

    r = await client.post(f"/v1/milk-transactions/{tx['id']}/reprice", headers=operator)
    assert r.status_code == 403, r.text
