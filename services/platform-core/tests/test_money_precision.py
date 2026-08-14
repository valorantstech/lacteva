"""A currency's decimal places, in one place (DEMO-014 §2).

Six modules each carried `MONEY = Decimal("0.01")`. Correct for every currency
Lacteva has onboarded and wrong for the next one, which is the shape of every
assumption worth testing: it holds today, it is invisible, and the day it
breaks it breaks money.

The tests below therefore care about two things — that nothing changed for the
currencies in use, and that a zero-decimal currency is now a lookup rather
than a defect.
"""

from decimal import Decimal

import pytest

from platform_core.core.locales import CURRENCIES
from platform_core.core.money import (
    format_money,
    minor_units,
    money_scale,
    quantize_money,
)
from platform_core.core.types import Money


@pytest.mark.parametrize("code", ["INR", "KES", "SAR", "AED", "QAR", "USD", "GBP"])
def test_every_onboardable_currency_still_has_two_decimals(code):
    """The regression that matters most: DEMO-014 changed no arithmetic.

    Every currency a tenant can be created with today has two decimals, so
    `quantize_money` must return exactly what `Decimal("0.01")` did.
    """
    assert minor_units(code) == 2
    assert money_scale(code) == Decimal("0.01")
    assert quantize_money("1234.567", code) == Decimal("1234.57")


def test_a_zero_decimal_currency_gains_no_hundredths():
    """JPY has no minor unit. `¥1,200.00` is not a price anybody has seen."""
    assert minor_units("JPY") == 0
    assert quantize_money("1234.567", "JPY") == Decimal("1235")
    assert format_money("1200", "JPY") == "1200"


def test_a_zero_decimal_currency_is_already_reachable():
    """UGX is in the COUNTRY registry, so this is not hypothetical: a Ugandan
    dairy could be onboarded today and would have been billed in hundredths of
    a shilling."""
    assert minor_units("UGX") == 0
    assert quantize_money("99.5", "UGX") == Decimal("100")


def test_rounding_is_half_up_everywhere():
    """The platform's stated policy (BR-0005), unchanged. A per-currency
    rounding mode would be a different decision nobody has asked for."""
    assert quantize_money("2.345", "INR") == Decimal("2.35")
    assert quantize_money("2.344", "INR") == Decimal("2.34")
    assert quantize_money("0.5", "JPY") == Decimal("1")


def test_an_unknown_currency_formats_rather_than_refusing():
    """This is the RENDERING side of money already stored. Refusing to format
    a row because its currency left the registry hides the row, not the
    problem — refusing to WRITE one is `tenant_currency`'s job, and it raises."""
    assert minor_units("ZZZ") == 2
    assert minor_units(None) == 2
    assert quantize_money("1.005", "ZZZ") == Decimal("1.01")


def test_the_money_value_object_takes_its_scale_from_the_registry():
    assert Money.of("1", "INR").precision == 2
    assert Money.of("1", "JPY").precision == 0
    # An explicit precision still wins: the pricing engine has its own reasons.
    assert Money.of("1", "JPY", precision=3).precision == 3


def test_multiplication_rounds_at_the_currencys_scale():
    """PRC-004's one arithmetic operation, now aware of the currency.

    The rounding policy stays explicit and required — BR-0005 — because the
    scale being automatic must not make the POLICY automatic too.
    """
    inr = Money.of("10.00", "INR").multiplied_by(Decimal("1.005"), rounding_policy="HALF_UP")
    assert inr.amount == Decimal("10.05")

    jpy = Money.of("1000", "JPY").multiplied_by(Decimal("1.005"), rounding_policy="HALF_UP")
    assert jpy.amount == Decimal("1005"), "a yen gained a fractional part"


def test_every_registered_currency_declares_a_usable_scale():
    """The registry is data, and data rots. A currency with a nonsense scale
    would misprint every amount in it."""
    for code, currency in CURRENCIES.items():
        assert 0 <= currency.minor_units <= 4, code
        assert currency.symbol, code
        assert quantize_money("1", code) is not None
