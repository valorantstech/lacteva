"""The milk day book, and the dispatch it needed (WO-56 · BR-0030).

A centre took milk in and some of it went out again in bulk — to a plant, a
chilling centre, a bulk buyer — and nothing recorded that at all, so "what is
left at this centre?" had no answer the platform could give.

These pin the record and the ledger, and the four ways both could lie:
a dispatch quietly edited after somebody read the day book; a cancelled
dispatch still counted; a remainder clamped so a wrong entry looks fine; and
sales folded into a subtraction that is neither the same unit nor the same
scope as the milk it would be taken from.
"""

import pytest

from tests.test_milk_type_reporting import _collect
from tests.test_procurement_e2e import _procurement_env

pytestmark = pytest.mark.asyncio


async def _book(client, headers, center_id=None):
    params = {"center_id": center_id} if center_id else {}
    r = await client.get("/v1/reports/day-book", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _today(client, headers) -> str:
    """The date the platform is on, asked of the platform.

    NOT the suite's UTC date: a business date is the DAIRY's day, and for a
    Nairobi cooperative after 21:00 UTC the two are different — which is
    exactly how a dispatch dated in UTC came to sit outside the day book that
    contained its own collections.
    """
    return (await _book(client, headers))["business_date"]


async def _dispatch(client, headers, center_id, *, milk_type="cow", quantity="10.000", **over):
    body = {
        "center_id": center_id,
        "business_date": await _today(client, headers),
        "milk_type": milk_type,
        "quantity": quantity,
        "destination": "Anand Chilling Plant",
        **over,
    }
    return await client.post("/v1/dispatches", json=body, headers=headers)


def _row(book, milk_type):
    return next(row for row in book["rows"] if row["milk_type"] == milk_type)


async def test_a_dispatch_is_recorded_and_appears_in_the_day_book(client):
    headers, center, supplier, session = await _procurement_env(client)
    await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=55.0)

    r = await _dispatch(client, headers, center["id"], quantity="20.000")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "recorded"
    # D-21 / WO-70: the ORGANISATION'S unit, read from the row. This tenant is
    # Kenyan, and Kenya trades in litres.
    assert r.json()["quantity_unit"] == "litre"

    book = await _book(client, headers, center["id"])
    cow = _row(book, "cow")
    assert cow["collected_kg"] == 50.0  # 55 gross - 5 tare
    assert cow["dispatched_kg"] == 20.0
    assert cow["remainder_kg"] == 30.0


async def test_a_dispatch_cannot_be_edited_only_cancelled_and_re_entered(client):
    """Immutability is the point, so the absence of an edit path is asserted
    rather than assumed: a day book somebody has already read must not change
    shape behind them."""
    headers, center, _supplier, _session = await _procurement_env(client)
    dispatch = (await _dispatch(client, headers, center["id"])).json()

    for method in ("patch", "put"):
        r = await getattr(client, method)(
            f"/v1/dispatches/{dispatch['id']}",
            json={"quantity": "1.000"},
            headers=headers,
        )
        assert r.status_code in (404, 405), (
            f"{method.upper()} on a dispatch answered {r.status_code}"
        )


async def test_a_cancellation_needs_a_reason_and_leaves_the_ledger(client):
    headers, center, supplier, session = await _procurement_env(client)
    await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=55.0)
    dispatch = (await _dispatch(client, headers, center["id"], quantity="20.000")).json()

    empty = await client.post(
        f"/v1/dispatches/{dispatch['id']}/cancel", json={"reason": ""}, headers=headers
    )
    assert empty.status_code == 422, "an unexplained cancellation was accepted"

    ok = await client.post(
        f"/v1/dispatches/{dispatch['id']}/cancel",
        json={"reason": "tanker turned back at the gate"},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "cancelled"
    assert ok.json()["cancel_reason"] == "tanker turned back at the gate"

    # Withdrawn means withdrawn: a cancelled movement moved nothing.
    cow = _row(await _book(client, headers, center["id"]), "cow")
    assert cow["dispatched_kg"] == 0.0
    assert cow["remainder_kg"] == 50.0


async def test_a_dispatch_is_cancelled_once(client):
    headers, center, _supplier, _session = await _procurement_env(client)
    dispatch = (await _dispatch(client, headers, center["id"])).json()
    body = {"reason": "recorded against the wrong centre"}
    cancel = f"/v1/dispatches/{dispatch['id']}/cancel"
    assert (await client.post(cancel, json=body, headers=headers)).status_code == 200
    assert (await client.post(cancel, json=body, headers=headers)).status_code == 409


async def test_the_operator_records_no_dispatch(client):
    """The authorization split, watched (BR-0030).

    The person at the intake bay answers for what ARRIVES. What left the
    centre is a claim nobody can check afterwards by looking at the milk, so
    it belongs to somebody who can be asked about it.
    """
    from platform_core.modules.authz.permissions import ALL_SYSTEM_ROLES

    operator = ALL_SYSTEM_ROLES["COLLECTION_OPERATOR"]
    assert "collection.transaction.record" in operator
    assert "operations.dispatch.record" not in operator, (
        "the person recording the milk can now record what left with it"
    )
    assert "operations.dispatch.read" in operator, "the operator cannot see the centre's own day"
    assert "operations.dispatch.record" in ALL_SYSTEM_ROLES["CENTRE_MANAGER"]


async def test_a_dispatch_carries_no_money_and_no_customer(client):
    """A movement, not a sale. The table is the assertion, because a column
    added later is how the two would quietly become one."""
    from platform_core.modules.dispatch.models import MilkDispatch

    columns = set(MilkDispatch.__table__.columns.keys())
    for financial in ("amount", "currency", "unit_price", "customer_id", "invoice_id"):
        assert financial not in columns, f"a dispatch acquired {financial}"


async def test_the_dispatch_module_imports_no_financial_model(client):
    """The boundary that keeps the day book's arithmetic sound: sales are the
    delivery module's, and a dispatch that could reference a customer would
    eventually be counted as both."""
    import pathlib

    import platform_core.modules.dispatch as module

    source = "\n".join(p.read_text() for p in pathlib.Path(module.__file__).parent.glob("*.py"))
    for forbidden in ("modules.customer", "modules.billing", "modules.pricing", "modules.delivery"):
        assert forbidden not in source, f"the dispatch module imports {forbidden}"


async def test_a_negative_remainder_is_shown_rather_than_hidden(client):
    """Dispatching more than was collected means something was recorded
    wrong. Clamping it to zero would hide exactly that."""
    headers, center, supplier, session = await _procurement_env(client)
    await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=15.0)
    await _dispatch(client, headers, center["id"], quantity="40.000")

    cow = _row(await _book(client, headers, center["id"]), "cow")
    assert cow["collected_kg"] == 10.0
    assert cow["remainder_kg"] == -30.0


