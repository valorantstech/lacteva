"""How many decimal places a currency has, in one place (DEMO-014 §2).

Six modules each carried `MONEY = Decimal("0.01")` and quantized against it.
That is correct for every currency Lacteva has onboarded and wrong for the
next one: JPY has no minor unit, UGX has none either and is already in the
country registry, and a platform that assumes two decimals would print
`¥1,200.00` and round a Ugandan shilling to a hundredth that does not exist.

The scale is a property of the CURRENCY, so it is read from the currency
registry rather than restated per module. `quantize_money` is the only place
that turns an exact value into a stored amount, and it always needs to be told
which money it is dealing with.

**This changes no arithmetic for any currency in use.** Every currency a
Lacteva tenant can be created with today has two decimals, so `quantize_money`
returns exactly what `Decimal("0.01")` did. What changes is that the assumption
now lives somewhere it can be corrected, and a zero-decimal currency is a
lookup rather than a defect.

Rounding stays HALF_UP everywhere, unchanged: it is the platform's stated
policy (BR-0005) and a per-currency rounding mode would be a different
decision, made for different reasons, that nobody has asked for.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from platform_core.core.locales import CURRENCIES

#: What the platform uses when it genuinely does not know the currency:
#: aggregate helpers that sum across tenants, and a handful of ratios. Two
#: decimals, which is what every one of them assumed before and what every
#: supported currency uses. It is NOT a default for stored money — that path
#: always knows its currency, and `quantize_money` requires one.
DEFAULT_MINOR_UNITS = 2


def minor_units(currency: str | None) -> int:
    """Decimal places for an ISO 4217 code.

    An unknown code falls back rather than raising: this is called on the
    RENDERING side of money that is already stored, and refusing to format a
    row because its currency left the registry would hide the row rather than
    the problem. Refusing to WRITE such a row is `tenant_currency`'s job, and
    it does raise.
    """
    entry = CURRENCIES.get((currency or "").upper())
    return entry.minor_units if entry else DEFAULT_MINOR_UNITS


def money_scale(currency: str | None) -> Decimal:
    """The quantization exponent: `0.01` for INR, `1` for JPY."""
    return Decimal(1).scaleb(-minor_units(currency))


def quantize_money(value: Decimal | int | str, currency: str | None) -> Decimal:
    """An exact value, rounded once to the currency's own scale.

    Once, and explicitly. Repeated quantization is how a total drifts from its
    lines; this is called at the boundary where a number becomes an amount.
    """
    return Decimal(value).quantize(money_scale(currency), rounding=ROUND_HALF_UP)


def format_money(value: Decimal | int | str, currency: str | None) -> str:
    """The amount as a plain decimal string at the currency's scale.

    No grouping, no symbol: those are presentation and belong to whichever
    client is drawing the screen. What belongs here is the number of decimal
    places, because that is a fact about the money rather than about the page.
    """
    return str(quantize_money(value, currency))
