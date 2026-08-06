"""Test fixtures: in-memory SQLite + in-memory event bus, no infrastructure needed."""

import os

# Must be set before any platform_core import (settings are cached).
os.environ["LACTEVA_ENV"] = "test"
os.environ["LACTEVA_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["LACTEVA_EVENT_BUS"] = "memory"
os.environ["LACTEVA_OUTBOX_MODE"] = "inline"
os.environ["LACTEVA_JWT_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"
# SEC-001: tests run the in-process rate limiter (no Redis) and reset it
# between tests, so a limit is only ever exercised by the test that asks for
# one — otherwise 600+ logins would exhaust the login budget.
os.environ["LACTEVA_RATE_LIMIT_BACKEND"] = "memory"

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from platform_core.core import db
from platform_core.infrastructure import events
from platform_core.main import create_app


@pytest.fixture(autouse=True)
def _reset_health_snapshot():
    """DEP-001: readiness answers from the last full health evaluation, which
    is process-global state. Any test that evaluates health would otherwise
    change what a later readiness test sees — so each test starts from the
    same place: no sample yet."""
    from platform_core.core import health

    health._last = None
    yield
    health._last = None


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """A fresh limiter per test: budgets must not leak between tests."""
    from platform_core.core import rate_limit

    rate_limit.set_rate_limiter(rate_limit.MemoryRateLimiter())
    yield
    rate_limit.set_rate_limiter(None)


@pytest.fixture
async def app():
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application
    await db.reset_engine()
    events.reset_event_bus()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def bus() -> events.InMemoryEventBus:
    b = events.get_event_bus()
    assert isinstance(b, events.InMemoryEventBus)
    return b


async def count_statements(coro_factory, *, selects_only: bool = True) -> tuple:
    """Run an awaitable and count the SQL statements it issues.

    Shared query-budget helper (PLT-001 engineering review: this was copied
    in three test modules). Returns (result, statement_count).
    """
    from sqlalchemy import event as sa_event

    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        if not selects_only or statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = db.get_engine().sync_engine
    sa_event.listen(engine, "before_cursor_execute", _record)
    try:
        result = await coro_factory()
    finally:
        sa_event.remove(engine, "before_cursor_execute", _record)
    return result, len(statements)


async def grant_platform_admin(user_id: uuid.UUID) -> None:
    """Directly assign the platform-admin system role (bootstrap stand-in)."""
    from platform_core.modules.authz.service import AuthzService

    async with db.get_session_factory()() as session:
        await AuthzService(session).assign_role(
            user_id=user_id, role_name="platform-admin", tenant_id=None
        )
        await session.commit()


async def register_and_login(
    client: AsyncClient, email: str = "user@example.com", *, admin: bool = False
) -> tuple[uuid.UUID, dict[str, str]]:
    """Returns (user_id, auth headers)."""
    r = await client.post(
        "/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Test User"},
    )
    assert r.status_code == 201, r.text
    user_id = uuid.UUID(r.json()["id"])
    if admin:
        await grant_platform_admin(user_id)
    r = await client.post(
        "/v1/auth/token", json={"email": email, "password": "correct-horse-battery"}
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}
