"""PILOT-F03 — a late collection is carried forward (BR-0027).

PILOT-001 stranded a real 1,800.00 KES collection. The settlement covering
its date had already been finalized, so BR-0010 froze the only period the
money could belong to, and BR-0009 refused any overlapping settlement that
might have taken it instead. The milk was collected, priced and completed,
and there was no longer anywhere on the platform for it to be paid.

Every test here is written against the HTTP surface, because the defect was
only ever visible as an operator sees it: the collection succeeds, and the
payment silently has no home.

The dates matter. A collection's business date is the day it was recorded
(`tx_date = as_utc(tx.created_at).date()`), so "today" is the only date a
new collection can carry, and a period that has not yet elapsed is exactly
the trap PILOT-001 fell into.
"""

from datetime import timedelta
from decimal import Decimal

from platform_core.core.business_time import business_today
from tests.test_payments import _second_tenant
from tests.test_procurement_e2e import _accept_complete, _procurement_env, _run_collection

# UTC, not the local day: the platform stamps a collection's business date
# from `as_utc(created_at)`, and for half of every day the two disagree —
# which is precisely how the first draft of this file failed.
# DEMO-019: the DAIRY's today, not UTC's. A settlement line is dated by the
# organization's business date, so a test whose `TODAY` came from `utcnow()`
# disagreed with the platform for the hours when a Nairobi dairy is already on
# tomorrow — three of every twenty-four, and green the rest of the time.
# Every REMAINING use below only offsets this by ten days or more to build
# period boundaries, so a midnight straddle cannot move a collection across
# one. The single place that needed the platform's exact day now asks for it.
TODAY = business_today("Africa/Nairobi")
# The period that contains today, closed prematurely — the PILOT-001 shape.
THIS_PERIOD = {
    "period_from": (TODAY - timedelta(days=20)).isoformat(),
    "period_to": (TODAY + timedelta(days=9)).isoformat(),
}
# The next period, adjacent and non-overlapping (BR-0009 allows adjacency).
NEXT_PERIOD = {
    "period_from": (TODAY + timedelta(days=10)).isoformat(),
    "period_to": (TODAY + timedelta(days=39)).isoformat(),
}
# A period wholly in the past — nothing collected today may land in it.
PAST_PERIOD = {
    "period_from": (TODAY - timedelta(days=60)).isoformat(),
    "period_to": (TODAY - timedelta(days=31)).isoformat(),
}


async def _settle(client, headers, supplier, center, period, *, finalize=True):
    """Create a settlement, sweep it, and (by default) close it."""
    settlement = (
        await client.post(
            "/v1/settlements",
            json={
                "supplier_id": supplier["id"],
                "center_id": center["id"],
                "currency": "KES",
                **period,
            },
            headers=headers,
        )
    ).json()
    swept = (
        await client.post(f"/v1/settlements/{settlement['id']}/collect", headers=headers)
    ).json()
    if finalize:
        await client.post(f"/v1/settlements/{settlement['id']}/calculate", headers=headers)
        r = await client.post(f"/v1/settlements/{settlement['id']}/finalize", headers=headers)
        assert r.status_code == 200, r.text
        settlement = r.json()
    return settlement, swept


async def _collect_one(client, headers, session, supplier, *, gross=30.0, tare=5.0):
    tx = await _run_collection(client, headers, session["id"], supplier, gross=gross, tare=tare)
    return await _accept_complete(client, headers, tx["id"])


async def _stranded(client):
    """The PILOT-001 situation, rebuilt: a closed period, then a collection
    whose date falls inside it. Returns the closed settlement and the
    collection that has nowhere to go."""
    headers, center, supplier, session = await _procurement_env(client)
    await _collect_one(client, headers, session, supplier)
    closed, _ = await _settle(client, headers, supplier, center, THIS_PERIOD)
    late = await _collect_one(client, headers, session, supplier, gross=45.0, tare=5.0)
    return headers, center, supplier, session, closed, late


# --- the defect, and the fix -------------------------------------------------


