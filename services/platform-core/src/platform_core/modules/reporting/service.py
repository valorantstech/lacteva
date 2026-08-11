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
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel
from sqlalchemy import Numeric, case, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.core.tenancy import require_current_tenant
from platform_core.modules.collection_center.models import CollectionCenter
from platform_core.modules.milk_collection.models import MilkCollectionTransaction as Tx
from platform_core.modules.payment.models import Payment
from platform_core.modules.pricing.models import PricingMatrix, PricingMatrixRow, RateCard
from platform_core.modules.settlement.models import Settlement, SettlementLine
from platform_core.modules.supplier.models import Supplier, SupplierProfile

# Reusable SQL predicates (single source for the report definitions above).
ACCEPTED = (Tx.state.in_(("ACCEPTED", "COMPLETED"))) & (Tx.rejected_reason.is_(None))
REJECTED = (Tx.state == "REJECTED") | (
    (Tx.state == "COMPLETED") & (Tx.rejected_reason.is_not(None))
)
PRICED = Tx.gross_amount.is_not(None)


# DB-002: `net_weight`, `fat` and `snf` are `double precision`, and floating
# point addition is NOT associative — the same rows summed in a different
# order give a different answer. Order comes from the plan, which changes with
# statistics and with parallel workers, so a report could disagree with itself
# between two runs and nothing would say so. Casting each value to NUMERIC
# before it enters the aggregate makes the sum exact and therefore
# reproducible.
#
# On PostgreSQL `float8::numeric` renders the shortest decimal that round-trips
# — the same rule `Decimal(str(x))` follows in the money path (BR-0005) — so a
# weight aggregates as the value it displays as.
#
# Unconstrained `NUMERIC` on purpose: pinning a scale here would round every
# ROW before summing, where the platform rounds the TOTAL once. The aggregate
# stays inside SQL; only the exactness of its arithmetic changes.
_EXACT_ZERO = Decimal(0)


def _exact(column):
    """A float column, promoted to exact decimal for aggregation."""
    return cast(column, Numeric)


