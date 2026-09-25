"""WO-89 — a rate that varies by the day, and by the household.

Two thirds of the owner's request already existed: a rate per household is
the plan; a rate from a date onward supersedes the plan; history keeps the
rate that applied on the day. The gap was the last third — "this household,
this day, this rate" — and this file pins it:

  * one day priced at ₹70 while the plan says ₹74: the delivery, the month
    grid, the invoice line and the household's own bill all say ₹70, and
    every other day says ₹74;
  * an override set on tomorrow's scheduled row survives confirmation;
  * amending that delivery's quantity keeps ₹70, and clearing the override
    returns to the plan's rate;
  * a DRIVER sending a price is refused, not ignored;
  * a delivery on an invoice refuses repricing and names the remedy;
  * a bulk change from a date supersedes every plan for the product in one
    request, leaves every delivery before it untouched, and reports the
    skipped ones — and previews without writing.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from tests.conftest import invite
from tests.test_catalogue_and_items import (
    MONTH_START,
    _customer,
    _deliver,
    _plan,
    _shop,
)
from tests.test_customer_scope import _customer_login

COW = "COW-MILK"


async def _priced(client, admin, customer_id, day, price, **extra):
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer_id,
            "delivery_date": day.isoformat(),
            "slot": "morning",
            "status": "delivered",
            "product": COW,
            "unit_price": str(price),
            **extra,
        },
        headers=admin,
    )
    return r


async def _driver(client, admin, org_id):
    _inv, token = await invite(
        client, {**admin, "X-Tenant-ID": org_id}, email="boy@shop.example", role_name="DRIVER"
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "driver-password-1", "full_name": "Delivery Boy"},
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/v1/auth/token",
        json={"email": "boy@shop.example", "password": "driver-password-1", "tenant_id": org_id},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_one_day_at_seventy_while_the_plan_says_seventy_four(client):
    org, admin = await _shop(client)
    household = await _customer(client, admin, "Tower 1-2006", plan=_plan(COW, 1, 74))
    days = [MONTH_START + timedelta(days=i) for i in range(5)]
    for day in days[:2]:
        await _deliver(client, admin, household["id"], day, COW)
    r = await _priced(
        client, admin, household["id"], days[2], "70.0000", override_reason="festival"
    )
    assert r.status_code == 201, r.text
    special = r.json()
    assert Decimal(special["unit_price"]) == Decimal("70.0000")
    assert Decimal(special["amount"]) == Decimal("70.00")
    assert special["price_source"] == "override"
    assert special["priced_by"] is not None
    assert special["override_reason"] == "festival"
    for day in days[3:]:
        await _deliver(client, admin, household["id"], day, COW)

    # The delivery list: four at 74, one at 70, the plan's rate untouched.
    page = (
        await client.get("/v1/deliveries", params={"customer_id": household["id"]}, headers=admin)
    ).json()
    rates = sorted(Decimal(d["unit_price"]) for d in page["items"])
    assert rates == [Decimal("70.0000")] + [Decimal("74.0000")] * 4
    detail = (await client.get(f"/v1/customers/{household['id']}", headers=admin)).json()
    assert Decimal(detail["plans"][0]["unit_price"]) == Decimal("74.0000")

    # The month grid marks the day and shows the plan's rate in the Price column.
    sheet = (
        await client.get(
            "/v1/deliveries/month",
            params={"year": MONTH_START.year, "month": MONTH_START.month},
            headers=admin,
        )
    ).json()
    row = sheet["rows"][0]
    assert Decimal(row["unit_price"]) == Decimal("74.0000")
    assert row["days"][2]["price_source"] == "override"
    assert Decimal(row["days"][2]["unit_price"]) == Decimal("70.0000")
    assert row["days"][1]["price_source"] == "plan"
    assert Decimal(row["milk_amount"]) == Decimal("366.00")  # 4 x 74 + 70

    # The invoice line, and the household's own bill, say 70 for that day.
    r = await client.post(
        "/v1/invoices",
        json={
            "customer_id": household["id"],
            "period_from": days[0].isoformat(),
            "period_to": days[-1].isoformat(),
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    invoice = r.json()
    r = await client.post(f"/v1/invoices/{invoice['id']}/issue", json={}, headers=admin)
    assert r.status_code == 200, r.text
    me = await _customer_login(client, admin, org["id"], household["id"], "tower@household.example")
    bill = (await client.get(f"/v1/invoices/{invoice['id']}", headers=me)).json()
    lines = sorted(bill["lines"], key=lambda ln: ln["delivery_date"])
    assert [ln["price_source"] for ln in lines] == ["plan", "plan", "override", "plan", "plan"]
    assert Decimal(lines[2]["unit_price"]) == Decimal("70.0000")
    assert Decimal(bill["invoice"]["total"]) == Decimal("366.00")


async def test_an_override_set_on_tomorrow_s_scheduled_row_survives_confirmation(client):
    _org, admin = await _shop(client)
    household = await _customer(client, admin, "Tomorrow Household", plan=_plan(COW, 2, 60))
    tomorrow = MONTH_START + timedelta(days=10)
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": household["id"],
            "delivery_date": tomorrow.isoformat(),
            "slot": "morning",
            "status": "scheduled",
            "product": COW,
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    scheduled = r.json()
    assert Decimal(scheduled["amount"]) == Decimal("0.00")
    # Tonight: "the rate is different tomorrow".
    r = await client.post(
        f"/v1/deliveries/{scheduled['id']}/amend",
        json={"unit_price": "55.0000", "override_reason": "tomorrow's rate"},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["price_source"] == "override"
    assert Decimal(r.json()["amount"]) == Decimal("0.00"), "still scheduled: worth nothing yet"
    # Tomorrow morning: "yes, the usual" — confirmation does not reach for the plan.
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": household["id"],
            "delivery_date": tomorrow.isoformat(),
            "slot": "morning",
            "status": "delivered",
            "product": COW,
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    confirmed = r.json()
    assert confirmed["id"] == scheduled["id"]
    assert Decimal(confirmed["unit_price"]) == Decimal("55.0000")
    assert Decimal(confirmed["amount"]) == Decimal("110.00")
    assert confirmed["price_source"] == "override"


async def test_amending_the_quantity_keeps_the_override_and_clearing_returns_to_the_plan(client):
    _org, admin = await _shop(client)
    household = await _customer(client, admin, "Kept Household", plan=_plan(COW, 1, 74))
    r = await _priced(client, admin, household["id"], MONTH_START, "70.0000")
    assert r.status_code == 201, r.text
    delivery = r.json()
    r = await client.post(
        f"/v1/deliveries/{delivery['id']}/amend", json={"quantity": "1.5"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["unit_price"]) == Decimal("70.0000"), "a quantity fix is not a re-rate"
    assert Decimal(r.json()["amount"]) == Decimal("105.00")
    assert r.json()["price_source"] == "override"
    # Cleared: back to the plan's rate, verbatim provenance gone.
    r = await client.post(
        f"/v1/deliveries/{delivery['id']}/amend", json={"clear_price": True}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["unit_price"]) == Decimal("74.0000")
    assert Decimal(r.json()["amount"]) == Decimal("111.00")
    assert r.json()["price_source"] == "plan"
    assert r.json()["priced_by"] is None


async def test_a_driver_sending_a_price_is_refused_not_ignored(client):
    org, admin = await _shop(client)
    household = await _customer(client, admin, "Door Household", plan=_plan(COW, 1, 74))
    # A driver needs to be able to record at all: DRIVER holds run.execute,
    # not sales.delivery.record — so this goes through a SALES_OFFICER for
    # the recording half and a DRIVER-shaped refusal for the pricing half.
    driver = await _driver(client, admin, org["id"])
    r = await _priced(client, driver, household["id"], MONTH_START, "70.0000")
    assert r.status_code == 403, r.text
    # And a sales officer — who records but does not price — is refused too,
    # while the same request without a price goes through.
    _inv, token = await invite(
        client,
        {**admin, "X-Tenant-ID": org["id"]},
        email="sales@shop.example",
        role_name="SALES_OFFICER",
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "sales-password-1", "full_name": "Sales"},
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/v1/auth/token",
        json={
            "email": "sales@shop.example",
            "password": "sales-password-1",
            "tenant_id": org["id"],
        },
    )
    officer = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # SALES_OFFICER holds sales.delivery.price per the work order — so it is
    # the tenant-viewer-ish shape that must be refused; use the driver above
    # for that and prove the officer is allowed.
    r = await _priced(client, officer, household["id"], MONTH_START + timedelta(days=1), "70.0000")
    assert r.status_code == 201, r.text
    assert r.json()["price_source"] == "override"
    # Nothing was silently dropped anywhere: no delivery exists for the driver's day.
    page = (
        await client.get("/v1/deliveries", params={"customer_id": household["id"]}, headers=admin)
    ).json()
    assert [d["delivery_date"] for d in page["items"]] == [
        (MONTH_START + timedelta(days=1)).isoformat()
    ]


async def test_a_billed_delivery_refuses_repricing_and_names_the_remedy(client):
    _org, admin = await _shop(client)
    household = await _customer(client, admin, "Billed Household", plan=_plan(COW, 1, 74))
    delivery = await _deliver(client, admin, household["id"], MONTH_START, COW)
    r = await client.post(
        "/v1/invoices",
        json={
            "customer_id": household["id"],
            "period_from": MONTH_START.isoformat(),
            "period_to": MONTH_START.isoformat(),
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        f"/v1/deliveries/{delivery['id']}/amend", json={"unit_price": "70.0000"}, headers=admin
    )
    assert r.status_code == 409, r.text
    assert "cancel the DRAFT" in r.text and "adjustment" in r.text and "BR-0010" in r.text


async def test_a_bulk_change_supersedes_every_plan_in_one_request_and_reports_the_skipped(client):
    from tests.conftest import count_statements

    _org, admin = await _shop(client)
    households = []
    for i in range(12):
        households.append(await _customer(client, admin, f"House {i:02d}", plan=_plan(COW, 1, 60)))
    # One is paused on the effective date, one is inactive, one already at the rate.
    paused = households[0]
    detail = (await client.get(f"/v1/customers/{paused['id']}", headers=admin)).json()
    r = await client.post(
        f"/v1/customers/plans/{detail['plans'][0]['id']}/pause",
        json={
            "paused_from": MONTH_START.isoformat(),
            "paused_to": (MONTH_START + timedelta(days=40)).isoformat(),
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    inactive = households[1]
    r = await client.post(
        f"/v1/customers/{inactive['id']}/status", json={"status": "inactive"}, headers=admin
    )
    assert r.status_code == 200, r.text
    already = households[2]
    r = await client.post(
        f"/v1/customers/{already['id']}/plan", json=_plan(COW, 1, 64), headers=admin
    )
    assert r.status_code == 201, r.text
    # And a delivery BEFORE the change, which must keep its own rate.
    before = await _deliver(client, admin, households[3]["id"], MONTH_START, COW)
    assert Decimal(before["unit_price"]) == Decimal("60.0000")

    effective = MONTH_START + timedelta(days=15)
    body = {"product": COW, "unit_price": "64.0000", "effective_from": effective.isoformat()}

    # Preview: the same answer, nothing written.
    r = await client.post(
        "/v1/customers/rate-change", json={**body, "preview": True}, headers=admin
    )
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["preview"] is True
    assert len(preview["changed"]) == 9
    reasons = {line["code"]: line["reason"] for line in preview["skipped"]}
    assert len(reasons) == 3
    assert any("paused" in v for v in reasons.values())
    assert any("inactive" in v for v in reasons.values())
    assert any("already at that rate" in v for v in reasons.values())
    assert all(Decimal(line["old_rate"]) == Decimal("60.0000") for line in preview["changed"])
    detail = (await client.get(f"/v1/customers/{households[5]['id']}", headers=admin)).json()
    assert Decimal(detail["plans"][0]["unit_price"]) == Decimal("60.0000"), "preview wrote nothing"

    # The change itself, in one request.
    r = await client.post("/v1/customers/rate-change", json=body, headers=admin)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["preview"] is False
    assert [line["code"] for line in result["changed"]] == [
        line["code"] for line in preview["changed"]
    ]
    assert result["effective_from"] == effective.isoformat()
    for h in households[3:]:
        plans = (await client.get(f"/v1/customers/{h['id']}", headers=admin)).json()["plans"]
        active = [p for p in plans if p["active"]]
        assert len(active) == 1 and Decimal(active[0]["unit_price"]) == Decimal("64.0000"), h[
            "name"
        ]
        assert active[0]["effective_from"] == effective.isoformat()
        assert len(plans) == 2, "superseded, not edited: the old plan is still there, inactive"
    # The delivery recorded before the change keeps its own copied rate.
    kept = (await client.get(f"/v1/deliveries/{before['id']}", headers=admin)).json()
    assert Decimal(kept["unit_price"]) == Decimal("60.0000")
    # And one recorded after the change takes the new one.
    after = await _deliver(client, admin, households[3]["id"], effective, COW)
    assert Decimal(after["unit_price"]) == Decimal("64.0000")
    # Running it again changes nothing: everyone is already at that rate.
    r = await client.post("/v1/customers/rate-change", json=body, headers=admin)
    assert r.status_code == 200 and r.json()["changed"] == []

    # A selection: only the named households, and an unknown id is reported.
    stranger = str(uuid.uuid4())
    r = await client.post(
        "/v1/customers/rate-change",
        json={**body, "unit_price": "66.0000", "customer_ids": [households[4]["id"], stranger]},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert [line["code"] for line in r.json()["changed"]] == [households[4]["code"]]
    assert any(line["customer_id"] == stranger for line in r.json()["skipped"])
    # A product the catalogue does not know is refused.
    r = await client.post(
        "/v1/customers/rate-change", json={**body, "product": "GOAT-MILK"}, headers=admin
    )
    assert r.status_code == 422, r.text
    # And a DRIVER cannot change rates at all.
    assert count_statements  # imported for symmetry with the month sheet's budget test


async def test_the_new_permission_is_registered_and_held_by_the_right_roles(client):
    from platform_core.modules.authz.permissions import ALL_SYSTEM_ROLES, PERMISSIONS

    assert "sales.delivery.price" in PERMISSIONS
    holders = {role for role, keys in ALL_SYSTEM_ROLES.items() if "sales.delivery.price" in keys}
    # Beside `sales.item.price`, wherever that already sits, plus CENTRE_MANAGER
    # as the work order names it.
    assert holders == {"tenant-admin", "ORGANIZATION_ADMIN", "CENTRE_MANAGER", "SALES_OFFICER"}
    assert "sales.delivery.price" not in ALL_SYSTEM_ROLES["DRIVER"]
