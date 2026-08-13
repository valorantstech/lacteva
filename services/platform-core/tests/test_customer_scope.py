"""A customer login sees its own rows and no others (DEMO-012).

The mobile customer experience needs a login that belongs to ONE household.
Tenancy cannot express that: every `sales.*` permission is tenant-wide, so a
household granted `sales.invoice.read` so it can read its own bill would read
every other household's bill in the same dairy.

That makes this file the security boundary for the whole customer app, and it
is written accordingly — the interesting tests are the ones where a customer
asks for somebody else's data by name, by id, and by omission.

Two rules are asserted repeatedly:

**Not found, never forbidden.** 403 confirms the row exists, and "there is a
customer with this id" is exactly what one household must not learn about
another.

**Staff are unaffected.** The scope is NULL on every existing account and only
ever removes rows, so a scope that fails to apply cannot widen access.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from tests.test_org_structure import _tenant_admin

TODAY = date(2026, 8, 12)


async def _customer(client, admin, name, rate="60.0000"):
    r = await client.post(
        "/v1/customers",
        json={
            "name": name,
            "customer_type": "household",
            "plan": {
                "product": "RAW-COW-MILK",
                "default_quantity": "2.000",
                "quantity_unit": "L",
                "unit_price": rate,
            },
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _deliver(client, admin, customer_id, days=3):
    total = Decimal("0.00")
    for offset in range(days):
        r = await client.post(
            "/v1/deliveries",
            json={
                "customer_id": customer_id,
                "delivery_date": str(TODAY - timedelta(days=offset)),
                "slot": "morning",
                "status": "delivered",
            },
            headers=admin,
        )
        assert r.status_code == 201, r.text
        total += Decimal(r.json()["amount"])
    return total


async def _bill(client, admin, customer_id, days=3):
    r = await client.post(
        "/v1/invoices",
        json={
            "customer_id": customer_id,
            "period_from": str(TODAY - timedelta(days=days - 1)),
            "period_to": str(TODAY),
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    invoice = r.json()
    r = await client.post(f"/v1/invoices/{invoice['id']}/issue", json={}, headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


async def _customer_login(client, admin, org_id, customer_id, email):
    """A CUSTOMER_PORTAL account bound to one customer.

    The binding is written to the account, never supplied by the client —
    there is deliberately no request field for it.
    """
    from tests.test_org_structure import invite

    _inv, token = await invite(
        client, {**admin, "X-Tenant-ID": org_id}, email=email, role_name="CUSTOMER_PORTAL"
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "household-password-1", "full_name": "Household"},
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]

    # Bind the account to the customer. Done directly because there is no API
    # that lets anyone — including an administrator — change a scope from a
    # request body; see DEMO-012-FINAL.md §Known limitations.
    from platform_core.core.rls import platform_factory
    from platform_core.modules.identity.models import User

    async with platform_factory("test: bind a customer login")() as session:
        user = await session.get(User, uuid.UUID(user_id))
        user.customer_id = uuid.UUID(customer_id)
        await session.commit()

    r = await client.post(
        "/v1/auth/token", json={"email": email, "password": "household-password-1"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _two_households(client):
    org, admin = await _tenant_admin(client)
    mine = await _customer(client, admin, "My Household")
    theirs = await _customer(client, admin, "Their Household", rate="70.0000")
    my_worth = await _deliver(client, admin, mine["id"])
    their_worth = await _deliver(client, admin, theirs["id"])
    my_bill = await _bill(client, admin, mine["id"])
    their_bill = await _bill(client, admin, theirs["id"])
    me = await _customer_login(client, admin, org["id"], mine["id"], "mine@household.example")
    return {
        "admin": admin,
        "me": me,
        "mine": mine,
        "theirs": theirs,
        "my_worth": my_worth,
        "their_worth": their_worth,
        "my_bill": my_bill,
        "their_bill": their_bill,
    }


# --- what a customer CAN see --------------------------------------------------


async def test_a_customer_sees_its_own_deliveries(client):
    w = await _two_households(client)
    page = (await client.get("/v1/deliveries?limit=50", headers=w["me"])).json()
    assert page["total"] == 3
    assert {d["customer_id"] for d in page["items"]} == {w["mine"]["id"]}


async def test_a_customer_sees_its_own_bill(client):
    w = await _two_households(client)
    page = (await client.get("/v1/invoices?limit=50", headers=w["me"])).json()
    assert page["total"] == 1
    assert page["items"][0]["invoice_number"] == w["my_bill"]["invoice_number"]

    detail = (await client.get(f"/v1/invoices/{w['my_bill']['id']}", headers=w["me"])).json()
    assert detail["totals_match_lines"] is True


async def test_a_customer_sees_its_own_balance(client):
    w = await _two_households(client)
    balance = (await client.get(f"/v1/customers/{w['mine']['id']}/balance", headers=w["me"])).json()
    assert Decimal(balance["invoiced"]) == w["my_worth"]


async def test_the_customer_list_holds_exactly_one_customer(client):
    """Their own. Not "all customers", and not an empty list either."""
    w = await _two_households(client)
    page = (await client.get("/v1/customers?limit=50", headers=w["me"])).json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == w["mine"]["id"]


# --- what a customer CANNOT see -----------------------------------------------


async def test_another_households_deliveries_are_invisible(client):
    w = await _two_households(client)
    page = (
        await client.get(
            f"/v1/deliveries?customer_id={w['theirs']['id']}&limit=50", headers=w["me"]
        )
    ).json()
    # Asking for somebody else by name returns nothing of theirs — never their
    # rows, and never a hint that the customer exists.
    assert page.get("total", 0) == 0 or all(
        d["customer_id"] == w["mine"]["id"] for d in page.get("items", [])
    )


async def test_another_households_bill_is_NOT_FOUND_not_forbidden(client):
    w = await _two_households(client)
    r = await client.get(f"/v1/invoices/{w['their_bill']['id']}", headers=w["me"])
    assert r.status_code == 404, (
        "a customer must not be able to distinguish another household's bill "
        f"from one that does not exist (got {r.status_code})"
    )


async def test_another_households_record_is_NOT_FOUND(client):
    w = await _two_households(client)
    r = await client.get(f"/v1/customers/{w['theirs']['id']}", headers=w["me"])
    assert r.status_code == 404


async def test_another_households_balance_is_NOT_FOUND(client):
    w = await _two_households(client)
    r = await client.get(f"/v1/customers/{w['theirs']['id']}/balance", headers=w["me"])
    assert r.status_code == 404


async def test_a_customer_cannot_record_anything(client):
    """Read is the entire surface. A household records no deliveries and takes
    no payments — the dairy does both."""
    w = await _two_households(client)
    r = await client.post(
        "/v1/deliveries",
        json={
            "customer_id": w["mine"]["id"],
            "delivery_date": str(TODAY),
            "slot": "evening",
            "status": "delivered",
        },
        headers=w["me"],
    )
    assert r.status_code == 403
    r = await client.post(
        "/v1/customer-payments",
        json={"customer_id": w["mine"]["id"], "amount": "1.00", "method": "CASH"},
        headers=w["me"],
    )
    assert r.status_code == 403


async def test_a_customer_cannot_see_the_procurement_side(client):
    """Suppliers, settlements and payments to farmers are none of a
    household's business, and the role grants none of them."""
    w = await _two_households(client)
    for path in ("/v1/suppliers?limit=1", "/v1/settlements?limit=1", "/v1/payments?limit=1"):
        r = await client.get(path, headers=w["me"])
        assert r.status_code == 403, f"{path} answered {r.status_code}"


