"""PricingCalculator domain service (PRC-004): pure Decimal math, rounding
policies, trace completeness, determinism. No I/O — no fixtures needed."""

from decimal import Decimal

import pytest

from platform_core.core.types import Money, Quantity
from platform_core.modules.pricing.calculator import CALCULATOR_VERSION, PricingCalculator

CALC = PricingCalculator()


def _calc(price, qty, *, policy="HALF_UP", currency="KES", precision=2, unit="kg"):
    return CALC.calculate(
        unit_price=Money.of(price, currency, precision=precision),
        quantity=Quantity(value=qty, unit=unit),
        rounding_policy=policy,
    )


# --- basic math --------------------------------------------------------------


def test_gross_is_unit_price_times_quantity():
    result = _calc("42.50", 125.5)
    assert result.gross_amount.amount == Decimal("5333.75")
    assert result.gross_amount.currency == "KES"
    assert result.rounding_policy == "HALF_UP"
    assert result.calculator_version == CALCULATOR_VERSION


def test_no_float_artifacts():
    """0.1 + 0.2 style traps must not exist: 3.33 x 3 is exactly 9.99."""
    assert _calc(3.33, 3.0).gross_amount.amount == Decimal("9.99")
    assert _calc(4.35, 1.0).gross_amount.amount == Decimal("4.35")
    assert _calc(0.07, 100.0).gross_amount.amount == Decimal("7.00")


def test_exactness_with_large_operands():
    result = _calc("999999.99", 999999.0)
    assert result.gross_amount.amount == Decimal("999998990000.01")


def test_zero_quantity_gives_zero_gross():
    result = _calc("42.50", 0.0)
    assert result.gross_amount.amount == Decimal("0.00")
    assert len(result.trace) == 4  # still fully traced


def test_large_quantity():
    result = _calc("42.50", 1_000_000_000.0)
    assert result.gross_amount.amount == Decimal("42500000000.00")


def test_fractional_quantity():
    assert _calc("40.00", 125.75).gross_amount.amount == Decimal("5030.00")
    assert _calc("40.10", 125.75).gross_amount.amount == Decimal("5042.58")  # ...575 rounds up


def test_negative_quantity_rejected():
    with pytest.raises(ValueError, match="negative"):
        _calc("42.50", -1.0)


def test_unknown_policy_rejected():
    with pytest.raises(ValueError, match="unknown rounding policy"):
        _calc("42.50", 1.0, policy="NEAREST_GOAT")


# --- rounding policies -------------------------------------------------------


def test_half_up_ties_round_away():
    assert _calc("4.445", 1.0, policy="HALF_UP").gross_amount.amount == Decimal("4.45")
    assert _calc("0.005", 1.0, policy="HALF_UP").gross_amount.amount == Decimal("0.01")


def test_half_even_ties_round_to_even():
    assert _calc("4.445", 1.0, policy="HALF_EVEN").gross_amount.amount == Decimal("4.44")
    assert _calc("4.455", 1.0, policy="HALF_EVEN").gross_amount.amount == Decimal("4.46")
    assert _calc("0.005", 1.0, policy="HALF_EVEN").gross_amount.amount == Decimal("0.00")


def test_down_truncates():
    assert _calc("4.449", 1.0, policy="DOWN").gross_amount.amount == Decimal("4.44")
    assert _calc("0.009", 1.0, policy="DOWN").gross_amount.amount == Decimal("0.00")


def test_policies_agree_when_no_tie():
    for policy in ("HALF_UP", "HALF_EVEN", "DOWN"):
        assert _calc("42.50", 2.0, policy=policy).gross_amount.amount == Decimal("85.00")


def test_boundary_half_cent():
    """0.01 x 0.5 = 0.005 — the smallest possible tie."""
    assert _calc("0.01", 0.5, policy="HALF_UP").gross_amount.amount == Decimal("0.01")
    assert _calc("0.01", 0.5, policy="HALF_EVEN").gross_amount.amount == Decimal("0.00")
    assert _calc("0.01", 0.5, policy="DOWN").gross_amount.amount == Decimal("0.00")


def test_precision_respected():
    result = _calc("1.23456", 1.0, precision=3)
    assert result.gross_amount.amount == Decimal("1.235")
    assert result.gross_amount.precision == 3


def test_three_decimal_quantity_tie():
    # 45 x 0.333 = 14.985 — tie: even neighbour is 14.98, commercial is 14.99
    assert _calc("45", 0.333, policy="HALF_EVEN").gross_amount.amount == Decimal("14.98")
    assert _calc("45", 0.333, policy="HALF_UP").gross_amount.amount == Decimal("14.99")


def test_zero_quantity_trace_values():
    trace = _calc("42.50", 0.0).trace
    assert trace[2].values["raw_amount"] == "0.000"  # exact Decimal product scale
    assert trace[3].values["rounded_amount"] == "0.00"


# --- trace (BR-0006) ---------------------------------------------------------


def test_trace_has_all_four_steps_in_order():
    trace = _calc("42.50", 125.5).trace
    assert [s.operation for s in trace] == ["inputs", "normalize", "multiply", "round"]
    assert [s.sequence for s in trace] == [1, 2, 3, 4]


def test_trace_explains_every_value():
    trace = _calc("40.10", 125.75).trace
    inputs, normalize, multiply, rounding = trace
    assert inputs.values["unit_price"] == "40.10"
    assert inputs.values["quantity"] == "125.75"
    assert inputs.values["currency"] == "KES" and inputs.values["unit"] == "kg"
    assert "Decimal" in normalize.detail
    assert multiply.values["expression"] == "40.10 x 125.75"
    assert multiply.values["raw_amount"] == "5042.5750"  # exact, unrounded
    assert rounding.values["policy"] == "HALF_UP"
    assert rounding.values["raw_amount"] == "5042.5750"
    assert rounding.values["rounded_amount"] == "5042.58"


def test_trace_raw_amount_is_exact_product():
    trace = _calc("3.33", 3.0).trace
    assert trace[2].values["raw_amount"] == str(Decimal("3.33") * Decimal("3.0"))


def test_trace_records_policy_and_precision():
    rounding = _calc("1.0", 1.0, policy="DOWN", precision=3).trace[3]
    assert rounding.values["policy"] == "DOWN" and rounding.values["precision"] == "3"


def test_trace_steps_are_frozen():
    step = _calc("1.0", 1.0).trace[0]
    with pytest.raises(Exception):  # noqa: B017 — pydantic frozen error
        step.detail = "tampered"


# --- determinism (BR-0007) ---------------------------------------------------


def test_same_input_same_output():
    a = _calc("40.10", 125.75)
    b = _calc("40.10", 125.75)
    assert a == b  # frozen models: full structural equality, trace included


def test_unit_and_currency_propagate():
    result = _calc("42.50", 10.0, currency="usd", unit="litre")
    assert result.currency == "USD"
    assert result.gross_amount.currency == "USD"
    assert result.quantity.unit == "litre"
    assert result.unit_price.currency == "USD"


def test_result_is_frozen():
    result = _calc("1.0", 1.0)
    with pytest.raises(Exception):  # noqa: B017 — pydantic frozen error
        result.currency = "USD"
