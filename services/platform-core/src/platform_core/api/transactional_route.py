"""The route class that commits before answering (E2E-001).

Most routers already carry `IdempotentRoute`, which now commits at the end of
its own wrapper. This is the same guarantee for the handful of routers that do
not need idempotency: the request's transaction is committed inside the route
handler, before the response can reach anyone.

Why a route class rather than the session dependency: FastAPI runs dependency
teardown outside the handler, and with a `BaseHTTPMiddleware` stack the
response has already started by then. A route class runs while the response is
still ours to change, which is exactly the property the commit needs.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute

from platform_core.core.db import commit_request_session


class TransactionalRoute(APIRoute):
    """Commits the request's transaction before the response is returned."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            response = await original(request)
            # Only on the way out with a response in hand: a raising handler
            # has nothing to commit, and `get_session` rolls it back.
            await commit_request_session()
            return response

        return handler
