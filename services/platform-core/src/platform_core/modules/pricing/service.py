"""Pricing module — application service for the Rate Card lifecycle.

Workflow: draft -> under_review -> approved -> published -> archived.
Only drafts (fields AND scope assignments) may be edited; published versions
are immutable; archived is terminal; history is never deleted. Changes to a
published card happen on a NEW draft version created from it.

NO pricing calculations live here (Increment-001 wall).
"""

import secrets
import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.org_context import tenant_currency
from platform_core.core.tenancy import require_current_tenant
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.collection_center.models import CollectionCenter
from platform_core.modules.organization.models import Branch
from platform_core.modules.pricing.models import (
    PricingMatrix,
    PricingMatrixRow,
    RateCard,
    RateCardCenterAssignment,
    RateCardProductAssignment,
)

# Domain event name (work order) -> wire event type (STD-0002).
BUS_EVENTS = {
    "RateCardCreated": "pricing.rate-card-created.v1",
    "RateCardUpdated": "pricing.rate-card-updated.v1",
    "RateCardSubmitted": "pricing.rate-card-submitted.v1",
    "RateCardApproved": "pricing.rate-card-approved.v1",
    "RateCardPublished": "pricing.rate-card-published.v1",
    "RateCardArchived": "pricing.rate-card-archived.v1",
}

OPEN_STATUSES = ("draft", "under_review", "approved")  # pre-publish, mutable-workflow states

CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]{1,28}$"
PRODUCT_CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]{1,38}$"


# --- DTOs ------------------------------------------------------------------


class RateCardInput(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=500)
    #: DEMO-013: optional, defaulting to the ORGANIZATION's currency. It was
    #: required, which meant every caller stated a currency — and the demo
    #: seeder stated "KES", so an Indian dairy's procurement side reported its
    #: collection value in Kenyan shillings while its sales side reported
    #: rupees. Still overridable: a rate card in another currency is a real
    #: arrangement, and the column has always carried one.
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    effective_from: date
    effective_until: date | None = None
    branch_id: uuid.UUID | None = None

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return v.upper()

    @model_validator(mode="after")
    def _valid_range(self) -> "RateCardInput":
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValueError("effective_until must be after effective_from")
        return self


class CreateRateCardCommand(RateCardInput):
    code: str | None = Field(default=None, pattern=CODE_PATTERN)


