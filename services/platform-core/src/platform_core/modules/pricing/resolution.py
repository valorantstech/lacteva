"""Pricing module — Pricing Resolution Engine (PRC-003).

READ-SIDE ONLY. Given (center, product, transaction date, quality dimension,
reading) the engine selects the ONE pricing-matrix row that applies — the
decision layer between master pricing data and the future Pricing
Calculator (PRC-004). It calculates nothing, mutates nothing, and emits no
events.

BR-0003 (see docs/03-architecture/01-business-layer/BUSINESS-RULES.md):
exactly one published rate card, one active matrix, one active band must
match. Zero matches raise a structured business exception naming the
failing stage; multiple matches raise a business *integrity* exception
(defending BR-0002/BR-0004 at read time). The engine never silently
chooses and never guesses.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.core.errors import AppError
from platform_core.core.tenancy import require_current_tenant
from platform_core.core.types import Money, Quantity
from platform_core.modules.pricing.models import (
    PricingMatrix,
    PricingMatrixRow,
    QualityDimension,
    RateCard,
    RateCardCenterAssignment,
    RateCardProductAssignment,
)

# Resolution stages, in evaluation order (used in structured exceptions).
STAGE_DIMENSION = "dimension"
STAGE_RATE_CARD = "rate_card"
STAGE_MATRIX = "matrix"
STAGE_BAND = "band"


class PricingResolutionError(AppError):
    """No applicable pricing (business exception). `detail` is a structured
    dict: {stage, reason, inputs, ...} — machine-readable for clients."""

    status_code = 422
    code = "pricing_no_match"
    message_key = "error.pricing_no_match"


class PricingIntegrityError(AppError):
    """More than one candidate matched where the platform invariants promise
    exactly one — pricing data needs administrator attention."""

    status_code = 409
    code = "pricing_integrity"
    message_key = "error.pricing_integrity"


# --- value objects / DTOs ---------------------------------------------------


class ResolutionQuery(BaseModel):
    """Value object: the exact question being asked of the engine."""

    model_config = {"frozen": True}

    center_id: uuid.UUID
    product_code: str = Field(min_length=2, max_length=40)
    transaction_date: date
    dimension_code: str = Field(min_length=2, max_length=30)
    value: float

    @field_validator("product_code", "dimension_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class MatchedRange(BaseModel):
    model_config = {"frozen": True}

    from_value: float
    to_value: float  # exclusive (half-open band)


class ResolutionResult(BaseModel):
    """The single applicable band, with full provenance for auditability."""

    rate_card_id: uuid.UUID
    rate_card_code: str
    rate_card_version: int
    matrix_id: uuid.UUID
    matrix_name: str
    row_id: uuid.UUID
    row_sequence: int
    matching_range: MatchedRange
    unit_price: Money
    reading: Quantity
    metadata: dict


class PricingResolutionRepository:
    """Lookup queries for pricing resolution.

    Deliberately a separate, injectable class (not folded into a service):
    the future Pricing Calculator (PRC-004) reuses exactly these methods.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def band_candidates(
        self, rate_card_id: uuid.UUID, q: ResolutionQuery
    ) -> list[tuple[PricingMatrix, PricingMatrixRow]]:
        """Matrix x band candidates within ONE rate card, as a single joined
        query. Query count never grows with the number of bands (no N+1)."""
        stmt = (
            select(PricingMatrix, PricingMatrixRow)
            .join(PricingMatrixRow, PricingMatrixRow.matrix_id == PricingMatrix.id)
            .where(
                PricingMatrix.rate_card_id == rate_card_id,
                PricingMatrix.product_code == q.product_code,
                PricingMatrix.dimension_code == q.dimension_code,
                PricingMatrix.status == "active",
                PricingMatrixRow.active,
                PricingMatrixRow.from_value <= q.value,
                PricingMatrixRow.to_value > q.value,  # half-open [from, to)
            )
        )
        result = await self._session.execute(stmt)
        return [(m, r) for m, r in result.all()]

    async def applicable_cards(
        self,
        tenant_id: uuid.UUID,
        center_id: uuid.UUID,
        product_code: str,
        on: date,
    ) -> list[RateCard]:
        """Published cards covering (center, product, date) — invariantly ≤ 1."""
        stmt = (
            select(RateCard)
            .join(
                RateCardCenterAssignment,
                RateCardCenterAssignment.rate_card_id == RateCard.id,
            )
            .join(
                RateCardProductAssignment,
                RateCardProductAssignment.rate_card_id == RateCard.id,
            )
            .where(
                RateCard.tenant_id == tenant_id,
                RateCard.status == "published",
                RateCard.effective_from <= on,
                or_(RateCard.effective_until.is_(None), RateCard.effective_until >= on),
                RateCardCenterAssignment.center_id == center_id,
                RateCardProductAssignment.product_code == product_code,
            )
        )
        return list((await self._session.scalars(stmt)).all())

    async def active_matrices(
        self, rate_card_id: uuid.UUID, product_code: str, dimension_code: str
    ) -> list[PricingMatrix]:
        """Active matrices for (card, product, dimension) — unique-constrained ≤ 1."""
        stmt = select(PricingMatrix).where(
            PricingMatrix.rate_card_id == rate_card_id,
            PricingMatrix.product_code == product_code,
            PricingMatrix.dimension_code == dimension_code,
            PricingMatrix.status == "active",
        )
        return list((await self._session.scalars(stmt)).all())

    async def matching_rows(self, matrix_id: uuid.UUID, value: float) -> list[PricingMatrixRow]:
        """Active bands containing value — the no-overlap invariant makes ≤ 1."""
        stmt = select(PricingMatrixRow).where(
            PricingMatrixRow.matrix_id == matrix_id,
            PricingMatrixRow.active,
            PricingMatrixRow.from_value <= value,
            PricingMatrixRow.to_value > value,
        )
        return list((await self._session.scalars(stmt)).all())

    async def dimension(self, tenant_id: uuid.UUID, code: str) -> QualityDimension | None:
        return await self._session.scalar(
            select(QualityDimension).where(
                QualityDimension.tenant_id == tenant_id, QualityDimension.code == code
            )
        )


