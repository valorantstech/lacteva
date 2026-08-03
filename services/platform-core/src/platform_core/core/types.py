"""Reusable platform value objects (PRC-003, arithmetic since PRC-004).

Money and Quantity are immutable, validated value types shared by every
module that talks about amounts and measured readings.

MONEY PRECISION POLICY (PRC-004, BR-0005):
- All monetary arithmetic is Decimal — float arithmetic is forbidden.
  Floats entering the money domain are converted via ``Decimal(str(x))``
  (shortest-repr round-trip, no binary artifacts); factors passed to
  arithmetic methods MUST already be Decimal (enforced with TypeError).
- Every rounding step names an explicit policy from ROUNDING_POLICIES.
  Platform default: HALF_UP (the commercial convention — ties round away
  from zero, the amount a supplier expects on a receipt). HALF_EVEN
  (banker's) and DOWN (truncation) are available per request or via the
  tenant configuration key ``pricing.rounding_policy``.
- Results quantize to the Money's ``precision`` decimal places (2 by
  default, per ISO-4217 minor units of the launch currencies).
"""

import decimal
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

# Legacy sentinel: marks Money that has not been through a rounding step
# (e.g. resolution output, which only *selects* a price).
ROUNDING_POLICY_UNSPECIFIED = "unspecified"

ROUNDING_POLICIES: dict[str, str] = {
    "HALF_UP": decimal.ROUND_HALF_UP,  # commercial rounding (default)
    "HALF_EVEN": decimal.ROUND_HALF_EVEN,  # banker's rounding
    "DOWN": decimal.ROUND_DOWN,  # truncate toward zero
}
DEFAULT_ROUNDING_POLICY = "HALF_UP"


class Money(BaseModel):
    """An amount of a specific currency.

    Arithmetic is deliberately minimal and always explicit about rounding:
    ``multiplied_by`` is the only operation (PRC-004 needs no more).
    Operators like ``+`` stay absent on purpose — silent money math is a
    bug factory; each new operation must arrive with its own policy story.
    """

    model_config = {"frozen": True}

    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)  # ISO 4217
    precision: int = Field(default=2, ge=0, le=6)
    rounding_policy: str = ROUNDING_POLICY_UNSPECIFIED

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return v.upper()

    @classmethod
    def of(
        cls, amount: float | str | int | Decimal, currency: str, *, precision: int = 2
    ) -> "Money":
        """Build from any numeric representation without float artifacts
        (floats go through str, so 42.5 becomes Decimal('42.5'))."""
        value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        return cls(amount=value, currency=currency, precision=precision)

    def plus(self, other: "Money") -> "Money":
        """Exact addition of same-currency, same-precision amounts (SET-001).

        Sums of already-quantized amounts stay exact, so no rounding step is
        involved — which is why this method needs no policy parameter.
        Mixed currencies or precisions are errors, never conversions."""
        if not isinstance(other, Money):
            raise TypeError("monetary addition requires Money operands (BR-0005)")
        if other.currency != self.currency:
            raise ValueError(
                f"cannot add {other.currency} to {self.currency} — "
                "currency conversion is not a Money operation"
            )
        if other.precision != self.precision:
            raise ValueError("cannot add Money values of different precision")
        return Money(
            amount=self.amount + other.amount,
            currency=self.currency,
            precision=self.precision,
            rounding_policy=self.rounding_policy,
        )

    def multiplied_by(self, factor: Decimal, *, rounding_policy: str) -> "Money":
        """amount x factor, quantized to this Money's precision under an
        explicit rounding policy (BR-0005: Decimal only, policy named)."""
        if not isinstance(factor, Decimal):
            raise TypeError(
                "monetary arithmetic requires a Decimal factor — convert floats "
                "with Decimal(str(x)) before they reach the money domain (BR-0005)"
            )
        rounded = (self.amount * factor).quantize(
            Decimal(1).scaleb(-self.precision), rounding=_rounding_mode(rounding_policy)
        )
        return Money(
            amount=rounded,
            currency=self.currency,
            precision=self.precision,
            rounding_policy=rounding_policy,
        )


def _rounding_mode(policy: str) -> str:
    mode = ROUNDING_POLICIES.get(policy)
    if mode is None:
        raise ValueError(
            f"unknown rounding policy {policy!r} — supported: {sorted(ROUNDING_POLICIES)}"
        )
    return mode


class Quantity(BaseModel):
    """A measured value with its unit (e.g. 4.2 '%', 12.5 'kg')."""

    model_config = {"frozen": True}

    value: float
    unit: str = Field(default="", max_length=20)
    precision: int = Field(default=2, ge=0, le=6)

    def as_decimal(self) -> Decimal:
        """Artifact-free Decimal view of the measured value."""
        return Decimal(str(self.value))
