"""Reusable platform value objects (PRC-003).

Money and Quantity are immutable, validated value types shared by every
module that talks about amounts and measured readings. INTENTIONALLY
arithmetic-free: the rounding policy is a placeholder until the Pricing
Calculator (PRC-004) defines the platform money-math rules — no module
may do monetary calculation before that policy exists.
"""

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

# Placeholder sentinel — PRC-004 replaces this with the platform rounding rule
# (candidate: ROUND_HALF_EVEN) and a quantize/arithmetic API.
ROUNDING_POLICY_UNSPECIFIED = "unspecified"


class Money(BaseModel):
    """An amount of a specific currency. Representation only — no arithmetic."""

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


class Quantity(BaseModel):
    """A measured value with its unit (e.g. 4.2 '%', 12.5 'kg')."""

    model_config = {"frozen": True}

    value: float
    unit: str = Field(default="", max_length=20)
    precision: int = Field(default=2, ge=0, le=6)
