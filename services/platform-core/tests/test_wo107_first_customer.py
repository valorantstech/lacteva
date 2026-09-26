"""A new shop can add its first customer (WO-107 · LACTEVA-SALES-005).

The owner, walking the rehearsal shop as its owner: "where is the option to
add cow milk or buffalo milk etc.. do we need to add those in products?" —
and the New customer form, which hard-coded the demo seed's product code, was
refused by the platform in every organisation but the demo's.

What this proves, on the platform, in a FRESH sales-only organisation with no
manual product set-up: Buffalo milk at 0.5 L and ₹56 is a standing order; a
second standing order of Cow milk on the same customer stands beside it; both
deliver and both bill; a customer of type "Temple" and a product sold per
"packet" work end to end; codes are generated from names; a plan that names
no product takes the organisation's first milk product; and a custom unit
never enters the D-21 measured-versus-traded conversion.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from platform_core.core import units
from tests.clock import reference_date
from tests.conftest import invite, register_and_login

TODAY = reference_date()
MONTH_START = TODAY.replace(day=1)
MONTH_END = (MONTH_START + timedelta(days=32)).replace(day=1) - timedelta(days=1)


async def _fresh_shop(client, *, slug="patel", name="Patel Dairy Shop and Sweets"):
    """A sales-only organisation exactly as onboarding leaves it — no product
    added by hand — and its owner's auth."""
    _, root = await register_and_login(client, f"root-{slug}@example.com", admin=True)
    r = await client.post(
        "/v1/organizations",
        json={"name": name, "slug": slug, "country_code": "in", "modules": ["sales"]},
        headers=root,
    )
    assert r.status_code == 201, r.text
    org = r.json()
    _inv, token = await invite(
        client,
        {**root, "X-Tenant-ID": org["id"]},
        email=f"owner-{slug}@example.com",
        role_name="tenant-admin",
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "owner-password-11", "full_name": "Sarwari Patel"},
    )
    assert r.status_code == 201, r.text
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": f"owner-{slug}@example.com",
                "password": "owner-password-11",
                "tenant_id": org["id"],
            },
        )
    ).json()
    return org, {"Authorization": f"Bearer {pair['access_token']}"}


async def _products(client, owner):
    return {p["code"]: p for p in (await client.get("/v1/products", headers=owner)).json()["items"]}


async def test_a_fresh_shop_starts_with_cow_and_buffalo_milk_beside_other(client):
    _org, owner = await _fresh_shop(client)
    codes = await _products(client, owner)
    assert set(codes) == {"COW-MILK", "BUFFALO-MILK", "OTHER"}
    for code, name in (("COW-MILK", "Cow milk"), ("BUFFALO-MILK", "Buffalo milk")):
        assert codes[code]["name"] == name
        assert codes[code]["unit"] == "L"
        assert codes[code]["default_price"] is None, "unpriced: the owner sets prices"
        assert codes[code]["currency"] == "INR"
    # The owner may rename, price or deactivate them like any product.
    r = await client.patch(
        f"/v1/products/{codes['BUFFALO-MILK']['id']}",
        json={"default_price": "56.00", "name": "Buffalo milk (full cream)"},
        headers=owner,
    )
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["default_price"]) == Decimal("56.00")


async def test_the_first_customer_takes_buffalo_milk_and_then_cow_milk_too(client):
    """The acceptance: no product set-up, Buffalo milk at 0.5 L and ₹56, a
    second standing order of Cow milk on the same customer, both deliver,
    both bill."""
    _org, owner = await _fresh_shop(client)
    r = await client.post(
        "/v1/customers",
        json={
            "name": "Flat C-1603",
            "customer_type": "household",
            "plan": {"product": "BUFFALO-MILK", "default_quantity": "0.500", "unit_price": "56.00"},
        },
        headers=owner,
    )
    assert r.status_code == 201, r.text
    customer = r.json()
    # The unit came from the PRODUCT, not from a form saying "L".
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=owner)).json()
    assert [(p["product"], p["quantity_unit"]) for p in detail["plans"]] == [("BUFFALO-MILK", "L")]

    # "Add another standing order": cow milk beside the buffalo, not instead of it.
    r = await client.post(
        f"/v1/customers/{customer['id']}/plan",
        json={"product": "COW-MILK", "default_quantity": "1.000", "unit_price": "48.00"},
        headers=owner,
    )
    assert r.status_code == 201, r.text
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=owner)).json()
    active = sorted((p["product"], p["default_quantity"]) for p in detail["plans"] if p["active"])
    assert [(p, Decimal(q)) for p, q in active] == [
        ("BUFFALO-MILK", Decimal("0.500")),
        ("COW-MILK", Decimal("1.000")),
    ]

    # Both deliver — the generator writes a row per standing order …
    r = await client.post(
        "/v1/deliveries/generate", json={"for_date": TODAY.isoformat()}, headers=owner
    )
    assert r.status_code in (200, 201), r.text
    rows = (
        await client.get(
            "/v1/deliveries",
            params={"date_from": TODAY.isoformat(), "date_to": TODAY.isoformat(), "limit": 50},
            headers=owner,
        )
    ).json()["items"]
    mine = sorted((d["product"], d["quantity"]) for d in rows if d["customer_id"] == customer["id"])
    assert [(p, Decimal(q)) for p, q in mine] == [
        ("BUFFALO-MILK", Decimal("0.500")),
        ("COW-MILK", Decimal("1.000")),
    ]
    # The delivery boy confirms both rows delivered (a scheduled row is not
    # yet a bill line) …
    for product in ("BUFFALO-MILK", "COW-MILK"):
        r = await client.post(
            "/v1/deliveries",
            json={
                "customer_id": customer["id"],
                "delivery_date": TODAY.isoformat(),
                "product": product,
                "status": "delivered",
            },
            headers=owner,
        )
        assert r.status_code == 201, r.text
    # … and both bill: one invoice, a line per product, priced from each plan.
    r = await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer["id"],
            "period_from": MONTH_START.isoformat(),
            "period_to": MONTH_END.isoformat(),
        },
        headers=owner,
    )
    assert r.status_code == 201, r.text
    invoice = (await client.get(f"/v1/invoices/{r.json()['id']}", headers=owner)).json()
    lines = {line["product"]: line for line in invoice["lines"]}
    assert set(lines) >= {"BUFFALO-MILK", "COW-MILK"}
    assert Decimal(lines["BUFFALO-MILK"]["amount"]) == Decimal("28.00")
    assert Decimal(lines["COW-MILK"]["amount"]) == Decimal("48.00")


