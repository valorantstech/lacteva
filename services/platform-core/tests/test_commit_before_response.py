"""The platform must not answer a write before it has committed it (E2E-001).

Found by executing, not by reading. The real client↔server harness kept seeing
a row created moments earlier reported "not found" by the very next request —
across supplier, device, branch, workspace and user alike. Row-level security
was innocent: the row genuinely did not exist yet. `get_session` committed in
FastAPI's dependency teardown, and because the middleware stack is built on
`BaseHTTPMiddleware` — whose `call_next` returns as soon as the response
*starts* — the answer reached the client 0.3-1.1 ms BEFORE the commit.

The read-your-writes break is the visible half. The dangerous half is that a
commit failing after the response is gone cannot change it: the platform would
have reported 201 for a write that never happened.

These tests watch the ASGI `send` channel rather than the client, because a
test client waits for the whole app to finish and would show the ordering as
correct however wrong it is. The assertion is therefore on the server's own
sequence: the commit must be recorded before the response body goes out.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.api.idempotent_route import IdempotentRoute
from platform_core.api.transactional_route import TransactionalRoute
from platform_core.main import create_app


class _Recorder:
    """The order in which the server did things, from inside the server."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def wrap_app(self, app):
        async def spy(scope, receive, send):
            async def _send(message):
                if message["type"] == "http.response.body" and not message.get("more_body"):
                    self.events.append("response-sent")
                await send(message)

            await app(scope, receive, _send)

        return spy

    def patch_commit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original = AsyncSession.commit

        async def recording_commit(self):  # the patched method, self is a session
            await original(self)
            _RECORDER.events.append("commit")

        monkeypatch.setattr(AsyncSession, "commit", recording_commit)


_RECORDER = _Recorder()


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    _RECORDER.events = []
    _RECORDER.patch_commit(monkeypatch)
    return _RECORDER


@pytest.mark.asyncio
async def test_write_is_committed_before_the_response_is_sent(app, recorder: _Recorder) -> None:
    """The defect itself: a 201 that preceded its own commit."""
    transport = ASGITransport(app=recorder.wrap_app(app))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": "commit-order@example.com",
                "password": "correct-horse-battery-1",
                "full_name": "Commit Order",
            },
        )

    assert response.status_code == 201
    assert "commit" in recorder.events, "the write was never committed"
    assert "response-sent" in recorder.events
    assert recorder.events.index("commit") < recorder.events.index("response-sent"), (
        f"the response went out before the commit: {recorder.events}"
    )


@pytest.mark.asyncio
async def test_the_row_is_readable_by_the_very_next_request(app, recorder: _Recorder) -> None:
    """What a real client does: act immediately on its own answer.

    This is the harness's failure reduced to two requests — register, then sign
    in as the person just registered. It failed intermittently against real
    PostgreSQL and could not fail at all in-process, which is precisely why the
    ordering assertion above exists alongside it.
    """
    transport = ASGITransport(app=recorder.wrap_app(app))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/v1/auth/register",
            json={
                "email": "read-your-writes@example.com",
                "password": "correct-horse-battery-1",
                "full_name": "Read Your Writes",
            },
        )
        assert created.status_code == 201

        signed_in = await client.post(
            "/v1/auth/token",
            json={"email": "read-your-writes@example.com", "password": "correct-horse-battery-1"},
        )

    assert signed_in.status_code == 200, signed_in.text


def test_every_mutating_route_commits_inside_the_handler() -> None:
    """The guard that keeps this fixed.

    A route class is easy to forget on a new router, and forgetting it
    reintroduces exactly this defect — silently, because the write still
    usually lands in time. So the rule is asserted over the built application
    rather than trusted to review: anything that can write commits inside its
    own handler.
    """
    app = create_app()
    mutating = {"POST", "PUT", "PATCH", "DELETE"}
    offenders = [
        (route.path, sorted(route.methods & mutating))
        for route in app.routes
        if getattr(route, "methods", None)
        and route.methods & mutating
        and not isinstance(route, IdempotentRoute | TransactionalRoute)
    ]
    assert offenders == [], (
        "these routes can write but do not commit inside the handler, so their "
        f"answer can precede their write: {offenders}"
    )