async def test_a_late_collection_is_carried_forward_into_the_next_period(client):
    """The whole point: milk collected after its period closed still gets paid."""
    headers, center, supplier, _s, closed, late = await _stranded(client)
    assert late["state"] == "COMPLETED"
    assert Decimal(str(late["gross_amount"])) == Decimal("1800.00")  # 40kg @ 45

    nxt, swept = await _settle(client, headers, supplier, center, NEXT_PERIOD, finalize=False)
    # 1 carried forward; the earlier collection is already settled and is
    # reported as seen-and-passed-over rather than hidden.
    assert swept == {"added": 1, "skipped": 1}

    detail = (await client.get(f"/v1/settlements/{nxt['id']}", headers=headers)).json()
    assert len(detail["lines"]) == 1
    line = detail["lines"][0]
    assert line["transaction_id"] == late["id"]
    # The line keeps the day the milk arrived, not the period that paid for it.
    #
    # Asked of the PLATFORM rather than recomputed here. `TODAY` is snapshotted
    # at module import and this suite runs for minutes, so when import and the
    # collection fall on opposite sides of Nairobi midnight the equality failed
    # for a reason that has nothing to do with carry-forward — observed at
    # 00:53 EAT. The organization's calendar is the same authority that dated
    # the line, so this compares the platform against itself.
    calendar = (await client.get("/v1/organization/calendar", headers=headers)).json()
    assert line["transaction_date"] == calendar["business_date"]
    assert line["transaction_date"] < nxt["period_from"]
    assert Decimal(str(line["gross_amount"])) == Decimal("1800.00")
    assert closed["status"] == "finalized"


async def test_the_closed_settlement_is_not_touched_by_the_carry_forward(client):
    """BR-0010 is not bent to make this work: the closed period is identical
    before and after, down to its totals, line set and finalization stamp."""
    headers, center, supplier, _s, closed, _late = await _stranded(client)
    before = (await client.get(f"/v1/settlements/{closed['id']}", headers=headers)).json()

    await _settle(client, headers, supplier, center, NEXT_PERIOD, finalize=False)

    after = (await client.get(f"/v1/settlements/{closed['id']}", headers=headers)).json()
    assert after == before
    assert after["settlement"]["status"] == "finalized"
    assert after["settlement"]["finalized_at"] == before["settlement"]["finalized_at"]
    assert len(after["lines"]) == 1  # the late line did NOT land here


async def test_a_finalized_settlement_still_refuses_every_mutation(client):
    """The existing immutability guarantee is unchanged (BR-0010)."""
    headers, _c, _s, _sess, closed, late = await _stranded(client)
    for action in ("collect", "calculate", "finalize"):
        r = await client.post(f"/v1/settlements/{closed['id']}/{action}", headers=headers)
        assert r.status_code == 409, action
    r = await client.post(
        f"/v1/settlements/{closed['id']}/transactions",
        json={"transaction_id": late["id"]},
        headers=headers,
    )
    assert r.status_code == 409
    assert "immutable" in r.json()["extra"]


# --- the relaxation is narrow -----------------------------------------------


async def test_a_collection_whose_own_period_is_still_open_is_not_late(client):
    """Carry-forward is for stranded money only. While the period that owns a
    collection is still open, the collection belongs there — pulling it
    forward would split one period's money across two statements."""
    headers, center, supplier, session = await _procurement_env(client)
    await _collect_one(client, headers, session, supplier)
    # This period is created but NEVER finalized, so today is still settleable.
    await _settle(client, headers, supplier, center, THIS_PERIOD, finalize=False)
    late = await _collect_one(client, headers, session, supplier, gross=45.0, tare=5.0)

    nxt, swept = await _settle(client, headers, supplier, center, NEXT_PERIOD, finalize=False)
    assert swept == {"added": 0, "skipped": 2}
    r = await client.post(
        f"/v1/settlements/{nxt['id']}/transactions",
        json={"transaction_id": late["id"]},
        headers=headers,
    )
    assert r.status_code == 409
    assert "outside the settlement period" in r.json()["extra"]


