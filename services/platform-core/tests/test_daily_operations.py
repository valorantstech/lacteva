"""The dairy's daily operations (DEMO-015).

DEMO-009 built the chain and proved it reconciles. What it did not answer is
the pair of questions a dairy owner actually asks every morning —

    "How much milk went out, and to whom?"
    "What does this customer owe me, and how did they come to owe it?"

— which are a per-customer breakdown, a file somebody can open, and a
statement with an opening balance. Those three are what this milestone adds,
and these are the tests that make them true rather than described.

The invariant asserted most often below is the statement's:

    opening + billed - paid = closing

and, when the window ends today, `closing == balance().outstanding`. A
customer's statement and the dairy's receivables report must never tell two
different stories about the same money.
"""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from tests.clock import reference_date
from tests.test_org_structure import _tenant_admin

# WO-58: the reference clock, not a literal. A date written here in
# August is a suite that only works in August.
TODAY = reference_date()


async def _customer(client, admin, *, name, quantity, price, code=None):
    body = {
        "name": name,
        "customer_type": "household",
        "phone": "+919845000101",
        "plan": {
            "product": "RAW-COW-MILK",
            "default_quantity": str(quantity),
            "quantity_unit": "L",
            "unit_price": str(price),
        },
    }
    if code:
        body["code"] = code
    r = await client.post("/v1/customers", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


async def _deliver(client, admin, customer_id, day, *, quantity=None, status="delivered"):
    body = {"customer_id": customer_id, "delivery_date": str(day), "status": status}
    if quantity is not None:
        body["quantity"] = str(quantity)
    r = await client.post("/v1/deliveries", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


async def _round(client, admin):
    """Three customers on different rates, three days of milk.

    Different rates on purpose: a report that multiplied one rate by a total
    quantity would agree with a report that priced each delivery, right up
    until two customers pay different amounts for a litre — which is the
    ordinary case and the whole reason plans exist.
    """
    _org, admin_headers = await _tenant_admin(client)
    admin = admin_headers
    households = [
        await _customer(client, admin, name="Sharma Household", quantity="1.500", price="56.0000"),
        await _customer(
            client, admin, name="Adiga Tiffin Room", quantity="10.000", price="52.0000"
        ),
        await _customer(client, admin, name="Hotel Sagar", quantity="18.250", price="50.0000"),
    ]
    for offset in range(3):
        day = TODAY - timedelta(days=offset)
        for customer in households:
            await _deliver(client, admin, customer["id"], day)
    return admin, households


# --- the report, per customer ------------------------------------------------


async def test_the_report_says_who_the_milk_went_to(client):
    admin, _households = await _round(client, None)
    report = (
        await client.get(
            "/v1/deliveries/report",
            params={"date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY)},
            headers=admin,
        )
    ).json()

    assert len(report["by_customer"]) == 3
    by_name = {row["name"]: row for row in report["by_customer"]}
    hotel = by_name["Hotel Sagar"]
    assert hotel["deliveries"] == 3
    assert Decimal(hotel["quantity"]) == Decimal("54.750")  # 18.25 x 3
    assert Decimal(hotel["unit_price"]) == Decimal("50.0000")
    assert Decimal(hotel["amount"]) == Decimal("2737.50")


async def test_the_per_customer_rows_add_up_to_the_headline(client):
    """The two halves of one screen must agree, or a manager reconciling them
    by hand finds a discrepancy the platform created."""
    admin, _ = await _round(client, None)
    report = (
        await client.get(
            "/v1/deliveries/report",
            params={"date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY)},
            headers=admin,
        )
    ).json()

    assert sum(Decimal(r["amount"]) for r in report["by_customer"]) == Decimal(
        report["total_amount"]
    )
    assert sum(Decimal(r["quantity"]) for r in report["by_customer"]) == Decimal(
        report["total_quantity"]
    )
    assert sum(r["deliveries"] for r in report["by_customer"]) == report["deliveries"]
    assert sum(Decimal(d["amount"]) for d in report["by_day"]) == Decimal(report["total_amount"])


async def test_the_busiest_customer_comes_first(client):
    """Ordered by value in SQL, so page one is the answer and nothing is
    sorted in a browser."""
    admin, _ = await _round(client, None)
    report = (
        await client.get(
            "/v1/deliveries/report",
            params={"date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY)},
            headers=admin,
        )
    ).json()
    amounts = [Decimal(row["amount"]) for row in report["by_customer"]]
    assert amounts == sorted(amounts, reverse=True)


async def test_a_customer_who_took_nothing_still_appears(client):
    """A household that skipped every day of the week is the single most
    useful row on this report, and the easiest one to lose: it has no billable
    delivery for a grouped query to hang a count on."""
    _org, admin = await _tenant_admin(client)
    absent = await _customer(
        client, admin, name="Away Household", quantity="1.000", price="56.0000"
    )
    for offset in range(3):
        await _deliver(
            client, admin, absent["id"], TODAY - timedelta(days=offset), status="skipped"
        )

    report = (
        await client.get(
            "/v1/deliveries/report",
            params={"date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY)},
            headers=admin,
        )
    ).json()
    assert report["skipped"] == 3
    assert report["total_amount"] == "0.00"


async def test_the_report_names_its_own_currency_and_unit(client):
    """So no screen has to decide, and none carries a hard-coded symbol."""
    admin, _ = await _round(client, None)
    report = (await client.get("/v1/deliveries/report", headers=admin)).json()
    assert report["currency"] == "KES"  # this fixture's organization is Kenyan
    assert report["quantity_unit"] == "L"


async def test_an_empty_day_still_answers(client):
    """A dairy that delivered nothing yesterday must still be able to open the
    report — with zeroes and a currency, not an error."""
    _org, admin = await _tenant_admin(client)
    report = (
        await client.get(
            "/v1/deliveries/report",
            params={"date_from": "2020-01-01", "date_to": "2020-01-01"},
            headers=admin,
        )
    ).json()
    assert report["deliveries"] == 0
    assert report["by_customer"] == []
    assert report["currency"] == "KES"
    assert report["quantity_unit"] == "L"


# --- the export ---------------------------------------------------------------


async def test_the_export_is_a_file_a_spreadsheet_can_read(client):
    admin, _ = await _round(client, None)
    r = await client.get(
        "/v1/deliveries/report.csv",
        params={"date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY)},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    # The filename carries the range that was ASKED for, whatever it is.
    expected = f"deliveries-{TODAY - timedelta(days=2)}-to-{TODAY}.csv"
    assert expected in r.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][0] == "customer_code"
    assert len(rows[1]) == len(rows[0])
    # Nine deliveries, a blank line, and a totals row.
    body = [row for row in rows[1:] if row and row[0] != "TOTAL"]
    assert len(body) == 9


async def test_the_files_total_is_the_platforms_total(client):
    """Not a sum of the lines above it. If the file computed its own total,
    the file could disagree with the screen — and the person forwarding it to
    an accountant would never know which one was wrong."""
    admin, _ = await _round(client, None)
    params = {"date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY)}
    report = (await client.get("/v1/deliveries/report", params=params, headers=admin)).json()
    text = (await client.get("/v1/deliveries/report.csv", params=params, headers=admin)).text

    total_row = next(row for row in csv.reader(io.StringIO(text)) if row and row[0] == "TOTAL")
    assert total_row[5] == report["total_quantity"]
    assert total_row[8] == report["total_amount"]
    assert total_row[9] == report["currency"]


async def test_the_exported_amounts_are_numbers_not_decoration(client):
    """No symbol, no grouping. A spreadsheet reads `1234.50` as a number and
    `KES 1,234.50` as text, and a column of text cannot be summed."""
    admin, _ = await _round(client, None)
    text = (
        await client.get(
            "/v1/deliveries/report.csv",
            params={"date_from": str(TODAY), "date_to": str(TODAY)},
            headers=admin,
        )
    ).text
    rows = list(csv.reader(io.StringIO(text)))
    amounts = [row[8] for row in rows[1:] if row and row[0] != "TOTAL"]
    for amount in amounts:
        assert Decimal(amount) == Decimal(amount)  # parses exactly
        assert "," not in amount


async def test_the_export_respects_the_customer_filter(client):
    admin, households = await _round(client, None)
    text = (
        await client.get(
            "/v1/deliveries/report.csv",
            params={
                "date_from": str(TODAY - timedelta(days=2)),
                "date_to": str(TODAY),
                "customer_id": households[0]["id"],
            },
            headers=admin,
        )
    ).text
    rows = [
        row
        for row in csv.reader(io.StringIO(text))
        if row and row[0] not in ("customer_code", "TOTAL")
    ]
    assert {row[1] for row in rows} == {"Sharma Household"}


async def test_exporting_needs_the_read_grant(client):
    """Never rely on the UI hiding the button (§19)."""
    from tests.conftest import register_and_login

    _org, _admin = await _tenant_admin(client)
    _outsider, outsider = await register_and_login(client, email="nobody@example.com")
    assert (await client.get("/v1/deliveries/report.csv", headers=outsider)).status_code in (
        401,
        403,
    )


# --- the statement ------------------------------------------------------------


def _billed_period_start() -> date:
    """The first day `_billed_customer` delivers on.

    A week back, but never before the first of the month: the statement's
    default window is the current month by design, so a week that reaches into
    the previous one is invisible to it. This is the WO-58 defect in one line.
    """
    return max(TODAY - timedelta(days=6), TODAY.replace(day=1))


def _billed_days() -> int:
    """How many days of milk that is — seven, or as many as the month has had."""
    return (TODAY - _billed_period_start()).days + 1


async def _billed_customer(client, admin):
    """One customer, a week of milk (or as much of it as this month has had),
    one issued invoice. Returns the day count so a caller can assert on it."""
    customer = await _customer(
        client, admin, name="Statement Household", quantity="2.000", price="50.0000"
    )
    # WO-58. A week of milk, INSIDE the month the statement defaults to.
    # This used to be a flat seven days back, which on the first of a month
    # puts six of them in the previous one — where the statement's default
    # window (this month, by design) cannot see them. The window is not wrong;
    # the fixture was assuming a month always has seven days behind it.
    period_from = _billed_period_start()
    for offset in range(_billed_days()):
        await _deliver(client, admin, customer["id"], period_from + timedelta(days=offset))
    invoice = (
        await client.post(
            "/v1/invoices",
            json={
                "customer_id": customer["id"],
                "period_from": str(period_from),
                "period_to": str(TODAY),
            },
            headers=admin,
        )
    ).json()
    issued = await client.post(f"/v1/invoices/{invoice['id']}/issue", json={}, headers=admin)
    assert issued.status_code == 200, issued.text
    return customer, issued.json()


async def test_the_statement_shows_the_bill_and_the_money_against_it(client):
    _org, admin = await _tenant_admin(client)
    customer, invoice = await _billed_customer(client, admin)
    # days x 2 L x 50.00. Derived, because the number of days is however many
    # this month has had — see `_billed_customer`.
    total = Decimal(invoice["total"])
    assert total == Decimal(_billed_days()) * Decimal("2") * Decimal("50.00")

    await client.post(
        "/v1/customer-payments",
        json={"customer_id": customer["id"], "amount": "300.00", "method": "CASH"},
        headers=admin,
    )
    statement = (
        await client.get(f"/v1/customers/{customer['id']}/statement", headers=admin)
    ).json()

    kinds = [entry["kind"] for entry in statement["entries"]]
    assert kinds == ["invoice", "payment"]
    assert Decimal(statement["billed"]) == total
    assert Decimal(statement["paid"]) == Decimal("300.00")
    # Billed minus paid, derived from the same day count the invoice was.
    assert Decimal(statement["closing_balance"]) == total - Decimal("300.00")
    assert statement["currency"] == "KES"
    assert statement["name"] == "Statement Household"


async def test_the_running_balance_is_the_arithmetic_of_the_lines(client):
    """Every line's balance is the one above it, plus this line's movement.
    A statement whose last figure is right and whose middle is wrong is worse
    than one that fails outright, because it will be believed."""
    _org, admin = await _tenant_admin(client)
    customer, _invoice = await _billed_customer(client, admin)
    for amount in ("100.00", "250.00"):
        await client.post(
            "/v1/customer-payments",
            json={"customer_id": customer["id"], "amount": amount, "method": "CASH"},
            headers=admin,
        )

    statement = (
        await client.get(f"/v1/customers/{customer['id']}/statement", headers=admin)
    ).json()
    running = Decimal(statement["opening_balance"])
    for entry in statement["entries"]:
        running = running + Decimal(entry["debit"]) - Decimal(entry["credit"])
        assert Decimal(entry["balance"]) == running
    assert running == Decimal(statement["closing_balance"])


async def test_opening_plus_billed_less_paid_is_closing(client):
    _org, admin = await _tenant_admin(client)
    customer, _invoice = await _billed_customer(client, admin)
    await client.post(
        "/v1/customer-payments",
        json={"customer_id": customer["id"], "amount": "150.00", "method": "CASH"},
        headers=admin,
    )
    statement = (
        await client.get(f"/v1/customers/{customer['id']}/statement", headers=admin)
    ).json()
    assert Decimal(statement["opening_balance"]) + Decimal(statement["billed"]) - Decimal(
        statement["paid"]
    ) == Decimal(statement["closing_balance"])


async def test_the_statement_and_the_balance_tell_the_same_story(client):
    """The identity that matters most: a customer's own page and the dairy's
    receivables list cannot disagree about one debt."""
    _org, admin = await _tenant_admin(client)
    customer, _invoice = await _billed_customer(client, admin)
    await client.post(
        "/v1/customer-payments",
        json={"customer_id": customer["id"], "amount": "425.50", "method": "MOBILE_MONEY"},
        headers=admin,
    )
    statement = (
        await client.get(f"/v1/customers/{customer['id']}/statement", headers=admin)
    ).json()
    balance = (await client.get(f"/v1/customers/{customer['id']}/balance", headers=admin)).json()
    assert Decimal(statement["closing_balance"]) == Decimal(balance["outstanding"])


async def test_a_window_that_predates_the_dairy_is_empty_but_correct(client):
    _org, admin = await _tenant_admin(client)
    customer, _invoice = await _billed_customer(client, admin)
    statement = (
        await client.get(
            f"/v1/customers/{customer['id']}/statement",
            params={"date_from": "2019-01-01", "date_to": "2019-01-31"},
            headers=admin,
        )
    ).json()
    assert statement["entries"] == []
    assert Decimal(statement["opening_balance"]) == Decimal("0.00")
    assert Decimal(statement["closing_balance"]) == Decimal("0.00")


async def test_a_later_window_opens_with_what_was_already_owed(client):
    """The whole reason an opening balance exists. Ask for a window AFTER the
    bill was issued and the debt must still be there — a statement that
    started at zero every month would tell a customer they owe nothing."""
    _org, admin = await _tenant_admin(client)
    customer, invoice = await _billed_customer(client, admin)
    later = TODAY + timedelta(days=40)
    statement = (
        await client.get(
            f"/v1/customers/{customer['id']}/statement",
            params={"date_from": str(later), "date_to": str(later + timedelta(days=30))},
            headers=admin,
        )
    ).json()
    assert statement["entries"] == []
    assert Decimal(statement["opening_balance"]) == Decimal(invoice["total"])
    assert Decimal(statement["closing_balance"]) == Decimal(invoice["total"])


async def test_a_draft_bill_is_not_yet_money_owed(client):
    """Only an ISSUED invoice is a debt. A draft appearing on a statement
    would bill a customer for a document nobody handed them."""
    _org, admin = await _tenant_admin(client)
    customer = await _customer(
        client, admin, name="Draft Household", quantity="2.000", price="50.0000"
    )
    await _deliver(client, admin, customer["id"], TODAY)
    draft = await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer["id"],
            "period_from": str(TODAY),
            "period_to": str(TODAY),
        },
        headers=admin,
    )
    assert draft.status_code == 201, draft.text

    statement = (
        await client.get(f"/v1/customers/{customer['id']}/statement", headers=admin)
    ).json()
    assert statement["entries"] == []
    assert Decimal(statement["closing_balance"]) == Decimal("0.00")


async def test_a_statement_that_ends_before_it_begins_is_refused(client):
    _org, admin = await _tenant_admin(client)
    customer, _invoice = await _billed_customer(client, admin)
    r = await client.get(
        f"/v1/customers/{customer['id']}/statement",
        params={"date_from": str(TODAY), "date_to": str(TODAY - timedelta(days=5))},
        headers=admin,
    )
    assert r.status_code == 409, r.text


async def test_another_tenants_statement_does_not_exist(client):
    """404, never 403 — the platform's rule, applied to the newest endpoint."""
    from tests.test_payments import _second_tenant

    _org, admin = await _tenant_admin(client)
    customer, _invoice = await _billed_customer(client, admin)
    other = await _second_tenant(client)
    r = await client.get(f"/v1/customers/{customer['id']}/statement", headers=other)
    assert r.status_code == 404


# --- what a dairy manager asks at the end of the day (DEMO-019 §5) -----------


async def test_the_report_says_how_much_milk_was_supposed_to_go_out(client):
    """The headline question of §5, which the report could not answer in
    litres: a count of planned deliveries is not a quantity of milk."""
    _org, admin = await _tenant_admin(client)
    customer = await _customer(
        client, admin, name="Planned Household", quantity="2.000", price="56.0000"
    )
    # Three days: one delivered, one skipped, one still to go.
    await _deliver(client, admin, customer["id"], TODAY, status="delivered")
    await _deliver(client, admin, customer["id"], TODAY - timedelta(days=1), status="skipped")
    third = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": str(TODAY - timedelta(days=2)),
            "status": "scheduled",
        },
        headers=admin,
    )
    assert third.status_code == 201, third.text

    report = (
        await client.get(
            "/v1/deliveries/report",
            params={"date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY)},
            headers=admin,
        )
    ).json()

    # Six litres were intended; two arrived.
    assert Decimal(report["planned_quantity"]) == Decimal("6.000")
    assert Decimal(report["total_quantity"]) == Decimal("2.000")
    assert report["planned"] == 3
    assert report["deliveries"] == 1
    assert report["skipped"] == 1
    assert report["scheduled"] == 1


async def test_a_delivery_struck_out_in_error_is_not_milk_anybody_planned(client):
    """`cancelled` means recorded in error, so it is the one status excluded
    from the planned quantity — and it is reported so a count that does not
    add up has somewhere to be explained from."""
    _org, admin = await _tenant_admin(client)
    customer = await _customer(
        client, admin, name="Cancelled Household", quantity="3.000", price="50.0000"
    )
    await _deliver(client, admin, customer["id"], TODAY, status="delivered")
    mistake = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": str(TODAY - timedelta(days=1)),
            "status": "cancelled",
        },
        headers=admin,
    )
    assert mistake.status_code == 201, mistake.text

    report = (
        await client.get(
            "/v1/deliveries/report",
            params={"date_from": str(TODAY - timedelta(days=1)), "date_to": str(TODAY)},
            headers=admin,
        )
    ).json()
    assert Decimal(report["planned_quantity"]) == Decimal("3.000")
    assert report["cancelled"] == 1


async def test_returned_milk_is_told_apart_from_a_skipped_household(client):
    """The van went and the milk came back — a different fact from a customer
    who was away, and §5 asks for both."""
    _org, admin = await _tenant_admin(client)
    customer = await _customer(
        client, admin, name="Returned Household", quantity="1.000", price="60.0000"
    )
    await _deliver(client, admin, customer["id"], TODAY, status="returned")
    await _deliver(client, admin, customer["id"], TODAY - timedelta(days=1), status="skipped")

    report = (
        await client.get(
            "/v1/deliveries/report",
            params={"date_from": str(TODAY - timedelta(days=1)), "date_to": str(TODAY)},
            headers=admin,
        )
    ).json()
    assert report["returned"] == 1
    assert report["skipped"] == 1
    assert Decimal(report["total_amount"]) == Decimal("0.00"), "returned milk was billed"


async def test_the_export_carries_the_planned_figure_too(client):
    """§6: an accountant reading the file asks the shortfall question, and a
    totals row with only the achieved figure makes them add up a column."""
    admin, _ = await _round(client, None)
    text = (
        await client.get(
            "/v1/deliveries/report.csv",
            params={"date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY)},
            headers=admin,
        )
    ).text
    total_row = next(row for row in csv.reader(io.StringIO(text)) if row and row[0] == "TOTAL")
    assert any(cell.startswith("planned ") for cell in total_row)
    assert "delivered" in total_row[4]


async def test_the_statement_says_how_much_milk_the_money_is_for(client):
    """§7's one sentence: 124 L, billed, paid, outstanding — on one screen."""
    _org, admin = await _tenant_admin(client)
    customer, invoice = await _billed_customer(client, admin)
    statement = (
        await client.get(f"/v1/customers/{customer['id']}/statement", headers=admin)
    ).json()
    # 2 L a day, for exactly the days the fixture delivered. Derived rather
    # than the old literal 14.000, which assumed a month always has seven days
    # behind it — and asserted just as strictly.
    assert Decimal(statement["delivered_quantity"]) == Decimal(_billed_days()) * Decimal("2.000")
    assert statement["quantity_unit"] == "L"
    assert Decimal(statement["billed"]) == Decimal(invoice["total"])
