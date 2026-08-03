"""Reporting module — read-only operational summaries (REP-001).

DELIBERATE EXCEPTION to the module-boundary rule: reporting SELECTs across
other modules' tables. It is allowed to because it owns no data, performs
no writes, emits no events, and duplicates no business logic — every number
is derived by SQL aggregation from the same columns the owning modules
write. If a definition here ever disagrees with an owning module, the
owning module wins (baseline precedence rule 5).

Definitions used consistently below:
- accepted   = state in (ACCEPTED, COMPLETED) and rejected_reason IS NULL
- rejected   = state = REJECTED, or COMPLETED with a rejected_reason
- payable    = sum of gross_amount over accepted AND priced transactions
- averages   = weighted by net weight (dairy convention: pooled milk quality)

No report copies transactional data; queries are fixed-count (no N+1).
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.core.tenancy import require_current_tenant
from platform_core.modules.collection_center.models import CollectionCenter
from platform_core.modules.milk_collection.models import MilkCollectionTransaction as Tx
from platform_core.modules.pricing.models import PricingMatrix, PricingMatrixRow, RateCard
from platform_core.modules.settlement.models import Settlement, SettlementLine
from platform_core.modules.supplier.models import Supplier, SupplierProfile

# Reusable SQL predicates (single source for the report definitions above).
ACCEPTED = (Tx.state.in_(("ACCEPTED", "COMPLETED"))) & (Tx.rejected_reason.is_(None))
REJECTED = (Tx.state == "REJECTED") | (
    (Tx.state == "COMPLETED") & (Tx.rejected_reason.is_not(None))
)
PRICED = Tx.gross_amount.is_not(None)


# --- DTOs ------------------------------------------------------------------


class DailyCollectionSummary(BaseModel):
    date_from: date
    date_to: date
    transactions: int
    accepted: int
    rejected: int
    cancelled: int
    in_progress: int
    suppliers_served: int
    total_net_weight_kg: float
    payable_by_currency: dict[str, Decimal]
    unpriced_accepted: int
    weighted_avg_fat: float | None
    weighted_avg_snf: float | None


class CenterSummaryRow(BaseModel):
    center_id: uuid.UUID
    center_code: str
    center_name: str
    transactions: int
    accepted: int
    total_net_weight_kg: float
    payable_amount: Decimal
    currency: str | None  # "MIX" when more than one currency appears
    weighted_avg_fat: float | None


class SupplierSummaryRow(BaseModel):
    supplier_id: uuid.UUID
    supplier_code: str
    supplier_name: str
    deliveries: int
    accepted: int
    total_net_weight_kg: float
    payable_amount: Decimal
    currency: str | None
    weighted_avg_fat: float | None


class SummaryPage(BaseModel):
    items: list[CenterSummaryRow] | list[SupplierSummaryRow]
    total: int
    limit: int
    offset: int


class SettlementStatusRow(BaseModel):
    status: str
    count: int
    net_amount: Decimal


class SettlementSummary(BaseModel):
    by_status: list[SettlementStatusRow]
    finalized_net_total: Decimal
    total_settlements: int
    total_lines: int


class PricingSummary(BaseModel):
    priced_transactions: int
    unpriced_transactions: int
    gross_by_currency: dict[str, Decimal]
    avg_unit_price: float | None
    min_unit_price: Decimal | None
    max_unit_price: Decimal | None
    published_rate_cards: int
    active_matrices: int
    active_bands: int


class ReportingService:
    """Read-only. Every method is a fixed number of aggregate queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    # --- daily collection summary -----------------------------------------

    async def daily_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        center_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
    ) -> DailyCollectionSummary:
        tenant_id = require_current_tenant()
        date_from = date_from or utcnow().date()
        date_to = date_to or date_from
        conditions = self._tx_conditions(
            tenant_id, date_from, date_to, center_id=center_id, supplier_id=supplier_id
        )
        stmt = select(
            func.count().label("transactions"),
            func.sum(case((ACCEPTED, 1), else_=0)),
            func.sum(case((REJECTED, 1), else_=0)),
            func.sum(case((Tx.state == "CANCELLED", 1), else_=0)),
            func.count(distinct(case((ACCEPTED, Tx.supplier_id)))),
            func.coalesce(func.sum(case((ACCEPTED, Tx.net_weight), else_=0.0)), 0.0),
            func.sum(case((ACCEPTED & PRICED, 0), (ACCEPTED, 1), else_=0)),
            func.sum(case((ACCEPTED & Tx.fat.is_not(None), Tx.fat * Tx.net_weight))),
            func.sum(case((ACCEPTED & Tx.fat.is_not(None), Tx.net_weight))),
            func.sum(case((ACCEPTED & Tx.snf.is_not(None), Tx.snf * Tx.net_weight))),
            func.sum(case((ACCEPTED & Tx.snf.is_not(None), Tx.net_weight))),
        ).where(*conditions)
        if branch_id is not None:
            stmt = stmt.join(CollectionCenter, CollectionCenter.id == Tx.center_id).where(
                CollectionCenter.branch_id == branch_id
            )
        row = (await self._session.execute(stmt)).one()
        (
            transactions,
            accepted,
            rejected,
            cancelled,
            suppliers,
            weight,
            unpriced,
            fat_sum,
            fat_weight,
            snf_sum,
            snf_weight,
        ) = row
        payable = await self._payable_by_currency(conditions, branch_id)
        return DailyCollectionSummary(
            date_from=date_from,
            date_to=date_to,
            transactions=transactions or 0,
            accepted=accepted or 0,
            rejected=rejected or 0,
            cancelled=cancelled or 0,
            in_progress=(transactions or 0) - (accepted or 0) - (rejected or 0) - (cancelled or 0),
            suppliers_served=suppliers or 0,
            total_net_weight_kg=round(float(weight or 0.0), 3),
            payable_by_currency=payable,
            unpriced_accepted=unpriced or 0,
            weighted_avg_fat=self._weighted(fat_sum, fat_weight),
            weighted_avg_snf=self._weighted(snf_sum, snf_weight),
        )

    async def _payable_by_currency(self, conditions, branch_id) -> dict[str, Decimal]:
        stmt = (
            select(Tx.currency, func.sum(Tx.gross_amount))
            .where(*conditions, ACCEPTED, PRICED)
            .group_by(Tx.currency)
        )
        if branch_id is not None:
            stmt = stmt.join(CollectionCenter, CollectionCenter.id == Tx.center_id).where(
                CollectionCenter.branch_id == branch_id
            )
        rows = await self._session.execute(stmt)
        return {currency: Decimal(str(total)) for currency, total in rows.all() if currency}

    # --- per-center summary -------------------------------------------------

    async def center_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        branch_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SummaryPage:
        tenant_id = require_current_tenant()
        date_from = date_from or utcnow().date()
        date_to = date_to or date_from
        limit = max(1, min(limit, 100))
        conditions = self._tx_conditions(tenant_id, date_from, date_to)
        stmt = (
            select(
                Tx.center_id,
                CollectionCenter.code,
                CollectionCenter.name,
                func.count(),
                func.sum(case((ACCEPTED, 1), else_=0)),
                func.coalesce(func.sum(case((ACCEPTED, Tx.net_weight), else_=0.0)), 0.0),
                func.coalesce(func.sum(case((ACCEPTED & PRICED, Tx.gross_amount))), 0),
                func.min(Tx.currency),
                func.count(distinct(Tx.currency)),
                func.sum(case((ACCEPTED & Tx.fat.is_not(None), Tx.fat * Tx.net_weight))),
                func.sum(case((ACCEPTED & Tx.fat.is_not(None), Tx.net_weight))),
            )
            .join(CollectionCenter, CollectionCenter.id == Tx.center_id)
            .where(*conditions)
            .group_by(Tx.center_id, CollectionCenter.code, CollectionCenter.name)
            .order_by(func.sum(case((ACCEPTED, Tx.net_weight), else_=0.0)).desc())
        )
        if branch_id is not None:
            stmt = stmt.where(CollectionCenter.branch_id == branch_id)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.execute(stmt.limit(limit).offset(offset))
        items = [
            CenterSummaryRow(
                center_id=center_id,
                center_code=code,
                center_name=name,
                transactions=tx_count,
                accepted=accepted or 0,
                total_net_weight_kg=round(float(weight or 0.0), 3),
                payable_amount=Decimal(str(payable or 0)),
                currency=("MIX" if (ncur or 0) > 1 else currency),
                weighted_avg_fat=self._weighted(fat_sum, fat_weight),
            )
            for (
                center_id,
                code,
                name,
                tx_count,
                accepted,
                weight,
                payable,
                currency,
                ncur,
                fat_sum,
                fat_weight,
            ) in rows.all()
        ]
        return SummaryPage(items=items, total=total or 0, limit=limit, offset=offset)

    # --- per-supplier summary -----------------------------------------------

    async def supplier_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        center_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SummaryPage:
        tenant_id = require_current_tenant()
        date_from = date_from or utcnow().date()
        date_to = date_to or date_from
        limit = max(1, min(limit, 100))
        conditions = self._tx_conditions(tenant_id, date_from, date_to, center_id=center_id)
        stmt = (
            select(
                Tx.supplier_id,
                Supplier.code,
                SupplierProfile.full_name,
                func.count(),
                func.sum(case((ACCEPTED, 1), else_=0)),
                func.coalesce(func.sum(case((ACCEPTED, Tx.net_weight), else_=0.0)), 0.0),
                func.coalesce(func.sum(case((ACCEPTED & PRICED, Tx.gross_amount))), 0),
                func.min(Tx.currency),
                func.count(distinct(Tx.currency)),
                func.sum(case((ACCEPTED & Tx.fat.is_not(None), Tx.fat * Tx.net_weight))),
                func.sum(case((ACCEPTED & Tx.fat.is_not(None), Tx.net_weight))),
            )
            .join(Supplier, Supplier.id == Tx.supplier_id)
            .join(SupplierProfile, SupplierProfile.supplier_id == Supplier.id)
            .where(*conditions, Tx.supplier_id.is_not(None))
            .group_by(Tx.supplier_id, Supplier.code, SupplierProfile.full_name)
            .order_by(func.sum(case((ACCEPTED, Tx.net_weight), else_=0.0)).desc())
        )
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.execute(stmt.limit(limit).offset(offset))
        items = [
            SupplierSummaryRow(
                supplier_id=supplier_id,
                supplier_code=code,
                supplier_name=name,
                deliveries=deliveries,
                accepted=accepted or 0,
                total_net_weight_kg=round(float(weight or 0.0), 3),
                payable_amount=Decimal(str(payable or 0)),
                currency=("MIX" if (ncur or 0) > 1 else currency),
                weighted_avg_fat=self._weighted(fat_sum, fat_weight),
            )
            for (
                supplier_id,
                code,
                name,
                deliveries,
                accepted,
                weight,
                payable,
                currency,
                ncur,
                fat_sum,
                fat_weight,
            ) in rows.all()
        ]
        return SummaryPage(items=items, total=total or 0, limit=limit, offset=offset)

    # --- settlement summary ---------------------------------------------------

    async def settlement_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        supplier_id: uuid.UUID | None = None,
        center_id: uuid.UUID | None = None,
    ) -> SettlementSummary:
        tenant_id = require_current_tenant()
        conditions = [Settlement.tenant_id == tenant_id]
        if date_from is not None:
            conditions.append(Settlement.period_to >= date_from)
        if date_to is not None:
            conditions.append(Settlement.period_from <= date_to)
        if supplier_id is not None:
            conditions.append(Settlement.supplier_id == supplier_id)
        if center_id is not None:
            conditions.append(Settlement.center_id == center_id)
        rows = await self._session.execute(
            select(
                Settlement.status, func.count(), func.coalesce(func.sum(Settlement.net_amount), 0)
            )
            .where(*conditions)
            .group_by(Settlement.status)
        )
        by_status = [
            SettlementStatusRow(status=status, count=count, net_amount=Decimal(str(net)))
            for status, count, net in rows.all()
        ]
        total_lines = (
            await self._session.scalar(
                select(func.count())
                .select_from(SettlementLine)
                .join(Settlement, Settlement.id == SettlementLine.settlement_id)
                .where(*conditions)
            )
            or 0
        )
        finalized = next((r.net_amount for r in by_status if r.status == "finalized"), Decimal("0"))
        return SettlementSummary(
            by_status=sorted(by_status, key=lambda r: r.status),
            finalized_net_total=finalized,
            total_settlements=sum(r.count for r in by_status),
            total_lines=total_lines,
        )

    # --- pricing summary -------------------------------------------------------

    async def pricing_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        center_id: uuid.UUID | None = None,
    ) -> PricingSummary:
        tenant_id = require_current_tenant()
        date_from = date_from or utcnow().date()
        date_to = date_to or date_from
        conditions = self._tx_conditions(tenant_id, date_from, date_to, center_id=center_id)
        row = (
            await self._session.execute(
                select(
                    func.sum(case((PRICED, 1), else_=0)),
                    func.sum(case((Tx.pricing_status == "pricing_unavailable", 1), else_=0)),
                    func.avg(Tx.unit_price),
                    func.min(Tx.unit_price),
                    func.max(Tx.unit_price),
                ).where(*conditions)
            )
        ).one()
        priced, unpriced, avg_price, min_price, max_price = row
        gross_rows = await self._session.execute(
            select(Tx.currency, func.sum(Tx.gross_amount))
            .where(*conditions, PRICED)
            .group_by(Tx.currency)
        )
        cards = await self._session.scalar(
            select(func.count())
            .select_from(RateCard)
            .where(RateCard.tenant_id == tenant_id, RateCard.status == "published")
        )
        matrices = await self._session.scalar(
            select(func.count())
            .select_from(PricingMatrix)
            .where(PricingMatrix.tenant_id == tenant_id, PricingMatrix.status == "active")
        )
        bands = await self._session.scalar(
            select(func.count())
            .select_from(PricingMatrixRow)
            .join(PricingMatrix, PricingMatrix.id == PricingMatrixRow.matrix_id)
            .where(
                PricingMatrix.tenant_id == tenant_id,
                PricingMatrix.status == "active",
                PricingMatrixRow.active,
            )
        )
        return PricingSummary(
            priced_transactions=priced or 0,
            unpriced_transactions=unpriced or 0,
            gross_by_currency={
                currency: Decimal(str(total)) for currency, total in gross_rows.all() if currency
            },
            avg_unit_price=round(float(avg_price), 4) if avg_price is not None else None,
            min_unit_price=Decimal(str(min_price)) if min_price is not None else None,
            max_unit_price=Decimal(str(max_price)) if max_price is not None else None,
            published_rate_cards=cards or 0,
            active_matrices=matrices or 0,
            active_bands=bands or 0,
        )

    # --- helpers ---------------------------------------------------------------

    @staticmethod
    def _tx_conditions(
        tenant_id: uuid.UUID,
        date_from: date,
        date_to: date,
        *,
        center_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
    ) -> list:
        """Closed date range [date_from, date_to] applied as half-open
        datetimes [00:00 of date_from, 00:00 of date_to + 1 day)."""
        conditions = [
            Tx.tenant_id == tenant_id,
            Tx.created_at >= datetime.combine(date_from, datetime.min.time()),
            Tx.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()),
        ]
        if center_id is not None:
            conditions.append(Tx.center_id == center_id)
        if supplier_id is not None:
            conditions.append(Tx.supplier_id == supplier_id)
        return conditions

    @staticmethod
    def _weighted(value_sum, weight_sum) -> float | None:
        if not value_sum or not weight_sum:
            return None
        return round(float(value_sum) / float(weight_sum), 2)