async def test_a_collection_after_the_period_is_always_refused(client):
    """One-directional: milk that has not been collected yet can never be
    settled, however many periods are closed around it."""
    headers, center, supplier, session = await _procurement_env(client)
    tx = await _collect_one(client, headers, session, supplier)
    past, swept = await _settle(client, headers, supplier, center, PAST_PERIOD, finalize=False)
    assert swept == {"added": 0, "skipped": 0}
    r = await client.post(
        f"/v1/settlements/{past['id']}/transactions",
        json={"transaction_id": tx["id"]},
        headers=headers,
    )
    assert r.status_code == 409
    assert "it is after" in r.json()["extra"]


# --- idempotency and duplicate protection ------------------------------------


async def test_carrying_forward_twice_is_idempotent(client):
    """BR-0008/BR-0012 still hold: the late line cannot be settled twice."""
    headers, center, supplier, _s, _closed, late = await _stranded(client)
    nxt, first = await _settle(client, headers, supplier, center, NEXT_PERIOD, finalize=False)
    assert first == {"added": 1, "skipped": 1}

    again = (await client.post(f"/v1/settlements/{nxt['id']}/collect", headers=headers)).json()
    assert again == {"added": 0, "skipped": 2}  # both seen, neither moved

    r = await client.post(
        f"/v1/settlements/{nxt['id']}/transactions",
        json={"transaction_id": late["id"]},
        headers=headers,
    )
    assert r.status_code == 409

    detail = (await client.get(f"/v1/settlements/{nxt['id']}", headers=headers)).json()
    assert len(detail["lines"]) == 1
    assert Decimal(str(detail["settlement"]["gross_amount"])) == Decimal("0")  # draft


async def test_a_late_line_cannot_be_settled_in_two_open_settlements(client):
    """Two open settlements competing for the same stranded collection: the
    second gets nothing. This is the double-payment case."""
    headers, center, supplier, _s, _closed, late = await _stranded(client)
    first, swept = await _settle(client, headers, supplier, center, NEXT_PERIOD, finalize=False)
    assert swept == {"added": 1, "skipped": 1}

    third = {
        "period_from": (TODAY + timedelta(days=40)).isoformat(),
        "period_to": (TODAY + timedelta(days=69)).isoformat(),
    }
    second, swept2 = await _settle(client, headers, supplier, center, third, finalize=False)
    assert swept2 == {"added": 0, "skipped": 2}
    r = await client.post(
        f"/v1/settlements/{second['id']}/transactions",
        json={"transaction_id": late["id"]},
        headers=headers,
    )
    assert r.status_code == 409
    assert first["id"] != second["id"]


# --- money -------------------------------------------------------------------


async def test_money_is_exact_from_collection_through_to_the_receipt(client):
    """40.000 kg x 45.0000 = 1800.00, and the same figure survives every hop:
    line -> gross -> adjustments -> net -> payment -> receipt."""
    headers, center, supplier, _s, _closed, _late = await _stranded(client)
    nxt, _ = await _settle(client, headers, supplier, center, NEXT_PERIOD, finalize=False)

    r = await client.post(f"/v1/settlements/{nxt['id']}/calculate", headers=headers)
    totals = r.json()
    assert Decimal(str(totals["gross_amount"])) == Decimal("1800.00")
    assert Decimal(str(totals["adjustments_amount"])) == Decimal("0.00")  # BR-0011
    assert Decimal(str(totals["net_amount"])) == Decimal("1800.00")
    assert Decimal(str(totals["net_amount"])) == Decimal(str(totals["gross_amount"])) + Decimal(
        str(totals["adjustments_amount"])
    )

    detail = (await client.get(f"/v1/settlements/{nxt['id']}", headers=headers)).json()
    assert detail["totals_match_lines"] is True
    line = detail["lines"][0]
    assert Decimal(str(line["quantity"])) == Decimal("40.000")
    assert Decimal(str(line["unit_price"])) == Decimal("45.0000")
    assert Decimal(str(line["quantity"])) * Decimal(str(line["unit_price"])) == Decimal(
        str(line["gross_amount"])
    )

    await client.post(f"/v1/settlements/{nxt['id']}/finalize", headers=headers)
    balance = (await client.get(f"/v1/settlements/{nxt['id']}/balance", headers=headers)).json()
    assert Decimal(balance["payable"]) == Decimal("1800.00")

    payment = (
        await client.post(
            "/v1/payments",
            json={
                "supplier_id": supplier["id"],
                "currency": "KES",
                "method": "MOBILE_MONEY",
                "allocations": [{"settlement_id": nxt["id"]}],
            },
            headers=headers,
        )
    ).json()
    assert Decimal(str(payment["amount"])) == Decimal("1800.00")
    for action, body in (("submit", {}), ("execute", {}), ("complete", {"reference": "LATE-1"})):
        r = await client.post(f"/v1/payments/{payment['id']}/{action}", json=body, headers=headers)
        assert r.status_code == 200, action

    balance = (await client.get(f"/v1/settlements/{nxt['id']}/balance", headers=headers)).json()
    assert Decimal(balance["paid"]) == Decimal("1800.00")
    assert Decimal(balance["outstanding"]) == Decimal("0.00")
    assert balance["fully_paid"] is True

    # The receipt is minted by a consumer from payment.completed.v1, so the
    # relay has to actually run — the same asynchrony the deployed platform has.
    from platform_core.core import db
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    await ConsumerRunner(db.get_session_factory()).run_once()

    receipts = (
        await client.get(f"/v1/receipts?payment_id={payment['id']}", headers=headers)
    ).json()
    assert receipts["total"] == 1, receipts
    assert Decimal(str(receipts["items"][0]["net_amount"])) == Decimal("1800.00")


