"""Security response headers (SEC-001).

This API serves JSON to a separate origin (the admin portal) and to native
apps. It renders no HTML of its own, which makes the correct policy unusually
strict: nothing should ever be framed, sniffed, or treated as a document.

Header choices, and why each is what it is:

- **HSTS** — only meaningful over TLS, so it is opt-in and off in dev. Emitting
  it on a plaintext dev origin teaches browsers a rule the developer cannot
  undo for `max-age` seconds.
- **X-Content-Type-Options: nosniff** — a JSON body must never be reinterpreted
  as script.
- **X-Frame-Options: DENY** and `frame-ancestors 'none'` — an API has no
  legitimate framing use; both are sent because older agents honour only one.
- **Referrer-Policy: no-referrer** — URLs here carry ids; none of them belong
  in a third party's logs.
- **Permissions-Policy** — the API needs no device capability at all, so every
  powerful feature is denied outright.
- **Content-Security-Policy** — `default-src 'none'` is correct for a service
  that returns data. It is relaxed only for the docs UI, which loads Swagger's
  own assets and never runs in prod.

Trusted proxy assumption: TLS terminates at the load balancer, which is also
the only component permitted to set `X-Forwarded-For`. Client IPs used for
rate limiting derive from that header, so an untrusted proxy in front of the
platform would let a caller forge its own identity — see SECURITY.md.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from platform_core.core.config import get_settings

# Paths whose responses are documents, not data. Only reachable outside prod.
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

_DOCS_CSP = (
    "default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardening headers to every response, including errors."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        settings = get_settings()
        if not settings.security_headers_enabled:
            return response

        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault(
            "Permissions-Policy",
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()",
        )
        is_docs = any(request.url.path.startswith(path) for path in _DOCS_PATHS)
        headers.setdefault(
            "Content-Security-Policy",
            _DOCS_CSP if is_docs else settings.content_security_policy,
        )
        if settings.hsts_enabled:
            headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.hsts_max_age_seconds}; includeSubDomains",
            )
        # Caching a tenant's data in a shared proxy is a cross-tenant leak
        # waiting to happen; API responses are never publicly cacheable.
        headers.setdefault("Cache-Control", "no-store")
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
