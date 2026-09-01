"""The month's bills, drafted rather than issued (DEMO-019 §8).

The safety argument in one sentence: **a draft is not money owed.** It is
absent from `PAYABLE_INVOICE_STATUSES`, so it appears on no statement, in no
receivable total and in no customer's outstanding balance — and issuing it,
the irreversible act, still belongs to a person who can look at the month
first.

These tests exist to keep that true. A month-end job that quietly started
issuing would be a machine posting receivables into a dairy's books on a
schedule, and the first anyone would hear of a mistake is a customer disputing
a bill nobody read.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from platform_core.modules.billing.month_end import draft_month_end, previous_month
from tests.clock import TODAY
from tests.test_org_structure import _tenant_admin

AUGUST = (date(2026, 8, 1), date(2026, 8, 31))

# WO-58. The month this fixture bills: the one before today, whichever that
# is. `AUGUST` above stays a literal because the `previous_month()` assertions
# are ABOUT specific dates; the data below must simply land in last month.
BILLED_MONTH = previous_month(TODAY)


def test_the_month_that_just_ended_is_the_one_billed():
    """A bill for August cannot be complete until August is over."""
    assert previous_month(date(2026, 9, 1)) == AUGUST
    assert previous_month(date(2026, 9, 30)) == AUGUST
    assert previous_month(date(2026, 1, 1)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert previous_month(date(2026, 3, 1)) == (date(2026, 2, 1), date(2026, 2, 28))


async def _dairy(client, *, customers: int = 2, days: int = 3):
    org, admin = await _tenant_admin(client)
    ids = []
    for index in range(customers):
        r = await client.post(
            "/v1/customers",
            json={
                "name": f"Household {index}",
                "plan": {
                    "unit_price": "56.0000",
                    "default_quantity": "2.000",
                    "effective_from": BILLED_MONTH[0].isoformat(),
                },
            },
            headers=admin,
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
        for offset in range(days):
            day = BILLED_MONTH[0] + timedelta(days=offset)
            d = await client.post(
                "/v1/deliveries",
                json={
                    "customer_id": r.json()["id"],
                    "delivery_date": str(day),
                    "status": "delivered",
                },
                headers=admin,
            )
            assert d.status_code == 201, d.text
    return org, admin, ids


async def _draft(client, org, period=BILLED_MONTH):
    from platform_core.core.db import get_session_factory
    from platform_core.core.rls import rebind_tenant

    async with get_session_factory()() as session:
        await rebind_tenant(session, uuid.UUID(org["id"]))
        result = await draft_month_end(
            session,
            tenant_id=uuid.UUID(org["id"]),
            timezone=org["timezone"],
            period=period,
        )
        await session.commit()
    return result


async def test_the_month_end_pass_drafts_a_bill_for_every_customer(client):
    org, admin, _ids = await _dairy(client)
    result = await _draft(client, org)

    assert result.customers == 2
    assert result.drafted == 2
    assert result.skipped == 0

    page = (await client.get("/v1/invoices", headers=admin)).json()
    assert page["total"] == 2
    assert all(inv["status"] == "draft" for inv in page["items"])
    assert all(Decimal(inv["total"]) == Decimal("336.00") for inv in page["items"])


async def test_a_drafted_bill_is_not_money_owed(client):
    """The whole safety argument, asserted."""
    org, admin, ids = await _dairy(client)
    await _draft(client, org)

    balance = (await client.get(f"/v1/customers/{ids[0]}/balance", headers=admin)).json()
    assert Decimal(balance["outstanding"]) == Decimal("0.00")
    assert Decimal(balance["invoiced"]) == Decimal("0.00")
    assert balance["open_invoices"] == 0

    statement = (
        await client.get(
            f"/v1/customers/{ids[0]}/statement",
            params={
                "date_from": str(BILLED_MONTH[0]),
                "date_to": str(BILLED_MONTH[1]),
            },
            headers=admin,
        )
    ).json()
    assert statement["entries"] == [], "a draft appeared on a customer's statement"
    assert Decimal(statement["closing_balance"]) == Decimal("0.00")


async def test_drafting_never_issues(client):
    """A machine may prepare a bill. Handing it over is a person's act."""
    org, admin, _ids = await _dairy(client)
    await _draft(client, org)
    page = (await client.get("/v1/invoices", headers=admin)).json()
    assert all(inv["status"] == "draft" for inv in page["items"])
    assert all(inv["issued_at"] is None for inv in page["items"])


