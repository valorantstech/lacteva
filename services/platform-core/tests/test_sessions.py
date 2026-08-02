"""Session lifecycle: rotation, reuse detection, logout."""

from tests.conftest import register_and_login


async def login(client, email="user@example.com", password="correct-horse-battery"):
    r = await client.post("/v1/auth/token", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


async def test_refresh_rotates_and_old_token_dies(client):
    await register_and_login(client)
    pair = await login(client)
    r = await client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 200
    rotated = r.json()
    assert rotated["refresh_token"] != pair["refresh_token"]

    # Reusing the pre-rotation token is a theft signal: 401 AND the session dies,
    # so even the rotated (legitimate) token stops working.
    r = await client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 401
    r = await client.post("/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert r.status_code == 401


async def test_logout_kills_access_and_refresh(client):
    await register_and_login(client)
    pair = await login(client)
    headers = {"Authorization": f"Bearer {pair['access_token']}"}
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 200

    assert (await client.post("/v1/auth/logout", headers=headers)).status_code == 204
    # Access token dies with the session, refresh token too.
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 401
    r = await client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 401


async def test_sessions_are_independent(client):
    await register_and_login(client)
    first, second = await login(client), await login(client)
    h1 = {"Authorization": f"Bearer {first['access_token']}"}
    assert (await client.post("/v1/auth/logout", headers=h1)).status_code == 204
    # Logging out one session leaves the other alive.
    h2 = {"Authorization": f"Bearer {second['access_token']}"}
    assert (await client.get("/v1/auth/me", headers=h2)).status_code == 200


async def test_garbage_refresh_token_is_401(client):
    r = await client.post("/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert r.status_code == 401