def _kg(total) -> float:
    """A weight total, rounded once, from an exact sum.

    The DTO field is `float` and stays `float` — the API contract does not
    move. What changed is that the value being rounded is now reproducible.
    """
    if total is None:
        return 0.0
    return float(Decimal(total).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


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


class PaymentStatusRow(BaseModel):
    status: str
    count: int
    amount: Decimal
    #: "MIX" when one status holds payments in more than one currency, the
    #: same convention `CenterSummaryRow` already uses. `amount` is then a sum
    #: across currencies and must be read as a count-weighted indicator, not a
    #: payable — which is why `total_by_currency` below is the exact answer.
    currency: str | None


class PaymentSummary(BaseModel):
    """DEMO-002: the aggregate DEMO-001 recorded as missing.

    The dashboard needs "how much is stuck in processing" and "how much failed"
    without pulling the payment table into a browser and adding it up there.
    Every figure is `SUM(payment.amount)` over persisted amounts.
    """

    by_status: list[PaymentStatusRow]
    total_payments: int
    completed_count: int
    processing_count: int
    pending_count: int
    failed_count: int
    completed_amount: Decimal
    outstanding_amount: Decimal  #: draft + pending + processing — money not yet delivered
    failed_amount: Decimal
    total_by_currency: dict[str, Decimal]


class TrendPoint(BaseModel):
    day: date
    transactions: int
    accepted: int
    total_net_weight_kg: float
    payable_amount: Decimal
    currency: str | None


class CollectionTrend(BaseModel):
    date_from: date
    date_to: date
    points: list[TrendPoint]


class RateBandRow(BaseModel):
    """One resolved unit price, and what was bought at it.

    NOT a new business concept: a pricing matrix maps a quality band to exactly
    one unit price, so grouping accepted, priced collections by the unit price
    the engine resolved IS the band distribution — read back off the
    transactions rather than re-derived from the matrix, which would risk
    disagreeing with what was actually paid.
    """

    unit_price: Decimal
    currency: str | None
    transactions: int
    total_net_weight_kg: float
    payable_amount: Decimal


class AttentionItem(BaseModel):
    key: str
    label: str
    count: int
    severity: str  #: warning | critical
    href: str | None = None


class DashboardSummary(BaseModel):
    """One round trip for the whole KPI block.

    Composed from the summaries that already exist rather than re-implementing
    them, so a definition has exactly one home. Anything a widget needs that is
    not here is its own endpoint, so one failing widget cannot blank the page.
    """

    date_from: date
    date_to: date
    collection: DailyCollectionSummary
    settlements: SettlementSummary
    payments: PaymentSummary
    rate_bands: list[RateBandRow]
    active_suppliers: int
    active_centers: int
    inactive_centers: int
    attention: list[AttentionItem]


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
            func.coalesce(
                func.sum(case((ACCEPTED, _exact(Tx.net_weight)), else_=_EXACT_ZERO)), _EXACT_ZERO
            ),
            func.sum(case((ACCEPTED & PRICED, 0), (ACCEPTED, 1), else_=0)),
            func.sum(
                case((ACCEPTED & Tx.fat.is_not(None), _exact(Tx.fat) * _exact(Tx.net_weight)))
            ),
            func.sum(case((ACCEPTED & Tx.fat.is_not(None), _exact(Tx.net_weight)))),
            func.sum(
                case((ACCEPTED & Tx.snf.is_not(None), _exact(Tx.snf) * _exact(Tx.net_weight)))
            ),
            func.sum(case((ACCEPTED & Tx.snf.is_not(None), _exact(Tx.net_weight)))),
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
            total_net_weight_kg=_kg(weight),
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
                func.coalesce(
                    func.sum(case((ACCEPTED, _exact(Tx.net_weight)), else_=_EXACT_ZERO)),
                    _EXACT_ZERO,
                ),
                func.coalesce(func.sum(case((ACCEPTED & PRICED, Tx.gross_amount))), 0),
                func.min(Tx.currency),
                func.count(distinct(Tx.currency)),
                func.sum(
                    case((ACCEPTED & Tx.fat.is_not(None), _exact(Tx.fat) * _exact(Tx.net_weight)))
                ),
                func.sum(case((ACCEPTED & Tx.fat.is_not(None), _exact(Tx.net_weight)))),
            )
            .join(CollectionCenter, CollectionCenter.id == Tx.center_id)
            .where(*conditions)
            .group_by(Tx.center_id, CollectionCenter.code, CollectionCenter.name)
            .order_by(func.sum(case((ACCEPTED, _exact(Tx.net_weight)), else_=_EXACT_ZERO)).desc())
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
                total_net_weight_kg=_kg(weight),
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
                func.coalesce(
                    func.sum(case((ACCEPTED, _exact(Tx.net_weight)), else_=_EXACT_ZERO)),
                    _EXACT_ZERO,
                ),
                func.coalesce(func.sum(case((ACCEPTED & PRICED, Tx.gross_amount))), 0),
                func.min(Tx.currency),
                func.count(distinct(Tx.currency)),
                func.sum(
                    case((ACCEPTED & Tx.fat.is_not(None), _exact(Tx.fat) * _exact(Tx.net_weight)))
                ),
                func.sum(case((ACCEPTED & Tx.fat.is_not(None), _exact(Tx.net_weight)))),
            )
            .join(Supplier, Supplier.id == Tx.supplier_id)
            .join(SupplierProfile, SupplierProfile.supplier_id == Supplier.id)
            .where(*conditions, Tx.supplier_id.is_not(None))
            .group_by(Tx.supplier_id, Supplier.code, SupplierProfile.full_name)
            .order_by(func.sum(case((ACCEPTED, _exact(Tx.net_weight)), else_=_EXACT_ZERO)).desc())
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
                total_net_weight_kg=_kg(weight),
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

    # --- payment summary (DEMO-002) -----------------------------------------

    async def payment_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        supplier_id: uuid.UUID | None = None,
    ) -> PaymentSummary:
        """Counts and money by payment status, entirely in SQL.

        Dated by `created_at`, because a payment's business moment is when it
        was raised — a failed payment never acquires a completion date, and a
        dashboard that only counted completed ones would hide exactly the
        payments somebody needs to act on.
        """
        tenant_id = require_current_tenant()
        conditions = [Payment.tenant_id == tenant_id]
        if date_from is not None:
            conditions.append(
                Payment.created_at >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            conditions.append(
                Payment.created_at
                < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
            )
        if supplier_id is not None:
            conditions.append(Payment.supplier_id == supplier_id)

        rows = (
            await self._session.execute(
                select(
                    Payment.status,
                    Payment.currency,
                    func.count(),
                    func.coalesce(func.sum(Payment.amount), 0),
                )
                .where(*conditions)
                .group_by(Payment.status, Payment.currency)
            )
        ).all()

        per_status: dict[str, dict] = {}
        by_currency: dict[str, Decimal] = {}
        for status, currency, count, amount in rows:
            amount = Decimal(str(amount))
            slot = per_status.setdefault(
                status, {"count": 0, "amount": Decimal("0"), "currencies": set()}
            )
            slot["count"] += count
            slot["amount"] += amount
            if currency:
                slot["currencies"].add(currency)
                by_currency[currency] = by_currency.get(currency, Decimal("0")) + amount

        by_status = [
            PaymentStatusRow(
                status=status,
                count=slot["count"],
                amount=slot["amount"],
                currency=(
                    next(iter(slot["currencies"]))
                    if len(slot["currencies"]) == 1
                    else ("MIX" if slot["currencies"] else None)
                ),
            )
            for status, slot in sorted(per_status.items())
        ]

        def count_of(*statuses: str) -> int:
            return sum(r.count for r in by_status if r.status in statuses)

        def amount_of(*statuses: str) -> Decimal:
            return sum((r.amount for r in by_status if r.status in statuses), Decimal("0"))

        return PaymentSummary(
            by_status=by_status,
            total_payments=sum(r.count for r in by_status),
            completed_count=count_of("completed"),
            processing_count=count_of("processing"),
            pending_count=count_of("pending", "draft"),
            failed_count=count_of("failed"),
            completed_amount=amount_of("completed"),
            outstanding_amount=amount_of("draft", "pending", "processing"),
            failed_amount=amount_of("failed"),
            total_by_currency=by_currency,
        )

    # --- collection trend (DEMO-002) ----------------------------------------

    async def collection_trend(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        center_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
    ) -> CollectionTrend:
        """Quantity and value per day — one grouped query, not one per day.

        Days with no collection are filled in as zeroes rather than omitted, so
        a chart shows a gap in supply as a gap rather than silently closing it.
        """
        tenant_id = require_current_tenant()
        date_to = date_to or utcnow().date()
        date_from = date_from or date_to
        conditions = self._tx_conditions(
            tenant_id, date_from, date_to, center_id=center_id, supplier_id=supplier_id
        )
        # `date()` is a function-style cast on PostgreSQL and a built-in on
        # SQLite, so one expression buckets correctly on both engines. The
        # database runs in UTC, which is the clock `created_at` is stamped with.
        day = func.date(Tx.created_at)
        rows = (
            await self._session.execute(
                select(
                    day,
                    func.count(),
                    func.sum(case((ACCEPTED, 1), else_=0)),
                    func.coalesce(
                        func.sum(case((ACCEPTED, _exact(Tx.net_weight)), else_=_EXACT_ZERO)),
                        _EXACT_ZERO,
                    ),
                    func.coalesce(func.sum(case((ACCEPTED & PRICED, Tx.gross_amount), else_=0)), 0),
                    func.max(case((ACCEPTED & PRICED, Tx.currency))),
                )
                .where(*conditions)
                .group_by(day)
                .order_by(day)
            )
        ).all()

        found = {
            (value if isinstance(value, date) else date.fromisoformat(str(value)[:10])): (
                transactions,
                accepted,
                weight,
                payable,
                currency,
            )
            for value, transactions, accepted, weight, payable, currency in rows
        }
        points: list[TrendPoint] = []
        cursor = date_from
        while cursor <= date_to:
            transactions, accepted, weight, payable, currency = found.get(
                cursor, (0, 0, _EXACT_ZERO, 0, None)
            )
            points.append(
                TrendPoint(
                    day=cursor,
                    transactions=transactions or 0,
                    accepted=accepted or 0,
                    total_net_weight_kg=_kg(weight),
                    payable_amount=Decimal(str(payable or 0)),
                    currency=currency,
                )
            )
            cursor += timedelta(days=1)
        return CollectionTrend(date_from=date_from, date_to=date_to, points=points)

    # --- rate/quality distribution (DEMO-002) -------------------------------

    async def rate_distribution(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        center_id: uuid.UUID | None = None,
    ) -> list[RateBandRow]:
        tenant_id = require_current_tenant()
        date_to = date_to or utcnow().date()
        date_from = date_from or date_to
        conditions = self._tx_conditions(tenant_id, date_from, date_to, center_id=center_id)
        rows = (
            await self._session.execute(
                select(
                    Tx.unit_price,
                    Tx.currency,
                    func.count(),
                    func.coalesce(func.sum(_exact(Tx.net_weight)), _EXACT_ZERO),
                    func.coalesce(func.sum(Tx.gross_amount), 0),
                )
                .where(*conditions, ACCEPTED, PRICED)
                .group_by(Tx.unit_price, Tx.currency)
                .order_by(Tx.unit_price)
            )
        ).all()
        return [
            RateBandRow(
                unit_price=Decimal(str(unit_price)),
                currency=currency,
                transactions=count,
                total_net_weight_kg=_kg(weight),
                payable_amount=Decimal(str(payable)),
            )
            for unit_price, currency, count, weight, payable in rows
            if unit_price is not None
        ]

    # --- the dashboard block (DEMO-002) -------------------------------------

    async def dashboard(
        self, *, date_from: date | None = None, date_to: date | None = None
    ) -> DashboardSummary:
        """Everything the KPI block needs, composed from the summaries above.

        Composition rather than re-implementation: `daily_summary` remains the
        only definition of "accepted", `settlement_summary` the only definition
        of settlement status. A second definition here would be a second thing
        to keep true.
        """
        tenant_id = require_current_tenant()
        date_to = date_to or utcnow().date()
        date_from = date_from or date_to

        collection = await self.daily_summary(date_from=date_from, date_to=date_to)
        settlements = await self.settlement_summary()
        payments = await self.payment_summary()
        rate_bands = await self.rate_distribution(date_from=date_from, date_to=date_to)

        active_suppliers = (
            await self._session.scalar(
                select(func.count())
                .select_from(Supplier)
                .where(Supplier.tenant_id == tenant_id, Supplier.status == "active")
            )
        ) or 0
        center_states = (
            await self._session.execute(
                select(CollectionCenter.status, func.count())
                .where(CollectionCenter.tenant_id == tenant_id)
                .group_by(CollectionCenter.status)
            )
        ).all()
        active_centers = sum(c for s, c in center_states if s == "active")
        inactive_centers = sum(c for s, c in center_states if s != "active")

        # Every item below is a real backend state with a real count. Nothing is
        # invented, and an item with a count of zero is omitted rather than
        # shown as reassuringly green — "no action required" is the empty state.
        attention: list[AttentionItem] = []
        if payments.failed_count:
            attention.append(
                AttentionItem(
                    key="failed_payments",
                    label="payments failed and need retrying",
                    count=payments.failed_count,
                    severity="critical",
                    href="/payments",
                )
            )
        ready = sum(r.count for r in settlements.by_status if r.status == "calculated")
        if ready:
            attention.append(
                AttentionItem(
                    key="settlements_ready",
                    label="settlements calculated and awaiting finalization",
                    count=ready,
                    severity="warning",
                    href="/settlements",
                )
            )
        if collection.rejected:
            attention.append(
                AttentionItem(
                    key="rejected_collections",
                    label="collections rejected in this period",
                    count=collection.rejected,
                    severity="warning",
                    href="/transactions",
                )
            )
        if collection.unpriced_accepted:
            attention.append(
                AttentionItem(
                    key="unpriced",
                    label="accepted collections with no price",
                    count=collection.unpriced_accepted,
                    severity="critical",
                    href="/transactions",
                )
            )
        if inactive_centers:
            attention.append(
                AttentionItem(
                    key="inactive_centers",
                    label="collection centres not active",
                    count=inactive_centers,
                    severity="warning",
                    href="/centers",
                )
            )

        return DashboardSummary(
            date_from=date_from,
            date_to=date_to,
            collection=collection,
            settlements=settlements,
            payments=payments,
            rate_bands=rate_bands,
            active_suppliers=active_suppliers,
            active_centers=active_centers,
            inactive_centers=inactive_centers,
            attention=attention,
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
        """Weighted average from two exact sums.

        DB-002: both operands now arrive as `Decimal`, so the division happens
        in decimal and quantizes once, explicitly. Going back through `float`
        here would reintroduce — at the very last step — the rounding this
        work order removed from the sums. The DTO still returns `float`, so no
        API contract moves; only the digit it rounds from is now reproducible.
        """
        if not value_sum or not weight_sum:
            return None
        ratio = Decimal(value_sum) / Decimal(weight_sum)
        return float(ratio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
