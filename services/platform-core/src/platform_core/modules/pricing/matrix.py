"""Pricing module — Pricing Matrix application service (Increment-002).

A matrix stores the price bands for one product of one rate card along one
configurable quality dimension. DATA ONLY: no price calculation, formulas,
bonuses, penalties, or taxes live here (those are later increments).

Editability follows the owning rate card, mirroring Increment-001's
scope-freeze rule: matrices and rows change only while the card is DRAFT;
the reviewed pricing data is exactly what publishes.
"""

import itertools
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import ConflictError, ForbiddenError, NotFoundError
from platform_core.core.tenancy import get_current_tenant
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.pricing.models import (
    PricingMatrix,
    PricingMatrixRow,
    QualityDimension,
    RateCard,
    RateCardProductAssignment,
)

# Domain event name (work order) -> wire event type (STD-0002).
MATRIX_BUS_EVENTS = {
    "PricingMatrixCreated": "pricing.pricing-matrix-created.v1",
    "PricingMatrixUpdated": "pricing.pricing-matrix-updated.v1",
    "PricingMatrixArchived": "pricing.pricing-matrix-archived.v1",
    "PricingMatrixRowCreated": "pricing.pricing-matrix-row-created.v1",
    "PricingMatrixRowUpdated": "pricing.pricing-matrix-row-updated.v1",
    "PricingMatrixRowDeleted": "pricing.pricing-matrix-row-deleted.v1",
}

# Seeded per tenant on first use; tenants edit and extend them as data.
DEFAULT_DIMENSIONS: tuple[dict, ...] = (
    {"code": "FAT", "name": "Fat", "unit": "%", "min_value": 0.0, "max_value": 15.0},
    {"code": "SNF", "name": "Solids-Not-Fat", "unit": "%", "min_value": 0.0, "max_value": 15.0},
    {
        "code": "CLR",
        "name": "Corrected Lactometer Reading",
        "unit": "°CLR",
        "min_value": 20.0,
        "max_value": 40.0,
    },
    {"code": "DENSITY", "name": "Density", "unit": "g/ml", "min_value": 1.0, "max_value": 1.15},
    {"code": "PROTEIN", "name": "Protein", "unit": "%", "min_value": 0.0, "max_value": 10.0},
    {"code": "MOISTURE", "name": "Moisture", "unit": "%", "min_value": 0.0, "max_value": 100.0},
    {
        "code": "ACIDITY",
        "name": "Titratable Acidity",
        "unit": "%LA",
        "min_value": 0.0,
        "max_value": 2.0,
    },
)

DIMENSION_CODE_PATTERN = r"^[A-Za-z][A-Za-z0-9-]{1,28}$"


# --- DTOs ------------------------------------------------------------------


class DimensionInput(BaseModel):
    code: str = Field(pattern=DIMENSION_CODE_PATTERN)
    name: str = Field(min_length=2, max_length=100)
    unit: str = Field(default="", max_length=20)
    min_value: float | None = None
    max_value: float | None = None

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _valid_bounds(self) -> "DimensionInput":
        if self.min_value is not None and self.max_value is not None:
            if self.max_value <= self.min_value:
                raise ValueError("max_value must be greater than min_value")
        return self


