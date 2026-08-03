"""Platform value objects (PRC-003/PRC-004): Money and Quantity."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from platform_core.core.types import (
    DEFAULT_ROUNDING_POLICY,
    ROUNDING_POLICIES,
    ROUNDING_POLICY_UNSPECIFIED,
    Money,
    Quantity,
)


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


def test_rounding_policy_registry():
    assert DEFAULT_ROUNDING_POLICY == "HALF_UP"
    assert set(ROUNDING_POLICIES) == {"HALF_UP", "HALF_EVEN", "DOWN"}


def test_money_multiplied_by_quantizes_with_policy():
    money = Money.of("42.50", "KES")
    result = money.multiplied_by(Decimal("125.5"), rounding_policy="HALF_UP")
    assert result.amount == Decimal("5333.75")
    assert result.currency == "KES"
    assert result.rounding_policy == "HALF_UP"
    assert result.precision == 2


def test_money_multiplied_by_policies_differ_on_ties():
    money = Money.of("4.445", "KES")
    one = Decimal("1")
    assert money.multiplied_by(one, rounding_policy="HALF_UP").amount == Decimal("4.45")
    assert money.multiplied_by(one, rounding_policy="HALF_EVEN").amount == Decimal("4.44")
    assert money.multiplied_by(one, rounding_policy="DOWN").amount == Decimal("4.44")


def test_money_multiplied_by_rejects_float_factor():
    """BR-0005: float arithmetic is forbidden in the money domain."""
    money = Money.of("42.50", "KES")
    with pytest.raises(TypeError, match="Decimal"):
        money.multiplied_by(125.5, rounding_policy="HALF_UP")  # type: ignore[arg-type]


def test_money_multiplied_by_rejects_unknown_policy():
    money = Money.of("42.50", "KES")
    with pytest.raises(ValueError, match="unknown rounding policy"):
        money.multiplied_by(Decimal("2"), rounding_policy="CEILING")


def test_money_multiplied_by_respects_precision():
    money = Money.of("1.23456", "KES", precision=4)
    result = money.multiplied_by(Decimal("1"), rounding_policy="HALF_UP")
    assert result.amount == Decimal("1.2346")


def test_money_multiplied_by_zero():
    result = Money.of("42.50", "KES").multiplied_by(Decimal("0"), rounding_policy="HALF_UP")
    assert result.amount == Decimal("0.00")


def test_money_negative_amounts_representable():
    """Deductions (future penalty engine) need negative money — representation
    is legal; only the arithmetic rules are restricted."""
    assert Money.of("-5.25", "KES").amount == Decimal("-5.25")


def test_money_plus_exact_addition():
    """SET-001: settlement totals are exact sums of quantized amounts."""
    total = Money.of("5647.50", "KES").plus(Money.of("2250.00", "KES"))
    assert total.amount == Decimal("7897.50")
    assert total.currency == "KES"


def test_money_plus_chain():
    total = Money.of("0.01", "KES").plus(Money.of("0.02", "KES")).plus(Money.of("0.03", "KES"))
    assert total.amount == Decimal("0.06")


def test_money_plus_zero_identity():
    money = Money.of("42.50", "KES")
    assert money.plus(Money.of("0.00", "KES")).amount == money.amount


def test_money_plus_currency_mismatch_rejected():
    with pytest.raises(ValueError, match="currency conversion"):
        Money.of("1.00", "KES").plus(Money.of("1.00", "USD"))


def test_money_plus_precision_mismatch_rejected():
    with pytest.raises(ValueError, match="precision"):
        Money.of("1.00", "KES").plus(Money.of("1.00", "KES", precision=4))


def test_money_plus_rejects_non_money():
    with pytest.raises(TypeError, match="Money"):
        Money.of("1.00", "KES").plus(Decimal("1.00"))  # type: ignore[arg-type]


def test_quantity_as_decimal_is_artifact_free():
    assert Quantity(value=125.5, unit="kg").as_decimal() == Decimal("125.5")
    assert Quantity(value=0.1, unit="kg").as_decimal() == Decimal("0.1")


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
