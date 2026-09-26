"""WO-81 · LACTEVA-SALES-001 — a product catalogue, and things sold that are
not the morning milk.

The acceptance scenario is the client's OWN spreadsheet, rebuilt against a
fresh organisation with their real figures, so a green test means the shop's
month reproduces to the paisa:

    Total Amount = Total milk x Price + other item + Past Due Amount

checked on their rows: Sr 10 → 23.25 x 56 + 160 + 244 = 1706. That is exactly
what `CustomerInvoice` already computed (subtotal + adjustments, then
+ previous_balance = amount_due); what was missing was the catalogue, the
item, and the constraint that refused the second milk.

The rules around it, each a way this goes wrong:
  * the catalogue's price is a SUGGESTION — a plan's rate wins, always;
  * a plan or a delivery must name an active catalogue product;
  * a household may take two products on one morning (the row that could
    not exist);
  * a driver records at the catalogue price and may not type one;
  * a product with no price cannot be sold at zero;
  * cancelling a draft releases the milk AND the item;
  * a new organisation starts with exactly `OTHER`.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from platform_core.modules.billing.month_end import draft_month_end
from tests.clock import through_today
from tests.conftest import invite
from tests.test_month_end_billing import BILLED_MONTH
from tests.test_org_structure import _tenant_admin

MONTH_START, MONTH_END = BILLED_MONTH
DAYS_IN_MONTH = (MONTH_END - MONTH_START).days + 1


async def _product(client, admin, code, name, unit, default_price=None):
    """The product, created — or, since WO-107 seeds Cow milk and Buffalo
    milk for every shop, the seeded one priced as this test wants it."""
    body = {"code": code, "name": name, "unit": unit}
    if default_price is not None:
        body["default_price"] = str(default_price)
    r = await client.post("/v1/products", json=body, headers=admin)
    if r.status_code == 409:
        page = (await client.get("/v1/products", headers=admin)).json()
        existing = next(p for p in page["items"] if p["code"] == code)
        patch = {"name": name, "active": True}
        if default_price is not None:
            patch["default_price"] = str(default_price)
        r = await client.patch(f"/v1/products/{existing['id']}", json=patch, headers=admin)
        assert r.status_code == 200, r.text
        return r.json()
    assert r.status_code == 201, r.text
    return r.json()


async def _customer(client, admin, name, *, plan=None):
    body = {"name": name, "customer_type": "household", "billing_mode": "credit"}
    if plan is not None:
        body["plan"] = plan
    r = await client.post("/v1/customers", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def _plan(product, quantity, price):
    return {
        "product": product,
        "default_quantity": str(quantity),
        "quantity_unit": "L",
        "unit_price": str(price),
        "effective_from": MONTH_START.isoformat(),
    }


async def _deliver(client, admin, customer_id, day, product, quantity=None):
    body = {
        "customer_id": customer_id,
        "delivery_date": day.isoformat(),
        "slot": "morning",
        "status": "delivered",
        "product": product,
    }
    if quantity is not None:
        body["quantity"] = str(quantity)
    r = await client.post("/v1/deliveries", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


async def _shop(client):
    """The client, as a fresh organisation: three products, three households."""
    org, admin = await _tenant_admin(client)
    await _product(client, admin, "COW-MILK", "Cow milk", "L")
    await _product(client, admin, "BUFFALO-MILK", "Buffalo milk", "L")
    return org, admin


# --- the catalogue ------------------------------------------------------------


async def test_a_new_organisation_starts_with_its_milk_and_other(client):
    """WO-107 §2: a shop's catalogue on day one is Cow milk, Buffalo milk and
    OTHER — unpriced milk, so the owner's first job is to set prices rather
    than to discover that "cow milk" has to be invented."""
    org, admin = await _tenant_admin(client)
    # The fixture added RAW-COW-MILK the way onboarding used to; everything
    # else on the list is what the platform seeded.
    page = (await client.get("/v1/products", headers=admin)).json()
    codes = {p["code"]: p for p in page["items"]}
    assert "OTHER" in codes
    for code, name in (("COW-MILK", "Cow milk"), ("BUFFALO-MILK", "Buffalo milk")):
        assert codes[code]["name"] == name and codes[code]["unit"] == "L"
        assert codes[code]["default_price"] is None and codes[code]["active"] is True
    other = codes["OTHER"]
    assert other["name"] == "Other shop item"
    assert other["unit"] == "pc"
    assert other["default_price"] is None
    assert other["active"] is True
    assert other["currency"] == org["currency_code"]
    # The seed, the fixture's milk — and nothing else guessed at.
    assert set(codes) == {"OTHER", "COW-MILK", "BUFFALO-MILK", "RAW-COW-MILK"}


async def test_a_plan_and_a_delivery_must_name_an_active_product(client):
    _org, admin = await _tenant_admin(client)
    r = await client.post(
        "/v1/customers",
        json={"name": "Nobody", "plan": _plan("GOAT-MILK", 1, 80)},
        headers=admin,
    )
    assert r.status_code == 422, r.text
    assert "catalogue" in r.text

    customer = await _customer(client, admin, "Tower 1-2006", plan=_plan("RAW-COW-MILK", 1, 74))
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": MONTH_START.isoformat(),
            "product": "GOAT-MILK",
        },
        headers=admin,
    )
    assert r.status_code == 422, r.text

    # Deactivate the milk: the existing plan keeps its history, but a NEW plan
    # or delivery on the retired product is refused, and the product still
    # resolves by name for anything already written.
    milk = next(
        p
        for p in (await client.get("/v1/products", headers=admin)).json()["items"]
        if p["code"] == "RAW-COW-MILK"
    )
    r = await client.patch(f"/v1/products/{milk['id']}", json={"active": False}, headers=admin)
    assert r.status_code == 200, r.text
    r = await client.post(
        "/v1/deliveries",
        json={"customer_id": customer["id"], "delivery_date": MONTH_START.isoformat()},
        headers=admin,
    )
    assert r.status_code == 422
    assert "deactivated" in r.text
    assert (await client.get(f"/v1/products/{milk['id']}", headers=admin)).json()["name"]


async def test_the_catalogue_price_never_overrides_a_plans_rate(client):
    """₹74, ₹56 and ₹72 sit in the same price column of the client's sheet.
    The rate is the household's, on its standing order; a catalogue price that
    re-rated four hundred households would do so silently."""
    _org, admin = await _tenant_admin(client)
    await _product(client, admin, "COW-MILK", "Cow milk", "L", default_price="99.00")
    customer = await _customer(client, admin, "Tower 1-2006", plan=_plan("COW-MILK", 1, 74))
    delivery = await _deliver(client, admin, customer["id"], MONTH_START, "COW-MILK")
    assert Decimal(delivery["unit_price"]) == Decimal("74.0000")
    assert Decimal(delivery["amount"]) == Decimal("74.00")

    # Changing the catalogue price afterwards moves nothing either.
    products = (await client.get("/v1/products", headers=admin)).json()["items"]
    cow = next(p for p in products if p["code"] == "COW-MILK")
    r = await client.patch(
        f"/v1/products/{cow['id']}", json={"default_price": "120.00"}, headers=admin
    )
    assert r.status_code == 200, r.text
    again = await _deliver(
        client, admin, customer["id"], MONTH_START + timedelta(days=1), "COW-MILK"
    )
    assert Decimal(again["unit_price"]) == Decimal("74.0000")


async def test_a_product_code_is_a_slug_and_cannot_be_renamed(client):
    _org, admin = await _tenant_admin(client)
    created = await _product(client, admin, "dahi 500g", "Dahi 500 g", "pc", "40.00")
    assert created["code"] == "DAHI-500G"
    r = await client.post(
        "/v1/products", json={"code": "DAHI-500G", "name": "Again", "unit": "pc"}, headers=admin
    )
    assert r.status_code == 409
    r = await client.patch(
        f"/v1/products/{created['id']}", json={"code": "DAHI-1KG"}, headers=admin
    )
    # Unknown fields are ignored by the command; the code is untouched.
    assert r.status_code == 200
    assert r.json()["code"] == "DAHI-500G"


# --- two milks on one morning ---------------------------------------------------


async def test_a_household_may_take_two_products_on_the_same_morning(client):
    """Flat C-1603 at ₹74 AND at ₹56: two standing orders, two deliveries,
    one household. The row the database refused until WO-81."""
    _org, admin = await _shop(client)
    flat = await _customer(
        client, admin, "lodha casa foresta C-1603", plan=_plan("COW-MILK", 1.5, 74)
    )
    r = await client.post(
        f"/v1/customers/{flat['id']}/plan", json=_plan("BUFFALO-MILK", 0.5, 56), headers=admin
    )
    assert r.status_code == 201, r.text
    detail = (await client.get(f"/v1/customers/{flat['id']}", headers=admin)).json()
    assert sorted(p["product"] for p in detail["plans"] if p["active"]) == [
        "BUFFALO-MILK",
        "COW-MILK",
    ]

    cow = await _deliver(client, admin, flat["id"], MONTH_START, "COW-MILK")
    buffalo = await _deliver(client, admin, flat["id"], MONTH_START, "BUFFALO-MILK")
    assert Decimal(cow["amount"]) == Decimal("111.00")
    assert Decimal(buffalo["amount"]) == Decimal("28.00")

    # The same milk twice on one morning is still a correction, not a sale —
    # and the refusal names the product.
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": flat["id"],
            "delivery_date": MONTH_START.isoformat(),
            "product": "COW-MILK",
        },
        headers=admin,
    )
    assert r.status_code == 409, r.text
    assert "COW-MILK" in r.text


async def test_the_generator_keeps_both_milks(client):
    """A guard on fewer columns than the constraint would drop one of the two
    milks every morning, silently."""
    _org, admin = await _shop(client)
    flat = await _customer(client, admin, "C-1603", plan=_plan("COW-MILK", 1.5, 74))
    await client.post(
        f"/v1/customers/{flat['id']}/plan", json=_plan("BUFFALO-MILK", 0.5, 56), headers=admin
    )
    day = MONTH_START + timedelta(days=3)
    for _ in range(2):  # a re-run is a no-op, and still two rows
        r = await client.post(
            "/v1/deliveries/generate", json={"for_date": day.isoformat()}, headers=admin
        )
        assert r.status_code in (200, 201), r.text
    page = (
        await client.get(
            "/v1/deliveries",
            params={"customer_id": flat["id"], "date_from": day, "date_to": day, "limit": 10},
            headers=admin,
        )
    ).json()
    assert sorted(d["product"] for d in page["items"]) == ["BUFFALO-MILK", "COW-MILK"]
    assert all(d["status"] == "scheduled" for d in page["items"])


# --- items ---------------------------------------------------------------------


async def test_an_item_is_priced_by_the_catalogue_unless_the_owner_says_otherwise(client):
    _org, admin = await _shop(client)
    await _product(client, admin, "DAHI-500G", "Dahi 500 g", "pc", "40.00")
    household = await _customer(client, admin, "A-1607", plan=_plan("BUFFALO-MILK", 0.75, 56))

    r = await client.post(
        f"/v1/customers/{household['id']}/items",
        json={"sale_date": MONTH_START.isoformat(), "product_code": "DAHI-500G", "quantity": "2"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["product_name"] == "Dahi 500 g"
    assert Decimal(item["unit_price"]) == Decimal("40.00")
    assert Decimal(item["amount"]) == Decimal("80.00")
    assert item["status"] == "recorded"

    # The owner (tenant-admin holds sales.item.price) may quote a different rate.
    r = await client.post(
        f"/v1/customers/{household['id']}/items",
        json={
            "sale_date": MONTH_START.isoformat(),
            "product_code": "DAHI-500G",
            "quantity": "1",
            "unit_price": "35.00",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["amount"]) == Decimal("35.00")

    # OTHER has no price: it needs one, and refuses a zero-rupee line.
    r = await client.post(
        f"/v1/customers/{household['id']}/items",
        json={"sale_date": MONTH_START.isoformat(), "product_code": "OTHER", "quantity": "1"},
        headers=admin,
    )
    assert r.status_code == 409, r.text
    assert "no price" in r.text
    r = await client.post(
        f"/v1/customers/{household['id']}/items",
        json={
            "sale_date": MONTH_START.isoformat(),
            "product_code": "OTHER",
            "quantity": "1",
            "unit_price": "160.00",
            "notes": "sweets",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    assert r.json()["product_name"] == "Other shop item"

    page = (await client.get(f"/v1/customers/{household['id']}/items", headers=admin)).json()
    assert page["total"] == 3
    assert Decimal(page["total_amount"]) == Decimal("275.00")


async def test_a_driver_records_at_the_catalogue_price_and_may_not_type_one(client):
    org, admin = await _shop(client)
    await _product(client, admin, "DAHI-500G", "Dahi 500 g", "pc", "40.00")
    household = await _customer(client, admin, "A-1607", plan=_plan("BUFFALO-MILK", 0.75, 56))

    _inv, token = await invite(client, admin, email="driver@shop.example", role_name="DRIVER")
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "driver-password-1", "full_name": "Delivery Boy"},
    )
    assert r.status_code == 201, r.text
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "driver@shop.example",
                "password": "driver-password-1",
                "tenant_id": org["id"],
            },
        )
    ).json()
    driver = {"Authorization": f"Bearer {pair['access_token']}"}

    # The driver sees the catalogue.
    assert (await client.get("/v1/products", headers=driver)).status_code == 200
    # Records at the catalogue price, with the phone's key; a replay is the
    # same row, not a second dahi.
    body = {
        "sale_date": MONTH_START.isoformat(),
        "product_code": "DAHI-500G",
        "quantity": "1",
        "idempotency_key": "phone-1",
        "recorded_via": "mobile",
    }
    first = await client.post(f"/v1/customers/{household['id']}/items", json=body, headers=driver)
    assert first.status_code == 201, first.text
    second = await client.post(f"/v1/customers/{household['id']}/items", json=body, headers=driver)
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    # May not type a price — refused, not ignored.
    r = await client.post(
        f"/v1/customers/{household['id']}/items",
        json={**body, "idempotency_key": "phone-2", "unit_price": "10.00"},
        headers=driver,
    )
    assert r.status_code == 403, r.text
    # And cannot sell what has no price.
    r = await client.post(
        f"/v1/customers/{household['id']}/items",
        json={**body, "idempotency_key": "phone-3", "product_code": "OTHER"},
        headers=driver,
    )
    assert r.status_code == 409


async def test_a_cancelled_item_is_released_and_a_billed_one_is_frozen(client):
    _org, admin = await _shop(client)
    await _product(client, admin, "DAHI-500G", "Dahi 500 g", "pc", "40.00")
    household = await _customer(client, admin, "A-1607", plan=_plan("BUFFALO-MILK", 0.75, 56))
    item = (
        await client.post(
            f"/v1/customers/{household['id']}/items",
            json={"sale_date": MONTH_START.isoformat(), "product_code": "DAHI-500G"},
            headers=admin,
        )
    ).json()
    r = await client.post(f"/v1/items/{item['id']}/cancel", json={"reason": "x"}, headers=admin)
    assert r.status_code == 422  # a reason must say something
    r = await client.post(
        f"/v1/items/{item['id']}/cancel", json={"reason": "recorded twice"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    balance = (await client.get(f"/v1/customers/{household['id']}/balance", headers=admin)).json()
    assert Decimal(balance["unbilled_amount"]) == Decimal("0.00")

    billed = (
        await client.post(
            f"/v1/customers/{household['id']}/items",
            json={"sale_date": MONTH_START.isoformat(), "product_code": "DAHI-500G"},
            headers=admin,
        )
    ).json()
    r = await client.post(
        "/v1/invoices",
        json={
            "customer_id": household["id"],
            "period_from": MONTH_START.isoformat(),
            "period_to": MONTH_END.isoformat(),
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        f"/v1/items/{billed['id']}/cancel", json={"reason": "too late"}, headers=admin
    )
    assert r.status_code == 409
    assert "invoice" in r.text


# --- the client's month, to the paisa -------------------------------------------


async def test_the_clients_spreadsheet_month_reproduces_to_the_paisa(client):
    """Their rows, their figures: Tower 1-2006, C-1603 with two milks, A-1607
    with an OTHER item and last month's ₹244 still owed."""
    org, admin = await _shop(client)

    tower = await _customer(client, admin, "Tower 1-2006", plan=_plan("COW-MILK", 1, 74))
    flat = await _customer(
        client, admin, "lodha casa foresta C-1603", plan=_plan("COW-MILK", 1.5, 74)
    )
    r = await client.post(
        f"/v1/customers/{flat['id']}/plan", json=_plan("BUFFALO-MILK", 0.5, 56), headers=admin
    )
    assert r.status_code == 201, r.text
    a1607 = await _customer(
        client, admin, "lodha casa foresta A-1607", plan=_plan("BUFFALO-MILK", 0.75, 56)
    )

    # A-1607 owes ₹244 from the previous month (their "Past Due Amount"): a
    # bill for the last day of last month — 4 L of buffalo (224.00) and an
    # OTHER item of ₹20 — issued and unpaid.
    previous_day = MONTH_START - timedelta(days=1)
    await _deliver(client, admin, a1607["id"], previous_day, "BUFFALO-MILK", quantity="4.000")
    r = await client.post(
        f"/v1/customers/{a1607['id']}/items",
        json={
            "sale_date": previous_day.isoformat(),
            "product_code": "OTHER",
            "unit_price": "20.00",
            "notes": "last month",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    prior = await client.post(
        "/v1/invoices",
        json={
            "customer_id": a1607["id"],
            "period_from": previous_day.isoformat(),
            "period_to": previous_day.isoformat(),
        },
        headers=admin,
    )
    assert prior.status_code == 201, prior.text
    assert Decimal(prior.json()["amount_due"]) == Decimal("244.00")
    r = await client.post(f"/v1/invoices/{prior.json()['id']}/issue", headers=admin)
    assert r.status_code == 200, r.text

    # The month itself.
    for offset in range(DAYS_IN_MONTH):
        day = MONTH_START + timedelta(days=offset)
        await _deliver(client, admin, tower["id"], day, "COW-MILK")
        await _deliver(client, admin, a1607["id"], day, "BUFFALO-MILK")
    for offset in range(20):
        day = MONTH_START + timedelta(days=offset)
        await _deliver(client, admin, flat["id"], day, "COW-MILK")
        await _deliver(client, admin, flat["id"], day, "BUFFALO-MILK")
    r = await client.post(
        f"/v1/customers/{a1607['id']}/items",
        json={
            "sale_date": (MONTH_START + timedelta(days=10)).isoformat(),
            "product_code": "OTHER",
            "unit_price": "160.00",
            "notes": "sweets",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text

    # Month-end drafts three bills — through the SAME function the API calls,
    # which is why the job needed no change for items.
    from platform_core.core.db import get_session_factory
    from platform_core.core.rls import rebind_tenant

    async with get_session_factory()() as session:
        await rebind_tenant(session, uuid.UUID(org["id"]))
        result = await draft_month_end(
            session,
            tenant_id=uuid.UUID(org["id"]),
            timezone=org["timezone"],
            period=BILLED_MONTH,
        )
        await session.commit()
    assert result.drafted == 3, result

    invoices = (await client.get("/v1/invoices", params={"status": "draft"}, headers=admin)).json()
    by_customer = {inv["customer_id"]: inv for inv in invoices["items"]}

    # Tower 1-2006 = 31 x 74 (their Sr 1: 46.5 x 74 = 3441 is the same rule).
    tower_inv = by_customer[tower["id"]]
    assert Decimal(tower_inv["total"]) == Decimal(DAYS_IN_MONTH) * Decimal("74.00")
    assert Decimal(tower_inv["previous_balance"]) == Decimal("0.00")

    # C-1603 = 20 x 1.5 x 74 + 20 x 0.5 x 56, with BOTH milks on the same dates.
    flat_inv = by_customer[flat["id"]]
    assert Decimal(flat_inv["total"]) == Decimal("2220.00") + Decimal("560.00")
    detail = (await client.get(f"/v1/invoices/{flat_inv['id']}", headers=admin)).json()
    dates = {}
    for line in detail["lines"]:
        dates.setdefault(line["delivery_date"], set()).add(line["product"])
    assert len(dates) == 20
    assert all(products == {"COW-MILK", "BUFFALO-MILK"} for products in dates.values())
    assert all(line["line_kind"] == "delivery" for line in detail["lines"])
    assert detail["totals_match_lines"] is True

    # A-1607 = 23.25 x 56 + 160 = 1462.00, previous_balance 244, amount_due 1706.00
    # — the exact number in cell AM of their sheet.
    a_inv = by_customer[a1607["id"]]
    assert Decimal(a_inv["subtotal"]) == Decimal("0.75") * DAYS_IN_MONTH * 56 + Decimal("160.00")
    assert Decimal(a_inv["previous_balance"]) == Decimal("244.00")
    assert Decimal(a_inv["amount_due"]) == Decimal(a_inv["subtotal"]) + Decimal("244.00")
    if DAYS_IN_MONTH == 31:
        assert Decimal(a_inv["subtotal"]) == Decimal("1462.00")
        assert Decimal(a_inv["amount_due"]) == Decimal("1706.00")
    detail = (await client.get(f"/v1/invoices/{a_inv['id']}", headers=admin)).json()
    assert detail["totals_match_lines"] is True
    kinds = [line["line_kind"] for line in detail["lines"]]
    assert kinds.count("item") == 1 and kinds.count("delivery") == DAYS_IN_MONTH
    item_line = next(line for line in detail["lines"] if line["line_kind"] == "item")
    assert item_line["product_name"] == "Other shop item"
    assert Decimal(item_line["amount"]) == Decimal("160.00")
    assert item_line["item_id"] is not None and item_line["delivery_id"] is None
    # Items come after the milk on the same date.
    same_day = [
        line for line in detail["lines"] if line["delivery_date"] == item_line["delivery_date"]
    ]
    assert [line["line_kind"] for line in same_day] == ["delivery", "item"]

    # Issue all three; the statement agrees with the invoice.
    for inv in (tower_inv, flat_inv, a_inv):
        r = await client.post(f"/v1/invoices/{inv['id']}/issue", headers=admin)
        assert r.status_code == 200, r.text
    # The statement's window is by ISSUE date in the DAIRY's calendar, and
    # the bills were issued "today" — which, for a Nairobi dairy after 21:00
    # UTC, is already tomorrow by UTC's `TODAY`. `through_today()` is the
    # window end that contains the organisation's own business date (WO-58);
    # this test failed at 03:15 IST for exactly that reason.
    statement = (
        await client.get(
            f"/v1/customers/{a1607['id']}/statement",
            params={"date_from": previous_day, "date_to": through_today()},
            headers=admin,
        )
    ).json()
    assert Decimal(statement["closing_balance"]) == Decimal(a_inv["amount_due"])
    assert Decimal(statement["items_amount"]) == Decimal("180.00")  # 20 + 160
    assert statement["items_count"] == 2


async def test_cancelling_a_draft_releases_the_milk_and_the_item(client):
    _org, admin = await _shop(client)
    await _product(client, admin, "DAHI-500G", "Dahi 500 g", "pc", "40.00")
    household = await _customer(client, admin, "A-1607", plan=_plan("BUFFALO-MILK", 0.75, 56))
    await _deliver(client, admin, household["id"], MONTH_START, "BUFFALO-MILK")
    item = (
        await client.post(
            f"/v1/customers/{household['id']}/items",
            json={"sale_date": MONTH_START.isoformat(), "product_code": "DAHI-500G"},
            headers=admin,
        )
    ).json()
    draft = (
        await client.post(
            "/v1/invoices",
            json={
                "customer_id": household["id"],
                "period_from": MONTH_START.isoformat(),
                "period_to": MONTH_END.isoformat(),
            },
            headers=admin,
        )
    ).json()
    assert draft["line_count"] == 2
    assert Decimal(draft["total"]) == Decimal("42.00") + Decimal("40.00")
    listed = (await client.get(f"/v1/customers/{household['id']}/items", headers=admin)).json()
    assert listed["items"][0]["invoice_id"] == draft["id"]

    r = await client.post(
        f"/v1/invoices/{draft['id']}/cancel", json={"reason": "wrong month"}, headers=admin
    )
    assert r.status_code == 200, r.text
    listed = (await client.get(f"/v1/customers/{household['id']}/items", headers=admin)).json()
    assert listed["items"][0]["invoice_id"] is None
    balance = (await client.get(f"/v1/customers/{household['id']}/balance", headers=admin)).json()
    assert Decimal(balance["unbilled_amount"]) == Decimal("82.00")
    assert balance["unbilled_deliveries"] == 1 and balance["unbilled_items"] == 1
    # Billable again: the same period drafts the same bill.
    again = (
        await client.post(
            "/v1/invoices",
            json={
                "customer_id": household["id"],
                "period_from": MONTH_START.isoformat(),
                "period_to": MONTH_END.isoformat(),
            },
            headers=admin,
        )
    ).json()
    assert again["line_count"] == 2 and again["id"] != draft["id"]
    assert item["id"] is not None


async def test_reporting_keeps_other_products_apart_from_the_milk(client):
    _org, admin = await _shop(client)
    await _product(client, admin, "DAHI-500G", "Dahi 500 g", "pc", "40.00")
    household = await _customer(client, admin, "A-1607", plan=_plan("BUFFALO-MILK", 0.75, 56))
    day = MONTH_START
    await _deliver(client, admin, household["id"], day, "BUFFALO-MILK")
    await client.post(
        f"/v1/customers/{household['id']}/items",
        json={"sale_date": day.isoformat(), "product_code": "DAHI-500G", "quantity": "2"},
        headers=admin,
    )
    summary = (
        await client.get(
            "/v1/reports/sales/summary",
            params={"date_from": day, "date_to": day},
            headers=admin,
        )
    ).json()
    assert Decimal(summary["sales_value_in_period"]) == Decimal("42.00")
    assert summary["other_product_items_in_period"] == 1
    assert Decimal(summary["other_products_value_in_period"]) == Decimal("80.00")
    assert summary["unbilled_items"] == 1
    assert Decimal(summary["unbilled_amount"]) == Decimal("122.00")

    book = (
        await client.get("/v1/reports/day-book", params={"business_date": day}, headers=admin)
    ).json()
    assert book["sales"]["deliveries"] == 1
    assert book["sales"]["other_product_items"] == 1
    assert Decimal(book["sales"]["other_products_value"]) == Decimal("80.00")
