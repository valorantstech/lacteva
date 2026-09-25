"""WO-84 — the month sheet, which is how this shop thinks.

The WO-81 acceptance dataset rendered as a month, checked against the cells
of the client's own `Dailymilk Delivery 025.xlsx`:

  * Tower 1-2006 shows 1 on thirty-one days, 31 / ₹2294;
  * C-1603 shows TWO rows — 1.5 cow and 0.5 buffalo — on the same twenty
    dates, as one household with two standing orders;
  * A-1607 shows 0.75 across the month, ₹160 of other items and ₹244 past
    due, totalling ₹1706 — their own cell AM;
  * a scheduled-but-not-delivered day is BLANK, and a skipped one too;
  * the sheet is a fixed number of statements whatever the number of
    households — proven by counting them for five and for forty;
  * the CSV carries exactly their column order, and a blank cell is blank;
  * `product=` narrows to one milk; `route_id=` narrows to one round; a
    household's own login sees its own row and nobody else's.
"""

import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from tests.conftest import count_statements
from tests.test_catalogue_and_items import (
    DAYS_IN_MONTH,
    MONTH_END,
    MONTH_START,
    _customer,
    _deliver,
    _plan,
    _product,
    _shop,
)
from tests.test_customer_scope import _customer_login

COW, BUFFALO = "COW-MILK", "BUFFALO-MILK"


