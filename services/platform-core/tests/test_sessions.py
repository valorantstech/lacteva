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


# --- D-26: thirty days from the LAST use (WO-79) -------------------------------


def _read_session_setting(text: str, key: str) -> str:
    for line in text.splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"{key} is not set in the example file")


def test_the_session_lifetime_is_thirty_days_everywhere_it_is_written():
    """Owner decision D-26 (2026-09-20): a session ends thirty days after its
    last use. The number is written in the platform default, both env
    examples and the portal's cookie; a drift between any two would mean the
    shorter wins and the longer is a lie."""
    from pathlib import Path

    from platform_core.core.config import Settings

    thirty_days = 30 * 24 * 3600
    assert Settings.model_fields["jwt_refresh_ttl_seconds"].default == thirty_days

    repo = Path(__file__).resolve().parents[3]
    for example in (".env.production.example", "services/platform-core/.env.example"):
        text = (repo / example).read_text()
        assert _read_session_setting(text, "LACTEVA_JWT_REFRESH_TTL_SECONDS") == str(thirty_days), (
            example
        )

    portal = (repo / "apps/admin-portal/src/lib/server/refresh.ts").read_text()
    assert "export const REFRESH_MAX_AGE = 30 * 24 * 60 * 60;" in portal

    # The access token is untouched: it limits the damage of a leaked token,
    # and nobody sees it expire.
    assert Settings.model_fields["jwt_access_ttl_seconds"].default == 900


async def test_a_session_slides_thirty_days_from_its_last_use(client):
    """Not thirty days from sign-in: every refresh restarts the month."""
    from datetime import UTC, datetime, timedelta

    import time_machine
    from sqlalchemy import select

    from platform_core.core import db
    from platform_core.core.db import as_utc
    from platform_core.modules.auth.models import AuthSession

    thirty_days = timedelta(days=30)

    async def expiries() -> list[datetime]:
        async with db.get_session_factory()() as session:
            rows = (await session.scalars(select(AuthSession))).all()
            return sorted(as_utc(row.expires_at) for row in rows)

    start = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
    with time_machine.travel(start, tick=False):
        await register_and_login(client)  # session one, never refreshed
        pair = await login(client)  # session two, refreshed below
        assert await expiries() == [start + thirty_days, start + thirty_days]

    # Ten days of use later, a refresh — and the month starts again from NOW,
    # not from the day the person signed in.
    later = start + timedelta(days=10)
    with time_machine.travel(later, tick=False):
        r = await client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        assert r.status_code == 200, r.text
    assert await expiries() == [start + thirty_days, later + thirty_days]

    # Thirty-one days of silence after that last use is the end of it: the
    # platform refuses the refresh, which is what signs both clients out.
    with time_machine.travel(later + timedelta(days=31), tick=False):
        rotated = r.json()["refresh_token"]
        r = await client.post("/v1/auth/refresh", json={"refresh_token": rotated})
        assert r.status_code == 401