async def test_a_plan_that_names_no_product_takes_the_first_milk_product(client):
    """The platform's own default was the demo's code, one layer below the
    form. Now: the organisation's first milk product by catalogue order —
    Cow milk — and a refusal that says what to do when there is none."""
    _org, owner = await _fresh_shop(client)
    r = await client.post(
        "/v1/customers",
        json={"name": "Corner Shop", "plan": {"default_quantity": "2.000", "unit_price": "50.00"}},
        headers=owner,
    )
    assert r.status_code == 201, r.text
    detail = (await client.get(f"/v1/customers/{r.json()['id']}", headers=owner)).json()
    assert detail["plans"][0]["product"] == "COW-MILK"
    assert detail["plans"][0]["quantity_unit"] == "L"
    # Retire both milks and the default has nothing to point at — said, not guessed.
    codes = await _products(client, owner)
    for code in ("COW-MILK", "BUFFALO-MILK"):
        r = await client.patch(
            f"/v1/products/{codes[code]['id']}", json={"active": False}, headers=owner
        )
        assert r.status_code == 200, r.text
    r = await client.post(
        "/v1/customers",
        json={"name": "Lost Shop", "plan": {"default_quantity": "1.000", "unit_price": "50.00"}},
        headers=owner,
    )
    assert r.status_code == 422, r.text
    assert "add your milk products first" in r.text


async def test_a_delivery_without_a_product_takes_the_one_plan_and_refuses_to_guess_between_two(
    client,
):
    _org, owner = await _fresh_shop(client)
    one = (
        await client.post(
            "/v1/customers",
            json={
                "name": "One Order",
                "plan": {"product": "COW-MILK", "default_quantity": "1", "unit_price": "50"},
            },
            headers=owner,
        )
    ).json()
    r = await client.post(
        "/v1/deliveries",
        json={"customer_id": one["id"], "delivery_date": TODAY.isoformat(), "status": "delivered"},
        headers=owner,
    )
    assert r.status_code == 201, r.text
    assert r.json()["product"] == "COW-MILK"
    two = (
        await client.post(
            "/v1/customers",
            json={
                "name": "Two Orders",
                "plan": {"product": "COW-MILK", "default_quantity": "1", "unit_price": "50"},
            },
            headers=owner,
        )
    ).json()
    await client.post(
        f"/v1/customers/{two['id']}/plan",
        json={"product": "BUFFALO-MILK", "default_quantity": "1", "unit_price": "56"},
        headers=owner,
    )
    r = await client.post(
        "/v1/deliveries",
        json={"customer_id": two["id"], "delivery_date": TODAY.isoformat(), "status": "delivered"},
        headers=owner,
    )
    assert r.status_code == 422, r.text
    assert "BUFFALO-MILK" in r.text and "COW-MILK" in r.text


