"""Country, currency, timezone and language reference data (DEMO-013).

Lacteva is a platform, not a Kenyan dairy application that happens to be
installed elsewhere. A tenant's country decides its money, its calendar and
its words, and **nothing in the application may branch on which country that
is**. This module is the one place that knows the difference between India and
Kenya; everywhere else reads an organization's resolved settings.

**Why a registry in code rather than a table.** This is REFERENCE data: it
changes when the world changes, not when a tenant does. Every other registry
in this platform is code for the same reason — permissions, `BUS_EVENTS`, the
model registry — because a typo becomes a failing build instead of a row
somebody has to notice. A table would need seeding, a migration per addition,
an RLS decision, and would still be edited by an engineer.

**Adding a country is a data entry here, never a code path.** And a country
absent from this registry is still onboardable: `resolve()` requires the
caller to supply currency and timezone explicitly rather than guessing, so an
unknown country fails loudly at onboarding instead of silently billing
somebody in the wrong money.

The registry is deliberately SMALL. It holds what is needed and what is
plausibly next, not an atlas — a hundred unused rows would be a hundred
unverified claims about other people's currencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from platform_core.core.units import normalise_unit


@dataclass(frozen=True)
class Currency:
    """ISO 4217.

    `minor_units` is the number of decimal places the currency is written in.
    It is carried because it is part of what a currency IS — JPY has none, and
    a platform that assumes two would misprint every Japanese amount. Today
    every supported currency has two, which is why `core/db.py`'s money scale
    is still a constant; the day one does not, this is where the truth lives
    and that constant becomes a lookup.
    """

    code: str
    name: str
    symbol: str
    minor_units: int = 2


CURRENCIES: dict[str, Currency] = {
    "INR": Currency("INR", "Indian Rupee", "₹"),
    "KES": Currency("KES", "Kenyan Shilling", "KSh"),
    "USD": Currency("USD", "US Dollar", "$"),
    "EUR": Currency("EUR", "Euro", "€"),
    "GBP": Currency("GBP", "Pound Sterling", "£"),
    "AED": Currency("AED", "UAE Dirham", "د.إ"),
    "SAR": Currency("SAR", "Saudi Riyal", "﷼"),
    "QAR": Currency("QAR", "Qatari Riyal", "ر.ق"),
    "UGX": Currency("UGX", "Ugandan Shilling", "USh", minor_units=0),
    "TZS": Currency("TZS", "Tanzanian Shilling", "TSh"),
    # DEMO-014: not offered for onboarding — no country in the registry uses
    # it — and present so the ZERO-DECIMAL path is exercised by something
    # real rather than by a hypothetical. `test_money.py` quantizes against
    # it; UGX above is the one a tenant could actually be created with.
    "JPY": Currency("JPY", "Japanese Yen", "¥", minor_units=0),
}


@dataclass(frozen=True)
class Language:
    """A language Lacteva can actually speak.

    Listing one here is a claim that a catalog exists for it. `rtl` is carried
    because Arabic is a stated target and a right-to-left interface is a
    layout decision, not a translation one.
    """

    tag: str  # BCP-47
    name: str  # in English, for administrators
    endonym: str  # in the language itself, for the person choosing it
    rtl: bool = False


LANGUAGES: dict[str, Language] = {
    "en": Language("en", "English", "English"),
    "hi": Language("hi", "Hindi", "हिन्दी"),
    "sw": Language("sw", "Swahili", "Kiswahili"),
    "ar": Language("ar", "Arabic", "العربية", rtl=True),
}


@dataclass(frozen=True)
class Country:
    """ISO 3166-1 alpha-2, and what it implies.

    `languages` is ordered: the first is what the country's organizations get
    as their default, the rest are what an administrator may switch on.
    """

    code: str
    name: str
    currency: str
    timezone: str  # IANA; the country's PRINCIPAL zone — see `resolve()`
    languages: tuple[str, ...]
    #: D-21 / WO-70. The unit the country's dairies SELL milk in — the unit a
    #: farmer reads on a receipt and a rate is quoted per. Not the unit a
    #: counter's instrument happens to report: India's AMCU specification has
    #: a weighing scale on it, and India trades in litres, which is the
    #: inference the architect got wrong. One of `core/units.UNITS`. Like the
    #: currency, a proposal an organisation may override at creation.
    quantity_unit: str = "litre"


#: `languages` is ORDERED and the first entry is the country's default.
#:
#: DEMO-014: the Gulf countries lead with Arabic, because a Saudi dairy's
#: staff read Arabic and English is the second language there, not the first.
#: That ordering is the whole mechanism — there is no `if country == "SA"`
#: anywhere deciding it.
#: `quantity_unit` (D-21): every listed market retails and quotes milk by the
#: litre — India (500 ml and 1 L packs, rates per litre), Kenya, the Gulf,
#: East Africa and Britain alike. The one exception below is stated with its
#: reason. Kilograms remain available to any organisation as an override, for
#: the cooperative that weighs deliberately.
COUNTRIES: dict[str, Country] = {
    "IN": Country("IN", "India", "INR", "Asia/Kolkata", ("en-IN", "hi-IN"), "litre"),
    "KE": Country("KE", "Kenya", "KES", "Africa/Nairobi", ("en-KE", "sw-KE"), "litre"),
    "SA": Country("SA", "Saudi Arabia", "SAR", "Asia/Riyadh", ("ar-SA", "en-SA"), "litre"),
    "AE": Country("AE", "United Arab Emirates", "AED", "Asia/Dubai", ("ar-AE", "en-AE"), "litre"),
    "QA": Country("QA", "Qatar", "QAR", "Asia/Qatar", ("ar-QA", "en-QA"), "litre"),
    "UG": Country("UG", "Uganda", "UGX", "Africa/Kampala", ("en-UG", "sw-UG"), "litre"),
    "TZ": Country("TZ", "Tanzania", "TZS", "Africa/Dar_es_Salaam", ("en-TZ", "sw-TZ"), "litre"),
    "GB": Country("GB", "United Kingdom", "GBP", "Europe/London", ("en-GB",), "litre"),
    # The United States spans six zones and no single one is "the" American
    # timezone. The registry names the most populous as a STARTING POINT and
    # `resolve()` takes an override — which is the honest shape for any large
    # country, and why the field is documented as principal rather than only.
    #
    # And it trades farm milk BY WEIGHT — priced per hundredweight, paid on
    # pounds. The platform's weight unit is the kilogram; pounds are not
    # supported, and this entry says "weight" rather than pretending the US
    # sells by the litre.
    "US": Country("US", "United States", "USD", "America/New_York", ("en-US",), "kg"),
}


class UnknownCountryError(ValueError):
    """A country with no profile, onboarded without the values it needs.

    Deliberately not a fallback. Guessing that an unlisted country uses USD in
    UTC would be a guess about somebody's money, and it would be wrong
    silently — the dairy would discover it on the first bill.
    """


@dataclass(frozen=True)
class LocaleSettings:
    """What an organization actually operates in, after resolution."""

    country_code: str
    currency_code: str
    timezone: str
    default_language: str
    supported_languages: tuple[str, ...]
    #: D-21. What this organisation MEASURES intake in; one of `units.UNITS`.
    quantity_unit: str = "litre"


def base_language(tag: str) -> str:
    """`en-IN` → `en`. The catalog key for a BCP-47 tag.

    Message catalogs are keyed by language, not by locale, because "Hindi as
    spoken in India" and "Hindi" are the same words — the region carries the
    money and the calendar, which live elsewhere. Splitting catalogs per
    region would double the translation work to say the same sentences.
    """
    return (tag or "").split("-", 1)[0].lower()


def is_valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False
    return True


def resolve(
    country_code: str,
    *,
    currency_code: str | None = None,
    timezone: str | None = None,
    default_language: str | None = None,
    supported_languages: list[str] | tuple[str, ...] | None = None,
    quantity_unit: str | None = None,
) -> LocaleSettings:
    """Country in, complete settings out — with every part overridable.

    The proposal comes from the registry so that onboarding can ask ONE
    question ("where are you?") and fill in the rest. Each answer is still an
    override, because the registry knows a country's principal timezone and a
    country is not always one zone: an Indian dairy is Asia/Kolkata and a US
    one is not usefully America/New_York. Where the registry would be a guess,
    the caller can say.

    An unknown country is not fatal — it is a country the registry has not met
    yet, and a platform that refused to onboard it would be exactly the
    country-specific coupling this milestone exists to remove. It just has to
    be told the money and the clock.
    """
    code = (country_code or "").strip().upper()
    profile = COUNTRIES.get(code)

    if profile is None:
        missing = [
            name
            for name, value in (
                ("currency_code", currency_code),
                ("timezone", timezone),
                # D-21: the unit is money-shaped in the sense that matters —
                # guessing it prices a stranger's milk in the wrong measure.
                ("quantity_unit", quantity_unit),
            )
            if not value
        ]
        if missing:
            raise UnknownCountryError(
                f"country {code!r} is not in the locale registry, so "
                f"{' and '.join(missing)} must be supplied explicitly"
            )

    resolved_currency = (currency_code or (profile.currency if profile else "")).upper()
    if resolved_currency not in CURRENCIES:
        raise ValueError(
            f"unknown currency {resolved_currency!r} — add it to CURRENCIES with its minor units"
        )

    resolved_timezone = timezone or (profile.timezone if profile else "")
    if not is_valid_timezone(resolved_timezone):
        raise ValueError(f"{resolved_timezone!r} is not an IANA timezone")

    proposed = tuple(supported_languages or (profile.languages if profile else ("en",)))
    if not proposed:
        raise ValueError("an organization must support at least one language")
    for tag in proposed:
        if base_language(tag) not in LANGUAGES:
            raise ValueError(
                f"no message catalog for {tag!r} — add it to LANGUAGES and to core/i18n.py"
            )

    # D-21. A country proposes the unit; an organisation may say otherwise
    # (a cooperative that weighs). Spelling is normalised at this boundary so
    # the column only ever holds one of `UNITS`.
    resolved_unit = normalise_unit(quantity_unit or (profile.quantity_unit if profile else ""))

    resolved_default = default_language or proposed[0]
    if resolved_default not in proposed:
        raise ValueError(
            f"default language {resolved_default!r} is not among the supported languages "
            f"{list(proposed)} — an organization cannot default to a language it has not enabled"
        )

    return LocaleSettings(
        country_code=code,
        currency_code=resolved_currency,
        timezone=resolved_timezone,
        default_language=resolved_default,
        supported_languages=proposed,
        quantity_unit=resolved_unit,
    )


def currency_symbol(code: str) -> str:
    """The symbol, or the code itself — which is a perfectly good symbol."""
    entry = CURRENCIES.get((code or "").upper())
    return entry.symbol if entry else (code or "").upper()


def country_choices() -> list[dict]:
    """The onboarding list: what a country implies, before anyone commits.

    Returned rather than rendered, so the portal and the mobile app show the
    same countries without either of them holding a copy.
    """
    return [
        {
            "code": c.code,
            "name": c.name,
            "currency_code": c.currency,
            "currency_symbol": currency_symbol(c.currency),
            "timezone": c.timezone,
            "default_language": c.languages[0],
            "supported_languages": list(c.languages),
            "quantity_unit": c.quantity_unit,
        }
        for c in sorted(COUNTRIES.values(), key=lambda c: c.name)
    ]


def language_choices(tags: list[str] | tuple[str, ...]) -> list[dict]:
    """Describe an organization's enabled languages, for a person choosing."""
    out = []
    for tag in tags:
        entry = LANGUAGES.get(base_language(tag))
        if entry is None:
            continue
        out.append({"tag": tag, "name": entry.name, "endonym": entry.endonym, "rtl": entry.rtl})
    return out