async def test_the_ledger_keeps_the_animals_apart(client):
    headers, center, supplier, session = await _procurement_env(client)
    await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=55.0)
    await _collect(client, headers, session["id"], supplier, milk_type="buffalo", gross=35.0)
    await _dispatch(client, headers, center["id"], milk_type="buffalo", quantity="10.000")

    book = await _book(client, headers, center["id"])
    assert _row(book, "cow") == {
        "milk_type": "cow",
        "collected_kg": 50.0,
        "dispatched_kg": 0.0,
        "remainder_kg": 50.0,
        "collections": 1,
        "dispatches": 0,
    }
    buffalo = _row(book, "buffalo")
    assert (buffalo["collected_kg"], buffalo["dispatched_kg"]) == (30.0, 10.0)
    # The totals are the platform's own aggregate and must agree with the rows.
    assert book["total_collected_kg"] == 80.0
    assert book["total_dispatched_kg"] == 10.0
    assert book["total_remainder_kg"] == 70.0


async def test_sales_are_reported_beside_the_ledger_and_never_subtracted(client):
    """The honest gap, pinned so nobody closes it by guessing.

    A delivery records a customer, a date and a free-text product — no centre,
    no milk type — and it is measured in litres while intake is weighed in
    kilograms. Subtracting it from a centre's remainder would look precise and
    be wrong twice over.
    """
    headers, center, supplier, session = await _procurement_env(client)
    await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=55.0)

    book = await _book(client, headers, center["id"])
    assert book["sales"]["attributable_to_centre"] is False
    assert book["sales"]["attributable_to_milk_type"] is False
    assert book["sales"]["quantity_unit"] != "kg"
    # The remainder is the ledger's own arithmetic, untouched by the sales
    # figure sitting next to it.
    assert book["total_remainder_kg"] == book["total_collected_kg"] - book["total_dispatched_kg"]


async def test_the_day_book_downloads_as_a_file_that_states_its_scope(client):
    headers, center, supplier, session = await _procurement_env(client)
    await _collect(client, headers, session["id"], supplier, milk_type="cow", gross=55.0)
    await _dispatch(client, headers, center["id"], quantity="20.000")

    r = await client.get(
        "/v1/reports/day-book.csv", params={"center_id": center["id"]}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    body = r.text
    assert "Milk day book" in body
    assert await _today(client, headers) in body
    assert center["name"] in body, "a forwarded file does not say which centre it is about"
    assert "cow,1,50.0,1,20.0,30.0" in body
    assert "TOTAL,1,50.0,1,20.0,30.0" in body
    # And the sentence that stops a reader subtracting the sales figure.
    assert "NOT" in body and "subtracted" in body


async def test_another_tenant_sees_none_of_it(client):
    headers, center, _supplier, _session = await _procurement_env(client)
    dispatch = (await _dispatch(client, headers, center["id"])).json()

    from tests.test_localization import _tenant_admin_for

    _org_b, other = await _tenant_admin_for(
        client, country="IN", slug="day-book-other", email="admin@day-book-other.example"
    )
    r = await client.get(f"/v1/dispatches/{dispatch['id']}", headers=other)
    # Another tenant's resource is a 404, never a 403.
    assert r.status_code == 404
    assert (await _book(client, other))["total_dispatched_kg"] == 0.0
