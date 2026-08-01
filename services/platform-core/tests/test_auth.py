from tests.conftest import register_and_login


async def test_register_login_me(client):
    _, headers = await register_and_login(client)
    r = await client.get("/v1/auth/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "user@example.com"
    assert body["tenant_id"] is None
    assert body["permissions"] == []  # no roles assigned yet


async def test_duplicate_registration_conflicts(client):
    await register_and_login(client)
    r = await client.post(
        "/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "correct-horse-battery",
            "full_name": "Dup",
        },
    )
    assert r.status_code == 409


async def test_wrong_password_is_401_problem_json(client):
    await register_and_login(client)
    r = await client.post(
        "/v1/auth/token", json={"email": "user@example.com", "password": "wrong-password-123"}
    )
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title"] == "invalid_credentials"


async def test_error_message_localized(client):
    await register_and_login(client)
    r = await client.post(
        "/v1/auth/token",
        json={"email": "user@example.com", "password": "wrong-password-123"},
        headers={"Accept-Language": "sw"},
    )
    assert r.json()["detail"] == "Barua pepe au nenosiri si sahihi."


async def test_refresh_rotates_tokens(client):
    await register_and_login(client)
    r = await client.post(
        "/v1/auth/token", json={"email": "user@example.com", "password": "correct-horse-battery"}
    )
    refresh_token = r.json()["refresh_token"]
    r2 = await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r2.status_code == 200
    assert r2.json()["access_token"]


async def test_protected_route_requires_token(client):
    r = await client.get("/v1/auth/me")
    assert r.status_code == 401
