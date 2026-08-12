from tests.conftest import register_and_login


async def test_permission_denied_without_role(client):
    _, headers = await register_and_login(client)
    r = await client.get("/v1/audit", headers=headers)
    assert r.status_code == 403


async def test_platform_admin_wildcard_grants_access(client):
    _, headers = await register_and_login(client, admin=True)
    r = await client.get("/v1/audit", headers=headers)
    assert r.status_code == 200
    actions = [rec["action"] for rec in r.json()["items"]]
    # Registration and login were audited.
    assert "identity.user.registered" in actions
    assert "auth.login.succeeded" in actions


async def test_role_creation_rejects_unknown_permission(client):
    _, headers = await register_and_login(client, admin=True)
    r = await client.post(
        "/v1/authz/roles",
        json={"name": "bad-role", "permission_keys": ["nonexistent.permission"]},
        headers=headers,
    )
    assert r.status_code == 409


async def test_custom_role_grants_specific_permission(client):
    _admin_id, admin_headers = await register_and_login(client, "admin@example.com", admin=True)
    user_id, user_headers = await register_and_login(client, "viewer@example.com")

    r = await client.post(
        "/v1/authz/roles",
        json={"name": "auditor", "permission_keys": ["audit.read"]},
        headers=admin_headers,
    )
    assert r.status_code == 201
    r = await client.post(
        "/v1/authz/assignments",
        json={"user_id": str(user_id), "role_name": "auditor"},
        headers=admin_headers,
    )
    assert r.status_code == 201

    assert (await client.get("/v1/audit", headers=user_headers)).status_code == 200
    # audit.read does not grant organization.manage
    r = await client.post(
        "/v1/organizations",
        json={"name": "X", "slug": "x-coop", "country_code": "ke"},
        headers=user_headers,
    )
    assert r.status_code == 403
