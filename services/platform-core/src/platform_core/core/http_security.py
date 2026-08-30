"""Response headers the APPLICATION owns (SEC-001, narrowed by WO-46).

THE EDGE OWNS TRANSPORT SECURITY. HSTS, `X-Frame-Options`, `nosniff`,
`Referrer-Policy`, `Permissions-Policy` and CSP are set by nginx, from
`infra/nginx/conf.d/security-headers.inc`, and are NOT set here.

They used to be set in both places, and the two disagreed. A live response
from `/v1/auth/me` carried `Referrer-Policy` twice — `no-referrer` from this
middleware and `strict-origin-when-cross-origin` from nginx — and
`Permissions-Policy` twice with different feature lists. Which one a browser
honours is a detail of header ordering, which is to say it was not decided by
anybody. Two owners of one policy is one owner too many, and the edge is the
right one: it is the only layer that sees BOTH the API and the portal, and
the portal is where the headers were missing entirely.

WHAT REMAINS HERE, and why it is not a leftover:

- **Cache-Control: no-store** — not transport hardening but a tenancy guard.
  Every response from this API is scoped to one organization, and a shared
  proxy that caches one tenant's data and serves it to another is a
  cross-tenant leak with extra steps. It belongs to the application because
  the application is what knows the response is tenant-scoped.

Trusted proxy assumption: TLS terminates at the load balancer, which is also
the only component permitted to set `X-Forwarded-For`. Client IPs used for
rate limiting derive from that header, so an untrusted proxy in front of the
platform would let a caller forge its own identity — see SECURITY.md.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach the headers the application owns to every response, errors included."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Caching a tenant's data in a shared proxy is a cross-tenant leak
        # waiting to happen; API responses are never publicly cacheable.
        response.headers.setdefault("Cache-Control", "no-store")
        return response


def client_ip(request: Request) -> str:
    """The caller's address for rate limiting.

    `X-Forwarded-For` is trusted because the deployment contract says only the
    load balancer may set it (see the module docstring). The FIRST entry is
    the original client; later entries are proxies.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