async def test_a_customer_type_is_the_owners_own_word(client):
    _org, owner = await _fresh_shop(client)
    r = await client.post(
        "/v1/customers",
        json={
            "name": "Shri Ganesh Mandir",
            "customer_type": "  Temple ",
            "plan": {"product": "COW-MILK", "default_quantity": "5", "unit_price": "50"},
        },
        headers=owner,
    )
    assert r.status_code == 201, r.text
    assert r.json()["customer_type"] == "Temple"
    # A suggestion typed in any case is the suggestion.
    r = await client.post(
        "/v1/customers", json={"name": "Hotel Annapurna", "customer_type": "HOTEL"}, headers=owner
    )
    assert r.status_code == 201 and r.json()["customer_type"] == "hotel"
    # The filter lists the types in use — the owner's word among them.
    assert (await client.get("/v1/customers/types", headers=owner)).json() == ["Temple", "hotel"]
    page = (
        await client.get("/v1/customers", params={"customer_type": "Temple"}, headers=owner)
    ).json()
    assert [c["name"] for c in page["items"]] == ["Shri Ganesh Mandir"]
    # Too short or too long is not a type.
    for bad in ("x", "y" * 41):
        r = await client.post(
            "/v1/customers", json={"name": "Bad", "customer_type": bad}, headers=owner
        )
        assert r.status_code == 422, bad


async def test_a_product_sold_per_packet_works_end_to_end_and_its_code_is_generated(client):
    _org, owner = await _fresh_shop(client)
    r = await client.post(
        "/v1/products",
        json={"name": "Paneer 200 g", "unit": "packet", "default_price": "90"},
        headers=owner,
    )
    assert r.status_code == 201, r.text
    paneer = r.json()
    assert paneer["code"] == "PANEER-200-G" and paneer["unit"] == "packet"
    # The same name again gets the next free code, not a refusal.
    r = await client.post(
        "/v1/products", json={"name": "Paneer 200 g", "unit": "packet"}, headers=owner
    )
    assert r.status_code == 201 and r.json()["code"] == "PANEER-200-G-2"
    # A caller who cares still names the code — and a clash is still a clash.
    r = await client.post(
        "/v1/products", json={"code": "paneer 200 g", "name": "Paneer"}, headers=owner
    )
    assert r.status_code == 409
    # A standing order in packets: the unit follows the product.
    customer = (
        await client.post(
            "/v1/customers",
            json={
                "name": "Sweet Tooth",
                "plan": {"product": "PANEER-200-G", "default_quantity": "2", "unit_price": "90"},
            },
            headers=owner,
        )
    ).json()
    detail = (await client.get(f"/v1/customers/{customer['id']}", headers=owner)).json()
    assert detail["plans"][0]["quantity_unit"] == "packet"
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": customer["id"],
            "delivery_date": TODAY.isoformat(),
            "product": "PANEER-200-G",
        },
        headers=owner,
    )
    assert r.status_code == 201, r.text
    assert r.json()["quantity_unit"] == "packet" and Decimal(r.json()["amount"]) == Decimal(
        "180.00"
    )
    r = await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer["id"],
            "period_from": MONTH_START.isoformat(),
            "period_to": MONTH_END.isoformat(),
        },
        headers=owner,
    )
    assert r.status_code == 201, r.text
    invoice = (await client.get(f"/v1/invoices/{r.json()['id']}", headers=owner)).json()
    line = next(line for line in invoice["lines"] if line["product"] == "PANEER-200-G")
    assert line["quantity_unit"] == "packet"
    # Unit labels have limits: empty and over 12 characters are refused.
    for bad in ("", "a" * 13, "bo<x>"):
        r = await client.post("/v1/products", json={"name": "Bad", "unit": bad}, headers=owner)
        assert r.status_code == 422, bad


async def test_routes_and_drivers_get_their_codes_from_their_names(client):
    _org, owner = await _fresh_shop(client)
    r = await client.post("/v1/routes", json={"name": "Morning round"}, headers=owner)
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "MORNING-ROUND"
    r = await client.post("/v1/routes", json={"name": "Morning round"}, headers=owner)
    assert r.status_code == 201 and r.json()["code"] == "MORNING-ROUND-2"
    r = await client.post("/v1/drivers", json={"full_name": "Ramesh Pawar"}, headers=owner)
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "RAMESH-PAWAR"
    # Still editable for those who care.
    r = await client.post(
        "/v1/drivers", json={"code": "DRV-7", "full_name": "Suresh"}, headers=owner
    )
    assert r.status_code == 201 and r.json()["code"] == "DRV-7"


def test_only_litres_and_kilograms_take_part_in_the_measured_versus_traded_conversion():
    """WO-107 §5: a custom product unit is a label on the sales side. The
    D-21 conversion is the COLLECTION side's, reads the organisation's
    intake unit, and knows exactly two units. `packet` is not one of them —
    and never will be by accident, because this is what it says."""
    assert units.UNITS == ("litre", "kg")
    assert units.normalise_unit("L") == "litre" and units.normalise_unit("kgs") == "kg"
    for label in ("packet", "pc", "dozen", "250 g"):
        with pytest.raises(ValueError):
            units.normalise_unit(label)


async def test_a_custom_unit_is_refused_as_the_organisations_intake_unit(client):
    """The other half of the same rule, at the API: the organisation's
    measured unit — the one the conversion reads — takes litres or kg only."""
    _org, owner = await _fresh_shop(client)
    r = await client.put(
        "/v1/organizations/settings/locale", json={"quantity_unit": "packet"}, headers=owner
    )
    assert r.status_code == 422, r.text
