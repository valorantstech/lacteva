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
        "error.rate_limited": "Too many requests. Please wait and try again.",
        "error.idempotency_key_invalid": "The Idempotency-Key header is empty or too long.",
        "error.idempotency_key_reused": "This Idempotency-Key was used for another request.",
        "error.idempotency_in_progress": "An identical request is still running. Retry shortly.",
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
        "error.rate_limited": "Maombi mengi mno. Tafadhali subiri kisha ujaribu tena.",
        "error.idempotency_key_invalid": "Kichwa cha Idempotency-Key ni tupu au kirefu mno.",
        "error.idempotency_key_reused": "Idempotency-Key hii ilitumika kwa ombi tofauti.",
        "error.idempotency_in_progress": "Ombi linalofanana bado linaendelea. Jaribu tena baadaye.",
    },
    "hi": {  # Hindi — starter subset
        "error.not_found": "अनुरोधित संसाधन नहीं मिला।",
        "error.unauthorized": "प्रमाणीकरण आवश्यक है।",
        "error.forbidden": "आपको यह कार्य करने की अनुमति नहीं है।",
        "error.invalid_credentials": "ईमेल या पासवर्ड गलत है।",
        "error.rate_limited": "बहुत अधिक अनुरोध। कृपया प्रतीक्षा करें और पुनः प्रयास करें।",
        "error.idempotency_key_invalid": "Idempotency-Key हेडर खाली है या बहुत लंबा है।",
        "error.idempotency_key_reused": "यह Idempotency-Key किसी अन्य अनुरोध हेतु प्रयुक्त हुई।",
        "error.idempotency_in_progress": "समान अनुरोध अभी चल रहा है। शीघ्र पुनः प्रयास करें।",
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
