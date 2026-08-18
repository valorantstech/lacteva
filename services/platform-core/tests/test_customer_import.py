"""The outlet list, loaded in one request (P0-PILOT-002).

The pilot dairy hands over a list of B2B outlets with their standing orders.
`POST /v1/customers/import` takes it the way `/suppliers/import` takes the
farmer list: rows validated individually, one bad row yields a per-row error
and never fails the batch, and every created outlet is indistinguishable from
a hand-entered one — numbered from the CUS- series, priced through its inline
plan, audited.
"""

from tests.test_org_structure import _tenant_admin


def _row(name: str, *, quantity: str = "20", price: str = "58.00") -> dict:
    return {
        "name": name,
        "customer_type": "shop",
        "phone": "+91 98450 00111",
        "address": "Shop 4, APMC Road",
        "plan": {
            "product": "RAW-COW-MILK",
            "default_quantity": quantity,
            "quantity_unit": "L",
            "unit_price": price,
        },
    }


async def test_the_outlet_list_arrives_with_its_standing_orders(client):
    _, admin = await _tenant_admin(client)
    rows = [
        _row("Sharma General Stores"),
        _row("Hotel Annapurna", quantity="45", price="56.50"),
        _row("Café Madhuban", quantity="12"),
    ]

    r = await client.post("/v1/customers/import", json={"rows": rows}, headers=admin)
    assert r.status_code == 200, r.text
    results = r.json()
    assert [x["status"] for x in results] == ["created"] * 3
    assert all(x["code"].startswith("CUS-") for x in results)

    # Each outlet is a full customer: numbered, planned, listable.
    detail = (await client.get(f"/v1/customers/{results[1]['customer_id']}", headers=admin)).json()
    assert detail["customer"]["name"] == "Hotel Annapurna"
    assert len(detail["plans"]) == 1
    from decimal import Decimal

    assert Decimal(str(detail["plans"][0]["default_quantity"])) == Decimal("45")

    page = (await client.get("/v1/customers", headers=admin)).json()
    assert page["total"] == 3


async def test_one_bad_row_fails_alone_never_the_batch(client):
    _, admin = await _tenant_admin(client)
    rows = [
        _row("Good Outlet One"),
        {"customer_type": "shop"},  # no name — invalid on its own
        _row("Good Outlet Two"),
    ]

    r = await client.post("/v1/customers/import", json={"rows": rows}, headers=admin)
    assert r.status_code == 200, r.text
    results = r.json()
    assert [x["status"] for x in results] == ["created", "error", "created"]
    assert results[1]["error"]
    assert results[1]["customer_id"] is None

    page = (await client.get("/v1/customers", headers=admin)).json()
    assert page["total"] == 2, "the bad row must not have taken the good ones down"


async def test_the_import_has_a_ceiling(client):
    _, admin = await _tenant_admin(client)
    r = await client.post(
        "/v1/customers/import",
        json={"rows": [_row(f"Outlet {i}") for i in range(501)]},
        headers=admin,
    )
    assert r.status_code == 409, r.text


async def test_the_import_needs_the_manage_permission(client):
    r = await client.post("/v1/customers/import", json={"rows": []})
    assert r.status_code == 401
