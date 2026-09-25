"""WO-94 / LACTEVA-TENANT-004 — every tenant could read every platform-level
notification.

Found on live while confirming the first real customer's invitation had
been delivered: listing notifications scoped to a tenant created four
minutes earlier returned its own row and three from August addressed to a
platform account. `NotificationService.search` matched
`tenant_id == mine OR tenant_id IS NULL`, and "no tenant" was read as
"everyone". Secrets did not leak (the stored body is redacted); other
people's addresses and message text did.

Tested from the TENANT's side, through the real routes:

  * a tenant-admin in organisation A sees none of organisation B's rows and
    none of the platform's — in the list, in the stats, by id, on retry;
  * a platform session still sees the platform's rows, and only those.
"""

import uuid

from tests.conftest import invite, register_and_login
from tests.test_org_structure import _tenant_admin


async def _second_org(client, *, name="Mara Dairy", slug="mara", root_email="root2@example.com"):
    """A second organisation with its own tenant-admin, via the real invitation flow."""
    _root_id, root = await register_and_login(client, root_email, admin=True)
    org = (
        await client.post(
            "/v1/organizations",
            json={"name": name, "slug": slug, "country_code": "ke"},
            headers=root,
        )
    ).json()
    _inv, token = await invite(
        client,
        {**root, "X-Tenant-ID": org["id"]},
        email=f"owner@{slug}.example",
        role_name="tenant-admin",
    )
    r = await client.post(
        "/v1/invitations/accept",
        json={"token": token, "password": f"{slug}-password-11", "full_name": "Owner"},
    )
    assert r.status_code == 201, r.text
    pair = await client.post(
        "/v1/auth/token",
        json={
            "email": f"owner@{slug}.example",
            "password": f"{slug}-password-11",
            "tenant_id": org["id"],
        },
    )
    return org, root, {"Authorization": f"Bearer {pair.json()['access_token']}"}


async def _platform_row(client, email="root@example.com"):
    """A notification with NO tenant: a password reset for a platform account
    is sent from the account's own (absent) tenant."""
    r = await client.post("/v1/auth/password-reset/request", json={"email": email})
    assert r.status_code == 202


def _recipients(page: dict) -> set[str]:
    return {row["recipient"] for row in page["items"]}


async def test_a_tenant_sees_only_its_own_rows(client):
    _org_a, admin_a = await _tenant_admin(client)  # invited manager@kilima.example
    _org_b, _root_b, admin_b = await _second_org(client)  # invited owner@mara.example
    await _platform_row(client)  # root@example.com, tenant NULL
    # One more row in each tenant, so both have something beyond bootstrap.
    await invite(client, admin_a, email="clerk@kilima.example", role_name="tenant-viewer")
    await invite(client, admin_b, email="clerk@mara.example", role_name="tenant-viewer")

    seen_a = (await client.get("/v1/notifications?limit=100", headers=admin_a)).json()
    seen_b = (await client.get("/v1/notifications?limit=100", headers=admin_b)).json()
    assert _recipients(seen_a) == {"manager@kilima.example", "clerk@kilima.example"}, seen_a
    assert _recipients(seen_b) == {"owner@mara.example", "clerk@mara.example"}, seen_b
    assert "root@example.com" not in _recipients(seen_a) | _recipients(seen_b)
    # The stats count the same rows the list shows — nothing else.
    stats_a = (await client.get("/v1/notifications/stats", headers=admin_a)).json()
    assert sum(stats_a["by_channel"].values()) == seen_a["total"] == 2


async def test_another_tenants_row_is_not_found_by_id_or_retry(client):
    _org_a, admin_a = await _tenant_admin(client)
    _org_b, _root_b, admin_b = await _second_org(client)
    theirs = (await client.get("/v1/notifications?limit=10", headers=admin_b)).json()["items"][0]
    assert (
        await client.get(f"/v1/notifications/{theirs['id']}", headers=admin_a)
    ).status_code == 404
    r = await client.post(f"/v1/notifications/{theirs['id']}/retry", headers=admin_a)
    assert r.status_code == 404, r.text
    # Their own row is still theirs.
    assert (
        await client.get(f"/v1/notifications/{theirs['id']}", headers=admin_b)
    ).status_code == 200
    assert (
        await client.get(f"/v1/notifications/{uuid.uuid4()}", headers=admin_a)
    ).status_code == 404


async def test_a_platform_session_sees_platform_rows_and_only_those(client):
    _org_a, admin_a = await _tenant_admin(client)  # bootstraps root@example.com as platform admin
    await _platform_row(client)
    root_pair = await client.post(
        "/v1/auth/token", json={"email": "root@example.com", "password": "correct-horse-battery"}
    )
    root = {"Authorization": f"Bearer {root_pair.json()['access_token']}"}
    page = (await client.get("/v1/notifications?limit=100", headers=root)).json()
    assert _recipients(page) == {"root@example.com"}, page
    assert all(row["tenant_id"] is None for row in page["items"] if "tenant_id" in row)
    # And the tenant-admin cannot see that platform row.
    assert "root@example.com" not in _recipients(
        (await client.get("/v1/notifications?limit=100", headers=admin_a)).json()
    )