class AssignProductCommand(BaseModel):
    product_code: str = Field(pattern=PRODUCT_CODE_PATTERN)
    product_name: str = Field(default="", max_length=120)

    @field_validator("product_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class RateCardView(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    currency: str
    effective_from: date
    effective_until: date | None
    status: str
    version: int
    branch_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    archived_at: datetime | None

    model_config = {"from_attributes": True}


class ProductAssignmentView(BaseModel):
    product_code: str
    product_name: str

    model_config = {"from_attributes": True}


class RateCardDetailView(BaseModel):
    card: RateCardView
    center_ids: list[uuid.UUID]
    products: list[ProductAssignmentView]
    # Placeholder only — populated by Increment-002 (Rate Tables). Always [].
    pricing_rules: list[dict]


class RateCardPage(BaseModel):
    items: list[RateCardView]
    total: int
    limit: int
    offset: int


def _overlaps(a_from: date, a_until: date | None, b_from: date, b_until: date | None) -> bool:
    """Closed date ranges; None = open-ended (applies forever)."""
    return (a_until is None or b_from <= a_until) and (b_until is None or a_from <= b_until)


class RateCardService:
    def __init__(self, session: AsyncSession, bus: EventBus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit

    # --- lifecycle --------------------------------------------------------

    async def create(self, cmd: CreateRateCardCommand, *, actor_id: uuid.UUID) -> RateCard:
        tenant_id = require_current_tenant()
        await self._check_branch(cmd.branch_id, tenant_id)
        code = cmd.code.upper() if cmd.code else await self._generate_code(tenant_id)
        existing = await self._session.scalar(
            select(RateCard).where(RateCard.tenant_id == tenant_id, RateCard.code == code)
        )
        if existing is not None:
            raise ConflictError(
                "rate card code already exists — create a new version of it instead"
            )
        card = RateCard(
            tenant_id=tenant_id,
            branch_id=cmd.branch_id,
            code=code,
            name=cmd.name,
            description=cmd.description,
            currency=cmd.currency or await tenant_currency(self._session),
            effective_from=cmd.effective_from,
            effective_until=cmd.effective_until,
        )
        self._session.add(card)
        await self._session.flush()
        await self._record(card, "RateCardCreated", {"version": card.version}, actor_id)
        return card

    async def update_draft(
        self, card_id: uuid.UUID, cmd: RateCardInput, *, actor_id: uuid.UUID
    ) -> RateCard:
        card = await self.get(card_id)
        self._require_draft(card)
        await self._check_branch(cmd.branch_id, card.tenant_id)
        card.name = cmd.name
        card.description = cmd.description
        card.currency = cmd.currency
        card.effective_from = cmd.effective_from
        card.effective_until = cmd.effective_until
        card.branch_id = cmd.branch_id
        await self._record(card, "RateCardUpdated", {"version": card.version}, actor_id)
        return card

    async def submit_for_review(self, card_id: uuid.UUID, *, actor_id: uuid.UUID) -> RateCard:
        card = await self.get(card_id)
        if card.status != "draft":
            raise ConflictError("only draft rate cards can be submitted for review")
        card.status = "under_review"
        await self._record(card, "RateCardSubmitted", {}, actor_id)
        return card

    async def approve(self, card_id: uuid.UUID, *, actor_id: uuid.UUID) -> RateCard:
        card = await self.get(card_id)
        if card.status != "under_review":
            raise ConflictError("only rate cards under review can be approved")
        card.status = "approved"
        await self._record(card, "RateCardApproved", {}, actor_id)
        return card

    async def publish(self, card_id: uuid.UUID, *, actor_id: uuid.UUID) -> RateCard:
        card = await self.get(card_id)
        if card.status != "approved":
            raise ConflictError("only approved rate cards can be published")
        center_ids = await self._center_ids(card.id)
        if not center_ids:
            raise ConflictError("publishing requires at least one collection center assignment")
        product_codes = await self._product_codes(card.id)
        if not product_codes:
            raise ConflictError("publishing requires at least one product assignment")
        await self._assert_no_published_overlap(card, center_ids, product_codes)
        now = utcnow()
        # CAS: concurrent publish attempts cannot both succeed.
        claim = await self._session.execute(
            update(RateCard)
            .where(RateCard.id == card.id, RateCard.status == "approved")
            .values(status="published", published_at=now, updated_at=now)
        )
        if claim.rowcount != 1:
            raise ConflictError("rate card is no longer approved")
        await self._session.refresh(card)
        await self._transition_matrices(card, "draft", "active", actor_id=actor_id)
        await self._record(
            card,
            "RateCardPublished",
            {
                "version": card.version,
                "effective_from": card.effective_from.isoformat(),
                "effective_until": (
                    card.effective_until.isoformat() if card.effective_until else None
                ),
            },
            actor_id,
        )
        return card

    async def archive(self, card_id: uuid.UUID, *, actor_id: uuid.UUID) -> RateCard:
        card = await self.get(card_id)
        if card.status == "archived":
            raise ConflictError("rate card is already archived")
        previous = card.status
        card.status = "archived"
        card.archived_at = utcnow()
        await self._transition_matrices(card, "draft", "archived", actor_id=actor_id)
        await self._transition_matrices(card, "active", "archived", actor_id=actor_id)
        await self._record(card, "RateCardArchived", {"from": previous}, actor_id)
        return card

    async def new_version(self, card_id: uuid.UUID, *, actor_id: uuid.UUID) -> RateCard:
        """Create the next draft version of a published/archived card.

        The source version is never touched — this is how a published
        (immutable) rate card evolves while its history stays intact.
        """
        source = await self.get(card_id)
        if source.status not in ("published", "archived"):
            raise ConflictError("new versions are created from published or archived rate cards")
        open_version = await self._session.scalar(
            select(RateCard).where(
                RateCard.tenant_id == source.tenant_id,
                RateCard.code == source.code,
                RateCard.status.in_(OPEN_STATUSES),
            )
        )
        if open_version is not None:
            raise ConflictError(
                f"version {open_version.version} of this rate card is still "
                f"{open_version.status} — finish or archive it first"
            )
        max_version = await self._session.scalar(
            select(func.max(RateCard.version)).where(
                RateCard.tenant_id == source.tenant_id, RateCard.code == source.code
            )
        )
        card = RateCard(
            tenant_id=source.tenant_id,
            branch_id=source.branch_id,
            code=source.code,
            name=source.name,
            description=source.description,
            currency=source.currency,
            effective_from=source.effective_from,
            effective_until=source.effective_until,
            version=(max_version or source.version) + 1,
        )
        self._session.add(card)
        await self._session.flush()
        for center_id in await self._center_ids(source.id):
            self._session.add(
                RateCardCenterAssignment(
                    tenant_id=card.tenant_id, rate_card_id=card.id, center_id=center_id
                )
            )
        for product in await self._products(source.id):
            self._session.add(
                RateCardProductAssignment(
                    tenant_id=card.tenant_id,
                    rate_card_id=card.id,
                    product_code=product.product_code,
                    product_name=product.product_name,
                )
            )
        await self._copy_matrices(source, card, actor_id=actor_id)
        await self._session.flush()
        await self._record(
            card,
            "RateCardCreated",
            {"version": card.version, "source_version": source.version},
            actor_id,
        )
        return card

    # --- scope assignments (draft-only: scope is frozen from submission on) --

    async def assign_center(
        self, card_id: uuid.UUID, center_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> RateCardCenterAssignment:
        card = await self.get(card_id)
        self._require_draft(card)
        center = await self._session.get(CollectionCenter, center_id)
        if center is None or center.tenant_id != card.tenant_id:
            raise NotFoundError("collection center not found")
        existing = await self._session.scalar(
            select(RateCardCenterAssignment).where(
                RateCardCenterAssignment.rate_card_id == card.id,
                RateCardCenterAssignment.center_id == center.id,
            )
        )
        if existing is not None:
            raise ConflictError("rate card is already assigned to this center")
        assignment = RateCardCenterAssignment(
            tenant_id=card.tenant_id, rate_card_id=card.id, center_id=center.id
        )
        self._session.add(assignment)
        await self._session.flush()
        await self._record(card, "RateCardUpdated", {"center_assigned": str(center.id)}, actor_id)
        return assignment

    async def unassign_center(
        self, card_id: uuid.UUID, center_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        card = await self.get(card_id)
        self._require_draft(card)
        assignment = await self._session.scalar(
            select(RateCardCenterAssignment).where(
                RateCardCenterAssignment.rate_card_id == card.id,
                RateCardCenterAssignment.center_id == center_id,
            )
        )
        if assignment is None:
            raise NotFoundError("assignment not found")
        await self._session.delete(assignment)
        await self._record(card, "RateCardUpdated", {"center_unassigned": str(center_id)}, actor_id)

    async def assign_product(
        self, card_id: uuid.UUID, cmd: AssignProductCommand, *, actor_id: uuid.UUID
    ) -> RateCardProductAssignment:
        card = await self.get(card_id)
        self._require_draft(card)
        existing = await self._session.scalar(
            select(RateCardProductAssignment).where(
                RateCardProductAssignment.rate_card_id == card.id,
                RateCardProductAssignment.product_code == cmd.product_code,
            )
        )
        if existing is not None:
            raise ConflictError("product is already assigned to this rate card")
        assignment = RateCardProductAssignment(
            tenant_id=card.tenant_id,
            rate_card_id=card.id,
            product_code=cmd.product_code,
            product_name=cmd.product_name,
        )
        self._session.add(assignment)
        await self._session.flush()
        await self._record(
            card, "RateCardUpdated", {"product_assigned": cmd.product_code}, actor_id
        )
        return assignment

    async def unassign_product(
        self, card_id: uuid.UUID, product_code: str, *, actor_id: uuid.UUID
    ) -> None:
        card = await self.get(card_id)
        self._require_draft(card)
        assignment = await self._session.scalar(
            select(RateCardProductAssignment).where(
                RateCardProductAssignment.rate_card_id == card.id,
                RateCardProductAssignment.product_code == product_code.upper(),
            )
        )
        if assignment is None:
            raise NotFoundError("assignment not found")
        await self._session.delete(assignment)
        await self._record(
            card, "RateCardUpdated", {"product_unassigned": product_code.upper()}, actor_id
        )

    # --- queries -----------------------------------------------------------

    async def get(self, card_id: uuid.UUID) -> RateCard:
        tenant_id = require_current_tenant()
        card = await self._session.get(RateCard, card_id)
        if card is None or card.tenant_id != tenant_id:
            raise NotFoundError("rate card not found")
        return card

    async def detail(self, card_id: uuid.UUID) -> RateCardDetailView:
        card = await self.get(card_id)
        return RateCardDetailView(
            card=RateCardView.model_validate(card),
            center_ids=await self._center_ids(card.id),
            products=[
                ProductAssignmentView.model_validate(p) for p in await self._products(card.id)
            ],
            pricing_rules=[],
        )

    async def search(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        currency: str | None = None,
        center_id: uuid.UUID | None = None,
        product_code: str | None = None,
        active_on: date | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> RateCardPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        stmt = select(RateCard).where(RateCard.tenant_id == tenant_id)
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(func.lower(RateCard.code).like(like), func.lower(RateCard.name).like(like))
            )
        if status:
            stmt = stmt.where(RateCard.status == status)
        if currency:
            stmt = stmt.where(RateCard.currency == currency.upper())
        if center_id:
            stmt = stmt.join(
                RateCardCenterAssignment, RateCardCenterAssignment.rate_card_id == RateCard.id
            ).where(RateCardCenterAssignment.center_id == center_id)
        if product_code:
            stmt = stmt.join(
                RateCardProductAssignment, RateCardProductAssignment.rate_card_id == RateCard.id
            ).where(RateCardProductAssignment.product_code == product_code.upper())
        if active_on:
            stmt = stmt.where(
                RateCard.status == "published",
                RateCard.effective_from <= active_on,
                or_(
                    RateCard.effective_until.is_(None),
                    RateCard.effective_until >= active_on,
                ),
            )
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.scalars(
            stmt.order_by(RateCard.code, RateCard.version.desc()).limit(limit).offset(offset)
        )
        return RateCardPage(
            items=[RateCardView.model_validate(c) for c in rows.all()],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    # --- helpers ------------------------------------------------------------

    async def _assert_no_published_overlap(
        self, card: RateCard, center_ids: list[uuid.UUID], product_codes: list[str]
    ) -> None:
        """BR-0002: only one published rate card may be active for the same
        scope — (collection center, product) with overlapping effective dates."""
        stmt = (
            select(RateCard)
            .join(RateCardCenterAssignment, RateCardCenterAssignment.rate_card_id == RateCard.id)
            .join(RateCardProductAssignment, RateCardProductAssignment.rate_card_id == RateCard.id)
            .where(
                RateCard.tenant_id == card.tenant_id,
                RateCard.status == "published",
                RateCard.id != card.id,
                RateCardCenterAssignment.center_id.in_(center_ids),
                RateCardProductAssignment.product_code.in_(product_codes),
            )
            .distinct()
        )
        for other in (await self._session.scalars(stmt)).all():
            if _overlaps(
                card.effective_from,
                card.effective_until,
                other.effective_from,
                other.effective_until,
            ):
                raise ConflictError(
                    f"effective dates overlap published rate card {other.code} "
                    f"v{other.version} on a shared center/product scope"
                )

    async def _record(self, card: RateCard, event: str, data: dict, actor_id: uuid.UUID) -> None:
        await self._audit.record(
            action=f"pricing.rate_card_{event.removeprefix('RateCard').lower()}",
            resource_type="rate_card",
            resource_id=card.id,
            actor_id=actor_id,
            detail={"code": card.code, "version": card.version, **data},
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS[event],
                {"rate_card_id": str(card.id), "code": card.code, "status": card.status, **data},
                actor_id=actor_id,
                aggregate_type="rate_card",
                aggregate_id=card.id,
            )
        )

    async def _center_ids(self, card_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self._session.scalars(
            select(RateCardCenterAssignment.center_id)
            .where(RateCardCenterAssignment.rate_card_id == card_id)
            .order_by(RateCardCenterAssignment.assigned_at)
        )
        return list(rows.all())

    async def _products(self, card_id: uuid.UUID) -> list[RateCardProductAssignment]:
        rows = await self._session.scalars(
            select(RateCardProductAssignment)
            .where(RateCardProductAssignment.rate_card_id == card_id)
            .order_by(RateCardProductAssignment.product_code)
        )
        return list(rows.all())

    async def _product_codes(self, card_id: uuid.UUID) -> list[str]:
        return [p.product_code for p in await self._products(card_id)]

    async def _transition_matrices(
        self, card: RateCard, from_status: str, to_status: str, *, actor_id: uuid.UUID
    ) -> None:
        """Matrices follow their rate card: active on publish, archived with it."""
        from platform_core.modules.pricing.matrix import MATRIX_BUS_EVENTS

        matrices = await self._session.scalars(
            select(PricingMatrix).where(
                PricingMatrix.rate_card_id == card.id, PricingMatrix.status == from_status
            )
        )
        event = "PricingMatrixArchived" if to_status == "archived" else "PricingMatrixUpdated"
        for matrix in matrices.all():
            matrix.status = to_status
            await self._bus.publish(
                EventEnvelope.new(
                    MATRIX_BUS_EVENTS[event],
                    {
                        "matrix_id": str(matrix.id),
                        "rate_card_id": str(card.id),
                        "product_code": matrix.product_code,
                        "dimension_code": matrix.dimension_code,
                        "status": to_status,
                    },
                    actor_id=actor_id,
                    aggregate_type="pricing_matrix",
                    aggregate_id=matrix.id,
                )
            )

    async def _copy_matrices(
        self, source: RateCard, card: RateCard, *, actor_id: uuid.UUID
    ) -> None:
        """New card versions carry their pricing data forward as fresh drafts."""
        from platform_core.modules.pricing.matrix import MATRIX_BUS_EVENTS

        matrices = await self._session.scalars(
            select(PricingMatrix).where(PricingMatrix.rate_card_id == source.id)
        )
        for old in matrices.all():
            copy = PricingMatrix(
                tenant_id=card.tenant_id,
                rate_card_id=card.id,
                name=old.name,
                product_code=old.product_code,
                product_name=old.product_name,
                dimension_code=old.dimension_code,
                status="draft",
                version=card.version,
            )
            self._session.add(copy)
            await self._session.flush()
            rows = await self._session.scalars(
                select(PricingMatrixRow).where(PricingMatrixRow.matrix_id == old.id)
            )
            for row in rows.all():
                self._session.add(
                    PricingMatrixRow(
                        tenant_id=copy.tenant_id,
                        matrix_id=copy.id,
                        sequence=row.sequence,
                        from_value=row.from_value,
                        to_value=row.to_value,
                        unit_price=row.unit_price,
                        active=row.active,
                    )
                )
            await self._bus.publish(
                EventEnvelope.new(
                    MATRIX_BUS_EVENTS["PricingMatrixCreated"],
                    {
                        "matrix_id": str(copy.id),
                        "rate_card_id": str(card.id),
                        "product_code": copy.product_code,
                        "dimension_code": copy.dimension_code,
                        "copied_from": str(old.id),
                    },
                    actor_id=actor_id,
                    aggregate_type="pricing_matrix",
                    aggregate_id=copy.id,
                )
            )

    async def _check_branch(self, branch_id: uuid.UUID | None, tenant_id: uuid.UUID) -> None:
        if branch_id is None:
            return
        branch = await self._session.get(Branch, branch_id)
        if branch is None or branch.tenant_id != tenant_id:
            raise NotFoundError("branch not found")

    @staticmethod
    def _require_draft(card: RateCard) -> None:
        # BR-0001: a published rate card is immutable (docs/03-architecture/
        # 01-business-layer/BUSINESS-RULES.md); editing already ends at submission.
        if card.status == "published":
            raise ConflictError("published rate cards are immutable — create a new version")
        if card.status != "draft":
            raise ConflictError(f"only draft rate cards can be edited (status: {card.status})")

    async def _generate_code(self, tenant_id: uuid.UUID) -> str:
        for _ in range(5):
            candidate = "RC-" + secrets.token_hex(3).upper()
            exists = await self._session.scalar(
                select(RateCard).where(RateCard.tenant_id == tenant_id, RateCard.code == candidate)
            )
            if exists is None:
                return candidate
        raise ConflictError("could not generate a unique rate card code")