async def test_running_it_again_drafts_nothing_new(client):
    """Idempotent through `generate_invoice`'s own refusal, not a second
    mechanism: a customer with a live invoice for the period is refused."""
    org, admin, _ids = await _dairy(client)
    first = await _draft(client, org)
    second = await _draft(client, org)

    assert first.drafted == 2
    assert second.drafted == 0
    assert second.skipped == 2
    assert second.reasons.get("already billed") == 2

    page = (await client.get("/v1/invoices", headers=admin)).json()
    assert page["total"] == 2, "the second pass drafted a duplicate bill"


async def test_a_customer_with_nothing_to_bill_is_counted_not_failed(client):
    org, admin, _ids = await _dairy(client, customers=1)
    r = await client.post(
        "/v1/customers",
        json={"name": "No Deliveries", "plan": {"unit_price": "50.0000"}},
        headers=admin,
    )
    assert r.status_code == 201

    result = await _draft(client, org)
    assert result.customers == 2
    assert result.drafted == 1
    assert result.skipped == 1
    assert result.reasons.get("nothing to bill") == 1


async def test_an_inactive_customer_is_not_billed(client):
    org, admin, ids = await _dairy(client, customers=2)
    await client.post(f"/v1/customers/{ids[0]}/status", json={"status": "inactive"}, headers=admin)
    result = await _draft(client, org)
    assert result.customers == 1
    assert result.drafted == 1


async def test_a_drafted_bill_still_reconciles_with_its_deliveries(client):
    """§22: the bill is the deliveries, and drafting does not change that."""
    org, admin, ids = await _dairy(client, customers=1, days=5)
    await _draft(client, org)

    invoice = (await client.get("/v1/invoices", headers=admin)).json()["items"][0]
    detail = (await client.get(f"/v1/invoices/{invoice['id']}", headers=admin)).json()

    assert detail["invoice"]["line_count"] == 5
    assert detail["totals_match_lines"] is True
    line_sum = sum(Decimal(line["amount"]) for line in detail["lines"])
    assert line_sum == Decimal(invoice["total"]) == Decimal("560.00")  # 5 x 2L x 56.00

    deliveries = (
        await client.get(
            "/v1/deliveries",
            params={
                "customer_id": ids[0],
                "date_from": str(BILLED_MONTH[0]),
                "date_to": str(BILLED_MONTH[1]),
            },
            headers=admin,
        )
    ).json()
    assert Decimal(deliveries["total_amount"]) == line_sum


async def test_the_drafted_bill_becomes_the_ordinary_chain(client):
    """Draft → issue → pay → receipt → balance, with no special path."""
    org, admin, ids = await _dairy(client, customers=1, days=3)
    await _draft(client, org)
    invoice = (await client.get("/v1/invoices", headers=admin)).json()["items"][0]

    issued = await client.post(f"/v1/invoices/{invoice['id']}/issue", json={}, headers=admin)
    assert issued.status_code == 200, issued.text
    assert issued.json()["status"] == "issued"

    paid = await client.post(
        "/v1/customer-payments",
        json={"customer_id": ids[0], "amount": "200.00", "method": "CASH"},
        headers=admin,
    )
    assert paid.status_code == 201, paid.text

    balance = (await client.get(f"/v1/customers/{ids[0]}/balance", headers=admin)).json()
    assert Decimal(balance["outstanding"]) == Decimal("136.00")  # 336.00 - 200.00

    statement = (
        await client.get(
            f"/v1/customers/{ids[0]}/statement",
            # From the milk to the money: the deliveries are last month's and
            # the invoice and payment are today's, so the window has to span
            # both or the statement shows one without the other.
            params={"date_from": str(BILLED_MONTH[0]), "date_to": str(TODAY)},
            headers=admin,
        )
    ).json()
    assert Decimal(statement["closing_balance"]) == Decimal(balance["outstanding"])
    assert Decimal(statement["delivered_quantity"]) == Decimal("6.000")


async def test_drafting_is_confined_to_one_tenant(client):
    from tests.test_payments import _second_tenant

    org, _admin, _ids = await _dairy(client, customers=2)
    other = await _second_tenant(client)
    await _draft(client, org)

    theirs = (await client.get("/v1/invoices", headers=other)).json()
    assert theirs["total"] == 0
