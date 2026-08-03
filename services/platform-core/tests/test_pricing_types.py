"""Platform value objects (PRC-003): Money and Quantity."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from platform_core.core.types import ROUNDING_POLICY_UNSPECIFIED, Money, Quantity


def test_money_of_float_has_no_float_artifacts():
    money = Money.of(42.5, "kes")
    assert money.amount == Decimal("42.5")
    assert money.currency == "KES"  # normalized upper-case


def test_money_of_string_int_and_decimal():
    assert Money.of("19.99", "KES").amount == Decimal("19.99")
    assert Money.of(7, "KES").amount == Decimal("7")
    assert Money.of(Decimal("3.141"), "KES").amount == Decimal("3.141")


def test_money_defaults():
    money = Money.of(10, "USD")
    assert money.precision == 2
    assert money.rounding_policy == ROUNDING_POLICY_UNSPECIFIED


def test_money_invalid_currency_rejected():
    for currency in ("K3S", "KESH", "K", ""):
        with pytest.raises(ValidationError):
            Money(amount=Decimal("1"), currency=currency)


def test_money_is_frozen():
    money = Money.of(10, "KES")
    with pytest.raises(ValidationError):
        money.amount = Decimal("11")


def test_money_precision_bounds():
    assert Money(amount=Decimal("1"), currency="KES", precision=6).precision == 6
    with pytest.raises(ValidationError):
        Money(amount=Decimal("1"), currency="KES", precision=7)
    with pytest.raises(ValidationError):
        Money(amount=Decimal("1"), currency="KES", precision=-1)


def test_money_has_no_arithmetic():
    """Arithmetic is intentionally absent until PRC-004 defines the rounding
    policy — adding Money must not silently work."""
    money = Money.of(10, "KES")
    with pytest.raises(TypeError):
        _ = money + money  # type: ignore[operator]


def test_quantity_defaults():
    reading = Quantity(value=4.2, unit="%")
    assert reading.precision == 2 and reading.unit == "%"


def test_quantity_is_frozen():
    reading = Quantity(value=4.2, unit="%")
    with pytest.raises(ValidationError):
        reading.value = 5.0


def test_quantity_unit_length_bounded():
    with pytest.raises(ValidationError):
        Quantity(value=1.0, unit="x" * 21)


def test_quantity_precision_bounds():
    with pytest.raises(ValidationError):
        Quantity(value=1.0, precision=7)
