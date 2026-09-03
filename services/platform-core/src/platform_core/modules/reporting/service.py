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

from platform_core.core.business_time import local_date_sql, range_bounds
from platform_core.core.db import as_utc
from platform_core.core.money import quantize_money
from platform_core.core.tenancy import require_current_tenant
from platform_core.modules.billing.models import (
    PAYABLE_INVOICE_STATUSES,
    CustomerInvoice,
    CustomerPayment,
    CustomerReceipt,
)
from platform_core.modules.collection_center.models import CollectionCenter
from platform_core.modules.customer.models import Customer
from platform_core.modules.delivery.models import BILLABLE_STATUSES, MilkDelivery
from platform_core.modules.dispatch.models import MilkDispatch
from platform_core.modules.milk_collection.models import MilkCollectionTransaction as Tx
from platform_core.modules.milk_collection.models import TransactionEvent
from platform_core.modules.payment.models import Payment, PaymentLine
from platform_core.modules.pricing.models import PricingMatrix, PricingMatrixRow, RateCard
from platform_core.modules.receipt.models import Receipt
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
    """A quantity total, rounded once, from an exact sum.

    The DTO field is `float` and stays `float` — the API contract does not
    move. What changed is that the value being rounded is now reproducible.

    D-21 / WO-70: the NAME is historical. The fields it feeds are called
    `*_kg` because kilograms were the only unit the platform knew when they
    were named; they now carry the ORGANISATION'S unit, stated beside them in
    `quantity_unit` on every DTO that has one. Renaming the wire fields is a
    coordinated client change and is recorded as a discovered item, not done
    silently here.
    """
    if total is None:
        return 0.0
    return float(Decimal(total).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def _unit(unit, distinct_count, default: str) -> str:
    """The unit of an aggregate, READ from the rows it summed (D-21).

    Every organisation has one unit at a time, so almost every window is
    uniform and this returns it. A window that straddles an owner's change
    of unit holds rows in both, and summing them would be a number in no
    unit — so it says `mixed`, and a client renders that word rather than
    either symbol. An empty window has no rows to read and reports the
    organisation's current unit.
    """
    if (distinct_count or 0) > 1:
        return "mixed"
    return unit or default


#: The two columns every quantity aggregate now selects beside its sum.
def _unit_columns():
    return (
        func.min(case((ACCEPTED, Tx.weight_unit))),
        func.count(distinct(case((ACCEPTED, Tx.weight_unit)))),
    )


def _money(total) -> Decimal:
    """An exact sum, rounded once to money scale — and never through float.

    The sales figures stay `Decimal` the whole way to the browser (BR-0005),
    unlike weights, which the API has always returned as `float`.
    """
    # DEMO-014: the scale rule lives in `core/money.py`, not here. Reporting
    # aggregates can span rows whose currency the caller has not threaded
    # through, so it asks for the platform default — two decimals, which is
    # what every onboarded currency uses and what this function always
    # assumed. The difference is that the assumption is now stated in one
    # place, where a zero-decimal currency would be corrected once.
    return quantize_money(total or 0, None)


def _litres(total) -> Decimal:
    """A delivered volume, at the scale the delivery column stores."""
    return Decimal(total or 0).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# --- DTOs ------------------------------------------------------------------


class MilkTypeRow(BaseModel):
    """What one kind of milk contributed (WO-55).

    `milk_type` has been on every transaction since the beginning and the
    pricing engine has always resolved a rate per type — a buffalo litre and a
    cow litre are different money. Nothing REPORTED by type, so a dairy taking
    both could see what it paid in total and never what it paid for which.
    """

    milk_type: str
    transactions: int
    net_weight_kg: float
    #: D-21: the unit of `net_weight_kg`, read from the rows. See `_kg`.
    quantity_unit: str
    weighted_avg_fat: float | None
    amount_by_currency: dict[str, Decimal]


# --- the milk day book (BR-0030) ---------------------------------------------


class DayBookRow(BaseModel):
    """One kind of milk, at one centre, on one day.

    A FLOW ledger: what came in, what went out in bulk, and the difference.
    It is not a measurement of a tank — see `DayBook` for what it cannot see.
    """

    milk_type: str
    collected_kg: float
    dispatched_kg: float
    #: collected minus dispatched. Shown as it falls out, negative included: a
    #: centre that dispatched more than it collected has recorded something
    #: wrong, and clamping it to zero would hide exactly that.
    remainder_kg: float
    collections: int
    dispatches: int


class DayBookSales(BaseModel):
    """What the dairy sold that day — reported BESIDE the ledger, not inside it.

    Two honest reasons it is not a column in `DayBookRow`, and both are
    properties of the platform's data rather than of this report:

    **A sale has no centre.** `milk_delivery` records a customer, a date and a
    product; the round visits households, and nothing ties a delivery back to
    the centre whose milk it was. Attributing sales to a centre would be a
    guess, and a guess subtracted from a real figure produces a remainder that
    looks precise and is not.

    **A sale has no milk type.** The sales side prices a *product* — a free
    text string, `RAW-COW-MILK` by default — and the platform holds no mapping
    from a product to an animal. Splitting sales by type would mean parsing
    that string, which is inventing data.

    So the day's deliveries are reported as their own figure, in their own
    unit (the sales side measures in litres; intake and dispatch are weighed
    in kilograms), and the ledger's remainder does not subtract them. Making
    sales attributable is a change to the sales model, not to this report.
    """

    deliveries: int
    quantity: Decimal
    quantity_unit: str
    attributable_to_centre: bool = False
    attributable_to_milk_type: bool = False


class DayBook(BaseModel):
    """One centre's day, or the whole organization's.

    What this ledger CANNOT see, stated once here rather than implied by a
    number: evaporation, spillage, a sample drawn for testing, milk carried
    over from yesterday, and anything a chilling tank knows about itself.
    Modelling actual stock needs BMC telemetry the platform does not have and
    is deliberately parked (D-17). This is arithmetic over recorded
    movements — which is a thing a dairy can check against its own gate pass,
    and therefore worth more than a number nobody can verify.
    """

    business_date: date
    center_id: uuid.UUID | None
    center_name: str | None
    rows: list[DayBookRow]
    total_collected_kg: float
    total_dispatched_kg: float
    total_remainder_kg: float
    #: D-21 / WO-70: the unit of every `*_kg` figure in this book — the
    #: organisation's intake unit, read from the collections and dispatches
    #: it summed. The suffix is historical (see `_kg`); the value is not.
    quantity_unit: str
    sales: DayBookSales


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
    #: D-21: the unit of `total_net_weight_kg`, read from the rows.
    quantity_unit: str
    payable_by_currency: dict[str, Decimal]
    unpriced_accepted: int
    weighted_avg_fat: float | None
    weighted_avg_snf: float | None
    #: WO-55. Accepted collections split by what animal the milk came from,
    #: heaviest first. Empty for a dairy that takes one kind, which is most of
    #: them — the breakdown appears when there is something to break down.
    by_milk_type: list[MilkTypeRow] = []


class CenterSummaryRow(BaseModel):
    center_id: uuid.UUID
    center_code: str
    center_name: str
    transactions: int
    accepted: int
    total_net_weight_kg: float
    quantity_unit: str  # D-21; "mixed" when the window straddles a unit change
    payable_amount: Decimal
    currency: str | None  # "MIX" when more than one currency appears
    weighted_avg_fat: float | None
    #: DEMO-003: when this centre last took milk. An operator scanning a list
    #: needs "is this centre still working?" and a quantity alone cannot say —
    #: a busy centre and one that stopped a fortnight ago look identical.
    last_collection_at: datetime | None = None


class SupplierSummaryRow(BaseModel):
    supplier_id: uuid.UUID
    supplier_code: str
    supplier_name: str
    deliveries: int
    accepted: int
    total_net_weight_kg: float
    quantity_unit: str  # D-21
    payable_amount: Decimal
    currency: str | None
    weighted_avg_fat: float | None
    last_collection_at: datetime | None = None


class SummaryPage(BaseModel):
    items: list[CenterSummaryRow] | list[SupplierSummaryRow]
    total: int
    limit: int
    offset: int


class SettlementStatusRow(BaseModel):
    status: str
    count: int
    net_amount: Decimal
    #: WO-61. "MIX" when one status holds settlements in more than one
    #: currency, the convention `PaymentStatusRow` and `CenterSummaryRow`
    #: already use. Without it this row is a number a client has to
    #: denominate for itself, and the only thing it has to hand is the
    #: organization — which is how a total in shillings came to be labelled
    #: in rupees on the live portal.
    currency: str | None


class SettlementSummary(BaseModel):
    """Settlement money, always denominated (WO-61 · BR-0031).

    `finalized_net_total` used to be a bare `Decimal` here: the platform
    summed money and did not say what money it was. It is now a figure PER
    CURRENCY, because a tenant holding both shillings and rupees has no single
    finalized value, and inventing one by addition is a category error rather
    than an arithmetic one.
    """

    by_status: list[SettlementStatusRow]
    #: Finalized net, keyed by the currency of the settlements summed. Empty
    #: when nothing is finalized — which is not the same as zero in some
    #: currency nobody has used.
    finalized_by_currency: dict[str, Decimal]
    total_settlements: int
    total_lines: int


class ChainSettlement(BaseModel):
    id: uuid.UUID
    settlement_number: str
    status: str
    period_from: date
    period_to: date
    currency: str
    gross_amount: Decimal
    adjustments_amount: Decimal
    net_amount: Decimal
    line_amount: Decimal  #: what THIS collection contributed
    finalized_at: datetime | None


class ChainPayment(BaseModel):
    id: uuid.UUID
    payment_number: str
    status: str
    method: str
    currency: str
    amount: Decimal
    allocated_amount: Decimal  #: allocated against the settlement above
    reference: str | None
    paid_at: datetime | None


class ChainReceipt(BaseModel):
    id: uuid.UUID
    receipt_number: str
    status: str
    net_amount: Decimal
    currency: str
    generated_at: datetime


class CollectionChain(BaseModel):
    """Where one collection's money went — settlement, payment, receipt.

    DEMO-004: the portal could not answer "was this paid?" without joining
    three modules in the browser, which is both an N+1 and a place for the
    answer to drift from the platform's. Reporting is the module allowed to
    SELECT across boundaries — it owns no data, writes nothing, and derives
    every field from the columns the owning modules wrote.

    Each stage is `None` when it has not happened, which is the honest answer
    and the one the timeline needs: a collection that is priced but unsettled
    must look different from one that was never priced.
    """

    transaction_id: uuid.UUID
    settlement: ChainSettlement | None
    payment: ChainPayment | None
    receipt: ChainReceipt | None


class OperationalStatus(BaseModel):
    """Where one collection has reached, financially and in its own event log.

    DEMO-007: the operational transaction list needs, per row, the settlement
    it belongs to, the payment that discharged it, the receipt that followed,
    and when anything last happened to it. `collection_chain` answers exactly
    that — for ONE transaction. Calling it per row is an N+1, and a list of
    fifty rows would be fifty round trips.

    So this is the same question asked in bulk: a page of transaction ids in,
    a status per id out, in a FIXED number of queries regardless of page size
    (four, plus one for the event log). The portal makes one extra call per
    page and never joins anything itself.
    """

    transaction_id: uuid.UUID
    last_event_type: str | None
    last_event_at: datetime | None
    settlement_id: uuid.UUID | None
    settlement_number: str | None
    settlement_status: str | None
    settled_amount: Decimal | None
    #: WO-61: the settlement's own currency, so a row's money is never
    #: denominated from the organization by whoever renders it.
    currency: str | None
    payment_id: uuid.UUID | None
    payment_number: str | None
    payment_status: str | None
    receipt_id: uuid.UUID | None
    receipt_number: str | None
    receipt_status: str | None


class OperationalStatusPage(BaseModel):
    items: list[OperationalStatus]


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
    #: WO-61: each of these keyed by the currency of the payments summed. They
    #: were bare `Decimal`s, which left the portal denominating them from the
    #: organization — right until an organization's currency and its payments'
    #: currency disagreed.
    completed_by_currency: dict[str, Decimal]
    #: draft + pending + processing — money not yet delivered.
    outstanding_by_currency: dict[str, Decimal]
    failed_by_currency: dict[str, Decimal]
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
    #: D-21: one unit for the whole series, read from the rows it summed.
    quantity_unit: str


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
    quantity_unit: str  # D-21: the unit the price is per, and the total is in
    payable_amount: Decimal


class AttentionItem(BaseModel):
    key: str
    label: str
    count: int
    severity: str  #: warning | critical
    href: str | None = None


class InvoiceStatusRow(BaseModel):
    status: str
    count: int
    total: Decimal
    #: WO-61, the row convention: "MIX" when one status holds invoices in more
    #: than one currency, `None` when none of them says.
    currency: str | None


class SalesSummary(BaseModel):
    """The receivable half of the business (DEMO-010).

    Two kinds of figure live here and the names say which is which, because
    confusing them is the easy mistake:

    * `*_in_period` is what happened between `date_from` and `date_to` —
      how much milk went out, what it was worth.
    * `receivable`, `invoiced` and `received` are BALANCES. They are as-at-now
      and ignore the period entirely, because "what do customers owe us" is
      not a question about a date range, and answering it for one would show a
      manager a smaller number than the debt they actually have to collect.

    `receivable` uses the same definition as `BillingService.balance()` —
    issued and paid invoices, less every recorded payment — so a manager
    adding up the customer pages gets the dashboard's number exactly.
    """

    date_from: date
    date_to: date
    currency: str | None

    deliveries_in_period: int
    delivered_quantity_in_period: Decimal
    quantity_unit: str
    sales_value_in_period: Decimal
    customers_served_in_period: int

    active_customers: int
    total_customers: int

    invoiced: Decimal  #: issued + paid invoices, all time
    received: Decimal  #: recorded customer payments, all time
    receivable: Decimal  #: invoiced less received; what is still owed
    by_status: list[InvoiceStatusRow]
    open_invoices: int  #: issued and not yet fully settled
    customers_owing: int

    unbilled_deliveries: int  #: delivered, billable, not yet on any bill
    unbilled_amount: Decimal
    receipts_issued: int


class ReceivableRow(BaseModel):
    customer_id: uuid.UUID
    code: str
    name: str
    phone: str
    status: str
    currency: str
    invoiced: Decimal
    paid: Decimal
    outstanding: Decimal
    open_invoices: int
    last_payment_at: datetime | None
    oldest_unpaid_from: date | None  #: start of the oldest issued, unsettled period


class ReceivablesPage(BaseModel):
    """Who owes money, worst first — the dairy owner's first question.

    Ordered by `outstanding` descending in SQL, so page one is the collection
    round for the morning and nothing needs sorting in a browser.
    """

    items: list[ReceivableRow]
    total: int  #: customers matching the filter, not rows on this page
    limit: int
    offset: int
    total_outstanding: Decimal  #: across every match, not just this page
    currency: str | None


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
    sales: SalesSummary
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

    async def _timezone(self) -> str:
        """The organization's IANA zone, for every window this module builds.

        DEMO-019: a report's date bounds and its "today" have to come from the
        same clock. They did not — `_today()` resolved the organization's zone
        and the windows were built from naive UTC midnights of the date it
        returned, which is a different instant for every dairy not on UTC.
        """
        from platform_core.core.org_context import tenant_timezone

        return await tenant_timezone(self._session)

    async def _today(self):
        """Today, as the ORGANIZATION reckons it (DEMO-013 §8).

        Not UTC's today. A report asked for "today" at 04:00 in Bengaluru is
        asking about a day that began four hours ago locally and does not
        start in UTC for another twenty; answering with UTC's date would show
        a dairy manager yesterday's round and call it today.
        """
        from platform_core.core.business_time import business_today
        from platform_core.core.org_context import tenant_timezone

        return business_today(await tenant_timezone(self._session))

    async def _unit_default(self) -> str:
        """The organisation's current intake unit, for an aggregate with no
        rows to read one from (D-21)."""
        from platform_core.core.org_context import tenant_locale

        return (await tenant_locale(self._session)).quantity_unit

    # --- the milk day book -------------------------------------------------

    async def day_book(
        self, *, business_date: date | None = None, center_id: uuid.UUID | None = None
    ) -> DayBook:
        """What happened to the milk at a centre on one day (BR-0030).

        Three queries and no loops: collections by type, dispatches by type,
        and the day's deliveries. A cancelled dispatch is excluded — it is
        withdrawn, and a withdrawn movement moved nothing.
        """
        tenant_id = require_current_tenant()
        day = business_date or await self._today()
        timezone = await self._timezone()

        conditions = self._tx_conditions(
            tenant_id, day, day, timezone=timezone, center_id=center_id
        )
        collected = (
            await self._session.execute(
                select(
                    Tx.milk_type,
                    func.count(),
                    func.coalesce(
                        func.sum(case((ACCEPTED, _exact(Tx.net_weight)), else_=_EXACT_ZERO)),
                        _EXACT_ZERO,
                    ),
                )
                .where(*conditions, ACCEPTED)
                .group_by(Tx.milk_type)
            )
        ).all()
        # D-21: the unit of this book, read from what it sums — collections
        # and dispatches alike, since the ledger subtracts one from the other.
        units_seen = set(
            (
                await self._session.execute(
                    select(distinct(Tx.weight_unit)).where(*conditions, ACCEPTED)
                )
            ).scalars()
        )

        dispatch_conditions = [
            MilkDispatch.tenant_id == tenant_id,
            MilkDispatch.business_date == day,
            MilkDispatch.status == "recorded",
        ]
        if center_id is not None:
            dispatch_conditions.append(MilkDispatch.center_id == center_id)
        dispatched = (
            await self._session.execute(
                select(
                    MilkDispatch.milk_type,
                    func.count(),
                    func.coalesce(func.sum(cast(MilkDispatch.quantity, Numeric)), _EXACT_ZERO),
                )
                .where(*dispatch_conditions)
                .group_by(MilkDispatch.milk_type)
            )
        ).all()
        units_seen |= set(
            (
                await self._session.execute(
                    select(distinct(MilkDispatch.quantity_unit)).where(*dispatch_conditions)
                )
            ).scalars()
        )
        units_seen.discard(None)
        book_unit = _unit(next(iter(units_seen), None), len(units_seen), await self._unit_default())

        sold = (
            await self._session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(cast(MilkDelivery.quantity, Numeric)), _EXACT_ZERO),
                    func.max(MilkDelivery.quantity_unit),
                ).where(
                    MilkDelivery.tenant_id == tenant_id,
                    MilkDelivery.delivery_date == day,
                    MilkDelivery.status.in_(BILLABLE_STATUSES),
                )
            )
        ).one()

        centre_name: str | None = None
        if center_id is not None:
            centre_name = await self._session.scalar(
                select(CollectionCenter.name).where(
                    CollectionCenter.id == center_id, CollectionCenter.tenant_id == tenant_id
                )
            )

        in_by_type = {row[0]: (int(row[1]), row[2]) for row in collected}
        out_by_type = {row[0]: (int(row[1]), row[2]) for row in dispatched}
        rows: list[DayBookRow] = []
        for milk_type in sorted(set(in_by_type) | set(out_by_type)):
            count_in, weight_in = in_by_type.get(milk_type, (0, _EXACT_ZERO))
            count_out, weight_out = out_by_type.get(milk_type, (0, _EXACT_ZERO))
            rows.append(
                DayBookRow(
                    milk_type=milk_type,
                    collected_kg=_kg(weight_in),
                    dispatched_kg=_kg(weight_out),
                    # Rounded once, from the exact sums, rather than from the
                    # two rounded figures above it: the column a manager
                    # checks must be the difference of the columns beside it.
                    remainder_kg=_kg(Decimal(weight_in or 0) - Decimal(weight_out or 0)),
                    collections=count_in,
                    dispatches=count_out,
                )
            )
        # Heaviest intake first, the same order the daily breakdown uses.
        rows.sort(key=lambda r: r.collected_kg, reverse=True)

        total_in = sum((Decimal(w or 0) for _, w in in_by_type.values()), _EXACT_ZERO)
        total_out = sum((Decimal(w or 0) for _, w in out_by_type.values()), _EXACT_ZERO)
        return DayBook(
            business_date=day,
            center_id=center_id,
            center_name=centre_name,
            rows=rows,
            total_collected_kg=_kg(total_in),
            total_dispatched_kg=_kg(total_out),
            total_remainder_kg=_kg(total_in - total_out),
            quantity_unit=book_unit,
            sales=DayBookSales(
                deliveries=int(sold[0] or 0),
                quantity=Decimal(sold[1] or 0).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                quantity_unit=sold[2] or "L",
            ),
        )

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
        date_from = date_from or await self._today()
        date_to = date_to or date_from
        conditions = self._tx_conditions(
            tenant_id,
            date_from,
            date_to,
            timezone=await self._timezone(),
            center_id=center_id,
            supplier_id=supplier_id,
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
            *_unit_columns(),
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
            unit,
            units,
        ) = row
        payable = await self._payable_by_currency(conditions, branch_id)
        by_type = await self._by_milk_type(conditions, branch_id)
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
            quantity_unit=_unit(unit, units, await self._unit_default()),
            payable_by_currency=payable,
            unpriced_accepted=unpriced or 0,
            weighted_avg_fat=self._weighted(fat_sum, fat_weight),
            weighted_avg_snf=self._weighted(snf_sum, snf_weight),
            by_milk_type=by_type,
        )

    async def _by_milk_type(self, conditions, branch_id) -> list["MilkTypeRow"]:
        """Accepted collections, split by the animal (WO-55).

        Grouped on `milk_type` and NOT on `milk_type_custom`: a dairy may type
        anything into the custom field, and grouping on free text would invent
        a category per spelling. A custom type reports as `custom`, honestly,
        and the transaction still carries what was typed.

        Amounts are per currency for the same reason the total is: a summary
        that added two currencies together would be a number meaning nothing.
        """
        stmt = (
            select(
                Tx.milk_type,
                Tx.currency,
                func.count(),
                func.coalesce(func.sum(_exact(Tx.net_weight)), _EXACT_ZERO),
                func.sum(case((Tx.fat.is_not(None), _exact(Tx.fat) * _exact(Tx.net_weight)))),
                func.sum(case((Tx.fat.is_not(None), _exact(Tx.net_weight)))),
                func.coalesce(func.sum(_exact(Tx.gross_amount)), _EXACT_ZERO),
                *_unit_columns(),
            )
            .where(*conditions, ACCEPTED)
            .group_by(Tx.milk_type, Tx.currency)
        )
        default_unit = await self._unit_default()
        if branch_id is not None:
            stmt = stmt.join(CollectionCenter, CollectionCenter.id == Tx.center_id).where(
                CollectionCenter.branch_id == branch_id
            )

        merged: dict[str, dict] = {}
        for milk_type, currency, count, weight, fat_sum, fat_weight, amount, unit, units in (
            await self._session.execute(stmt)
        ).all():
            key = milk_type or "unspecified"
            row = merged.setdefault(
                key,
                {
                    "transactions": 0,
                    "weight": Decimal(0),
                    "fat_sum": Decimal(0),
                    "fat_weight": Decimal(0),
                    "amounts": {},
                    "units": set(),
                },
            )
            row["transactions"] += count or 0
            row["weight"] += Decimal(weight or 0)
            if (units or 0) > 1:
                row["units"].add("mixed")
            elif unit:
                row["units"].add(unit)
            row["fat_sum"] += Decimal(fat_sum or 0)
            row["fat_weight"] += Decimal(fat_weight or 0)
            if currency and amount:
                row["amounts"][currency] = row["amounts"].get(currency, Decimal(0)) + Decimal(
                    amount
                )

        return sorted(
            (
                MilkTypeRow(
                    milk_type=key,
                    transactions=row["transactions"],
                    net_weight_kg=_kg(row["weight"]),
                    quantity_unit=_unit(
                        next(iter(row["units"]), None), len(row["units"]), default_unit
                    ),
                    weighted_avg_fat=self._weighted(row["fat_sum"], row["fat_weight"]),
                    amount_by_currency={c: quantize_money(a, c) for c, a in row["amounts"].items()},
                )
                for key, row in merged.items()
            ),
            key=lambda r: r.net_weight_kg,
            reverse=True,
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
        date_from = date_from or await self._today()
        date_to = date_to or date_from
        limit = max(1, min(limit, 100))
        conditions = self._tx_conditions(
            tenant_id, date_from, date_to, timezone=await self._timezone()
        )
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
                func.max(Tx.created_at),
                *_unit_columns(),
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
        default_unit = await self._unit_default()
        items = [
            CenterSummaryRow(
                center_id=center_id,
                center_code=code,
                center_name=name,
                transactions=tx_count,
                accepted=accepted or 0,
                total_net_weight_kg=_kg(weight),
                quantity_unit=_unit(unit, units, default_unit),
                payable_amount=Decimal(str(payable or 0)),
                currency=("MIX" if (ncur or 0) > 1 else currency),
                weighted_avg_fat=self._weighted(fat_sum, fat_weight),
                last_collection_at=as_utc(last_at) if last_at else None,
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
                last_at,
                unit,
                units,
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
        date_from = date_from or await self._today()
        date_to = date_to or date_from
        limit = max(1, min(limit, 100))
        conditions = self._tx_conditions(
            tenant_id, date_from, date_to, timezone=await self._timezone(), center_id=center_id
        )
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
                func.max(Tx.created_at),
                *_unit_columns(),
            )
            .join(Supplier, Supplier.id == Tx.supplier_id)
            .join(SupplierProfile, SupplierProfile.supplier_id == Supplier.id)
            .where(*conditions, Tx.supplier_id.is_not(None))
            .group_by(Tx.supplier_id, Supplier.code, SupplierProfile.full_name)
            .order_by(func.sum(case((ACCEPTED, _exact(Tx.net_weight)), else_=_EXACT_ZERO)).desc())
        )
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.execute(stmt.limit(limit).offset(offset))
        default_unit = await self._unit_default()
        items = [
            SupplierSummaryRow(
                supplier_id=supplier_id,
                supplier_code=code,
                supplier_name=name,
                deliveries=deliveries,
                accepted=accepted or 0,
                total_net_weight_kg=_kg(weight),
                quantity_unit=_unit(unit, units, default_unit),
                payable_amount=Decimal(str(payable or 0)),
                currency=("MIX" if (ncur or 0) > 1 else currency),
                weighted_avg_fat=self._weighted(fat_sum, fat_weight),
                last_collection_at=as_utc(last_at) if last_at else None,
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
                last_at,
                unit,
                units,
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
        # WO-61: grouped by currency as well as status, because the currency
        # of a total is a property of the rows summed and of nothing else.
        rows = await self._session.execute(
            select(
                Settlement.status,
                Settlement.currency,
                func.count(),
                func.coalesce(func.sum(Settlement.net_amount), 0),
            )
            .where(*conditions)
            .group_by(Settlement.status, Settlement.currency)
        )
        per_status: dict[str, dict] = {}
        finalized_by_currency: dict[str, Decimal] = {}
        for status, currency, count, net in rows.all():
            net = Decimal(str(net))
            slot = per_status.setdefault(
                status, {"count": 0, "net": Decimal("0"), "currencies": set()}
            )
            slot["count"] += count
            slot["net"] += net
            if currency:
                slot["currencies"].add(currency)
                if status == "finalized":
                    finalized_by_currency[currency] = (
                        finalized_by_currency.get(currency, Decimal("0")) + net
                    )
        by_status = [
            SettlementStatusRow(
                status=status,
                count=slot["count"],
                net_amount=slot["net"],
                currency=(
                    next(iter(slot["currencies"]))
                    if len(slot["currencies"]) == 1
                    else ("MIX" if slot["currencies"] else None)
                ),
            )
            for status, slot in per_status.items()
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
        return SettlementSummary(
            by_status=sorted(by_status, key=lambda r: r.status),
            finalized_by_currency=finalized_by_currency,
            total_settlements=sum(r.count for r in by_status),
            total_lines=total_lines,
        )

    # --- one collection's money trail (DEMO-004) ----------------------------

    async def collection_chain(self, transaction_id: uuid.UUID) -> CollectionChain:
        """Follow a collection to its settlement, payment and receipt.

        Four small keyed lookups, not a scan: settlement_line by transaction,
        payment_line by settlement, receipt by payment. Every one is filtered
        by tenant as well as by key — a transaction id from another
        organization finds nothing rather than someone else's money.
        """
        tenant_id = require_current_tenant()

        line = (
            await self._session.execute(
                select(SettlementLine, Settlement)
                .join(Settlement, Settlement.id == SettlementLine.settlement_id)
                .where(
                    SettlementLine.tenant_id == tenant_id,
                    SettlementLine.transaction_id == transaction_id,
                    Settlement.status != "cancelled",
                )
                .limit(1)
            )
        ).first()
        if line is None:
            return CollectionChain(
                transaction_id=transaction_id, settlement=None, payment=None, receipt=None
            )

        settlement_line, settlement = line
        chain_settlement = ChainSettlement(
            id=settlement.id,
            settlement_number=settlement.settlement_number,
            status=settlement.status,
            period_from=settlement.period_from,
            period_to=settlement.period_to,
            currency=settlement.currency,
            gross_amount=Decimal(settlement.gross_amount),
            adjustments_amount=Decimal(settlement.adjustments_amount),
            net_amount=Decimal(settlement.net_amount),
            line_amount=Decimal(settlement_line.gross_amount),
            finalized_at=as_utc(settlement.finalized_at) if settlement.finalized_at else None,
        )

        paid = (
            await self._session.execute(
                select(PaymentLine, Payment)
                .join(Payment, Payment.id == PaymentLine.payment_id)
                .where(
                    PaymentLine.tenant_id == tenant_id,
                    PaymentLine.settlement_id == settlement.id,
                    Payment.status != "cancelled",
                )
                .order_by(Payment.created_at.desc())
                .limit(1)
            )
        ).first()
        if paid is None:
            return CollectionChain(
                transaction_id=transaction_id,
                settlement=chain_settlement,
                payment=None,
                receipt=None,
            )

        payment_line, payment = paid
        chain_payment = ChainPayment(
            id=payment.id,
            payment_number=payment.payment_number,
            status=payment.status,
            method=payment.method,
            currency=payment.currency,
            amount=Decimal(payment.amount),
            allocated_amount=Decimal(payment_line.amount),
            reference=payment.reference,
            paid_at=as_utc(payment.completed_at) if payment.completed_at else None,
        )

        receipt = await self._session.scalar(
            select(Receipt).where(Receipt.tenant_id == tenant_id, Receipt.payment_id == payment.id)
        )
        return CollectionChain(
            transaction_id=transaction_id,
            settlement=chain_settlement,
            payment=chain_payment,
            receipt=(
                ChainReceipt(
                    id=receipt.id,
                    receipt_number=receipt.receipt_number,
                    status=receipt.status,
                    net_amount=Decimal(receipt.net_amount),
                    currency=receipt.currency,
                    generated_at=as_utc(receipt.generated_at),
                )
                if receipt is not None
                else None
            ),
        )

    # --- payment summary (DEMO-002) -----------------------------------------

    async def operational_status(self, transaction_ids: list[uuid.UUID]) -> OperationalStatusPage:
        """Bulk `collection_chain`, for a page of transactions.

        Five grouped queries, whatever the page size — the last event per
        transaction, the settlement line and settlement, the payment line and
        payment, and the receipt. Every one is filtered by tenant as well as
        by key, so an id belonging to another organization simply finds
        nothing; it is never an error, and never someone else's money.

        Cancelled settlements and payments are excluded exactly as
        `collection_chain` excludes them: a cancelled settlement did not
        settle anything, and saying otherwise on a list would be the same lie
        told faster.
        """
        tenant_id = require_current_tenant()
        ids = list(dict.fromkeys(transaction_ids))
        if not ids:
            return OperationalStatusPage(items=[])

        # 1. the latest event per transaction — the "last activity" column.
        newest = (
            select(
                TransactionEvent.transaction_id.label("tx_id"),
                func.max(TransactionEvent.sequence).label("seq"),
            )
            .where(
                TransactionEvent.tenant_id == tenant_id,
                TransactionEvent.transaction_id.in_(ids),
            )
            .group_by(TransactionEvent.transaction_id)
            .subquery()
        )
        last_events = {
            row.transaction_id: row
            for row in (
                await self._session.execute(
                    select(TransactionEvent).join(
                        newest,
                        (TransactionEvent.transaction_id == newest.c.tx_id)
                        & (TransactionEvent.sequence == newest.c.seq),
                    )
                )
            ).scalars()
        }

        # 2. settlement line -> settlement, for every id at once.
        settled: dict[uuid.UUID, tuple] = {}
        for line, settlement in (
            await self._session.execute(
                select(SettlementLine, Settlement)
                .join(Settlement, Settlement.id == SettlementLine.settlement_id)
                .where(
                    SettlementLine.tenant_id == tenant_id,
                    SettlementLine.transaction_id.in_(ids),
                    Settlement.status != "cancelled",
                )
            )
        ).all():
            settled.setdefault(line.transaction_id, (line, settlement))

        # 3. payment line -> payment, keyed by the settlements we just found.
        settlement_ids = [s.id for _line, s in settled.values()]
        paid: dict[uuid.UUID, Payment] = {}
        if settlement_ids:
            for payment_line, payment in (
                await self._session.execute(
                    select(PaymentLine, Payment)
                    .join(Payment, Payment.id == PaymentLine.payment_id)
                    .where(
                        PaymentLine.tenant_id == tenant_id,
                        PaymentLine.settlement_id.in_(settlement_ids),
                        Payment.status != "cancelled",
                    )
                    .order_by(Payment.created_at.desc())
                )
            ).all():
                paid.setdefault(payment_line.settlement_id, payment)

        # 4. receipts, keyed by payment.
        payment_ids = [p.id for p in paid.values()]
        receipts: dict[uuid.UUID, Receipt] = {}
        if payment_ids:
            for receipt in (
                await self._session.scalars(
                    select(Receipt).where(
                        Receipt.tenant_id == tenant_id,
                        Receipt.payment_id.in_(payment_ids),
                    )
                )
            ).all():
                receipts.setdefault(receipt.payment_id, receipt)

        items = []
        for tx_id in ids:
            event = last_events.get(tx_id)
            pair = settled.get(tx_id)
            line, settlement = pair if pair else (None, None)
            payment = paid.get(settlement.id) if settlement is not None else None
            receipt = receipts.get(payment.id) if payment is not None else None
            items.append(
                OperationalStatus(
                    transaction_id=tx_id,
                    last_event_type=event.event_type if event else None,
                    last_event_at=as_utc(event.created_at) if event else None,
                    settlement_id=settlement.id if settlement else None,
                    settlement_number=settlement.settlement_number if settlement else None,
                    settlement_status=settlement.status if settlement else None,
                    settled_amount=Decimal(line.gross_amount) if line else None,
                    currency=settlement.currency if settlement else None,
                    payment_id=payment.id if payment else None,
                    payment_number=payment.payment_number if payment else None,
                    payment_status=payment.status if payment else None,
                    receipt_id=receipt.id if receipt else None,
                    receipt_number=receipt.receipt_number if receipt else None,
                    receipt_status=receipt.status if receipt else None,
                )
            )
        return OperationalStatusPage(items=items)

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
        # Same defect, same fix as `_tx_conditions`: a payment raised at 23:30
        # in Nairobi belongs to that local day, and a naive UTC midnight put it
        # outside the window that asked for it.
        timezone = await self._timezone()
        conditions = [Payment.tenant_id == tenant_id]
        if date_from is not None:
            start, _ = range_bounds(date_from, date_from, timezone)
            conditions.append(Payment.created_at >= start)
        if date_to is not None:
            _, end = range_bounds(date_to, date_to, timezone)
            conditions.append(Payment.created_at < end)
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
        #: WO-61: the same rows again, kept per (status, currency) so a total
        #: for a group of statuses can be reported in the currencies it is
        #: actually made of rather than in the organization's.
        per_status_currency: dict[tuple[str, str], Decimal] = {}
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
                key = (status, currency)
                per_status_currency[key] = per_status_currency.get(key, Decimal("0")) + amount

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

        def amount_of(*statuses: str) -> dict[str, Decimal]:
            """The money in those statuses, per currency. Never one number:
            a tenant with payments in two currencies has two answers."""
            out: dict[str, Decimal] = {}
            for (status, currency), amount in per_status_currency.items():
                if status in statuses:
                    out[currency] = out.get(currency, Decimal("0")) + amount
            return out

        return PaymentSummary(
            by_status=by_status,
            total_payments=sum(r.count for r in by_status),
            completed_count=count_of("completed"),
            processing_count=count_of("processing"),
            pending_count=count_of("pending", "draft"),
            failed_count=count_of("failed"),
            completed_by_currency=amount_of("completed"),
            outstanding_by_currency=amount_of("draft", "pending", "processing"),
            failed_by_currency=amount_of("failed"),
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
        date_to = date_to or await self._today()
        date_from = date_from or date_to
        conditions = self._tx_conditions(
            tenant_id,
            date_from,
            date_to,
            timezone=await self._timezone(),
            center_id=center_id,
            supplier_id=supplier_id,
        )
        # Bucketed by the DAIRY's day, through the one expression that knows
        # how (DEMO-019). PostgreSQL gets the native `AT TIME ZONE`; the
        # window above and this grouping now answer the same question, so a
        # collection recorded after local midnight sits on the point its own
        # total is counted in.
        day = local_date_sql(
            Tx.created_at, await self._timezone(), self._session.get_bind().dialect.name
        )
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
                    *_unit_columns(),
                )
                .where(*conditions)
                .group_by(day)
                .order_by(day)
            )
        ).all()

        series_units = {unit for *_, unit, _n in rows if unit}
        if any((n or 0) > 1 for *_, n in rows):
            series_units.add("mixed")
        found = {
            (value if isinstance(value, date) else date.fromisoformat(str(value)[:10])): (
                transactions,
                accepted,
                weight,
                payable,
                currency,
            )
            for value, transactions, accepted, weight, payable, currency, _unit_, _n in rows
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
        return CollectionTrend(
            date_from=date_from,
            date_to=date_to,
            points=points,
            quantity_unit=_unit(
                next(iter(series_units), None), len(series_units), await self._unit_default()
            ),
        )

    # --- rate/quality distribution (DEMO-002) -------------------------------

    async def rate_distribution(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        center_id: uuid.UUID | None = None,
    ) -> list[RateBandRow]:
        tenant_id = require_current_tenant()
        date_to = date_to or await self._today()
        date_from = date_from or date_to
        conditions = self._tx_conditions(
            tenant_id, date_from, date_to, timezone=await self._timezone(), center_id=center_id
        )
        rows = (
            await self._session.execute(
                select(
                    Tx.unit_price,
                    Tx.currency,
                    func.count(),
                    func.coalesce(func.sum(_exact(Tx.net_weight)), _EXACT_ZERO),
                    func.coalesce(func.sum(Tx.gross_amount), 0),
                    # The unit the PRICE is per (D-21 ruling 3): the pinned
                    # trade unit where one exists, the measured one otherwise.
                    func.min(func.coalesce(Tx.trade_unit, Tx.weight_unit)),
                    func.count(distinct(func.coalesce(Tx.trade_unit, Tx.weight_unit))),
                )
                .where(*conditions, ACCEPTED, PRICED)
                .group_by(Tx.unit_price, Tx.currency)
                .order_by(Tx.unit_price)
            )
        ).all()
        default_unit = await self._unit_default()
        return [
            RateBandRow(
                unit_price=Decimal(str(unit_price)),
                currency=currency,
                transactions=count,
                total_net_weight_kg=_kg(weight),
                quantity_unit=_unit(unit, units, default_unit),
                payable_amount=Decimal(str(payable)),
            )
            for unit_price, currency, count, weight, payable, unit, units in rows
            if unit_price is not None
        ]

    # --- the sales side (DEMO-010) ------------------------------------------

    async def sales_summary(
        self, *, date_from: date | None = None, date_to: date | None = None
    ) -> SalesSummary:
        """The whole receivable side in six grouped queries.

        Not one query per customer, and nothing summed in the browser: a dairy
        with three hundred households would otherwise ship three hundred rows
        to a dashboard so React could add them up, which is both slow and — for
        money — wrong, since JavaScript numbers are binary floats.

        Every sum casts to unconstrained `NUMERIC` inside the aggregate for the
        same reason the collection reports do (DB-002): the total is rounded
        once, at the end, not per row.
        """
        tenant_id = require_current_tenant()
        date_to = date_to or await self._today()
        date_from = date_from or date_to

        # 1. What went out in the period. `BILLABLE_STATUSES` is the delivery
        #    module's own definition of "this actually reached the customer";
        #    a cancelled or missed delivery is worth nothing and must not
        #    inflate a sales figure.
        period = (
            await self._session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(cast(MilkDelivery.quantity, Numeric)), _EXACT_ZERO),
                    func.coalesce(func.sum(cast(MilkDelivery.amount, Numeric)), _EXACT_ZERO),
                    func.count(distinct(MilkDelivery.customer_id)),
                    func.max(MilkDelivery.currency),
                    func.max(MilkDelivery.quantity_unit),
                ).where(
                    MilkDelivery.tenant_id == tenant_id,
                    MilkDelivery.delivery_date >= date_from,
                    MilkDelivery.delivery_date <= date_to,
                    MilkDelivery.status.in_(BILLABLE_STATUSES),
                )
            )
        ).one()

        # 2. Bills by status — counts AND totals, so "twelve issued" can be
        #    read next to what those twelve are worth.
        status_rows = (
            await self._session.execute(
                select(
                    CustomerInvoice.status,
                    CustomerInvoice.currency,
                    func.count(),
                    func.coalesce(func.sum(cast(CustomerInvoice.total, Numeric)), _EXACT_ZERO),
                )
                .where(CustomerInvoice.tenant_id == tenant_id)
                .group_by(CustomerInvoice.status, CustomerInvoice.currency)
                .order_by(CustomerInvoice.status)
            )
        ).all()

        # 3 and 4. The balance. Same definition as BillingService.balance(),
        #    applied to every customer at once instead of one at a time.
        invoiced = await self._session.scalar(
            select(
                func.coalesce(func.sum(cast(CustomerInvoice.total, Numeric)), _EXACT_ZERO)
            ).where(
                CustomerInvoice.tenant_id == tenant_id,
                CustomerInvoice.status.in_(PAYABLE_INVOICE_STATUSES),
            )
        )
        received = await self._session.scalar(
            select(
                func.coalesce(func.sum(cast(CustomerPayment.amount, Numeric)), _EXACT_ZERO)
            ).where(
                CustomerPayment.tenant_id == tenant_id,
                CustomerPayment.status == "recorded",
            )
        )

        # 5. How many households are behind, which is the question a dairy
        #    owner actually asks. Owed and paid are grouped per customer and
        #    compared in SQL — the browser never sees the per-customer rows.
        billed = (
            select(
                CustomerInvoice.customer_id.label("customer_id"),
                func.coalesce(func.sum(cast(CustomerInvoice.total, Numeric)), _EXACT_ZERO).label(
                    "owed"
                ),
            )
            .where(
                CustomerInvoice.tenant_id == tenant_id,
                CustomerInvoice.status.in_(PAYABLE_INVOICE_STATUSES),
            )
            .group_by(CustomerInvoice.customer_id)
            .subquery()
        )
        settled = (
            select(
                CustomerPayment.customer_id.label("customer_id"),
                func.coalesce(func.sum(cast(CustomerPayment.amount, Numeric)), _EXACT_ZERO).label(
                    "paid"
                ),
            )
            .where(
                CustomerPayment.tenant_id == tenant_id,
                CustomerPayment.status == "recorded",
            )
            .group_by(CustomerPayment.customer_id)
            .subquery()
        )
        customers_owing = (
            await self._session.scalar(
                select(func.count()).select_from(
                    select(billed.c.customer_id)
                    .outerjoin(settled, settled.c.customer_id == billed.c.customer_id)
                    .where(billed.c.owed > func.coalesce(settled.c.paid, _EXACT_ZERO))
                    .subquery()
                )
            )
        ) or 0

        # 6. Delivered but not yet billed — the work waiting to become money,
        #    and the number that tells a manager it is time to run billing.
        unbilled = (
            await self._session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(cast(MilkDelivery.amount, Numeric)), _EXACT_ZERO),
                ).where(
                    MilkDelivery.tenant_id == tenant_id,
                    MilkDelivery.status.in_(BILLABLE_STATUSES),
                    MilkDelivery.invoice_id.is_(None),
                )
            )
        ).one()

        customer_states = (
            await self._session.execute(
                select(Customer.status, func.count())
                .where(Customer.tenant_id == tenant_id)
                .group_by(Customer.status)
            )
        ).all()
        receipts_issued = (
            await self._session.scalar(
                select(func.count())
                .select_from(CustomerReceipt)
                .where(CustomerReceipt.tenant_id == tenant_id)
            )
        ) or 0

        per_invoice_status: dict[str, dict] = {}
        for status, currency, count, total in status_rows:
            slot = per_invoice_status.setdefault(
                status, {"count": 0, "total": Decimal("0"), "currencies": set()}
            )
            slot["count"] += count
            slot["total"] += Decimal(str(total))
            if currency:
                slot["currencies"].add(currency)
        by_status = [
            InvoiceStatusRow(
                status=status,
                count=slot["count"],
                total=_money(slot["total"]),
                currency=(
                    next(iter(slot["currencies"]))
                    if len(slot["currencies"]) == 1
                    else ("MIX" if slot["currencies"] else None)
                ),
            )
            for status, slot in sorted(per_invoice_status.items())
        ]
        return SalesSummary(
            date_from=date_from,
            date_to=date_to,
            currency=period[4],
            deliveries_in_period=period[0] or 0,
            delivered_quantity_in_period=_litres(period[1]),
            quantity_unit=period[5] or "L",
            sales_value_in_period=_money(period[2]),
            customers_served_in_period=period[3] or 0,
            active_customers=sum(c for s, c in customer_states if s == "active"),
            total_customers=sum(c for _, c in customer_states),
            invoiced=_money(invoiced),
            received=_money(received),
            receivable=_money(Decimal(invoiced or 0) - Decimal(received or 0)),
            by_status=by_status,
            open_invoices=sum(r.count for r in by_status if r.status == "issued"),
            customers_owing=customers_owing,
            unbilled_deliveries=unbilled[0] or 0,
            unbilled_amount=_money(unbilled[1]),
            receipts_issued=receipts_issued,
        )

    async def receivables(
        self,
        *,
        q: str | None = None,
        owing_only: bool = True,
        limit: int = 20,
        offset: int = 0,
    ) -> ReceivablesPage:
        """Who owes money, worst first, entirely in SQL.

        The obvious wrong implementation is to list customers and call
        `BillingService.balance()` for each — correct, and N+1 queries against
        the database for every page. This joins two grouped aggregates onto
        the customer table instead: three queries whatever the page size, and
        the same arithmetic, because both aggregates use the same status
        predicates `balance()` does.

        `total_outstanding` is deliberately computed across every match rather
        than summed from `items`. A page of twenty rows summed in the browser
        would silently understate the debt of a dairy with a hundred
        households — and it is the number the owner reads first.
        """
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        billed = (
            select(
                CustomerInvoice.customer_id.label("customer_id"),
                func.coalesce(func.sum(cast(CustomerInvoice.total, Numeric)), _EXACT_ZERO).label(
                    "invoiced"
                ),
                func.sum(case((CustomerInvoice.status == "issued", 1), else_=0)).label("open"),
                func.min(
                    case((CustomerInvoice.status == "issued", CustomerInvoice.period_from))
                ).label("oldest"),
            )
            .where(
                CustomerInvoice.tenant_id == tenant_id,
                CustomerInvoice.status.in_(PAYABLE_INVOICE_STATUSES),
            )
            .group_by(CustomerInvoice.customer_id)
            .subquery()
        )
        settled = (
            select(
                CustomerPayment.customer_id.label("customer_id"),
                func.coalesce(func.sum(cast(CustomerPayment.amount, Numeric)), _EXACT_ZERO).label(
                    "paid"
                ),
                func.max(CustomerPayment.received_at).label("last_payment_at"),
            )
            .where(
                CustomerPayment.tenant_id == tenant_id,
                CustomerPayment.status == "recorded",
            )
            .group_by(CustomerPayment.customer_id)
            .subquery()
        )

        invoiced_col = func.coalesce(billed.c.invoiced, _EXACT_ZERO)
        paid_col = func.coalesce(settled.c.paid, _EXACT_ZERO)
        outstanding_col = invoiced_col - paid_col

        conditions = [Customer.tenant_id == tenant_id]
        if q:
            like = f"%{q.strip()}%"
            conditions.append(Customer.name.ilike(like) | Customer.code.ilike(like))
        if owing_only:
            # Strictly greater than zero: a customer who has paid in full, and
            # one who has overpaid, are both settled and neither belongs on a
            # collection round.
            conditions.append(outstanding_col > 0)

        base = (
            select(
                Customer.id,
                Customer.code,
                Customer.name,
                Customer.phone,
                Customer.status,
                Customer.currency,
                invoiced_col.label("invoiced"),
                paid_col.label("paid"),
                outstanding_col.label("outstanding"),
                func.coalesce(billed.c.open, 0).label("open_invoices"),
                settled.c.last_payment_at,
                billed.c.oldest,
            )
            .select_from(Customer)
            .outerjoin(billed, billed.c.customer_id == Customer.id)
            .outerjoin(settled, settled.c.customer_id == Customer.id)
            .where(*conditions)
        )

        # ONE subquery object, used twice. Calling `.subquery()` twice would
        # build two distinct derived tables and join them — a cartesian
        # product that reports the square of the customer count and a wildly
        # inflated total.
        matched = base.subquery()
        totals = (
            await self._session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(matched.c.outstanding), _EXACT_ZERO),
                ).select_from(matched)
            )
        ).one()

        rows = (
            await self._session.execute(
                base.order_by(outstanding_col.desc(), Customer.name).limit(limit).offset(offset)
            )
        ).all()

        items = [
            ReceivableRow(
                customer_id=r[0],
                code=r[1],
                name=r[2],
                phone=r[3],
                status=r[4],
                currency=r[5],
                invoiced=_money(r[6]),
                paid=_money(r[7]),
                outstanding=_money(r[8]),
                open_invoices=r[9] or 0,
                last_payment_at=as_utc(r[10]) if r[10] else None,
                oldest_unpaid_from=r[11],
            )
            for r in rows
        ]
        return ReceivablesPage(
            items=items,
            total=totals[0] or 0,
            limit=limit,
            offset=offset,
            total_outstanding=_money(totals[1]),
            currency=items[0].currency if items else None,
        )

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
        date_to = date_to or await self._today()
        date_from = date_from or date_to

        collection = await self.daily_summary(date_from=date_from, date_to=date_to)
        settlements = await self.settlement_summary()
        payments = await self.payment_summary()
        sales = await self.sales_summary(date_from=date_from, date_to=date_to)
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
        # The sales side gets the same treatment: real backend states, real
        # counts, omitted entirely when zero.
        if sales.customers_owing:
            attention.append(
                AttentionItem(
                    key="customers_owing",
                    label="customers with an outstanding balance",
                    count=sales.customers_owing,
                    severity="warning",
                    href="/receivables",
                )
            )
        if sales.unbilled_deliveries:
            attention.append(
                AttentionItem(
                    key="unbilled_deliveries",
                    label="deliveries made but not yet billed",
                    count=sales.unbilled_deliveries,
                    severity="warning",
                    href="/deliveries?invoiced=false",
                )
            )
        draft_bills = sum(r.count for r in sales.by_status if r.status == "draft")
        if draft_bills:
            attention.append(
                AttentionItem(
                    key="draft_bills",
                    label="customer bills drafted and not yet issued",
                    count=draft_bills,
                    severity="warning",
                    href="/billing?status=draft",
                )
            )

        return DashboardSummary(
            date_from=date_from,
            date_to=date_to,
            collection=collection,
            settlements=settlements,
            payments=payments,
            sales=sales,
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
        date_from = date_from or await self._today()
        date_to = date_to or date_from
        conditions = self._tx_conditions(
            tenant_id, date_from, date_to, timezone=await self._timezone(), center_id=center_id
        )
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
        timezone: str | None = None,
        center_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
    ) -> list:
        """Closed local date range, applied as the half-open UTC interval it
        actually spans.

        **This used to build the window from NAIVE UTC MIDNIGHTS of a date
        that is the ORGANIZATION's**, and the two are not the same instant for
        any dairy that is not on UTC. For a Nairobi cooperative at 00:24 local
        — 21:24 UTC the previous day — `date_from` was correctly today's local
        date and the window began at that date's UTC midnight, three hours in
        the future. Every collection recorded that evening fell outside it, so
        the daily collection report read ZERO for a day on which milk had been
        collected, for the last three hours of every UTC day. An Indian dairy
        lost five and a half.

        DEMO-013 built `range_bounds` for exactly this and the delivery side
        has used it since; the procurement reports were never converted.
        Found by DEMO-019 when the wall clock happened to be inside the
        window — which is to say, found by the suite failing at midnight in
        Nairobi rather than by anybody reading it.
        """
        start, end = range_bounds(date_from, date_to, timezone)
        conditions = [
            Tx.tenant_id == tenant_id,
            Tx.created_at >= start,
            Tx.created_at < end,
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
