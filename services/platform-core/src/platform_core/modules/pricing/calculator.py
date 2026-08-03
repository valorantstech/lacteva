"""Pricing module — Pricing Calculator (PRC-004).

The FIRST component allowed to perform monetary calculation. Scope is
intentionally simple: Gross Amount = Unit Price x Quantity — no bonuses,
penalties, taxes, discounts, settlement, or formula engine (later
increments).

Rules (Business Rules Register):
- BR-0005: monetary calculation is Decimal-only under an explicit,
  configurable rounding policy — float arithmetic is forbidden.
- BR-0006: every calculation result carries a complete trace explaining
  each step from inputs to rounded output.
- BR-0007: calculation is deterministic — the same input always produces
  the same monetary output.

The calculator NEVER performs pricing resolution: it consumes the output
of a successful resolution (PRC-003). The application service re-verifies
the resolved band against the database (read-only) so clients submit a
row id, never a price — client-supplied amounts are not trusted.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.core.errors import AppError, NotFoundError
from platform_core.core.tenancy import require_current_tenant
from platform_core.core.types import (
    DEFAULT_ROUNDING_POLICY,
    ROUNDING_POLICIES,
    Money,
    Quantity,
)
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.configuration.service import ConfigurationService
from platform_core.modules.pricing.models import PricingMatrix, PricingMatrixRow, RateCard

CALCULATOR_VERSION = "1.0.0"
CALCULATED_EVENT = "pricing.calculated.v1"
ROUNDING_POLICY_CONFIG_KEY = "pricing.rounding_policy"


class PricingCalculationError(AppError):
    """The resolved band can no longer be calculated against (business
    exception). `detail` is structured: {reason, inputs}."""

    status_code = 422
    code = "pricing_calculation_invalid"
    message_key = "error.pricing_no_match"


# --- value objects -----------------------------------------------------------


class TraceStep(BaseModel):
    """One explained step of a calculation (BR-0006). Values are strings —
    exact Decimal representations, safe for any transport."""

    model_config = {"frozen": True}

    sequence: int
    operation: str  # inputs | normalize | multiply | round
    detail: str
    values: dict[str, str]


class ResolutionTraceRef(BaseModel):
    """Provenance: WHICH pricing data produced the unit price."""

    model_config = {"frozen": True}

    rate_card_id: uuid.UUID
    rate_card_code: str
    rate_card_version: int
    matrix_id: uuid.UUID
    matrix_name: str
    row_id: uuid.UUID
    range_from: float
    range_to: float


class Calculation(BaseModel):
    """Domain result: the money outcome plus its full trace."""

    model_config = {"frozen": True}

    unit_price: Money
    quantity: Quantity
    gross_amount: Money
    currency: str
    rounding_policy: str
    calculator_version: str
    trace: list[TraceStep]


class CalculationResult(BaseModel):
    """API result: the domain calculation plus provenance and identity."""

    calculation_id: uuid.UUID
    unit_price: Money
    quantity: Quantity
    gross_amount: Money
    currency: str
    rounding_policy: str
    calculator_version: str
    calculated_at: datetime
    resolution: ResolutionTraceRef
    trace: list[TraceStep]


class CalculationRequest(BaseModel):
    """Input: the resolved row (by id — prices are never client-supplied)
    plus the transaction quantity."""

    row_id: uuid.UUID  # from a successful POST /v1/pricing/resolve
    quantity: float = Field(ge=0)  # zero is legal (empty container), negative is not
    quantity_unit: str = Field(default="kg", max_length=20)
    transaction_date: date
    rounding_policy: str | None = None  # override; else tenant config; else HALF_UP

    @field_validator("rounding_policy")
    @classmethod
    def _known_policy(cls, v: str | None) -> str | None:
        if v is not None and v not in ROUNDING_POLICIES:
            raise ValueError(
                f"unknown rounding policy {v!r} — supported: {sorted(ROUNDING_POLICIES)}"
            )
        return v


# --- domain service ----------------------------------------------------------


class PricingCalculator:
    """Pure, deterministic domain service (BR-0007): no I/O, no clock, no
    randomness — Money in, Money out, every step traced."""

    def calculate(
        self, *, unit_price: Money, quantity: Quantity, rounding_policy: str
    ) -> Calculation:
        if rounding_policy not in ROUNDING_POLICIES:
            raise ValueError(
                f"unknown rounding policy {rounding_policy!r} — "
                f"supported: {sorted(ROUNDING_POLICIES)}"
            )
        if quantity.value < 0:
            raise ValueError("quantity must not be negative")
        factor = quantity.as_decimal()
        raw = unit_price.amount * factor  # Decimal x Decimal — BR-0005
        gross = unit_price.multiplied_by(factor, rounding_policy=rounding_policy)
        trace = [
            TraceStep(
                sequence=1,
                operation="inputs",
                detail=(
                    f"unit price {unit_price.amount} {unit_price.currency} per "
                    f"{quantity.unit or 'unit'}; quantity {factor} {quantity.unit}"
                ),
                values={
                    "unit_price": str(unit_price.amount),
                    "currency": unit_price.currency,
                    "quantity": str(factor),
                    "unit": quantity.unit,
                },
            ),
            TraceStep(
                sequence=2,
                operation="normalize",
                detail="all values as Decimal via Decimal(str(x)) — no float arithmetic",
                values={"unit_price": str(unit_price.amount), "quantity": str(factor)},
            ),
            TraceStep(
                sequence=3,
                operation="multiply",
                detail="gross = unit price x quantity (exact, unrounded)",
                values={
                    "expression": f"{unit_price.amount} x {factor}",
                    "raw_amount": str(raw),
                },
            ),
            TraceStep(
                sequence=4,
                operation="round",
                detail=(
                    f"{rounding_policy} to {unit_price.precision} decimal place(s) "
                    f"({unit_price.currency} minor units)"
                ),
                values={
                    "policy": rounding_policy,
                    "precision": str(unit_price.precision),
                    "raw_amount": str(raw),
                    "rounded_amount": str(gross.amount),
                },
            ),
        ]
        return Calculation(
            unit_price=unit_price,
            quantity=quantity,
            gross_amount=gross,
            currency=unit_price.currency,
            rounding_policy=rounding_policy,
            calculator_version=CALCULATOR_VERSION,
            trace=trace,
        )


# --- application service -----------------------------------------------------


class PricingCalculationService:
    """Verifies the resolved band against the database (read-only), applies
    the rounding-policy configuration, runs the domain calculator, and
    emits `pricing.calculated.v1` through the Relay. Stateless: the outbox
    event IS the durable record (no calculation table exists yet)."""

    def __init__(self, session: AsyncSession, bus: EventBus, config: ConfigurationService):
        self._session = session
        self._bus = bus
        self._config = config
        self._calculator = PricingCalculator()

    async def calculate(self, req: CalculationRequest, *, actor_id: uuid.UUID) -> CalculationResult:
        tenant_id = require_current_tenant()
        row, matrix, card = await self._verified_band(tenant_id, req)
        policy = await self._rounding_policy(req)
        calculation = self._calculator.calculate(
            unit_price=Money.of(row.unit_price, card.currency),
            quantity=Quantity(value=req.quantity, unit=req.quantity_unit),
            rounding_policy=policy,
        )
        calculation_id = uuid.uuid4()
        now = utcnow()
        await self._bus.publish(
            EventEnvelope.new(
                CALCULATED_EVENT,
                {
                    "calculation_id": str(calculation_id),
                    "rate_card_id": str(card.id),
                    "matrix_id": str(matrix.id),
                    "row_id": str(row.id),
                    "quantity": str(calculation.quantity.as_decimal()),
                    "quantity_unit": calculation.quantity.unit,
                    "unit_price": str(calculation.unit_price.amount),
                    "gross_amount": str(calculation.gross_amount.amount),
                    "currency": calculation.currency,
                    "rounding_policy": calculation.rounding_policy,
                    "calculator_version": calculation.calculator_version,
                    "transaction_date": req.transaction_date.isoformat(),
                },
                actor_id=actor_id,
                aggregate_type="pricing_calculation",
                aggregate_id=calculation_id,
            )
        )
        return CalculationResult(
            calculation_id=calculation_id,
            unit_price=calculation.unit_price,
            quantity=calculation.quantity,
            gross_amount=calculation.gross_amount,
            currency=calculation.currency,
            rounding_policy=calculation.rounding_policy,
            calculator_version=calculation.calculator_version,
            calculated_at=now,
            resolution=ResolutionTraceRef(
                rate_card_id=card.id,
                rate_card_code=card.code,
                rate_card_version=card.version,
                matrix_id=matrix.id,
                matrix_name=matrix.name,
                row_id=row.id,
                range_from=row.from_value,
                range_to=row.to_value,
            ),
            trace=calculation.trace,
        )

    # --- helpers ------------------------------------------------------------

    async def _verified_band(
        self, tenant_id: uuid.UUID, req: CalculationRequest
    ) -> tuple[PricingMatrixRow, PricingMatrix, RateCard]:
        """The calculator never resolves — but it also never trusts: the
        client's resolved row is re-verified against current pricing data."""
        row = await self._session.get(PricingMatrixRow, req.row_id)
        matrix = await self._session.get(PricingMatrix, row.matrix_id) if row is not None else None
        if row is None or matrix is None or matrix.tenant_id != tenant_id:
            raise NotFoundError("pricing matrix row not found")
        card = await self._session.get(RateCard, matrix.rate_card_id)
        problems = []
        if not row.active:
            problems.append("the resolved band is inactive")
        if matrix.status != "active":
            problems.append(f"the pricing matrix is {matrix.status}, not active")
        if card is None or card.status != "published":
            problems.append("the rate card is no longer published")
        elif not (
            card.effective_from <= req.transaction_date
            and (card.effective_until is None or card.effective_until >= req.transaction_date)
        ):
            problems.append("the transaction date is outside the rate card's effective window")
        if problems:
            raise PricingCalculationError(
                {
                    "reason": "; ".join(problems),
                    "inputs": {
                        "row_id": str(req.row_id),
                        "transaction_date": req.transaction_date.isoformat(),
                    },
                }
            )
        return row, matrix, card

    async def _rounding_policy(self, req: CalculationRequest) -> str:
        """Request override -> tenant configuration -> platform default."""
        if req.rounding_policy is not None:
            return req.rounding_policy
        try:
            configured = await self._config.resolve(ROUNDING_POLICY_CONFIG_KEY)
        except NotFoundError:
            return DEFAULT_ROUNDING_POLICY
        if configured not in ROUNDING_POLICIES:
            raise PricingCalculationError(
                {
                    "reason": (
                        f"tenant configuration {ROUNDING_POLICY_CONFIG_KEY}={configured!r} "
                        f"is not a supported rounding policy {sorted(ROUNDING_POLICIES)}"
                    ),
                    "inputs": {"config_key": ROUNDING_POLICY_CONFIG_KEY},
                }
            )
        return configured
