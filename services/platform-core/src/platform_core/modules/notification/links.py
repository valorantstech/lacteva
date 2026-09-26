"""The links the platform puts in mail (WO-100).

The portal's public address comes from a RUNTIME setting on the API
(`LACTEVA_PORTAL_PUBLIC_URL`); the token goes in the URL FRAGMENT, never a
query string. A fragment is not sent to the server, so the token never lands
in nginx's access log, in any proxy's log or in the log pipeline — a query
string would write it in plain text into every access-log line for that
request, which undoes SEC-003 / F-04's discipline that the raw token travels
only by email. The page reads the fragment, prefills the code, and removes it
from the address bar.
"""

from platform_core.core.config import get_settings


def portal_url() -> str:
    return get_settings().portal_public_url.rstrip("/")


def invitation_link(token: str) -> str:
    return f"{portal_url()}/accept-invitation#code={token}"


def password_reset_link(token: str) -> str:
    return f"{portal_url()}/reset-password#code={token}"


def email_change_link(token: str) -> str:
    return f"{portal_url()}/confirm-email#code={token}"
