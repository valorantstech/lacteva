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
        "error.ambiguous_tenant": (
            "This sign-in works for more than one organization. Choose which one to sign in to."
        ),
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
        "error.mock_hardware_refused": (
            "Simulated scale and analyzer readings are not permitted here. "
            "Weigh and test the milk, then enter the reading."
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
        "error.ambiguous_tenant": (
            "Kuingia huku kunafanya kazi kwa zaidi ya shirika moja. Chagua shirika la kuingia."
        ),
        "error.rate_limited": "Maombi mengi mno. Tafadhali subiri kisha ujaribu tena.",
        "error.idempotency_key_invalid": "Kichwa cha Idempotency-Key ni tupu au kirefu mno.",
        "error.idempotency_key_reused": "Idempotency-Key hii ilitumika kwa ombi tofauti.",
        "error.idempotency_in_progress": "Ombi linalofanana bado linaendelea. Jaribu tena baadaye.",
        "error.mock_hardware_refused": (
            "Vipimo vya mfano havihairuhusiwi hapa. Pima maziwa kisha uweke kipimo halisi."
        ),
    },
    "hi": {  # Hindi — starter subset
        "error.not_found": "अनुरोधित संसाधन नहीं मिला।",
        "error.unauthorized": "प्रमाणीकरण आवश्यक है।",
        "error.forbidden": "आपको यह कार्य करने की अनुमति नहीं है।",
        "error.invalid_credentials": "ईमेल या पासवर्ड गलत है।",
        "error.ambiguous_tenant": (
            "यह साइन-इन एक से अधिक संगठनों के लिए काम करता है। चुनें कि किसमें साइन इन करना है।"
        ),
        "error.rate_limited": "बहुत अधिक अनुरोध। कृपया प्रतीक्षा करें और पुनः प्रयास करें।",
        "error.idempotency_key_invalid": "Idempotency-Key हेडर खाली है या बहुत लंबा है।",
        "error.idempotency_key_reused": "यह Idempotency-Key किसी अन्य अनुरोध हेतु प्रयुक्त हुई।",
        "error.idempotency_in_progress": "समान अनुरोध अभी चल रहा है। शीघ्र पुनः प्रयास करें।",
        "error.mock_hardware_refused": (
            "यहाँ नकली रीडिंग की अनुमति नहीं है। दूध तौलें और वास्तविक रीडिंग दर्ज करें।"
        ),
    },
}

_current_locale: ContextVar[str] = ContextVar("current_locale", default="en")


def negotiate_locale(request: Request) -> str:
    """The browser's preference, as a STARTING point.

    DEMO-013 makes this the weakest of three signals, and it runs earliest:
    this is middleware, before anything has authenticated. Once a principal is
    resolved, `api/deps.py` overrides it with the person's own stored language
    (`user.locale`), which is the only one they actually chose. A device
    left on the wrong setting must not decide what language a dairy's staff
    read.
    """
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
    """A message in the best language available, never a blank.

    DEMO-013: accepts a BCP-47 tag. Catalogs are keyed by LANGUAGE (`hi`), not
    by locale (`hi-IN`), because "Hindi as spoken in India" and "Hindi" are
    the same words — the region carries the money and the calendar, which live
    on the organization. Splitting catalogs per region would double the
    translation work to say the same sentences.

    Falls back language → English → the key itself. A missing translation
    shows an English sentence, which a person can act on; a missing key shows
    the key, which an engineer can find.
    """
    from platform_core.core.locales import base_language

    loc = base_language(locale or get_locale())
    return CATALOGS.get(loc, {}).get(key) or CATALOGS["en"].get(key, key)