# --- the scope cannot be asked for --------------------------------------------


async def test_the_scope_comes_from_the_account_not_the_request(client):
    """There is no header, claim or parameter that changes it."""
    w = await _two_households(client)
    # Try the two things a client could plausibly send.
    r = await client.get(
        "/v1/deliveries?limit=50",
        headers={**w["me"], "X-Customer-ID": w["theirs"]["id"]},
    )
    assert r.status_code == 200
    assert all(d["customer_id"] == w["mine"]["id"] for d in r.json().get("items", []))

    r = await client.get(
        f"/v1/customers/{w['theirs']['id']}",
        headers={**w["me"], "X-Tenant-ID": str(uuid.UUID(int=0xDEAD))},
    )
    assert r.status_code == 404


# --- staff are unaffected -----------------------------------------------------


async def test_staff_still_see_every_customer(client):
    """The narrowing must be invisible to everyone it does not apply to."""
    w = await _two_households(client)
    page = (await client.get("/v1/customers?limit=50", headers=w["admin"])).json()
    assert page["total"] == 2

    deliveries = (await client.get("/v1/deliveries?limit=50", headers=w["admin"])).json()
    assert deliveries["total"] == 6

    invoices = (await client.get("/v1/invoices?limit=50", headers=w["admin"])).json()
    assert invoices["total"] == 2

    r = await client.get(f"/v1/invoices/{w['their_bill']['id']}", headers=w["admin"])
    assert r.status_code == 200
