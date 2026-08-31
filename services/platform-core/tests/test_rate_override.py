"""An authorized, attributed rate override (BR-0029; LACTEVA-PRICING-002).

D-15 makes a counter-side rate change a product capability. D-3 makes it
never silent and always attributed. The tests that matter are therefore not
"can a rate be changed" — they are the ones that stop a changed rate from
becoming an unexplained payment difference, or from being quietly erased by a
rate card published a week later.
"""

import pytest

from tests.test_procurement_e2e import _procurement_env, _run_collection

pytestmark = pytest.mark.asyncio


async def _priced(client, headers, session, supplier, **kw):
    return await _run_collection(client, headers, session["id"], supplier, **kw)


async def test_an_override_pays_the_new_rate_and_keeps_the_old_one(client):
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _priced(client, headers, session, supplier, fat=4.2, gross=30.0, tare=5.0)
    assert tx["unit_price"] is not None
    resolved = tx["unit_price"]

    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/override-rate",
        json={"unit_price": "52.5000", "reason": "quality dispute settled at the counter"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # The effective rate is the override — settlement and the parchi read this
    # field and must never see a superseded number.
    assert body["unit_price"] == "52.5000"
    # …and the resolved rate survives, or the departure is indistinguishable
    # from an error.
    assert body["base_unit_price"] == resolved
    assert body["override_reason"] == "quality dispute settled at the counter"
    assert body["overridden_by"] and body["overridden_at"]

    # 25 kg net at 52.50 = 1312.50, recomputed rather than scaled.
    assert body["gross_amount"] == "1312.50"


async def test_an_override_without_a_reason_is_refused(client):
    """An override with no reason is an unexplained payment difference, which
    is exactly what an auditor asks about."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _priced(client, headers, session, supplier)

    for reason in ("", "  ", "x"):
        r = await client.post(
            f"/v1/milk-transactions/{tx['id']}/override-rate",
            json={"unit_price": "52.5000", "reason": reason},
            headers=headers,
        )
        assert r.status_code == 422, f"reason {reason!r} was accepted"


async def test_a_zero_or_negative_rate_is_refused(client):
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _priced(client, headers, session, supplier)
    for price in ("0", "-1.0000"):
        r = await client.post(
            f"/v1/milk-transactions/{tx['id']}/override-rate",
            json={"unit_price": price, "reason": "a valid looking reason"},
            headers=headers,
        )
        assert r.status_code == 422


async def test_the_override_is_recorded_in_the_event_log(client):
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _priced(client, headers, session, supplier)
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/override-rate",
        json={"unit_price": "52.5000", "reason": "negotiated for this farmer"},
        headers=headers,
    )

    events = (await client.get(f"/v1/milk-transactions/{tx['id']}/events", headers=headers)).json()
    rows = events["items"] if isinstance(events, dict) else events
    recorded = [e for e in rows if e["event_type"] == "RateOverridden"]
    assert len(recorded) == 1
    data = recorded[0]["data"]
    assert data["unit_price"] == "52.5000"
    assert data["base_unit_price"] == tx["unit_price"]
    assert data["reason"] == "negotiated for this farmer"


async def test_a_second_override_keeps_the_RATE_CARD_rate_as_the_base(client):
    """The base is what the rate card said, not the previous decision.

    Otherwise two overrides make the base a number nobody ever resolved, and
    the audit trail loses the only figure it can be checked against.
    """
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _priced(client, headers, session, supplier)
    resolved = tx["unit_price"]

    for price in ("52.5000", "48.0000"):
        r = await client.post(
            f"/v1/milk-transactions/{tx['id']}/override-rate",
            json={"unit_price": price, "reason": "revised after re-testing the sample"},
            headers=headers,
        )
        assert r.status_code == 200, r.text

    assert r.json()["base_unit_price"] == resolved
    assert r.json()["unit_price"] == "48.0000"


async def test_an_override_cannot_be_applied_after_the_decision(client):
    """Once a farmer has been told what they are getting, the rate stops
    moving. A rate that can change afterwards is a negotiation the farmer is
    not present for."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _priced(client, headers, session, supplier)
    await client.post(f"/v1/milk-transactions/{tx['id']}/accept", headers=headers)

    r = await client.post(
        f"/v1/milk-transactions/{tx['id']}/override-rate",
        json={"unit_price": "52.5000", "reason": "too late for this"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_an_operator_may_not_override_a_rate(client):
    """The authorization refusal, watched.

    `collection.transaction.record` is what the person at the intake bay
    holds. Recording milk and deciding what it is worth are different
    authorities — which is the same reason capture cannot invent a price.
    """
    from platform_core.modules.authz.permissions import ALL_SYSTEM_ROLES

    operator = ALL_SYSTEM_ROLES["COLLECTION_OPERATOR"]
    assert "collection.transaction.record" in operator
    assert "pricing.rate.override" not in operator, (
        "the person recording the milk can now change what it is worth"
    )
    # And the manager, who can be asked about it afterwards, does hold it.
    assert "pricing.rate.override" in ALL_SYSTEM_ROLES["CENTRE_MANAGER"]


async def test_a_reprice_never_silently_replaces_an_override(client):
    """The rule that makes the whole feature safe.

    A rate card published after the fact would otherwise erase a decision a
    person made and signed for — on a collection the farmer has already been
    quoted.
    """
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _priced(client, headers, session, supplier)
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/override-rate",
        json={"unit_price": "52.5000", "reason": "settled at the counter"},
        headers=headers,
    )

    r = await client.post(f"/v1/milk-transactions/{tx['id']}/reprice", headers=headers)
    # Either the reprice is refused outright, or it runs and changes nothing —
    # both are correct; silently overwriting the override is not.
    after = (await client.get(f"/v1/milk-transactions/{tx['id']}", headers=headers)).json()
    assert after["unit_price"] == "52.5000", (
        f"a reprice replaced an authorized override (reprice returned {r.status_code})"
    )
    assert after["override_reason"] == "settled at the counter"


async def test_the_parchi_shows_both_rates_and_the_reason(client):
    """An override the farmer cannot see on their own copy is a silent one."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _priced(client, headers, session, supplier)
    resolved = tx["unit_price"]
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/override-rate",
        json={"unit_price": "52.5000", "reason": "quality re-tested at the counter"},
        headers=headers,
    )
    await client.post(f"/v1/milk-transactions/{tx['id']}/accept", headers=headers)
    await client.post(f"/v1/milk-transactions/{tx['id']}/complete", headers=headers)

    slip = (await client.get(f"/v1/milk-transactions/{tx['id']}/slip", headers=headers)).json()
    assert slip["unit_price"] == "52.5000"
    assert slip["base_unit_price"] == resolved
    assert slip["override_reason"] == "quality re-tested at the counter"
    # …and in the text a farmer is actually handed.
    assert "52.5000" in slip["text"]
    assert "Card rate" in slip["text"]
    assert "quality re-tested at the counter" in slip["text"]


async def test_settlement_pays_the_overridden_rate(client):
    """The seam crossing. Settlement reads the EFFECTIVE rate and never learns
    an override happened — which is exactly why it cannot settle on a rate
    that was superseded."""
    headers, _center, supplier, session = await _procurement_env(client)
    tx = await _priced(client, headers, session, supplier, gross=30.0, tare=5.0)
    await client.post(
        f"/v1/milk-transactions/{tx['id']}/override-rate",
        json={"unit_price": "52.5000", "reason": "negotiated rate for this farmer"},
        headers=headers,
    )
    await client.post(f"/v1/milk-transactions/{tx['id']}/accept", headers=headers)
    completed = await client.post(f"/v1/milk-transactions/{tx['id']}/complete", headers=headers)
    assert completed.status_code == 200, completed.text

    # 25 kg at 52.50 — the number the dairy agreed to pay.
    assert completed.json()["gross_amount"] == "1312.50"
    assert completed.json()["unit_price"] == "52.5000"
