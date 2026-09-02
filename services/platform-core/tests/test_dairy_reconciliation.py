"""The whole customer workflow, reconciled to the paisa (DEMO-019 §22, §23).

§22 lists five identities a dairy's books must hold to. They are asserted here
against one representative customer driven through the real endpoints, because
a reconciliation that is described rather than executed is exactly the shape
this repository has been burned by:

    SUM(deliveries)   = bill lines
    bill total        = the authoritative invoice total
    invoice - payments = outstanding balance
    payment           = receipt
    statement closing = customer balance

§23 asks the daily report to survive three hundred customers without an N+1.
The test below asserts the QUERY COUNT rather than a wall-clock number: a
timing threshold is a flake on a busy machine, while "this report costs a
fixed number of statements no matter how many customers there are" is the
property that actually matters and the one that breaks silently.
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import event

from platform_core.modules.billing.month_end import previous_month
from tests.clock import TODAY, through_today
from tests.test_org_structure import _tenant_admin

# WO-63: derived, not a literal August. The deliveries have to land in a month
# that is OVER (so it can be billed in full) and the bill and the payment are
# raised now — a fixed window stops containing "now" the moment the calendar
# moves past it, and this one had.
MONTH = (previous_month(TODAY)[0], previous_month(TODAY)[0] + timedelta(days=27))
RATE = Decimal("60.0000")
LITRES = Decimal("2.000")


async def _customer(client, admin, name, *, quantity=LITRES, price=RATE):
    r = await client.post(
        "/v1/customers",
        json={
            "name": name,
            "plan": {
                "unit_price": str(price),
                "default_quantity": str(quantity),
                "effective_from": str(MONTH[0]),
            },
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_the_month_reconciles_exactly(client):
    """One household, a month of milk, a bill, a part payment, a receipt."""
    _org, admin = await _tenant_admin(client)
    customer = await _customer(client, admin, "Sharma Household")

    delivered = skipped = 0
    for offset in range((MONTH[1] - MONTH[0]).days + 1):
        day = MONTH[0] + timedelta(days=offset)
        # A realistic month: most days delivered, Sundays skipped, one returned.
        status = "delivered"
        if day.weekday() == 6:
            status = "skipped"
        elif offset == 10:
            status = "returned"
        r = await client.post(
            "/v1/deliveries",
            json={
                "customer_id": customer["id"],
                "delivery_date": str(day),
                "status": status,
            },
            headers=admin,
        )
        assert r.status_code == 201, r.text
        if status == "delivered":
            delivered += 1
        elif status == "skipped":
            skipped += 1

    expected_litres = LITRES * delivered
    expected_value = (expected_litres * RATE).quantize(Decimal("0.01"))

    # --- the report agrees with the deliveries ---------------------------
    report = (
        await client.get(
            "/v1/deliveries/report",
            params={"date_from": str(MONTH[0]), "date_to": str(MONTH[1])},
            headers=admin,
        )
    ).json()
    assert report["deliveries"] == delivered
    assert report["skipped"] == skipped
    assert report["returned"] == 1
    assert Decimal(report["total_quantity"]) == expected_litres
    assert Decimal(report["total_amount"]) == expected_value

    # --- the bill is the deliveries --------------------------------------
    invoice = (
        await client.post(
            "/v1/invoices",
            json={
                "customer_id": customer["id"],
                "period_from": str(MONTH[0]),
                "period_to": str(MONTH[1]),
            },
            headers=admin,
        )
    ).json()
    assert invoice["line_count"] == delivered, "a skipped or returned day was billed"
    assert Decimal(invoice["total"]) == expected_value

    detail = (await client.get(f"/v1/invoices/{invoice['id']}", headers=admin)).json()
    assert detail["totals_match_lines"] is True
    assert sum(Decimal(line["amount"]) for line in detail["lines"]) == Decimal(invoice["total"])
    assert sum(Decimal(line["quantity"]) for line in detail["lines"]) == expected_litres

    issued = await client.post(f"/v1/invoices/{invoice['id']}/issue", json={}, headers=admin)
    assert issued.status_code == 200

    # --- a part payment ---------------------------------------------------
    part = Decimal("1000.00")
    payment = (
        await client.post(
            "/v1/customer-payments",
            json={"customer_id": customer["id"], "amount": str(part), "method": "CASH"},
            headers=admin,
        )
    ).json()

    balance = (await client.get(f"/v1/customers/{customer['id']}/balance", headers=admin)).json()
    assert Decimal(balance["invoiced"]) == expected_value
    assert Decimal(balance["paid"]) == part
    assert Decimal(balance["outstanding"]) == expected_value - part

    # --- the receipt is the payment ---------------------------------------
    from platform_core.core.rls import platform_factory
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    runner = ConsumerRunner(platform_factory("reconciliation test: drive consumers"))
    for _ in range(3):
        await runner.run_once()

    receipts = (
        await client.get(
            "/v1/customer-receipts", params={"customer_id": customer["id"]}, headers=admin
        )
    ).json()["items"]
    assert len(receipts) == 1
    assert Decimal(receipts[0]["amount"]) == Decimal(payment["amount"]) == part

    # --- the statement closes where the balance says ----------------------
    statement = (
        await client.get(
            f"/v1/customers/{customer['id']}/statement",
            # The deliveries are last month's; the invoice and the payment are
            # today's, so the window has to span both. `through_today()` ends
            # it a day out because the platform reads this window in the
            # ORGANIZATION's calendar, which is already tomorrow for a Kenyan
            # dairy after 21:00 UTC (the B8 finding, in a second file).
            params={"date_from": str(MONTH[0]), "date_to": str(through_today())},
            headers=admin,
        )
    ).json()
    assert Decimal(statement["closing_balance"]) == Decimal(balance["outstanding"])
    assert Decimal(statement["opening_balance"]) + Decimal(statement["billed"]) - Decimal(
        statement["paid"]
    ) == Decimal(statement["closing_balance"])
    assert Decimal(statement["delivered_quantity"]) == expected_litres


async def test_the_daily_report_costs_the_same_at_three_hundred_customers(client):
    """§23. The property is a FIXED query count, not a wall-clock number.

    A timing threshold flakes on a busy machine and passes on a fast one while
    an N+1 hides inside it. This counts statements: three hundred customers
    must cost what three cost, or the report has grown a per-row query.
    """
    _org, admin = await _tenant_admin(client)
    day = MONTH[0]
    for index in range(300):
        customer = await _customer(client, admin, f"Household {index:03d}")
        await client.post(
            "/v1/deliveries",
            json={"customer_id": customer["id"], "delivery_date": str(day)},
            headers=admin,
        )

    from platform_core.core.db import get_engine

    counted: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        counted.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        report = (
            await client.get(
                "/v1/deliveries/report",
                params={"date_from": str(day), "date_to": str(day)},
                headers=admin,
            )
        ).json()
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert report["customers_served"] == 300
    assert len(report["by_customer"]) == 300
    assert Decimal(report["total_quantity"]) == LITRES * 300

    selects = [s for s in counted if s.lstrip().lower().startswith("select")]
    assert len(selects) < 20, (
        f"the report issued {len(selects)} SELECTs for 300 customers — "
        "that is a query per row, not an aggregate"
    )
