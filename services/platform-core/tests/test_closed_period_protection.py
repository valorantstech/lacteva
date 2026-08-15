"""A closed financial period refuses, on every path that commits money.

DEMO-020 built the period and the guard and called it from nothing. This is
where the guard meets the business: invoices, customer payments, settlements
and supplier payments, driven through the real endpoints.

**Every test asserts the premise before the refusal.** The same call must
succeed while the period is open, so a passing test cannot be a broken
endpoint returning 409 for its own reasons. And each one closes the period
covering the date the record BELONGS to — which for an invoice is the period
it bills, not the day somebody pressed the button.
"""

from datetime import date, timedelta

from tests.test_daily_operations import TODAY, _billed_customer, _customer, _deliver
from tests.test_org_structure import _tenant_admin


async def _open_period(client, admin, start: date, end: date, label: str = ""):
    r = await client.post(
        "/v1/organization/financial-periods",
        json={"period_start": str(start), "period_end": str(end), "label": label},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _close(client, admin, period_id: str):
    r = await client.post(f"/v1/organization/financial-periods/{period_id}/close", headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


async def _business_today(client, admin) -> date:
    cal = (await client.get("/v1/organization/calendar", headers=admin)).json()
    return date.fromisoformat(cal["business_date"])


# --- invoices ----------------------------------------------------------------


async def test_a_closed_month_cannot_be_billed(client):
    """The headline: no new bill may be raised against a shut month."""
    _org, admin = await _tenant_admin(client)
    customer = await _customer(
        client, admin, name="Closed Month Household", quantity="2.000", price="50.0000"
    )
    period_from = TODAY - timedelta(days=6)
    for offset in range(7):
        await _deliver(client, admin, customer["id"], period_from + timedelta(days=offset))

    body = {
        "customer_id": customer["id"],
        "period_from": str(period_from),
        "period_to": str(TODAY),
    }

    # PREMISE: with no period declared, billing works. Without this the
    # refusal below proves nothing.
    first = await client.post("/v1/invoices", json=body, headers=admin)
    assert first.status_code == 201, first.text
    await client.post(
        f"/v1/invoices/{first.json()['id']}/cancel",
        json={"reason": "making room for the real test"},
        headers=admin,
    )

    period = await _open_period(client, admin, period_from, TODAY, "the billed window")
    await _close(client, admin, period["id"])

    refused = await client.post("/v1/invoices", json=body, headers=admin)
    assert refused.status_code == 409, refused.text
    assert "closed financial period" in refused.json()["extra"]


async def test_issuing_into_a_closed_month_is_refused(client):
    """Issuing is the irreversible act, so it is guarded separately."""
    _org, admin = await _tenant_admin(client)
    customer = await _customer(
        client, admin, name="Issue Household", quantity="1.500", price="48.0000"
    )
    period_from = TODAY - timedelta(days=3)
    for offset in range(4):
        await _deliver(client, admin, customer["id"], period_from + timedelta(days=offset))

    draft = (
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

    # The draft exists and is issuable — that is the premise.
    period = await _open_period(client, admin, period_from, TODAY)
    await _close(client, admin, period["id"])

    refused = await client.post(f"/v1/invoices/{draft['id']}/issue", json={}, headers=admin)
    assert refused.status_code == 409, refused.text
    assert "closed financial period" in refused.json()["extra"]

    # And reopening lets it through — the guard follows the period, and a
    # month closed by mistake does not strand a bill forever.
    await client.post(f"/v1/organization/financial-periods/{period['id']}/reopen", headers=admin)
    issued = await client.post(f"/v1/invoices/{draft['id']}/issue", json={}, headers=admin)
    assert issued.status_code == 200, issued.text


async def test_a_bill_for_an_OPEN_month_is_unaffected_by_another_closed_one(client):
    """The guard is not a global switch: only the closed window refuses."""
    _org, admin = await _tenant_admin(client)
    customer = await _customer(
        client, admin, name="Two Months Household", quantity="2.000", price="45.0000"
    )
    old_from, old_to = date(2026, 6, 1), date(2026, 6, 30)
    for offset in range(3):
        await _deliver(client, admin, customer["id"], TODAY - timedelta(days=offset))

    closed = await _open_period(client, admin, old_from, old_to, "June")
    await _close(client, admin, closed["id"])

    # August is untouched by June being shut.
    ok = await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer["id"],
            "period_from": str(TODAY - timedelta(days=2)),
            "period_to": str(TODAY),
        },
        headers=admin,
    )
    assert ok.status_code == 201, ok.text


# --- customer payments -------------------------------------------------------


async def test_money_cannot_be_received_into_a_closed_period(client):
    """A payment belongs to the day it ARRIVED — the dairy's today."""
    _org, admin = await _tenant_admin(client)
    customer, invoice = await _billed_customer(client, admin)

    payment = {
        "customer_id": customer["id"],
        "amount": "100.00",
        "method": "CASH",
        "invoice_ids": [invoice["id"]],
    }

    # PREMISE: it works with nothing closed.
    first = await client.post("/v1/customer-payments", json=payment, headers=admin)
    assert first.status_code == 201, first.text

    today = await _business_today(client, admin)
    period = await _open_period(client, admin, today, today, "today only")
    await _close(client, admin, period["id"])

    refused = await client.post("/v1/customer-payments", json=payment, headers=admin)
    assert refused.status_code == 409, refused.text
    assert "closed financial period" in refused.json()["extra"]


# --- the guard does not exist until somebody closes something ----------------


async def test_nothing_changes_for_an_organization_with_no_periods(client):
    """The property that made this safe to deploy into a running platform.

    An organization that has declared no periods has none closed, so the whole
    chain behaves exactly as it did before the guard existed. This is the test
    that would fail if the guard defaulted the other way.
    """
    _org, admin = await _tenant_admin(client)
    assert (await client.get("/v1/organization/financial-periods", headers=admin)).json() == []

    customer, invoice = await _billed_customer(client, admin)
    assert invoice["status"] == "issued"
    paid = await client.post(
        "/v1/customer-payments",
        json={
            "customer_id": customer["id"],
            "amount": "50.00",
            "method": "CASH",
            "invoice_ids": [invoice["id"]],
        },
        headers=admin,
    )
    assert paid.status_code == 201, paid.text


async def test_an_open_period_refuses_nothing(client):
    """Declaring a period is not the same as closing one."""
    _org, admin = await _tenant_admin(client)
    customer = await _customer(
        client, admin, name="Open Period Household", quantity="2.000", price="50.0000"
    )
    for offset in range(3):
        await _deliver(client, admin, customer["id"], TODAY - timedelta(days=offset))

    await _open_period(client, admin, TODAY - timedelta(days=30), TODAY, "declared, open")

    ok = await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer["id"],
            "period_from": str(TODAY - timedelta(days=2)),
            "period_to": str(TODAY),
        },
        headers=admin,
    )
    assert ok.status_code == 201, ok.text


