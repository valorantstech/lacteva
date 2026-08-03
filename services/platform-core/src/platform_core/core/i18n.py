"""Localization: message catalogs and locale negotiation.

Catalogs are in-code for the foundation; TODO(M2): externalize to per-locale
resource files managed under the ETE.LOC market-pack process, and cover all
user-facing strings (notifications, receipts).
"""

from contextvars import ContextVar

from starlette.requests import Request

from platform_core.core.config import get_settings

CATALOGS: dict[str, dict[str, str]] = {
    "en": {
        "error.not_found": "The requested resource was not found.",
        "error.conflict": "The resource already exists.",
        "error.unauthorized": "Authentication is required.",
        "error.forbidden": "You do not have permission to perform this action.",
        "error.invalid_credentials": "Email or password is incorrect.",
        "error.validation": "The request is invalid.",
        "error.invalid_token": "This link is invalid or has expired.",
        "error.pricing_no_match": "No applicable pricing was found for this transaction.",
        "error.pricing_integrity": (
            "Pricing data is ambiguous for this transaction — contact an administrator."
        ),
        "notification.welcome.subject": "Welcome to Lacteva",
        "notification.password_reset.subject": "Reset your Lacteva password",
        "notification.invitation.subject": "You have been invited to Lacteva",
    },
    "sw": {  # Kiswahili — starter subset; full catalog is a market-pack task
        "error.not_found": "Rasilimali haikupatikana.",
        "error.unauthorized": "Uthibitisho unahitajika.",
        "error.forbidden": "Huna ruhusa ya kufanya kitendo hiki.",
        "error.invalid_credentials": "Barua pepe au nenosiri si sahihi.",
    },
    "hi": {  # Hindi — starter subset
        "error.not_found": "अनुरोधित संसाधन नहीं मिला।",
        "error.unauthorized": "प्रमाणीकरण आवश्यक है।",
        "error.forbidden": "आपको यह कार्य करने की अनुमति नहीं है।",
        "error.invalid_credentials": "ईमेल या पासवर्ड गलत है।",
    },
}

_current_locale: ContextVar[str] = ContextVar("current_locale", default="en")


def negotiate_locale(request: Request) -> str:
    """Pick the best supported locale from Accept-Language (simple prefix match)."""
    settings = get_settings()
    header = request.headers.get("Accept-Language", "")
    for part in header.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in settings.supported_locales:
            return code
    return settings.default_locale


def set_locale(locale: str) -> None:
    _current_locale.set(locale)


def get_locale() -> str:
    return _current_locale.get()


def translate(key: str, locale: str | None = None) -> str:
    loc = locale or get_locale()
    return CATALOGS.get(loc, {}).get(key) or CATALOGS["en"].get(key, key)
