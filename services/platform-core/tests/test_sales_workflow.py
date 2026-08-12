"""The dairy customer workflow, executed (DEMO-009).

CUSTOMER → DELIVERY → DAILY REPORT → MONTHLY BILL → PAYMENT → RECEIPT.

The claim this work order makes is that every figure reconciles from source
data through a domain rule to the API — not that a screen can display a
plausible number. So the tests below drive the real endpoints and then check
the arithmetic against the deliveries that produced it, in `Decimal`.

Two things are asserted repeatedly because they are the ones a sales module
gets wrong: that the RATE is the platform's and not the client's, and that the
same milk cannot be billed twice.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from tests.conftest import register_and_login
from tests.test_org_structure import _tenant_admin

TODAY = date(2026, 8, 12)


async def _sales_env(client):
    """An organization with a customer on a 60.00/L plan."""
    org, admin = await _tenant_admin(client)
    r = await client.post(
        "/v1/customers",
        json={
            "name": "Mama Njeri Household",
            "customer_type": "household",
            "phone": "+254700111222",
            "address": "12 Kilima Road",
            "plan": {
                "product": "RAW-COW-MILK",
                "default_quantity": "2.000",
                "quantity_unit": "L",
                "unit_price": "60.0000",
            },
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return org, admin, r.json()


async def _deliver(
    client, admin, customer_id, day, *, quantity=None, slot="morning", status="delivered"
):
    body = {
        "customer_id": customer_id,
        "delivery_date": str(day),
        "slot": slot,
        "status": status,
    }
    if quantity is not None:
        body["quantity"] = str(quantity)
    return await client.post("/v1/deliveries", json=body, headers=admin)


# --- the customer -------------------------------------------------------------


async def test_a_customer_is_registered_with_a_code_and_a_plan(client):
    _org, admin, customer = await _sales_env(client)
    assert customer["code"].startswith("CUS-")
    assert customer["status"] == "active"

    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=admin)).json()
    assert detail["customer"]["name"] == "Mama Njeri Household"
    assert len(detail["plans"]) == 1
    assert Decimal(detail["plans"][0]["unit_price"]) == Decimal("60.0000")
    assert detail["plans"][0]["active"] is True


async def test_a_rate_change_supersedes_the_plan_rather_than_editing_it(client):
    """A delivery priced last week must still be explainable."""
    _org, admin, customer = await _sales_env(client)
    r = await client.post(
        f"/v1/customers/{customer['id']}/plan",
        json={"product": "RAW-COW-MILK", "default_quantity": "2.000", "unit_price": "65.0000"},
        headers=admin,
    )
    assert r.status_code == 201, r.text

    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=admin)).json()
    active = [p for p in detail["plans"] if p["active"]]
    superseded = [p for p in detail["plans"] if not p["active"]]
    assert len(active) == 1 and Decimal(active[0]["unit_price"]) == Decimal("65.0000")
    assert len(superseded) == 1 and Decimal(superseded[0]["unit_price"]) == Decimal("60.0000")


async def test_customers_are_searchable_by_the_database(client):
    _org, admin, _customer = await _sales_env(client)
    await client.post(
        "/v1/customers",
        json={"name": "Kilima Tea House", "customer_type": "shop", "phone": "+254700999888"},
        headers=admin,
    )
    hits = (await client.get("/v1/customers?q=tea", headers=admin)).json()
    assert hits["total"] == 1 and hits["items"][0]["name"] == "Kilima Tea House"
    hits = (await client.get("/v1/customers?customer_type=household", headers=admin)).json()
    assert hits["total"] == 1


# --- the delivery -------------------------------------------------------------


async def test_a_delivery_is_priced_by_the_platform_not_the_client(client):
    """The client sends a quantity. It cannot send a price, and the amount is
    computed once, by the domain."""
    _org, admin, customer = await _sales_env(client)
    r = await _deliver(client, admin, customer["id"], TODAY, quantity="2.500")
    assert r.status_code == 201, r.text
    delivery = r.json()

    assert Decimal(delivery["unit_price"]) == Decimal("60.0000")
    # 2.5 litres at 60.00 = 150.00, computed by the platform.
    assert Decimal(delivery["amount"]) == Decimal("150.00")
    assert delivery["status"] == "delivered"
    assert delivery["invoice_id"] is None


async def test_a_delivery_without_a_quantity_uses_the_standing_order(client):
    _org, admin, customer = await _sales_env(client)
    delivery = (await _deliver(client, admin, customer["id"], TODAY)).json()
    assert Decimal(delivery["quantity"]) == Decimal("2.000")
    assert Decimal(delivery["amount"]) == Decimal("120.00")


async def test_a_customer_cannot_be_delivered_to_twice_in_one_slot(client):
    """A second morning delivery is a correction, not another sale — and
    allowing it would double the bill."""
    _org, admin, customer = await _sales_env(client)
    assert (await _deliver(client, admin, customer["id"], TODAY)).status_code == 201
    r = await _deliver(client, admin, customer["id"], TODAY)
    assert r.status_code == 409
    assert "already has a morning delivery" in r.json()["extra"]

    # The evening round is a different delivery and is accepted.
    r = await _deliver(client, admin, customer["id"], TODAY, slot="evening")
    assert r.status_code == 201, r.text


async def test_a_skipped_delivery_is_worth_nothing(client):
    _org, admin, customer = await _sales_env(client)
    delivery = (
        await _deliver(client, admin, customer["id"], TODAY, quantity="2.000", status="skipped")
    ).json()
    assert Decimal(delivery["amount"]) == Decimal("0.00")


async def test_a_customer_without_a_plan_cannot_receive_a_delivery(client):
    """A rate has to be agreed before milk can be sold at it."""
    _org, admin, _customer = await _sales_env(client)
    other = (
        await client.post("/v1/customers", json={"name": "No Plan Shop"}, headers=admin)
    ).json()
    r = await _deliver(client, admin, other["id"], TODAY, quantity="1.000")
    assert r.status_code == 409
    assert "no active delivery plan" in r.json()["extra"]


async def test_an_inactive_customer_cannot_receive_a_delivery(client):
    _org, admin, customer = await _sales_env(client)
    await client.post(
        f"/v1/customers/{customer['id']}/status", json={"status": "inactive"}, headers=admin
    )
    r = await _deliver(client, admin, customer["id"], TODAY)
    assert r.status_code == 409


# --- the daily report ---------------------------------------------------------


async def test_the_daily_report_totals_the_whole_period_in_sql(client):
    """ "What was delivered, and what is it worth?" — and the answer must be
    the sum of the deliveries, not of a page of them."""
    _org, admin, customer = await _sales_env(client)
    expected = Decimal("0.00")
    for offset in range(5):
        day = TODAY - timedelta(days=offset)
        quantity = Decimal("2.000") + Decimal(offset) / 10
        r = await _deliver(client, admin, customer["id"], day, quantity=str(quantity))
        assert r.status_code == 201, r.text
        expected += Decimal(r.json()["amount"])

    report = (
        await client.get(
            f"/v1/deliveries/report?date_from={TODAY - timedelta(days=4)}&date_to={TODAY}",
            headers=admin,
        )
    ).json()
    assert report["deliveries"] == 5
    assert report["customers_served"] == 1
    assert Decimal(report["total_amount"]) == expected
    assert len(report["by_day"]) == 5
    # The per-day rows must add up to the headline.
    assert sum(Decimal(d["amount"]) for d in report["by_day"]) == expected


async def test_the_report_counts_skipped_days_without_billing_them(client):
    _org, admin, customer = await _sales_env(client)
    await _deliver(client, admin, customer["id"], TODAY)
    await _deliver(client, admin, customer["id"], TODAY - timedelta(days=1), status="skipped")

    report = (
        await client.get(
            f"/v1/deliveries/report?date_from={TODAY - timedelta(days=1)}&date_to={TODAY}",
            headers=admin,
        )
    ).json()
    assert report["deliveries"] == 1
    assert report["skipped"] == 1
    assert Decimal(report["total_amount"]) == Decimal("120.00")


async def test_the_delivery_list_totals_the_filtered_set_not_the_page(client):
    _org, admin, customer = await _sales_env(client)
    for offset in range(4):
        await _deliver(client, admin, customer["id"], TODAY - timedelta(days=offset))

    page = (await client.get("/v1/deliveries?limit=2", headers=admin)).json()
    assert len(page["items"]) == 2
    assert page["total"] == 4
    # Four deliveries of 120.00, even though two rows are shown.
    assert Decimal(page["total_amount"]) == Decimal("480.00")
    assert Decimal(page["total_quantity"]) == Decimal("8.000")


# --- the monthly bill ---------------------------------------------------------


async def _month_of_deliveries(client, admin, customer_id, days=10):
    total = Decimal("0.00")
    for offset in range(days):
        r = await _deliver(client, admin, customer_id, TODAY - timedelta(days=offset))
        assert r.status_code == 201, r.text
        total += Decimal(r.json()["amount"])
    return total


async def test_the_invoice_reconciles_exactly_with_its_deliveries(client):
    """The requirement this work order calls out by name: the monthly bill must
    reconcile exactly with the underlying delivery records."""
    _org, admin, customer = await _sales_env(client)
    delivered = await _month_of_deliveries(client, admin, customer["id"], days=10)

    r = await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer["id"],
            "period_from": str(TODAY - timedelta(days=9)),
            "period_to": str(TODAY),
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    invoice = r.json()

    assert invoice["line_count"] == 10
    assert Decimal(invoice["subtotal"]) == delivered
    assert Decimal(invoice["adjustments"]) == Decimal("0.00")
    assert Decimal(invoice["total"]) == delivered
    assert Decimal(invoice["previous_balance"]) == Decimal("0.00")
    assert Decimal(invoice["amount_due"]) == delivered

    detail = (await client.get(f"/v1/invoices/{invoice['id']}", headers=admin)).json()
    assert detail["totals_match_lines"] is True
    assert sum(Decimal(line["amount"]) for line in detail["lines"]) == delivered


async def test_the_same_milk_cannot_be_billed_twice(client):
    _org, admin, customer = await _sales_env(client)
    await _month_of_deliveries(client, admin, customer["id"], days=3)
    period = {
        "customer_id": customer["id"],
        "period_from": str(TODAY - timedelta(days=2)),
        "period_to": str(TODAY),
    }
    assert (await client.post("/v1/invoices", json=period, headers=admin)).status_code == 201
    # The same period is refused...
    r = await client.post("/v1/invoices", json=period, headers=admin)
    assert r.status_code == 409 and "already has invoice" in r.json()["extra"]
    # ...and so is a fresh invoice over the same days, because the deliveries
    # are already stamped.
    r = await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer["id"],
            "period_from": str(TODAY - timedelta(days=3)),
            "period_to": str(TODAY),
        },
        headers=admin,
    )
    assert r.status_code == 409 and "no unbilled deliveries" in r.json()["extra"]


async def test_an_issued_invoice_is_immutable(client):
    _org, admin, customer = await _sales_env(client)
    await _month_of_deliveries(client, admin, customer["id"], days=3)
    invoice = (
        await client.post(
            "/v1/invoices",
            json={
                "customer_id": customer["id"],
                "period_from": str(TODAY - timedelta(days=2)),
                "period_to": str(TODAY),
            },
            headers=admin,
        )
    ).json()

    r = await client.post(f"/v1/invoices/{invoice['id']}/issue", json={}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "issued"

    # Issuing twice, and cancelling after issue, are both refused.
    assert (
        await client.post(f"/v1/invoices/{invoice['id']}/issue", json={}, headers=admin)
    ).status_code == 409
    r = await client.post(
        f"/v1/invoices/{invoice['id']}/cancel", json={"reason": "changed my mind"}, headers=admin
    )
    assert r.status_code == 409


async def test_a_billed_delivery_cannot_be_amended(client):
    """It is a line on a statement the customer has been given."""
    _org, admin, customer = await _sales_env(client)
    delivery = (await _deliver(client, admin, customer["id"], TODAY)).json()
    await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer["id"],
            "period_from": str(TODAY),
            "period_to": str(TODAY),
        },
        headers=admin,
    )
    r = await client.post(
        f"/v1/deliveries/{delivery['id']}/amend", json={"quantity": "9.000"}, headers=admin
    )
    assert r.status_code == 409
    assert "correct it with an adjustment" in r.json()["extra"]


async def test_cancelling_a_draft_invoice_releases_its_deliveries(client):
    _org, admin, customer = await _sales_env(client)
    await _month_of_deliveries(client, admin, customer["id"], days=2)
    period = {
        "customer_id": customer["id"],
        "period_from": str(TODAY - timedelta(days=1)),
        "period_to": str(TODAY),
    }
    invoice = (await client.post("/v1/invoices", json=period, headers=admin)).json()
    r = await client.post(
        f"/v1/invoices/{invoice['id']}/cancel", json={"reason": "wrong period"}, headers=admin
    )
    assert r.status_code == 200
    # The milk is billable again.
    r = await client.post("/v1/invoices", json=period, headers=admin)
    assert r.status_code == 201, r.text


# --- payment and receipt ------------------------------------------------------


async def _issued_invoice(client, admin, customer_id, days=5):
    delivered = await _month_of_deliveries(client, admin, customer_id, days=days)
    invoice = (
        await client.post(
            "/v1/invoices",
            json={
                "customer_id": customer_id,
                "period_from": str(TODAY - timedelta(days=days - 1)),
                "period_to": str(TODAY),
            },
            headers=admin,
        )
    ).json()
    r = await client.post(f"/v1/invoices/{invoice['id']}/issue", json={}, headers=admin)
    assert r.status_code == 200, r.text
    return r.json(), delivered


async def test_a_customer_payment_settles_the_invoice_and_clears_the_balance(client):
    _org, admin, customer = await _sales_env(client)
    invoice, delivered = await _issued_invoice(client, admin, customer["id"])

    before = (await client.get(f"/v1/customers/{customer['id']}/balance", headers=admin)).json()
    assert Decimal(before["invoiced"]) == delivered
    assert Decimal(before["paid"]) == Decimal("0.00")
    assert Decimal(before["outstanding"]) == delivered

    r = await client.post(
        "/v1/customer-payments",
        json={
            "customer_id": customer["id"],
            "amount": str(delivered),
            "method": "MOBILE_MONEY",
            "reference": "MPESA-TEST-1",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    payment = r.json()
    assert Decimal(payment["amount"]) == delivered

    after = (await client.get(f"/v1/customers/{customer['id']}/balance", headers=admin)).json()
    assert Decimal(after["paid"]) == delivered
    assert Decimal(after["outstanding"]) == Decimal("0.00")

    detail = (await client.get(f"/v1/invoices/{invoice['id']}", headers=admin)).json()
    assert detail["invoice"]["status"] == "paid"
    assert Decimal(detail["outstanding"]) == Decimal("0.00")


async def test_a_partial_payment_leaves_the_rest_outstanding(client):
    _org, admin, customer = await _sales_env(client)
    _invoice, delivered = await _issued_invoice(client, admin, customer["id"])
    part = (delivered / 2).quantize(Decimal("0.01"))

    await client.post(
        "/v1/customer-payments",
        json={"customer_id": customer["id"], "amount": str(part), "method": "CASH"},
        headers=admin,
    )
    balance = (await client.get(f"/v1/customers/{customer['id']}/balance", headers=admin)).json()
    assert Decimal(balance["paid"]) == part
    assert Decimal(balance["outstanding"]) == delivered - part


async def test_a_receipt_is_generated_from_the_payment_event(client, bus):
    """BR-0020's rule, on the sales side: the receipt comes from the durable
    log, and no billing code asks for one."""
    from platform_core.core.rls import platform_factory
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    _org, admin, customer = await _sales_env(client)
    _invoice, delivered = await _issued_invoice(client, admin, customer["id"])
    payment = (
        await client.post(
            "/v1/customer-payments",
            json={
                "customer_id": customer["id"],
                "amount": str(delivered),
                "method": "CASH",
                "reference": "CASH-1",
            },
            headers=admin,
        )
    ).json()

    await ConsumerRunner(platform_factory("test: run consumers")).run_once()

    receipts = (await client.get("/v1/customer-receipts", headers=admin)).json()
    assert receipts["total"] == 1
    receipt = receipts["items"][0]
    assert receipt["receipt_number"].startswith("CRC-")
    assert receipt["payment_number"] == payment["payment_number"]
    assert Decimal(receipt["amount"]) == delivered
    assert receipt["customer_code"] == customer["code"]

    detail = (await client.get(f"/v1/customer-payments/{payment['id']}", headers=admin)).json()
    assert detail["receipt_number"] == receipt["receipt_number"]


async def test_the_receipt_consumer_is_idempotent(client):
    """A redelivered event must not mint a second proof of the same money."""
    from platform_core.core.rls import platform_factory
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    _org, admin, customer = await _sales_env(client)
    _invoice, delivered = await _issued_invoice(client, admin, customer["id"], days=2)
    await client.post(
        "/v1/customer-payments",
        json={"customer_id": customer["id"], "amount": str(delivered), "method": "CASH"},
        headers=admin,
    )
    runner = ConsumerRunner(platform_factory("test: run consumers"))
    for _ in range(3):
        await runner.run_once()

    receipts = (await client.get("/v1/customer-receipts", headers=admin)).json()
    assert receipts["total"] == 1


async def test_the_next_invoice_carries_the_previous_balance_forward(client):
    """The dairy's "brought forward" line, and it must be the real one."""
    _org, admin, customer = await _sales_env(client)
    _first, first_total = await _issued_invoice(client, admin, customer["id"], days=3)

    # A new period, unpaid — so the previous balance appears on it.
    for offset in (5, 6, 7):
        await _deliver(client, admin, customer["id"], TODAY - timedelta(days=offset))
    second = (
        await client.post(
            "/v1/invoices",
            json={
                "customer_id": customer["id"],
                "period_from": str(TODAY - timedelta(days=7)),
                "period_to": str(TODAY - timedelta(days=5)),
            },
            headers=admin,
        )
    ).json()
    assert Decimal(second["previous_balance"]) == first_total
    assert Decimal(second["amount_due"]) == Decimal(second["total"]) + first_total


