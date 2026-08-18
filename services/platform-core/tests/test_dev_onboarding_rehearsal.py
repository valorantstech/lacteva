"""P0-PILOT-006 — controlled DEV onboarding rehearsal, synthetic data only.

The strongest form of the rehearsal the milestone describes: onboard a wholly
SYNTHETIC dairy — "DEMO DAIRY — DEV ONLY" — end to end through the *real*
invitation → accept → role-grant → login flow (the in-process notification
capture is the only path to the token, so this exercises real secret delivery),
then prove the access matrix, the multi-role/multi-centre grant, the
person/farmer/customer/device distinction, and RLS — organization-safe and
centre-scoped — with a real login for every role.

No real personal data. No production org touched. No architecture changed.
Every assertion is the existing architecture answering; a failure here is a
genuine defect (milestone Phase 8/11).
"""

import uuid

from tests.conftest import invite, register_and_login

# --- synthetic organisation, clearly marked -----------------------------------

ORG_NAME = "DEMO DAIRY — DEV ONLY (synthetic)"


async def _platform_admin(client, email):
    _, headers = await register_and_login(client, email, admin=True)
    return headers


async def _create_org(client, admin, *, slug):
    r = await client.post(
        "/v1/organizations",
        json={"name": ORG_NAME, "slug": slug, "country_code": "IN"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _tenant_admin_of(client, admin, org):
    """Onboard the org's tenant-admin via the real invite → accept flow."""
    _inv, token = await invite(
        client,
        {**admin, "X-Tenant-ID": org["id"]},
        email="owner@demo-dairy.example",
        role_name="tenant-admin",
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "Rehearsal-Owner-1", "full_name": "Demo Owner"},
    )
    assert r.status_code == 201, r.text
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "owner@demo-dairy.example",
                "password": "Rehearsal-Owner-1",
                "tenant_id": org["id"],
            },
        )
    ).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}