# --- tenancy -----------------------------------------------------------------


async def test_another_tenants_closed_period_cannot_unlock_a_late_line(client):
    """The closed-period lookup is tenant-scoped. Were it not, one tenant's
    finalized settlement would decide what another tenant may settle."""
    headers, center, supplier, session = await _procurement_env(client)
    await _collect_one(client, headers, session, supplier)
    await _second_tenant(client)  # a whole separate organization exists

    # No finalized settlement in THIS tenant covers today, so today's
    # collection is not late — it is simply out of period.
    nxt, swept = await _settle(client, headers, supplier, center, NEXT_PERIOD, finalize=False)
    assert swept == {"added": 0, "skipped": 1}
    detail = (await client.get(f"/v1/settlements/{nxt['id']}", headers=headers)).json()
    assert detail["lines"] == []


async def test_a_late_settlement_is_invisible_to_another_tenant(client):
    headers, center, supplier, _s, _closed, _late = await _stranded(client)
    nxt, _ = await _settle(client, headers, supplier, center, NEXT_PERIOD, finalize=False)
    other = await _second_tenant(client)
    r = await client.get(f"/v1/settlements/{nxt['id']}", headers=other)
    assert r.status_code == 404  # never 403 — never leak existence


# --- the PILOT-001 regression ------------------------------------------------


async def test_pilot_001_1800_kes_collection_can_now_be_settled(client):
    """The exact PILOT-001 case, end to end.

    A settlement was finalized on 2026-08-09 for a period running to
    2026-08-10; a 1,800.00 KES collection was then recorded on 2026-08-10 and
    could never be paid. Rebuilt here in relative time — a period closed while
    it still contains today, then a collection — and carried to completion.
    """
    headers, center, supplier, _s, closed, late = await _stranded(client)

    # The state PILOT-001 reported: completed, priced, and unsettleable.
    assert late["state"] == "COMPLETED"
    assert late["calculation_id"] is not None
    assert Decimal(str(late["gross_amount"])) == Decimal("1800.00")
    r = await client.post(
        f"/v1/settlements/{closed['id']}/transactions",
        json={"transaction_id": late["id"]},
        headers=headers,
    )
    assert r.status_code == 409  # its own period is closed forever

    # And the resolution: paid in the following period, in full.
    nxt, swept = await _settle(client, headers, supplier, center, NEXT_PERIOD, finalize=False)
    assert swept == {"added": 1, "skipped": 1}
    r = await client.post(f"/v1/settlements/{nxt['id']}/calculate", headers=headers)
    assert Decimal(str(r.json()["net_amount"])) == Decimal("1800.00")
    r = await client.post(f"/v1/settlements/{nxt['id']}/finalize", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "finalized"

    # The closed settlement is still exactly as it was.
    before = (await client.get(f"/v1/settlements/{closed['id']}", headers=headers)).json()
    assert before["settlement"]["status"] == "finalized"
    assert len(before["lines"]) == 1