class PricingResolutionService:
    """Application service: orchestrates the repository, enforces the
    exactly-one rule, and shapes the result. No calculation, no writes."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self.repository = PricingResolutionRepository(session)

    async def resolve(self, q: ResolutionQuery) -> ResolutionResult:
        """Three fixed queries: dimension → the ONE applicable rate card →
        the ONE matrix x band candidate. Every stage enforces exactly-one:
        the engine never silently chooses between candidates."""
        tenant_id = require_current_tenant()
        dimension = await self.repository.dimension(tenant_id, q.dimension_code)
        if dimension is None:
            raise PricingResolutionError(
                self._no_match(STAGE_DIMENSION, q, "unknown quality dimension")
            )

        cards = await self.repository.applicable_cards(
            tenant_id, q.center_id, q.product_code, q.transaction_date
        )
        if not cards:
            raise PricingResolutionError(
                self._no_match(
                    STAGE_RATE_CARD,
                    q,
                    "no published rate card covers this center, product, and date",
                )
            )
        if len(cards) > 1:
            raise PricingIntegrityError(
                self._ambiguity_meta(STAGE_RATE_CARD, q, sorted(str(c.id) for c in cards))
            )
        card = cards[0]

        candidates = await self.repository.band_candidates(card.id, q)
        if len(candidates) == 1:
            matrix, row = candidates[0]
            return self._result(card, matrix, row, q, dimension, now=utcnow())
        if len(candidates) > 1:
            raise PricingIntegrityError(
                self._ambiguity_meta(STAGE_BAND, q, sorted(str(r.id) for _, r in candidates))
            )
        # Zero candidates: one cheap probe tells the caller WHERE it failed —
        # no active matrix at all, or a matrix whose bands miss the reading.
        matrices = await self.repository.active_matrices(card.id, q.product_code, q.dimension_code)
        if not matrices:
            raise PricingResolutionError(
                self._no_match(
                    STAGE_MATRIX,
                    q,
                    f"rate card {card.code} v{card.version} has no active matrix "
                    f"for this product and dimension",
                )
            )
        raise PricingResolutionError(
            self._no_match(
                STAGE_BAND,
                q,
                f"no active price band of matrix '{matrices[0].name}' contains "
                f"the reading {q.value}",
            )
        )

    @staticmethod
    def _inputs(q: ResolutionQuery) -> dict:
        return {
            "center_id": str(q.center_id),
            "product_code": q.product_code,
            "transaction_date": q.transaction_date.isoformat(),
            "dimension_code": q.dimension_code,
            "value": q.value,
        }

    def _no_match(self, stage: str, q: ResolutionQuery, reason: str) -> dict:
        return {"stage": stage, "reason": reason, "inputs": self._inputs(q)}

    def _ambiguity_meta(self, stage: str, q: ResolutionQuery, candidate_ids: list[str]) -> dict:
        return {
            "stage": stage,
            "reason": "multiple candidates matched where exactly one is required",
            "candidates": candidate_ids,
            "inputs": self._inputs(q),
        }

    # --- result shaping -----------------------------------------------------

    def _result(
        self,
        card: RateCard,
        matrix: PricingMatrix,
        row: PricingMatrixRow,
        q: ResolutionQuery,
        dimension: QualityDimension,
        *,
        now: datetime,
    ) -> ResolutionResult:
        return ResolutionResult(
            rate_card_id=card.id,
            rate_card_code=card.code,
            rate_card_version=card.version,
            matrix_id=matrix.id,
            matrix_name=matrix.name,
            row_id=row.id,
            row_sequence=row.sequence,
            matching_range=MatchedRange(from_value=row.from_value, to_value=row.to_value),
            unit_price=Money.of(row.unit_price, card.currency),
            reading=Quantity(value=q.value, unit=dimension.unit),
            metadata={
                "strategy": "single-query",
                "resolved_at": now.isoformat(),
                "effective_from": card.effective_from.isoformat(),
                "effective_until": (
                    card.effective_until.isoformat() if card.effective_until else None
                ),
                "product_code": matrix.product_code,
                "dimension_code": matrix.dimension_code,
                "dimension_name": dimension.name,
                "center_id": str(q.center_id),
            },
        )
