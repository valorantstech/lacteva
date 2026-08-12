"""Signing in without knowing your organization's UUID (DEMO-010).

The portal's login form asked for "Organization ID (tenant)" in a text box.
Nobody knows their tenant UUID, and it was the first thing on the first screen
of a customer demonstration.

The tenant is now resolved from the credentials. That reads like a loosening,
so the tests below are mostly about what did NOT loosen:

* a wrong password answers exactly as it always did, and says nothing about
  which organizations the address belongs to;
* the token issued is scoped to that user's own tenant, never platform-level;
* a member still cannot see another organization's rows;
* an inactive account is still refused;
* and when one password really does open accounts in two organizations, the
  caller is asked which — only AFTER proving the password, so nothing is
  revealed that trying each in turn would not have revealed anyway.
"""

import uuid

from tests.conftest import register_and_login
from tests.test_org_structure import _tenant_admin, invite


async def _member(client, admin_headers, org_id, email, password, role="tenant-viewer"):
    _inv, token = await invite(
        client, {**admin_headers, "X-Tenant-ID": org_id}, email=email, role_name=role
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": password, "full_name": "Demo Member"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _login(client, email, password, tenant_id=None):
    body = {"email": email, "password": password}
    if tenant_id:
        body["tenant_id"] = tenant_id
    return await client.post("/v1/auth/token", json=body)


async def _second_org(client, root_headers, name, slug):
    return (
        await client.post(
            "/v1/organizations",
            json={"name": name, "slug": slug, "country_code": "ke"},
            headers=root_headers,
        )
    ).json()


# --- the thing that changed ---------------------------------------------------


async def test_a_member_signs_in_with_an_email_and_a_password(client):
    org, admin = await _tenant_admin(client)
    await _member(client, admin, org["id"], "dairy.owner@kilima.example", "owner-password-1")

    r = await _login(client, "dairy.owner@kilima.example", "owner-password-1")
    assert r.status_code == 200, r.text

    me = (
        await client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
        )
    ).json()
    assert me["tenant_id"] == org["id"]


async def test_the_resolved_session_is_scoped_to_that_tenant_not_the_platform(client):
    """Convenience must not become breadth."""
    org, admin = await _tenant_admin(client)
    member = await _member(client, admin, org["id"], "scoped@kilima.example", "scoped-password-1")

    token = (await _login(client, "scoped@kilima.example", "scoped-password-1")).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}

    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["tenant_id"] == org["id"]
    assert me["tenant_id"] is not None

    # And they carry the grants of the role they were invited with, not more:
    # a viewer resolved this way still may not administer a user.
    r = await client.post(
        f"/v1/identity/users/{member['id']}/status",
        json={"is_active": False},
        headers=headers,
    )
    assert r.status_code == 403


# --- what did not change ------------------------------------------------------


async def test_a_wrong_password_answers_exactly_as_before(client):
    org, admin = await _tenant_admin(client)
    await _member(client, admin, org["id"], "known@kilima.example", "known-password-1")

    wrong = await _login(client, "known@kilima.example", "not-the-password")
    unknown = await _login(client, "nobody@nowhere.example", "not-the-password")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["title"] == unknown.json()["title"] == "invalid_credentials"
    # No oracle: the failure must not name the organization, its slug or its id.
    for body in (wrong.text.lower(), unknown.text.lower()):
        assert "kilima" not in body
        assert org["id"] not in body


async def test_an_inactive_account_is_still_refused(client):
    org, admin = await _tenant_admin(client)
    member = await _member(client, admin, org["id"], "leaver@kilima.example", "leaver-password-1")
    r = await client.post(
        f"/v1/identity/users/{member['id']}/status",
        json={"is_active": False},
        headers={**admin, "X-Tenant-ID": org["id"]},
    )
    assert r.status_code == 200, r.text

    assert (await _login(client, "leaver@kilima.example", "leaver-password-1")).status_code == 401


async def test_a_resolved_login_still_cannot_read_another_organization(client):
    org, admin = await _tenant_admin(client)
    await _member(client, admin, org["id"], "ours@kilima.example", "ours-password-11")

    from tests.test_payments import _second_tenant

    other = await _second_tenant(client)
    their_suppliers = (await client.get("/v1/suppliers?limit=100", headers=other)).json()

    token = (await _login(client, "ours@kilima.example", "ours-password-11")).json()["access_token"]
    ours = {"Authorization": f"Bearer {token}"}
    mine = (await client.get("/v1/suppliers?limit=100", headers=ours)).json()
    assert not {s["id"] for s in mine.get("items", [])} & {
        s["id"] for s in their_suppliers.get("items", [])
    }


async def test_naming_the_tenant_explicitly_still_works(client):
    """The old call shape is unchanged — integrations do not have to move."""
    org, admin = await _tenant_admin(client)
    await _member(client, admin, org["id"], "explicit@kilima.example", "explicit-pass-1")

    r = await _login(client, "explicit@kilima.example", "explicit-pass-1", org["id"])
    assert r.status_code == 200
    me = (
        await client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
        )
    ).json()
    assert me["tenant_id"] == org["id"]


async def test_naming_a_tenant_you_do_not_belong_to_is_still_refused(client):
    org, admin = await _tenant_admin(client)
    await _member(client, admin, org["id"], "elsewhere@kilima.example", "elsewhere-pass-1")

    r = await _login(
        client, "elsewhere@kilima.example", "elsewhere-pass-1", str(uuid.UUID(int=0xDEAD))
    )
    assert r.status_code == 401


async def test_a_platform_administrator_still_signs_in_with_no_tenant(client):
    """Their account belongs to no organization; that path is untouched."""
    _uid, headers = await register_and_login(client, "root@example.com", admin=True)
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["tenant_id"] is None


# --- the ambiguous case -------------------------------------------------------


async def test_one_password_opening_two_organizations_asks_which(client):
    """Only reachable AFTER the password verifies, so it reveals nothing."""
    org_a, admin = await _tenant_admin(client)
    _uid, root = await register_and_login(client, "root2@example.com", admin=True)
    org_b = await _second_org(client, root, "Rift Valley Dairy", "rift-two")

    shared = "shared-password-123"
    await _member(client, admin, org_a["id"], "both@dairy.example", shared)
    await _member(client, root, org_b["id"], "both@dairy.example", shared)

    r = await _login(client, "both@dairy.example", shared)
    assert r.status_code == 401
    assert r.json()["title"] == "ambiguous_tenant"

    # And naming one resolves it.
    r = await _login(client, "both@dairy.example", shared, org_a["id"])
    assert r.status_code == 200
    me = (
        await client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
        )
    ).json()
    assert me["tenant_id"] == org_a["id"]


async def test_the_ambiguous_answer_is_unreachable_without_the_password(client):
    """The distinguishing response must cost a correct password."""
    org_a, admin = await _tenant_admin(client)
    _uid, root = await register_and_login(client, "root2@example.com", admin=True)
    org_b = await _second_org(client, root, "Rift Valley Dairy", "rift-two")

    shared = "shared-password-123"
    await _member(client, admin, org_a["id"], "both@dairy.example", shared)
    await _member(client, root, org_b["id"], "both@dairy.example", shared)

    r = await _login(client, "both@dairy.example", "wrong-password-entirely")
    assert r.status_code == 401
    assert r.json()["title"] == "invalid_credentials"
    assert org_a["id"] not in r.text and org_b["id"] not in r.text
