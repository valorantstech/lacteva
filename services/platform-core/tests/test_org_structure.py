"""Organization structure, membership, and invitation flows."""

import uuid

from tests.conftest import invite, register_and_login


async def _tenant_admin(client):
    """Platform admin creates an org; invites a tenant-admin; returns their auth."""
    _, admin_headers = await register_and_login(client, "root@example.com", admin=True)
    org = (
        await client.post(
            "/v1/organizations",
            json={"name": "Kilima Dairy Cooperative", "slug": "kilima", "country_code": "ke"},
            headers=admin_headers,
        )
    ).json()
    # Platform admin acts within the tenant via X-Tenant-ID (bootstrap path):
    _inv, inv_token = await invite(
        client,
        {**admin_headers, "X-Tenant-ID": org["id"]},
        email="manager@kilima.example",
        role_name="tenant-admin",
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
            "password": "manager-password-1",
            "full_name": "Kilima Manager",
        },
    )
    assert r.status_code == 201, r.text
    pair = (
        await client.post(
            "/v1/auth/token",
            json={
                "email": "manager@kilima.example",
                "password": "manager-password-1",
                "tenant_id": org["id"],
            },
        )
    ).json()
    return org, {"Authorization": f"Bearer {pair['access_token']}"}


async def test_invitation_grants_tenant_scoped_admin(client):
    org, headers = await _tenant_admin(client)
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["tenant_id"] == org["id"]
    assert "organization.structure.manage" in me["permissions"]
    members = (await client.get("/v1/members", headers=headers)).json()
    assert len(members) == 1 and members[0]["status"] == "active"


async def test_workspace_and_branch_lifecycle(client, bus):
    _, headers = await _tenant_admin(client)
    ws = (
        await client.post(
            "/v1/workspaces",
            json={"name": "Northern Region", "slug": "northern"},
            headers=headers,
        )
    ).json()
    r = await client.post(
        "/v1/workspaces", json={"name": "Dup", "slug": "northern"}, headers=headers
    )
    assert r.status_code == 409

    branch = (
        await client.post(
            "/v1/branches",
            json={"workspace_id": ws["id"], "name": "Kilima Hill Site", "code": "KH-01"},
            headers=headers,
        )
    ).json()
    assert branch["status"] == "active"
    # Unknown workspace → 404; duplicate code → 409.
    r = await client.post(
        "/v1/branches",
        json={"workspace_id": str(uuid.uuid4()), "name": "Nowhere", "code": "X-1"},
        headers=headers,
    )
    assert r.status_code == 404
    r = await client.post(
        "/v1/branches",
        json={"workspace_id": ws["id"], "name": "Other", "code": "KH-01"},
        headers=headers,
    )
    assert r.status_code == 409

    assert len((await client.get("/v1/workspaces", headers=headers)).json()) == 1
    assert len((await client.get("/v1/branches", headers=headers)).json()) == 1
    types = [e.type for e in bus.published]
    assert "organization.workspace-created.v1" in types
    assert "organization.branch-created.v1" in types


async def test_viewer_role_cannot_manage_structure(client):
    org, admin_headers = await _tenant_admin(client)
    _inv, inv_token = await invite(
        client,
        admin_headers,
        email="viewer@kilima.example",
        role_name="tenant-viewer",
    )
    await client.post(
        "/v1/invitations/accept",
        json={
            "token": inv_token,
            "password": "viewer-password-1",
            "full_name": "Viewer",
        },
    )
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
    assert (await client.get("/v1/workspaces", headers=viewer)).status_code == 200
    r = await client.post("/v1/workspaces", json={"name": "Nope", "slug": "nope"}, headers=viewer)
    assert r.status_code == 403


async def test_invitation_is_single_use_and_tenant_isolated(client):
    org, headers = await _tenant_admin(client)
    _inv, inv_token = await invite(
        client,
        headers,
        email="once@kilima.example",
        role_name="tenant-viewer",
    )
    body = {
        "token": inv_token,
        "password": "once-password-11",
        "full_name": "Once",
    }
    assert (await client.post("/v1/invitations/accept", json=body)).status_code == 201
    assert (await client.post("/v1/invitations/accept", json=body)).status_code == 400

    # DEMO-010 changed what happens when the tenant is NOT named, and this is
    # the assertion that changed with it.
    #
    # It used to be a 401: `get_by_email` matched on `tenant_id`, so an account
    # inside an organization was invisible unless the caller supplied that
    # organization's UUID — which is exactly what the portal's login form
    # asked a dairy owner to paste, first thing.
    #
    # Now the tenant is resolved from the credentials. The isolation this test
    # exists to defend is unchanged and is asserted more strongly than before:
    # the token that comes back is scoped to THIS tenant, not a platform
    # session, so the login is convenient without being broader.
    r = await client.post(
        "/v1/auth/token",
        json={"email": "once@kilima.example", "password": "once-password-11"},
    )
    assert r.status_code == 200, r.text
    resolved = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get("/v1/auth/me", headers=resolved)).json()
    assert me["tenant_id"] == org["id"]  # their own organization, not none

    # A wrong password is still refused, and says nothing about which
    # organizations the address belongs to.
    r = await client.post(
        "/v1/auth/token",
        json={"email": "once@kilima.example", "password": "not-the-password"},
    )
    assert r.status_code == 401
    assert "kilima" not in r.text.lower()

    # Naming the tenant explicitly still works, and lands in the same place.
    r = await client.post(
        "/v1/auth/token",
        json={
            "email": "once@kilima.example",
            "password": "once-password-11",
            "tenant_id": org["id"],
        },
    )
    assert r.status_code == 200
    named = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/v1/auth/me", headers=named)).json()["tenant_id"] == org["id"]


async def test_suspended_member_cannot_login(client):
    org, _headers = await _tenant_admin(client)
    # Suspend the manager directly (admin API for suspension is Sprint-003 scope).
    from sqlalchemy import update

    from platform_core.core.db import get_session_factory
    from platform_core.modules.organization.models import Membership

    async with get_session_factory()() as session:
        await session.execute(update(Membership).values(status="suspended"))
        await session.commit()
    r = await client.post(
        "/v1/auth/token",
        json={
            "email": "manager@kilima.example",
            "password": "manager-password-1",
            "tenant_id": org["id"],
        },
    )
    assert r.status_code == 401
