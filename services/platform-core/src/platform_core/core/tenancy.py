"""Multi-tenancy context.

The tenant is carried in the access token (authoritative) or the X-Tenant-ID
header (fallback for unauthenticated/bootstrap flows). All tenant-scoped
repositories MUST filter by the current tenant.

TODO(M1): enforce tenant isolation in PostgreSQL with row-level security
(RLS) policies bound to a session variable, so isolation holds by
construction even if a query forgets a filter (per SRS template §4.5).
"""

import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_current_tenant: ContextVar[uuid.UUID | None] = ContextVar("current_tenant", default=None)


def get_current_tenant() -> uuid.UUID | None:
    return _current_tenant.get()


def set_current_tenant(tenant_id: uuid.UUID | None) -> None:
    _current_tenant.set(tenant_id)
    if tenant_id is not None:
        structlog.contextvars.bind_contextvars(tenant_id=str(tenant_id))


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Seed tenant context from X-Tenant-ID; auth overrides it from the token."""

    async def dispatch(self, request: Request, call_next):
        set_current_tenant(None)
        header = request.headers.get("X-Tenant-ID")
        if header:
            try:
                set_current_tenant(uuid.UUID(header))
            except ValueError:
                pass  # invalid header is ignored; auth layer decides access
        return await call_next(request)