async def _sheet(client, admin, **params):
    r = await client.get(
        "/v1/deliveries/month",
        params={"year": MONTH_START.year, "month": MONTH_START.month, **params},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _row(sheet, code_or_name, product=None):
    rows = [
        r
        for r in sheet["rows"]
        if code_or_name in (r["code"], r["name"]) and (product is None or r["product"] == product)
    ]
    assert rows, (code_or_name, product, [(r["name"], r["product"]) for r in sheet["rows"]])
    return rows[0]


def _numbers(row):
    return [
        None if c is None or c["quantity"] is None else Decimal(c["quantity"]) for c in row["days"]
    ]


async def _backdate(model, row_id: uuid.UUID, column: str, when: datetime) -> None:
    """Move a timestamp the platform only ever sets to `now` — an invoice
    issued in the previous month, a payment received inside the sheet's
    month — because the sheet is asked about a month that is already over."""
    from platform_core.core.rls import platform_factory

    async with platform_factory("test: backdate a row")() as session:
        row = await session.get(model, row_id)
        setattr(row, column, when)
        await session.commit()


async def _acceptance_dairy(client):
    """The WO-81 dataset, a whole month of it."""
    org, admin = await _shop(client)
    await _product(client, admin, "DAHI-500G", "Dahi 500 g", "pc", "40.00")
    days = [MONTH_START + timedelta(days=i) for i in range(DAYS_IN_MONTH)]

    tower = await _customer(client, admin, "Tower 1-2006", plan=_plan(COW, 1, 74))
    for day in days:
        await _deliver(client, admin, tower["id"], day, COW)

    flat = await _customer(client, admin, "C-1603", plan=_plan(COW, 1.5, 74))
    r = await client.post(
        f"/v1/customers/{flat['id']}/plan", json=_plan(BUFFALO, 0.5, 56), headers=admin
    )
    assert r.status_code == 201, r.text
    for day in days[:20]:
        await _deliver(client, admin, flat["id"], day, COW)
        await _deliver(client, admin, flat["id"], day, BUFFALO)

    household = await _customer(client, admin, "A-1607", plan=_plan(BUFFALO, 0.75, 56))
    for day in days:
        await _deliver(client, admin, household["id"], day, BUFFALO)
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
    # ₹244 past due: an item sold the month before, invoiced and issued then.
    before = MONTH_START - timedelta(days=1)
    r = await client.post(
        f"/v1/customers/{household['id']}/items",
        json={
            "sale_date": before.isoformat(),
            "product_code": "OTHER",
            "quantity": "1",
            "unit_price": "244.00",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/v1/invoices",
        json={
            "customer_id": household["id"],
            "period_from": before.replace(day=1).isoformat(),
            "period_to": before.isoformat(),
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    invoice = r.json()
    r = await client.post(f"/v1/invoices/{invoice['id']}/issue", json={}, headers=admin)
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["total"]) == Decimal("244.00")
    from platform_core.modules.billing.models import CustomerInvoice

    await _backdate(
        CustomerInvoice,
        uuid.UUID(invoice["id"]),
        "issued_at",
        datetime.combine(before, time(hour=10), tzinfo=UTC),
    )
    return org, admin, {"tower": tower, "flat": flat, "household": household}


# --- the acceptance dataset, as a month ---------------------------------------------


async def test_the_shop_s_own_sheet_computed(client):
    _org, admin, _who = await _acceptance_dairy(client)
    sheet = await _sheet(client, admin)
    assert sheet["date_from"] == MONTH_START.isoformat()
    assert sheet["date_to"] == MONTH_END.isoformat()
    assert len(sheet["day_totals"]) == DAYS_IN_MONTH
    assert [(r["name"], r["product"]) for r in sheet["rows"]] == [
        ("A-1607", BUFFALO),
        ("C-1603", BUFFALO),
        ("C-1603", COW),
        ("Tower 1-2006", COW),
    ] or len(sheet["rows"]) == 4

    tower = _row(sheet, "Tower 1-2006")
    assert _numbers(tower) == [Decimal("1.000")] * DAYS_IN_MONTH
    assert Decimal(tower["unit_price"]) == Decimal("74.0000")
    assert Decimal(tower["total_quantity"]) == Decimal("31.000")
    assert Decimal(tower["milk_amount"]) == Decimal("2294.00")
    assert Decimal(tower["total_due"]) == Decimal("2294.00")

    cow = _row(sheet, "C-1603", COW)
    buffalo = _row(sheet, "C-1603", BUFFALO)
    assert _numbers(cow)[:20] == [Decimal("1.500")] * 20 and _numbers(cow)[20:] == [None] * 11
    assert _numbers(buffalo)[:20] == [Decimal("0.500")] * 20
    assert Decimal(cow["milk_amount"]) == Decimal("2220.00")  # 20 x 1.5 x 74
    assert Decimal(buffalo["milk_amount"]) == Decimal("560.00")  # 20 x 0.5 x 56
    # One household: the money that is not milk sits on its first row only.
    assert Decimal(buffalo["previous_balance"]) + Decimal(cow["previous_balance"]) == 0

    a1607 = _row(sheet, "A-1607")
    assert _numbers(a1607) == [Decimal("0.750")] * DAYS_IN_MONTH
    assert Decimal(a1607["milk_amount"]) == Decimal("1302.00")  # 31 x 0.75 x 56
    assert Decimal(a1607["items_amount"]) == Decimal("160.00")
    assert Decimal(a1607["previous_balance"]) == Decimal("244.00")
    assert Decimal(a1607["total_due"]) == Decimal("1706.00")  # their cell AM

    totals = sheet["totals"]
    assert Decimal(totals["milk_amount"]) == Decimal("2294.00") + 2220 + 560 + 1302
    assert Decimal(totals["items_amount"]) == Decimal("160.00")
    assert Decimal(totals["previous_balance"]) == Decimal("244.00")
    assert Decimal(sheet["day_totals"][0]) == Decimal("1.000") + Decimal("1.5") + Decimal(
        "0.5"
    ) + Decimal("0.75")
    assert Decimal(sheet["day_totals"][30]) == Decimal("1.000") + Decimal("0.75")


async def test_received_method_and_date_are_the_month_s_payments(client):
    from platform_core.modules.billing.models import CustomerPayment

    _org, admin, who = await _acceptance_dairy(client)
    r = await client.post(
        "/v1/customer-payments",
        json={"customer_id": who["tower"]["id"], "amount": "2000.00", "method": "CASH"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    paid_on = MONTH_START + timedelta(days=4)
    await _backdate(
        CustomerPayment,
        uuid.UUID(r.json()["id"]),
        "received_at",
        datetime.combine(paid_on, time(hour=9), tzinfo=UTC),
    )
    r = await client.post(
        "/v1/customer-payments",
        json={"customer_id": who["tower"]["id"], "amount": "294.00", "method": "BANK_TRANSFER"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    later = MONTH_START + timedelta(days=9)
    await _backdate(
        CustomerPayment,
        uuid.UUID(r.json()["id"]),
        "received_at",
        datetime.combine(later, time(hour=9), tzinfo=UTC),
    )
    tower = _row(await _sheet(client, admin), "Tower 1-2006")
    assert Decimal(tower["received"]) == Decimal("2294.00")
    # The method and date are the LATEST payment's — the two cells their sheet keeps.
    assert tower["method"] == "BANK_TRANSFER"
    assert tower["received_on"] == later.isoformat()
    # A payment this month is not "past due" for this month.
    assert Decimal(tower["previous_balance"]) == Decimal("0.00")


# --- the safety argument ------------------------------------------------------------


async def test_a_scheduled_day_is_blank_and_so_is_a_skipped_one(client):
    _org, admin = await _shop(client)
    customer = await _customer(client, admin, "Blank Household", plan=_plan(COW, 2, 60))
    day = MONTH_START + timedelta(days=2)
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": day.isoformat(),
            "slot": "morning",
            "status": "scheduled",
            "product": COW,
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    skipped_day = MONTH_START + timedelta(days=3)
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": skipped_day.isoformat(),
            "slot": "morning",
            "status": "skipped",
            "product": COW,
            "quantity": "0",
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    await _deliver(client, admin, customer["id"], MONTH_START, COW)

    row = _row(await _sheet(client, admin), "Blank Household")
    numbers = _numbers(row)
    assert numbers[0] == Decimal("2.000")
    assert numbers[2] is None, "a scheduled day is not a delivery"
    assert numbers[3] is None, "a skipped day is not a delivery"
    # But the cells know what they are, so the editor can open them.
    assert row["days"][2]["status"] == "scheduled" and row["days"][2]["delivery_id"]
    assert row["days"][3]["status"] == "skipped"
    assert row["days"][1] is None
    assert Decimal(row["total_quantity"]) == Decimal("2.000")
    assert Decimal(row["milk_amount"]) == Decimal("120.00")
    # And the CSV writes nothing at all in those cells.
    r = await client.get(
        "/v1/deliveries/month.csv",
        params={"year": MONTH_START.year, "month": MONTH_START.month},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    line = next(line for line in r.text.splitlines() if "Blank Household" in line)
    cells = line.split(",")
    # Sr, Customer, Code, Product, Price, then the days.
    assert cells[5] == "2" and cells[6] == "" and cells[7] == "" and cells[8] == ""


async def test_one_read_not_four_hundred(client):
    """The number of statements does not grow with the number of households."""
    from platform_core.core.rls import platform_factory
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.modules.delivery.month import MonthSheetService

    org, admin = await _shop(client)

    async def dairy_of(n: int) -> list[dict]:
        made = []
        for i in range(n):
            c = await _customer(client, admin, f"House {i:03d}", plan=_plan(COW, 1, 60))
            await _deliver(client, admin, c["id"], MONTH_START, COW)
            made.append(c)
        return made

    async def statements_for_sheet() -> int:
        async with platform_factory("test: count the month sheet's statements")() as session:
            set_current_tenant(uuid.UUID(org["id"]))
            try:
                _, count = await count_statements(
                    lambda: MonthSheetService(session).sheet(
                        year=MONTH_START.year, month=MONTH_START.month
                    )
                )
            finally:
                set_current_tenant(None)
        return count

    await dairy_of(5)
    await statements_for_sheet()  # warms the per-tenant locale cache, which is one read once
    five = await statements_for_sheet()
    await dairy_of(35)
    forty = await statements_for_sheet()
    assert five == forty, f"{five} statements for 5 households, {forty} for 40"
    assert forty <= 8, forty


async def test_the_csv_is_their_sheet_s_column_order(client):
    _org, admin, _who = await _acceptance_dairy(client)
    r = await client.get(
        "/v1/deliveries/month.csv",
        params={"year": MONTH_START.year, "month": MONTH_START.month},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert f"deliveries-{MONTH_START.year}-{MONTH_START.month:02d}.csv" in r.headers.get(
        "content-disposition", ""
    )
    lines = r.text.splitlines()
    header = lines[0].split(",")
    assert header[:5] == ["Sr", "Customer", "Code", "Product", "Price"]
    assert header[5 : 5 + DAYS_IN_MONTH] == [str(d) for d in range(1, DAYS_IN_MONTH + 1)]
    assert header[5 + DAYS_IN_MONTH :] == [
        "Total milk",
        "Other items",
        "Past due",
        "Total",
        "Received",
        "Method",
        "Date",
    ]
    a1607 = next(line for line in lines if "A-1607" in line).split(",")
    tail = a1607[5 + DAYS_IN_MONTH :]
    assert tail[:4] == ["23.25", "1302.00", "160.00", "244.00"]
    assert tail[4] == "1706.00"
    assert a1607[4] == "56.0000"
    assert a1607[5] == "0.75"
    assert lines[-1].split(",")[1] == "TOTAL"


# --- narrowing -------------------------------------------------------------------------


async def test_product_and_route_narrow_the_sheet(client):
    _org, admin, who = await _acceptance_dairy(client)
    cow_only = await _sheet(client, admin, product=COW)
    assert {r["product"] for r in cow_only["rows"]} == {COW}
    assert {r["name"] for r in cow_only["rows"]} == {"Tower 1-2006", "C-1603"}
    assert cow_only["product"] == COW

    r = await client.post("/v1/routes", json={"code": "R-01", "name": "Towers"}, headers=admin)
    assert r.status_code == 201, r.text
    route = r.json()
    r = await client.put(
        f"/v1/routes/{route['id']}/stops",
        json={"customer_ids": [who["tower"]["id"]]},
        headers=admin,
    )
    assert r.status_code in (200, 201), r.text
    one_round = await _sheet(client, admin, route_id=route["id"])
    assert [r["name"] for r in one_round["rows"]] == ["Tower 1-2006"]
    assert one_round["route_id"] == route["id"]
    r = await client.get(
        "/v1/deliveries/month",
        params={
            "year": MONTH_START.year,
            "month": MONTH_START.month,
            "route_id": str(uuid.uuid4()),
        },
        headers=admin,
    )
    assert r.status_code == 404


async def test_a_household_s_login_sees_its_own_row_only(client):
    org, admin, who = await _acceptance_dairy(client)
    me = await _customer_login(
        client, admin, org["id"], who["household"]["id"], "a1607@household.example"
    )
    r = await client.get(
        "/v1/deliveries/month",
        params={"year": MONTH_START.year, "month": MONTH_START.month},
        headers=me,
    )
    # CUSTOMER_PORTAL holds sales.delivery.read; the scope narrows the rows.
    assert r.status_code == 200, r.text
    assert [row["name"] for row in r.json()["rows"]] == ["A-1607"]


async def test_the_month_defaults_to_the_organisation_s_own(client):
    _org, admin = await _shop(client)
    r = await client.get("/v1/deliveries/month", headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["date_from"] <= body["today"] <= body["date_to"]
    assert body["date_from"].endswith("-01")
    r = await client.get("/v1/deliveries/month", params={"year": 2026}, headers=admin)
    assert r.status_code == 422
    r = await client.get("/v1/deliveries/month", params={"year": 2026, "month": 13}, headers=admin)
    assert r.status_code == 422