# --- cross-tenant: one dairy's closure is not another's -----------------------


async def test_one_dairys_closed_period_does_not_bind_another(client):
    """Closing August in one organization must not stop another billing it."""
    from tests.test_localization import _tenant_admin_for

    _org_a, admin_a = await _tenant_admin_for(
        client, country="IN", slug="cpp-a", email="cpp-a@india.example"
    )
    _org_b, admin_b = await _tenant_admin_for(
        client, country="KE", slug="cpp-b", email="cpp-b@kenya.example"
    )

    today = await _business_today(client, admin_a)
    closed = await _open_period(client, admin_a, today, today, "A's closed day")
    await _close(client, admin_a, closed["id"])

    # B has declared nothing and is unaffected.
    assert (await client.get("/v1/organization/financial-periods", headers=admin_b)).json() == []
    customer_b, invoice_b = await _billed_customer(client, admin_b)
    paid = await client.post(
        "/v1/customer-payments",
        json={
            "customer_id": customer_b["id"],
            "amount": "25.00",
            "method": "CASH",
            "invoice_ids": [invoice_b["id"]],
        },
        headers=admin_b,
    )
    assert paid.status_code == 201, paid.text


# --- settlements and supplier payments ---------------------------------------


async def test_a_settlement_for_a_closed_period_cannot_be_finalized(client):
    """Finalizing fixes what a supplier is owed, so a shut period refuses it."""
    from tests.test_financial_operations_demo import (
        _add_calculation,
        _calculation_id,
        _post,
        _settlement_env,
    )

    headers, center, _supplier, settlement = await _settlement_env(client)
    calc_id = await _calculation_id(client, headers, center["id"], quantity=20.0)
    assert (await _add_calculation(client, headers, settlement["id"], calc_id)).status_code == 201
    assert (await _post(client, headers, settlement["id"], "calculate")).status_code == 200

    # PREMISE: this settlement is finalizable right now. Close the period its
    # own dates fall in, and it must stop being so.
    period = await _open_period(
        client,
        headers,
        date.fromisoformat(settlement["period_from"]),
        date.fromisoformat(settlement["period_to"]),
        "the settled window",
    )
    await _close(client, headers, period["id"])

    refused = await _post(client, headers, settlement["id"], "finalize")
    assert refused.status_code == 409, refused.text
    assert "closed financial period" in refused.json()["extra"]

    # Reopen and it finalizes — proving the period was the only obstacle.
    await client.post(f"/v1/organization/financial-periods/{period['id']}/reopen", headers=headers)
    ok = await _post(client, headers, settlement["id"], "finalize")
    assert ok.status_code == 200, ok.text


async def test_a_supplier_cannot_be_paid_out_of_a_closed_period(client):
    """Creating the payment is the decision; completing it is not."""
    from tests.test_financial_operations_demo import _finalized

    headers, _center, supplier, settlement = await _finalized(client)

    body = {
        "supplier_id": supplier["id"],
        "currency": "KES",
        "method": "BANK_TRANSFER",
        "allocations": [{"settlement_id": settlement["id"]}],
    }

    today = await _business_today(client, headers)
    period = await _open_period(client, headers, today, today, "today only")
    await _close(client, headers, period["id"])

    refused = await client.post("/v1/payments", json=body, headers=headers)
    assert refused.status_code == 409, refused.text
    assert "closed financial period" in refused.json()["extra"]

    await client.post(f"/v1/organization/financial-periods/{period['id']}/reopen", headers=headers)
    ok = await client.post("/v1/payments", json=body, headers=headers)
    assert ok.status_code == 201, ok.text