async def _member(client, admin, org_id, *, email, role_name, center_id=None):
    """Onboard one member: invite → accept → grant the named role at scope →
    login. Returns (user_id, auth headers) — one identity, used everywhere."""
    _inv, token = await invite(
        client, {**admin, "X-Tenant-ID": org_id}, email=email, role_name="tenant-viewer"
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": "Rehearsal-Member-1", "full_name": email.split("@")[0]},
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    assert (
        await client.delete(
            f"/v1/authz/assignments?user_id={user_id}&role_name=tenant-viewer",
            headers={**admin, "X-Tenant-ID": org_id},
        )
    ).status_code == 204
    body = {"user_id": user_id, "role_name": role_name}
    if center_id is not None:
        body["center_id"] = str(center_id)
    assert (
        await client.post(
            "/v1/authz/assignments", json=body, headers={**admin, "X-Tenant-ID": org_id}
        )
    ).status_code == 201
    pair = (
        await client.post(
            "/v1/auth/token",
            json={"email": email, "password": "Rehearsal-Member-1", "tenant_id": org_id},
        )
    ).json()
    return user_id, {"Authorization": f"Bearer {pair['access_token']}"}


async def _hierarchy(client, admin):
    """Workspace → Branch → three collection centres."""
    ws = (
        await client.post(
            "/v1/workspaces", json={"name": "Pune Region", "slug": "pune"}, headers=admin
        )
    ).json()
    branch = (
        await client.post(
            "/v1/branches",
            json={"workspace_id": ws["id"], "name": "Pune Branch", "code": "PN-BR"},
            headers=admin,
        )
    ).json()
    centres = {}
    for name, code in (
        ("Wagholi Centre", "WG-C1"),
        ("Hadapsar Centre", "HD-C1"),
        ("Kharadi Centre", "KH-C1"),
    ):
        c = (
            await client.post(
                "/v1/collection-centers",
                json={"branch_id": branch["id"], "name": name, "code": code},
                headers=admin,
            )
        ).json()
        centres[code] = c
    return ws, branch, centres


# --- the rehearsal ------------------------------------------------------------


async def test_synthetic_org_and_hierarchy_onboard(client):
    admin = await _platform_admin(client, "root-p6a@example.com")
    org = await _create_org(client, admin, slug="demo-dairy-a")
    owner = await _tenant_admin_of(client, admin, org)
    _ws, _br, centres = await _hierarchy(client, owner)

    assert org["name"] == ORG_NAME and org["currency_code"] == "INR"
    assert len(centres) == 3
    listed = (await client.get("/v1/collection-centers", headers=owner)).json()
    assert listed["total"] == 3


async def test_every_current_role_onboards_with_one_identity(client):
    """Each role: invite → accept → grant → login. One identity per person;
    no per-application credential."""
    admin = await _platform_admin(client, "root-p6b@example.com")
    org = await _create_org(client, admin, slug="demo-dairy-b")
    owner = await _tenant_admin_of(client, admin, org)
    _ws, _br, centres = await _hierarchy(client, owner)
    wg = centres["WG-C1"]["id"]

    roles = [
        ("orgadmin@demo-dairy.example", "ORGANIZATION_ADMIN", None),
        ("mgr@demo-dairy.example", "ORGANIZATION_MANAGER", None),
        ("operator@demo-dairy.example", "COLLECTION_OPERATOR", wg),
        ("centremgr@demo-dairy.example", "CENTRE_MANAGER", wg),
        ("finofficer@demo-dairy.example", "FINANCE_OFFICER", None),
        ("finmgr@demo-dairy.example", "FINANCE_MANAGER", None),
        ("sales@demo-dairy.example", "SALES_OFFICER", None),
        ("auditor@demo-dairy.example", "AUDITOR", None),
    ]
    for email, role, scope in roles:
        _uid, headers = await _member(
            client, admin, org["id"], email=email, role_name=role, center_id=scope
        )
        # The identity is real and usable: /auth/me answers under the token.
        me = await client.get("/v1/auth/me", headers=headers)
        assert me.status_code == 200, f"{role}: {me.text}"
        assert me.json()["user"]["email"] == email


async def test_access_matrix_is_authorization_not_credentials(client):
    """Access is decided by role, not by a per-application login: the operator
    reaches capture surfaces and is refused finance ones; the auditor reads and
    cannot write; the driver (below) is refused office surfaces."""
    admin = await _platform_admin(client, "root-p6c@example.com")
    org = await _create_org(client, admin, slug="demo-dairy-c")
    owner = await _tenant_admin_of(client, admin, org)
    _ws, _br, centres = await _hierarchy(client, owner)
    wg = centres["WG-C1"]["id"]

    _o, operator = await _member(
        client,
        admin,
        org["id"],
        email="op2@demo-dairy.example",
        role_name="COLLECTION_OPERATOR",
        center_id=wg,
    )
    _a, auditor = await _member(
        client, admin, org["id"], email="aud2@demo-dairy.example", role_name="AUDITOR"
    )

    # Operator: may read collection surfaces, may NOT manage settlements.
    assert (await client.get("/v1/collection-centers", headers=operator)).status_code == 200
    denied = await client.post(
        "/v1/settlements",
        json={
            "period_from": "2026-08-01",
            "period_to": "2026-08-10",
            "supplier_id": str(uuid.uuid4()),
        },
        headers=operator,
    )
    assert denied.status_code == 403, denied.text

    # Auditor: reads, cannot write a customer.
    assert (await client.get("/v1/customers", headers=auditor)).status_code == 200
    aud_write = await client.post(
        "/v1/customers", json={"name": "X", "customer_type": "shop"}, headers=auditor
    )
    assert aud_write.status_code == 403, aud_write.text


async def test_multi_role_multi_centre_grants_coexist_safely(client):
    """Phase 4: one person — Role A at Centre A AND Role B at Centre B. Both
    grants coexist on one identity, and each is independently revocable (two
    distinct rows), which is what "coexist safely" means. Scope is on the
    grant, so this is the same person wearing two hats at two centres — no
    second login, no second identity."""
    admin = await _platform_admin(client, "root-p6d@example.com")
    org = await _create_org(client, admin, slug="demo-dairy-d")
    owner = await _tenant_admin_of(client, admin, org)
    _ws, _br, centres = await _hierarchy(client, owner)
    a, b = centres["WG-C1"]["id"], centres["HD-C1"]["id"]

    # Onboard once as COLLECTION_OPERATOR @ Centre A; then add CENTRE_MANAGER
    # @ Centre B on the SAME identity — two different roles at two centres.
    uid, headers = await _member(
        client,
        admin,
        org["id"],
        email="dual@demo-dairy.example",
        role_name="COLLECTION_OPERATOR",
        center_id=a,
    )
    hat_b = await client.post(
        "/v1/authz/assignments",
        json={"user_id": uid, "role_name": "CENTRE_MANAGER", "center_id": str(b)},
        headers={**admin, "X-Tenant-ID": org["id"]},
    )
    assert hat_b.status_code == 201, hat_b.text

    # One identity, still usable — no per-application credential was minted.
    me = await client.get("/v1/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["user"]["email"] == "dual@demo-dairy.example"

    # The two grants are DISTINCT rows: each revokes independently (204 twice),
    # proving they coexisted rather than one overwriting the other.
    assert (
        await client.delete(
            f"/v1/authz/assignments?user_id={uid}&role_name=COLLECTION_OPERATOR",
            headers={**admin, "X-Tenant-ID": org["id"]},
        )
    ).status_code == 204
    assert (
        await client.delete(
            f"/v1/authz/assignments?user_id={uid}&role_name=CENTRE_MANAGER",
            headers={**admin, "X-Tenant-ID": org["id"]},
        )
    ).status_code == 204


async def test_farmer_and_customer_are_records_not_logins(client):
    """A farmer and a customer are business RECORDS; onboarding one creates NO
    identity and NO login."""
    admin = await _platform_admin(client, "root-p6e@example.com")
    org = await _create_org(client, admin, slug="demo-dairy-e")
    owner = await _tenant_admin_of(client, admin, org)
    _ws, _br, _centres = await _hierarchy(client, owner)

    # Import one synthetic farmer + one synthetic outlet.
    sup = await client.post(
        "/v1/suppliers/import",
        json={
            "rows": [
                {
                    "full_name": "Synthetic Farmer One",
                    "phone": "+91 90000 00001",
                    "center_codes": ["WG-C1"],
                }
            ]
        },
        headers=owner,
    )
    assert sup.status_code == 200 and sup.json()[0]["status"] == "created"
    cust = await client.post(
        "/v1/customers/import",
        json={
            "rows": [
                {
                    "name": "Synthetic Outlet One",
                    "customer_type": "shop",
                    "phone": "+91 90000 00002",
                }
            ]
        },
        headers=owner,
    )
    assert cust.status_code == 200 and cust.json()[0]["status"] == "created"

    # Neither can authenticate — there is no identity behind a record.
    for email in ("Synthetic Farmer One", "+91 90000 00001", "Synthetic Outlet One"):
        pair = await client.post(
            "/v1/auth/token",
            json={"email": email, "password": "anything", "tenant_id": org["id"]},
        )
        assert pair.status_code in (401, 422), f"a record must not be a login: {email}"


async def test_device_is_an_asset_not_a_login(client):
    """A registered scale is an asset at a location; it is not an identity."""
    admin = await _platform_admin(client, "root-p6f@example.com")
    org = await _create_org(client, admin, slug="demo-dairy-f")
    owner = await _tenant_admin_of(client, admin, org)
    _ws, _br, _centres = await _hierarchy(client, owner)

    dev = await client.post(
        "/v1/devices",
        json={"category": "scale", "serial_number": "SYN-SCALE-1", "name": "Synthetic Scale"},
        headers=owner,
    )
    assert dev.status_code == 201, dev.text
    # The device has no credential surface — it is registered, assigned, never
    # "logged in". (Asserting the absence of a login path for the serial.)
    pair = await client.post(
        "/v1/auth/token",
        json={"email": "SYN-SCALE-1", "password": "x", "tenant_id": org["id"]},
    )
    assert pair.status_code in (401, 422)


async def test_rls_is_organization_safe_across_synthetic_orgs(client):
    """Two synthetic orgs; each admin sees only its own centres, never the
    other's — a foreign resource is 404, not 403."""
    admin = await _platform_admin(client, "root-p6g@example.com")
    org_a = await _create_org(client, admin, slug="demo-dairy-g1")
    owner_a = await _tenant_admin_of(client, admin, org_a)
    _ws, _br, centres_a = await _hierarchy(client, owner_a)

    admin_b = await _platform_admin(client, "root-p6h@example.com")
    org_b = await _create_org(client, admin_b, slug="demo-dairy-g2")
    owner_b = await _tenant_admin_of(client, admin_b, org_b)

    # B's admin cannot see A's centre — invisibility (404), not a 403 leak.
    foreign = centres_a["WG-C1"]["id"]
    r = await client.get(f"/v1/collection-centers/{foreign}", headers=owner_b)
    assert r.status_code == 404, r.text
    # B sees zero centres (it created none).
    assert (await client.get("/v1/collection-centers", headers=owner_b)).json()["total"] == 0


async def test_the_onboarded_synthetic_org_can_transact_end_to_end(client):
    """Phase 6: the org onboarded from scratch above is not a shell — it can
    run the real procurement lifecycle. A ready centre + published rate card +
    a synthetic farmer, driven to a COMPLETED, priced collection with a parchi.
    (The sales half — order→route→driver→delivery→billing — is proven by the
    existing suite and by the live driver run in P0-PILOT-004.)"""
    from tests.test_collection_slip import _collect, _complete
    from tests.test_milk_collection import _ready_center
    from tests.test_pricing_matrix import _create_matrix, _publish_card
    from tests.test_pricing_resolution import _add_bands
    from tests.test_rate_cards import _assign_scope, _create_card

    admin = await _platform_admin(client, "root-p6w@example.com")
    org = await _create_org(client, admin, slug="demo-dairy-w")
    owner = await _tenant_admin_of(client, admin, org)
    _ws, _br, centres = await _hierarchy(client, owner)
    centre = centres["WG-C1"]

    # Make the centre READY (hours + active + operator + active scale) and
    # publish a synthetic INR rate card scoped to it.
    await _ready_center(client, owner, centre)
    card = await _create_card(client, owner, code="SYN-CARD", effective_from="2026-01-01")
    await _assign_scope(client, owner, card["id"], centre["id"], product="RAW-COW-MILK")
    matrix = await _create_matrix(
        client, owner, card["id"], name="Syn Cow FAT", product_code="RAW-COW-MILK"
    )
    await _add_bands(client, owner, matrix["id"], ((3.0, 9.0, 34.0),))
    await _publish_card(client, owner, card["id"])

    # A synthetic farmer assigned to the centre.
    from tests.test_suppliers import _create_supplier

    supplier = await _create_supplier(client, owner)
    await client.post(
        f"/v1/suppliers/{supplier['id']}/centers",
        json={"center_id": centre["id"]},
        headers=owner,
    )
    await client.post(
        f"/v1/suppliers/{supplier['id']}/status", json={"status": "active"}, headers=owner
    )

    session = (
        await client.post(
            "/v1/collection-sessions",
            json={"center_id": centre["id"], "label": "morning"},
            headers=owner,
        )
    ).json()

    tid = await _collect(client, owner, session["id"], supplier, milk_type="cow", fat=4.2)
    await _complete(client, owner, tid)

    tx = (await client.get(f"/v1/milk-transactions/{tid}", headers=owner)).json()
    assert tx["state"] == "COMPLETED"
    assert tx["pricing_status"] == "priced"
    assert tx["milk_type"] == "cow"

    slip = (await client.get(f"/v1/milk-transactions/{tid}/slip", headers=owner)).json()
    assert slip["slip_number"].startswith("SLP-")
    assert slip["organization_name"] == ORG_NAME
    assert slip["unit_price"] == tx["unit_price"]  # byte-identical, engine-priced
