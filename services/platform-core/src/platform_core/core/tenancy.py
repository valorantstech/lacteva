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


def require_current_tenant() -> uuid.UUID:
    """The tenant demanded: raises ForbiddenError outside tenant context.
    Single source for the guard every tenant-scoped service needs
    (SPRINT-008B engineering review: was copied in 11 services)."""
    from platform_core.core.errors import ForbiddenError

    tenant_id = get_current_tenant()
    if tenant_id is None:
        raise ForbiddenError("tenant context required")
    return tenant_id


def get_current_tenant() -> uuid.UUID | None:
    return _current_tenant.get()


# --- customer scope (DEMO-012) ----------------------------------------------
#
# A tenant is not a fine enough boundary for a CUSTOMER using the mobile app.
# Every sales permission is tenant-wide: a household given `sales.invoice.read`
# so it can see its own bill would see every other household's bill in the same
# dairy. Tenancy answers "which organization"; this answers "which customer
# inside it", and without it there is no safe customer-facing experience.
#
# It is deliberately the same shape as the tenant contextvar — set once from
# the authenticated principal, read by the services that return customer-owned
# rows — because a second mechanism for the same idea is how the two drift.
#
# NULL means "not customer-scoped", which is every staff user and every
# existing caller. The narrowing only ever REMOVES rows, so a scope that fails
# to apply cannot widen anyone's access; it can only show a customer nothing.
_current_customer: ContextVar[uuid.UUID | None] = ContextVar("current_customer", default=None)


def get_current_customer() -> uuid.UUID | None:
    """The customer this principal is limited to, or None for staff."""
    return _current_customer.get()


def set_current_customer(customer_id: uuid.UUID | None) -> None:
    _current_customer.set(customer_id)
    if customer_id is not None:
        structlog.contextvars.bind_contextvars(customer_scope=str(customer_id))


def enforce_customer_scope(requested: uuid.UUID | None) -> uuid.UUID | None:
    """Narrow a customer filter to what this principal may see.

    The ONE place the rule lives, so a service cannot forget half of it:

    * staff (no scope) — whatever they asked for, unchanged;
    * a customer asking for nothing in particular — their own rows;
    * a customer asking for SOMEBODY ELSE — `NotFoundError`.

    404 rather than 403, for the same reason another tenant's resource is a
    404: a 403 confirms the row exists, and "there is a customer with this id"
    is exactly what a customer must not learn about the dairy's other
    customers.
    """
    from platform_core.core.errors import NotFoundError

    scope = get_current_customer()
    if scope is None:
        return requested
    if requested is not None and requested != scope:
        raise NotFoundError("customer not found")
    return scope


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
