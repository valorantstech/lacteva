"""Rate Card Foundation: creation, validation, editing, assignments, search, authz."""

import uuid

from tests.conftest import invite, register_and_login
from tests.test_collection_centers import _center_fixture
from tests.test_org_structure import _tenant_admin

PRODUCT = "RAW-COW-MILK"


async def _create_card(client, headers, **overrides):
    body = {
        "name": "Standard Milk Rates",
        "currency": "KES",
        "effective_from": "2026-09-01",
        **overrides,
    }
    r = await client.post("/v1/rate-cards", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _assign_scope(client, headers, card_id, center_id, product=PRODUCT):
    r = await client.post(
        f"/v1/rate-cards/{card_id}/centers", json={"center_id": center_id}, headers=headers
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        f"/v1/rate-cards/{card_id}/products", json={"product_code": product}, headers=headers
    )
    assert r.status_code == 201, r.text


# --- creation ---------------------------------------------------------------


async def test_create_draft_defaults(client, bus):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers, currency="kes")
    assert card["status"] == "draft"
    assert card["version"] == 1
    assert card["code"].startswith("RC-")
    assert card["currency"] == "KES"  # normalized to ISO upper-case
    assert card["published_at"] is None and card["archived_at"] is None
    assert "pricing.rate-card-created.v1" in [e.type for e in bus.published]


async def test_create_with_explicit_code_and_duplicate_rejected(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers, code="MILK-2026")
    assert card["code"] == "MILK-2026"
    r = await client.post(
        "/v1/rate-cards",
        json={
            "name": "Duplicate",
            "currency": "KES",
            "effective_from": "2026-10-01",
            "code": "MILK-2026",
        },
        headers=headers,
    )
    assert r.status_code == 409