class DimensionView(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    unit: str
    min_value: float | None
    max_value: float | None
    active: bool

    model_config = {"from_attributes": True}


class CreateMatrixCommand(BaseModel):
    rate_card_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    product_code: str = Field(min_length=2, max_length=40)
    product_name: str = Field(default="", max_length=120)
    dimension_code: str = Field(min_length=2, max_length=30)

    @field_validator("product_code", "dimension_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class UpdateMatrixCommand(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    product_code: str = Field(min_length=2, max_length=40)
    product_name: str = Field(default="", max_length=120)
    dimension_code: str = Field(min_length=2, max_length=30)

    @field_validator("product_code", "dimension_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class RowInput(BaseModel):
    from_value: float
    to_value: float
    unit_price: float = Field(gt=0)
    sequence: int | None = Field(default=None, ge=1)
    active: bool = True

    @model_validator(mode="after")
    def _valid_range(self) -> "RowInput":
        if self.to_value <= self.from_value:
            raise ValueError("to_value must be greater than from_value")
        return self


class MatrixView(BaseModel):
    id: uuid.UUID
    rate_card_id: uuid.UUID
    rate_card_code: str
    name: str
    product_code: str
    product_name: str
    dimension_code: str
    status: str
    version: int
    row_count: int
    created_at: datetime
    updated_at: datetime


class RowView(BaseModel):
    id: uuid.UUID
    sequence: int
    from_value: float
    to_value: float
    unit_price: float
    active: bool

    model_config = {"from_attributes": True}


class GapView(BaseModel):
    from_value: float
    to_value: float


class MatrixDetailView(BaseModel):
    matrix: MatrixView
    dimension: DimensionView
    rows: list[RowView]  # ordered by from_value
    gaps: list[GapView]  # holes between consecutive ACTIVE bands (continuity check)
    editable: bool  # true only while the owning rate card is draft


class MatrixPage(BaseModel):
    items: list[MatrixView]
    total: int
    limit: int
    offset: int


def _ranges_overlap(a_from: float, a_to: float, b_from: float, b_to: float) -> bool:
    """Half-open [from, to) ranges: adjacent bands (a_to == b_from) do NOT overlap."""
    return a_from < b_to and b_from < a_to


class PricingMatrixService:
    def __init__(self, session: AsyncSession, bus: EventBus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit

    # --- quality dimensions (business data, seeded once per tenant) --------

    async def list_dimensions(self) -> list[QualityDimension]:
        tenant_id = self._require_tenant()
        await self._ensure_default_dimensions(tenant_id)
        rows = await self._session.scalars(
            select(QualityDimension)
            .where(QualityDimension.tenant_id == tenant_id)
            .order_by(QualityDimension.code)
        )
        return list(rows.all())

    async def create_dimension(
        self, cmd: DimensionInput, *, actor_id: uuid.UUID
    ) -> QualityDimension:
        tenant_id = self._require_tenant()
        await self._ensure_default_dimensions(tenant_id)
        existing = await self._session.scalar(
            select(QualityDimension).where(
                QualityDimension.tenant_id == tenant_id, QualityDimension.code == cmd.code
            )
        )
        if existing is not None:
            raise ConflictError("quality dimension code already exists")
        dimension = QualityDimension(tenant_id=tenant_id, **cmd.model_dump())
        self._session.add(dimension)
        await self._session.flush()
        await self._audit.record(
            action="pricing.dimension_created",
            resource_type="quality_dimension",
            resource_id=dimension.id,
            actor_id=actor_id,
            detail={"code": dimension.code},
        )
        return dimension

    async def _ensure_default_dimensions(self, tenant_id: uuid.UUID) -> None:
        count = await self._session.scalar(
            select(func.count())
            .select_from(QualityDimension)
            .where(QualityDimension.tenant_id == tenant_id)
        )
        if count:
            return
        for spec in DEFAULT_DIMENSIONS:
            self._session.add(QualityDimension(tenant_id=tenant_id, **spec))
        await self._session.flush()

    # --- matrix lifecycle ---------------------------------------------------

    async def create_matrix(
        self, cmd: CreateMatrixCommand, *, actor_id: uuid.UUID
    ) -> PricingMatrix:
        card = await self._get_card(cmd.rate_card_id)
        self._require_card_draft(card)
        await self._require_product_in_scope(card, cmd.product_code)
        await self._get_dimension(card.tenant_id, cmd.dimension_code)
        duplicate = await self._session.scalar(
            select(PricingMatrix).where(
                PricingMatrix.rate_card_id == card.id,
                PricingMatrix.product_code == cmd.product_code,
                PricingMatrix.dimension_code == cmd.dimension_code,
            )
        )
        if duplicate is not None:
            raise ConflictError(
                "this rate card already has a matrix for that product and dimension"
            )
        matrix = PricingMatrix(
            tenant_id=card.tenant_id,
            rate_card_id=card.id,
            name=cmd.name,
            product_code=cmd.product_code,
            product_name=cmd.product_name,
            dimension_code=cmd.dimension_code,
            version=card.version,
        )
        self._session.add(matrix)
        await self._session.flush()
        await self._record(matrix, "PricingMatrixCreated", {}, actor_id)
        return matrix

    async def update_matrix(
        self, matrix_id: uuid.UUID, cmd: UpdateMatrixCommand, *, actor_id: uuid.UUID
    ) -> PricingMatrix:
        matrix, card = await self._editable_matrix(matrix_id)
        if cmd.dimension_code != matrix.dimension_code:
            if await self._row_count(matrix.id):
                raise ConflictError(
                    "cannot change the dimension of a matrix that has rows — delete the rows first"
                )
            await self._get_dimension(card.tenant_id, cmd.dimension_code)
        if cmd.product_code != matrix.product_code:
            await self._require_product_in_scope(card, cmd.product_code)
        if (cmd.product_code, cmd.dimension_code) != (
            matrix.product_code,
            matrix.dimension_code,
        ):
            duplicate = await self._session.scalar(
                select(PricingMatrix).where(
                    PricingMatrix.rate_card_id == card.id,
                    PricingMatrix.product_code == cmd.product_code,
                    PricingMatrix.dimension_code == cmd.dimension_code,
                    PricingMatrix.id != matrix.id,
                )
            )
            if duplicate is not None:
                raise ConflictError(
                    "this rate card already has a matrix for that product and dimension"
                )
        matrix.name = cmd.name
        matrix.product_code = cmd.product_code
        matrix.product_name = cmd.product_name
        matrix.dimension_code = cmd.dimension_code
        await self._record(matrix, "PricingMatrixUpdated", {}, actor_id)
        return matrix

    async def delete_matrix(self, matrix_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        """Hard delete — allowed only while the card is draft (working data,
        never published, so no history is lost)."""
        matrix, _ = await self._editable_matrix(matrix_id)
        for row in await self._rows(matrix.id):
            await self._session.delete(row)
        await self._record(matrix, "PricingMatrixArchived", {"deleted": True}, actor_id)
        await self._session.delete(matrix)
        await self._session.flush()

    # --- rows ---------------------------------------------------------------

    async def add_row(
        self, matrix_id: uuid.UUID, cmd: RowInput, *, actor_id: uuid.UUID
    ) -> PricingMatrixRow:
        matrix, card = await self._editable_matrix(matrix_id)
        dimension = await self._get_dimension(card.tenant_id, matrix.dimension_code)
        self._require_within_bounds(cmd, dimension)
        await self._require_no_overlap(matrix.id, cmd)
        sequence = cmd.sequence
        if sequence is None:
            max_seq = await self._session.scalar(
                select(func.max(PricingMatrixRow.sequence)).where(
                    PricingMatrixRow.matrix_id == matrix.id
                )
            )
            sequence = (max_seq or 0) + 1
        row = PricingMatrixRow(
            matrix_id=matrix.id,
            sequence=sequence,
            from_value=cmd.from_value,
            to_value=cmd.to_value,
            unit_price=cmd.unit_price,
            active=cmd.active,
        )
        self._session.add(row)
        await self._session.flush()
        await self._record(
            matrix,
            "PricingMatrixRowCreated",
            {"row_id": str(row.id), "from": cmd.from_value, "to": cmd.to_value},
            actor_id,
        )
        return row

    async def update_row(
        self, matrix_id: uuid.UUID, row_id: uuid.UUID, cmd: RowInput, *, actor_id: uuid.UUID
    ) -> PricingMatrixRow:
        matrix, card = await self._editable_matrix(matrix_id)
        row = await self._get_row(matrix.id, row_id)
        dimension = await self._get_dimension(card.tenant_id, matrix.dimension_code)
        self._require_within_bounds(cmd, dimension)
        await self._require_no_overlap(matrix.id, cmd, exclude_row_id=row.id)
        row.from_value = cmd.from_value
        row.to_value = cmd.to_value
        row.unit_price = cmd.unit_price
        row.active = cmd.active
        if cmd.sequence is not None:
            row.sequence = cmd.sequence
        await self._record(matrix, "PricingMatrixRowUpdated", {"row_id": str(row.id)}, actor_id)
        return row

    async def delete_row(
        self, matrix_id: uuid.UUID, row_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        matrix, _ = await self._editable_matrix(matrix_id)
        row = await self._get_row(matrix.id, row_id)
        await self._session.delete(row)
        await self._record(matrix, "PricingMatrixRowDeleted", {"row_id": str(row.id)}, actor_id)

    # --- queries ------------------------------------------------------------

    async def get(self, matrix_id: uuid.UUID) -> PricingMatrix:
        tenant_id = self._require_tenant()
        matrix = await self._session.get(PricingMatrix, matrix_id)
        if matrix is None or matrix.tenant_id != tenant_id:
            raise NotFoundError("pricing matrix not found")
        return matrix

    async def detail(self, matrix_id: uuid.UUID) -> MatrixDetailView:
        matrix = await self.get(matrix_id)
        card = await self._session.get(RateCard, matrix.rate_card_id)
        dimension = await self._get_dimension(matrix.tenant_id, matrix.dimension_code)
        rows = await self._rows(matrix.id)
        active = sorted((r for r in rows if r.active), key=lambda r: (r.from_value, r.to_value))
        gaps = [
            GapView(from_value=prev.to_value, to_value=nxt.from_value)
            for prev, nxt in itertools.pairwise(active)
            if nxt.from_value > prev.to_value
        ]
        return MatrixDetailView(
            matrix=self._view(matrix, card.code if card else "", len(rows)),
            dimension=DimensionView.model_validate(dimension),
            rows=[
                RowView.model_validate(r)
                for r in sorted(rows, key=lambda r: (r.from_value, r.to_value))
            ],
            gaps=gaps,
            editable=card is not None and card.status == "draft",
        )

    async def search(
        self,
        *,
        q: str | None = None,
        rate_card_id: uuid.UUID | None = None,
        product_code: str | None = None,
        dimension_code: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> MatrixPage:
        tenant_id = self._require_tenant()
        limit = max(1, min(limit, 100))
        stmt = (
            select(PricingMatrix, RateCard.code)
            .join(RateCard, RateCard.id == PricingMatrix.rate_card_id)
            .where(PricingMatrix.tenant_id == tenant_id)
        )
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(PricingMatrix.name).like(like),
                    func.lower(PricingMatrix.product_code).like(like),
                    func.lower(PricingMatrix.product_name).like(like),
                )
            )
        if rate_card_id:
            stmt = stmt.where(PricingMatrix.rate_card_id == rate_card_id)
        if product_code:
            stmt = stmt.where(PricingMatrix.product_code == product_code.upper())
        if dimension_code:
            stmt = stmt.where(PricingMatrix.dimension_code == dimension_code.upper())
        if status:
            stmt = stmt.where(PricingMatrix.status == status)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        result = await self._session.execute(
            stmt.order_by(PricingMatrix.product_code, PricingMatrix.dimension_code)
            .limit(limit)
            .offset(offset)
        )
        pairs = result.all()
        counts = await self._row_counts([m.id for m, _ in pairs])
        return MatrixPage(
            items=[self._view(m, code, counts.get(m.id, 0)) for m, code in pairs],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    # --- helpers ------------------------------------------------------------

    async def _require_no_overlap(
        self, matrix_id: uuid.UUID, cmd: RowInput, *, exclude_row_id: uuid.UUID | None = None
    ) -> None:
        """BR-0004: active bands must never overlap (duplicates are total
        overlaps). Inactive rows are parked data and do not participate."""
        if not cmd.active:
            return
        for other in await self._rows(matrix_id):
            if other.id == exclude_row_id or not other.active:
                continue
            if _ranges_overlap(cmd.from_value, cmd.to_value, other.from_value, other.to_value):
                raise ConflictError(
                    f"range [{cmd.from_value}, {cmd.to_value}) overlaps existing band "
                    f"[{other.from_value}, {other.to_value})"
                )

    @staticmethod
    def _require_within_bounds(cmd: RowInput, dimension: QualityDimension) -> None:
        if dimension.min_value is not None and cmd.from_value < dimension.min_value:
            raise ConflictError(
                f"from_value is below the {dimension.code} minimum ({dimension.min_value})"
            )
        if dimension.max_value is not None and cmd.to_value > dimension.max_value:
            raise ConflictError(
                f"to_value is above the {dimension.code} maximum ({dimension.max_value})"
            )

    async def _editable_matrix(self, matrix_id: uuid.UUID) -> tuple[PricingMatrix, RateCard]:
        matrix = await self.get(matrix_id)
        card = await self._session.get(RateCard, matrix.rate_card_id)
        if card is None:  # defensive: matrices are created against a live card
            raise NotFoundError("rate card not found")
        self._require_card_draft(card)
        return matrix, card

    @staticmethod
    def _require_card_draft(card: RateCard) -> None:
        if card.status != "draft":
            raise ConflictError(
                "pricing matrices are editable only while the rate card is draft "
                f"(rate card status: {card.status})"
            )

    async def _get_card(self, rate_card_id: uuid.UUID) -> RateCard:
        tenant_id = self._require_tenant()
        card = await self._session.get(RateCard, rate_card_id)
        if card is None or card.tenant_id != tenant_id:
            raise NotFoundError("rate card not found")
        return card

    async def _require_product_in_scope(self, card: RateCard, product_code: str) -> None:
        assigned = await self._session.scalar(
            select(RateCardProductAssignment).where(
                RateCardProductAssignment.rate_card_id == card.id,
                RateCardProductAssignment.product_code == product_code,
            )
        )
        if assigned is None:
            raise ConflictError(f"product {product_code} is not assigned to this rate card")

    async def _get_dimension(self, tenant_id: uuid.UUID, code: str) -> QualityDimension:
        await self._ensure_default_dimensions(tenant_id)
        dimension = await self._session.scalar(
            select(QualityDimension).where(
                QualityDimension.tenant_id == tenant_id, QualityDimension.code == code
            )
        )
        if dimension is None or not dimension.active:
            raise NotFoundError(f"quality dimension {code} not found")
        return dimension

    async def _get_row(self, matrix_id: uuid.UUID, row_id: uuid.UUID) -> PricingMatrixRow:
        row = await self._session.get(PricingMatrixRow, row_id)
        if row is None or row.matrix_id != matrix_id:
            raise NotFoundError("pricing matrix row not found")
        return row

    async def _rows(self, matrix_id: uuid.UUID) -> list[PricingMatrixRow]:
        rows = await self._session.scalars(
            select(PricingMatrixRow).where(PricingMatrixRow.matrix_id == matrix_id)
        )
        return list(rows.all())

    async def _row_count(self, matrix_id: uuid.UUID) -> int:
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(PricingMatrixRow)
                .where(PricingMatrixRow.matrix_id == matrix_id)
            )
            or 0
        )

    async def _row_counts(self, matrix_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not matrix_ids:
            return {}
        rows = await self._session.execute(
            select(PricingMatrixRow.matrix_id, func.count())
            .where(PricingMatrixRow.matrix_id.in_(matrix_ids))
            .group_by(PricingMatrixRow.matrix_id)
        )
        return dict(rows.all())

    def _view(self, matrix: PricingMatrix, rate_card_code: str, row_count: int) -> MatrixView:
        return MatrixView(
            id=matrix.id,
            rate_card_id=matrix.rate_card_id,
            rate_card_code=rate_card_code,
            name=matrix.name,
            product_code=matrix.product_code,
            product_name=matrix.product_name,
            dimension_code=matrix.dimension_code,
            status=matrix.status,
            version=matrix.version,
            row_count=row_count,
            created_at=matrix.created_at,
            updated_at=matrix.updated_at,
        )

    async def _record(
        self, matrix: PricingMatrix, event: str, data: dict, actor_id: uuid.UUID
    ) -> None:
        await self._audit.record(
            action=f"pricing.matrix_{event.removeprefix('PricingMatrix').lower()}",
            resource_type="pricing_matrix",
            resource_id=matrix.id,
            actor_id=actor_id,
            detail={"product": matrix.product_code, "dimension": matrix.dimension_code, **data},
        )
        await self._bus.publish(
            EventEnvelope.new(
                MATRIX_BUS_EVENTS[event],
                {
                    "matrix_id": str(matrix.id),
                    "rate_card_id": str(matrix.rate_card_id),
                    "product_code": matrix.product_code,
                    "dimension_code": matrix.dimension_code,
                    **data,
                },
                actor_id=actor_id,
                aggregate_type="pricing_matrix",
                aggregate_id=matrix.id,
            )
        )

    @staticmethod
    def _require_tenant() -> uuid.UUID:
        tenant_id = get_current_tenant()
        if tenant_id is None:
            raise ForbiddenError("tenant context required")
        return tenant_id
