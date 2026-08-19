"""Batch display-name resolution and the 100-row ceiling (P1-PORTAL-SCALE-001).

The P0-PRODUCT-008 audit found the portal prefetching the first 100 suppliers
and rendering UUID fragments for everybody past that. The fix is an `ids`
filter on the directory searches, so a page resolves exactly the rows it
shows in one request. Two properties matter:

1. `ids` is a NARROWING — it composes with the tenant filter (and the
   customer scope), so a foreign tenant's id resolves to nothing rather than
   to somebody else's farmer.
2. The directory itself has no 100-row ceiling: the cap is a PAGE size, and
   page two exists.
"""

import uuid

from tests.conftest import invite, register_and_login


async def _org_admin(client, admin_headers, *, name: str, slug: str, email: str):
    org = (
        await client.post(
            "/v1/organizations",
            json={"name": name, "slug": slug, "country_code": "in"},
            headers=admin_headers,
        )
    ).json()
    _inv, token = await invite(
        client,
        {**admin_headers, "X-Tenant-ID": org["id"]},
        email=email,
        role_name="tenant-admin",
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "manager-password-1", "full_name": "Manager"},
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/v1/auth/token",
        json={"email": email, "password": "manager-password-1", "tenant_id": org["id"]},
    )
    assert r.status_code == 200, r.text
    return org, {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _two_tenants(client):
    _, root = await register_and_login(client, "root@example.com", admin=True)
    _a_org, a = await _org_admin(
        client, root, name="Anand Dairy", slug="anand", email="a@anand.example"
    )
    _b_org, b = await _org_admin(
        client, root, name="Baroda Dairy", slug="baroda", email="b@baroda.example"
    )
    return a, b


async def _supplier(client, headers, name: str) -> str:
    r = await client.post(
        "/v1/suppliers",
        json={"full_name": name, "phone": f"+91{uuid.uuid4().int % 10**10:010d}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_ids_returns_exactly_the_named_rows(client):
    a, _b = await _two_tenants(client)
    ids = [await _supplier(client, a, f"Farmer {i}") for i in range(5)]
    wanted = [ids[1], ids[3]]

    r = await client.get(
        "/v1/suppliers", params=[("ids", wanted[0]), ("ids", wanted[1])], headers=a
    )
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["total"] == 2
    assert sorted(item["id"] for item in page["items"]) == sorted(wanted)

    # `ids` composes with the other filters instead of replacing them.
    r = await client.get(
        "/v1/suppliers",
        params=[("ids", wanted[0]), ("ids", wanted[1]), ("q", "Farmer 3")],
        headers=a,
    )
    assert [item["id"] for item in r.json()["items"]] == [ids[3]]


async def test_a_foreign_tenants_id_resolves_to_nothing(client):
    a, b = await _two_tenants(client)
    a_id = await _supplier(client, a, "Anand Farmer")
    b_id = await _supplier(client, b, "Baroda Farmer")

    # Tenant A asks for its own id and tenant B's in one request: it gets
    # exactly its own row back. No error, no leak — the foreign id is simply
    # not a row in A's world (the tenant filter narrows first).
    r = await client.get("/v1/suppliers", params=[("ids", a_id), ("ids", b_id)], headers=a)
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["total"] == 1
    assert [item["id"] for item in page["items"]] == [a_id]

    # And the customers twin behaves the same way.
    rows = [
        {
            "name": name,
            "customer_type": "shop",
            "phone": f"+91{uuid.uuid4().int % 10**10:010d}",
            "address": "MG Road",
        }
        for name in ("Sharma Stores", "Patel Stores")
    ]
    made = (await client.post("/v1/customers/import", json={"rows": rows}, headers=a)).json()
    a_cus = made[0]["customer_id"]
    b_rows = [
        {
            "name": "Baroda Shop",
            "customer_type": "shop",
            "phone": f"+91{uuid.uuid4().int % 10**10:010d}",
            "address": "Station Road",
        }
    ]
    b_made = (await client.post("/v1/customers/import", json={"rows": b_rows}, headers=b)).json()
    b_cus = b_made[0]["customer_id"]

    r = await client.get("/v1/customers", params=[("ids", a_cus), ("ids", b_cus)], headers=a)
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["total"] == 1
    assert [item["id"] for item in page["items"]] == [a_cus]


async def test_the_directory_has_pages_not_a_ceiling(client):
    """120 farmers: page one is full at the cap, page two holds the rest, and
    a search finds farmer #117 without either page."""
    a, _b = await _two_tenants(client)
    for i in range(120):
        await _supplier(client, a, f"Milk Producer {i:03d}")

    first = (
        await client.get("/v1/suppliers", params={"limit": 100, "offset": 0}, headers=a)
    ).json()
    assert first["total"] == 120
    assert len(first["items"]) == 100

    second = (
        await client.get("/v1/suppliers", params={"limit": 100, "offset": 100}, headers=a)
    ).json()
    assert second["total"] == 120
    assert len(second["items"]) == 20
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}

    found = (await client.get("/v1/suppliers", params={"q": "Producer 117"}, headers=a)).json()
    assert found["total"] == 1
    assert found["items"][0]["full_name"] == "Milk Producer 117"