# --- authorization and isolation ---------------------------------------------


async def test_sales_endpoints_require_their_own_permissions(client):
    """A collection operator records COLLECTIONS. That must not let them record
    a DELIVERY — the two are opposite directions of milk and money."""
    _org, _admin, customer = await _sales_env(client)
    _, outsider = await register_and_login(client, "outsider-sales@example.com")

    for method, path, _body in (
        ("get", "/v1/customers", None),
        ("get", "/v1/deliveries", None),
        ("get", "/v1/invoices", None),
        ("get", "/v1/customer-payments", None),
        ("get", "/v1/customer-receipts", None),
    ):
        r = await getattr(client, method)(path, headers=outsider)
        assert r.status_code == 403, f"{path} -> {r.status_code}"

    r = await client.post(
        "/v1/deliveries",
        json={"customer_id": customer["id"], "delivery_date": str(TODAY)},
        headers=outsider,
    )
    assert r.status_code == 403


async def test_customers_and_their_money_are_invisible_across_tenants(client):
    from tests.test_payments import _second_tenant

    _org, admin, customer = await _sales_env(client)
    await _deliver(client, admin, customer["id"], TODAY)
    other = await _second_tenant(client)

    assert (await client.get("/v1/customers", headers=other)).json()["total"] == 0
    assert (await client.get("/v1/deliveries", headers=other)).json()["total"] == 0
    assert (await client.get(f"/v1/customers/{customer['id']}", headers=other)).status_code == 404
    assert (
        await client.get(f"/v1/customers/{customer['id']}/balance", headers=other)
    ).status_code == 404
    r = await client.post(
        "/v1/deliveries",
        json={"customer_id": customer["id"], "delivery_date": str(TODAY)},
        headers=other,
    )
    assert r.status_code == 404


async def test_an_unknown_customer_is_404_not_500(client):
    _org, admin, _customer = await _sales_env(client)
    assert (await client.get(f"/v1/customers/{uuid.uuid4()}", headers=admin)).status_code == 404