async def test_create_duplicate_code_case_insensitive(client):
    headers, _, _ = await _center_fixture(client)
    await _create_card(client, headers, code="milk-a")
    r = await client.post(
        "/v1/rate-cards",
        json={"name": "Dup", "currency": "KES", "effective_from": "2026-09-01", "code": "MILK-A"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_create_with_branch_and_unknown_branch(client):
    headers, branch, _ = await _center_fixture(client)
    card = await _create_card(client, headers, branch_id=branch["id"])
    assert card["branch_id"] == branch["id"]
    r = await client.post(
        "/v1/rate-cards",
        json={
            "name": "Orphan",
            "currency": "KES",
            "effective_from": "2026-09-01",
            "branch_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert r.status_code == 404


async def test_create_invalid_currency_rejected(client):
    headers, _, _ = await _center_fixture(client)
    for currency in ("K3S", "KESH", "K"):
        r = await client.post(
            "/v1/rate-cards",
            json={"name": "Bad Currency", "currency": currency, "effective_from": "2026-09-01"},
            headers=headers,
        )
        assert r.status_code == 422, currency


async def test_create_invalid_effective_range_rejected(client):
    headers, _, _ = await _center_fixture(client)
    for until in ("2026-09-01", "2026-08-31"):  # equal and before effective_from
        r = await client.post(
            "/v1/rate-cards",
            json={
                "name": "Bad Range",
                "currency": "KES",
                "effective_from": "2026-09-01",
                "effective_until": until,
            },
            headers=headers,
        )
        assert r.status_code == 422, until


async def test_create_open_ended_card(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers, effective_until=None)
    assert card["effective_until"] is None


# --- editing (drafts only) ---------------------------------------------------


async def test_update_draft_fields(client, bus):
    headers, branch, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    r = await client.put(
        f"/v1/rate-cards/{card['id']}",
        json={
            "name": "Premium Milk Rates",
            "description": "Season 2026/27",
            "currency": "usd",
            "effective_from": "2026-10-01",
            "effective_until": "2027-09-30",
            "branch_id": branch["id"],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["name"] == "Premium Milk Rates"
    assert updated["currency"] == "USD"
    assert updated["effective_until"] == "2027-09-30"
    assert updated["branch_id"] == branch["id"]
    assert "pricing.rate-card-updated.v1" in [e.type for e in bus.published]


async def test_update_requires_draft(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    r = await client.post(f"/v1/rate-cards/{card['id']}/submit", headers=headers)
    assert r.status_code == 200
    r = await client.put(
        f"/v1/rate-cards/{card['id']}",
        json={"name": "Too Late", "currency": "KES", "effective_from": "2026-09-01"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_update_validates_range(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    r = await client.put(
        f"/v1/rate-cards/{card['id']}",
        json={
            "name": "Bad Range",
            "currency": "KES",
            "effective_from": "2026-09-01",
            "effective_until": "2026-09-01",
        },
        headers=headers,
    )
    assert r.status_code == 422


async def test_update_unknown_branch(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    r = await client.put(
        f"/v1/rate-cards/{card['id']}",
        json={
            "name": "Orphan Branch",
            "currency": "KES",
            "effective_from": "2026-09-01",
            "branch_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert r.status_code == 404


async def test_detail_includes_scope_and_placeholder_rules(client):
    headers, _, center = await _center_fixture(client)
    card = await _create_card(client, headers)
    await _assign_scope(client, headers, card["id"], center["id"])
    detail = (await client.get(f"/v1/rate-cards/{card['id']}", headers=headers)).json()
    assert detail["card"]["id"] == card["id"]
    assert detail["center_ids"] == [center["id"]]
    assert detail["products"] == [{"product_code": PRODUCT, "product_name": ""}]
    assert detail["pricing_rules"] == []  # Increment-002 placeholder — must stay empty


# --- scope assignments -------------------------------------------------------


async def test_assign_center_duplicate_and_unknown(client):
    headers, _, center = await _center_fixture(client)
    card = await _create_card(client, headers)
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/centers", json={"center_id": center["id"]}, headers=headers
    )
    assert r.status_code == 201
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/centers", json={"center_id": center["id"]}, headers=headers
    )
    assert r.status_code == 409
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/centers",
        json={"center_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert r.status_code == 404


async def test_unassign_center(client):
    headers, _, center = await _center_fixture(client)
    card = await _create_card(client, headers)
    await _assign_scope(client, headers, card["id"], center["id"])
    r = await client.delete(f"/v1/rate-cards/{card['id']}/centers/{center['id']}", headers=headers)
    assert r.status_code == 204
    r = await client.delete(f"/v1/rate-cards/{card['id']}/centers/{center['id']}", headers=headers)
    assert r.status_code == 404
    detail = (await client.get(f"/v1/rate-cards/{card['id']}", headers=headers)).json()
    assert detail["center_ids"] == []


async def test_assign_product_normalized_and_duplicate(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/products",
        json={"product_code": "raw-cow-milk", "product_name": "Raw Cow Milk"},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["product_code"] == "RAW-COW-MILK"
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/products",
        json={"product_code": "RAW-COW-MILK"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_assign_product_invalid_code(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/products",
        json={"product_code": "!!bad code!!"},
        headers=headers,
    )
    assert r.status_code == 422


async def test_unassign_product(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    await client.post(
        f"/v1/rate-cards/{card['id']}/products", json={"product_code": PRODUCT}, headers=headers
    )
    r = await client.delete(f"/v1/rate-cards/{card['id']}/products/{PRODUCT}", headers=headers)
    assert r.status_code == 204
    r = await client.delete(f"/v1/rate-cards/{card['id']}/products/{PRODUCT}", headers=headers)
    assert r.status_code == 404


async def test_scope_locked_after_submission(client):
    headers, _, center = await _center_fixture(client)
    card = await _create_card(client, headers)
    await _assign_scope(client, headers, card["id"], center["id"])
    await client.post(f"/v1/rate-cards/{card['id']}/submit", headers=headers)
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/centers", json={"center_id": center["id"]}, headers=headers
    )
    assert r.status_code == 409
    r = await client.post(
        f"/v1/rate-cards/{card['id']}/products", json={"product_code": "GOAT-MILK"}, headers=headers
    )
    assert r.status_code == 409
    r = await client.delete(f"/v1/rate-cards/{card['id']}/centers/{center['id']}", headers=headers)
    assert r.status_code == 409


# --- review workflow ---------------------------------------------------------


async def test_submit_and_approve_workflow(client, bus):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    r = await client.post(f"/v1/rate-cards/{card['id']}/submit", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "under_review"
    r = await client.post(f"/v1/rate-cards/{card['id']}/approve", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    types = [e.type for e in bus.published]
    assert "pricing.rate-card-submitted.v1" in types
    assert "pricing.rate-card-approved.v1" in types


async def test_submit_requires_draft(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    await client.post(f"/v1/rate-cards/{card['id']}/submit", headers=headers)
    r = await client.post(f"/v1/rate-cards/{card['id']}/submit", headers=headers)
    assert r.status_code == 409


async def test_approve_requires_under_review(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)
    r = await client.post(f"/v1/rate-cards/{card['id']}/approve", headers=headers)
    assert r.status_code == 409  # still draft


# --- search ------------------------------------------------------------------


async def test_search_by_name_and_code(client):
    headers, _, _ = await _center_fixture(client)
    await _create_card(client, headers, code="MILK-STD", name="Standard Milk Rates")
    await _create_card(client, headers, code="GOAT-STD", name="Goat Premium")
    hits = (await client.get("/v1/rate-cards?q=goat", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["code"] == "GOAT-STD"
    hits = (await client.get("/v1/rate-cards?q=milk-std", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["name"] == "Standard Milk Rates"


async def test_filter_by_status_and_currency(client):
    headers, _, _ = await _center_fixture(client)
    await _create_card(client, headers, code="A-KES", currency="KES")
    usd = await _create_card(client, headers, code="B-USD", currency="USD")
    await client.post(f"/v1/rate-cards/{usd['id']}/submit", headers=headers)
    hits = (await client.get("/v1/rate-cards?status=under_review", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["code"] == "B-USD"
    hits = (await client.get("/v1/rate-cards?currency=usd", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["currency"] == "USD"


async def test_filter_by_center_and_product(client):
    headers, _, center = await _center_fixture(client)
    scoped = await _create_card(client, headers, code="SCOPED")
    await _create_card(client, headers, code="UNSCOPED")
    await _assign_scope(client, headers, scoped["id"], center["id"])
    hits = (await client.get(f"/v1/rate-cards?center_id={center['id']}", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["code"] == "SCOPED"
    hits = (await client.get(f"/v1/rate-cards?product_code={PRODUCT}", headers=headers)).json()
    assert hits["total"] == 1 and hits["items"][0]["code"] == "SCOPED"


async def test_pagination(client):
    headers, _, _ = await _center_fixture(client)
    for i in range(3):
        await _create_card(client, headers, code=f"PAGE-{i}")
    page = (await client.get("/v1/rate-cards?limit=2&offset=0", headers=headers)).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    page = (await client.get("/v1/rate-cards?limit=2&offset=2", headers=headers)).json()
    assert page["total"] == 3 and len(page["items"]) == 1


# --- authorization -----------------------------------------------------------


async def test_requires_authentication(client):
    r = await client.get("/v1/rate-cards")
    assert r.status_code == 401


async def test_viewer_reads_but_cannot_manage_or_approve(client):
    org, headers = await _tenant_admin(client)
    card = await _create_card(client, headers)
    _inv, inv_token = await invite(
        client,
        headers,
        email="viewer@kilima.example",
        role_name="tenant-viewer",
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
            "password": "viewer-password-1",
            "full_name": "Read Only",
        },
    )
    assert r.status_code == 201, r.text
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "viewer@kilima.example",
                "password": "viewer-password-1",
                "tenant_id": org["id"],
            },
        )
    ).json()
    viewer = {"Authorization": f"Bearer {pair['access_token']}"}

    r = await client.get("/v1/rate-cards", headers=viewer)
    assert r.status_code == 200 and r.json()["total"] == 1
    r = await client.post(
        "/v1/rate-cards",
        json={"name": "Nope", "currency": "KES", "effective_from": "2026-09-01"},
        headers=viewer,
    )
    assert r.status_code == 403
    r = await client.post(f"/v1/rate-cards/{card['id']}/approve", headers=viewer)
    assert r.status_code == 403


async def test_tenant_isolation(client):
    headers, _, _ = await _center_fixture(client)
    card = await _create_card(client, headers)

    # A second organization with its own tenant admin cannot see the card.
    _, root2 = await register_and_login(client, "root2@example.com", admin=True)
    org2 = (
        await client.post(
            "/v1/organizations",
            json={"name": "Rift Valley Dairy", "slug": "rift", "country_code": "ke"},
            headers=root2,
        )
    ).json()
    _inv, inv_token = await invite(
        client,
        {**root2, "X-Tenant-ID": org2["id"]},
        email="manager@rift.example",
        role_name="tenant-admin",
    )
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
            "password": "manager-password-2",
            "full_name": "Rift Manager",
        },
    )
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "manager@rift.example",
                "password": "manager-password-2",
                "tenant_id": org2["id"],
            },
        )
    ).json()
    other = {"Authorization": f"Bearer {pair['access_token']}"}
    r = await client.get(f"/v1/rate-cards/{card['id']}", headers=other)
    assert r.status_code == 404
    assert (await client.get("/v1/rate-cards", headers=other)).json()["total"] == 0
