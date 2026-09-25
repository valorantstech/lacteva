"""The month sheet — the shop's register, computed (WO-84).

The client's `Dailymilk Delivery 025.xlsx` is four hundred rows, thirty-one
columns of litres, then the month's totals and what was received. That grid
is not a report they produce; it IS their register, the thing they look at
every day and the thing they will check Lacteva against during the parallel
run. This module gives it back to them, computed from what the platform
already holds, in the column order of their own sheet.

Four rules, each with a test:

* **A fixed number of queries, whatever the size of the dairy.** Four
  hundred households by thirty-one days is twelve thousand cells and is ONE
  delivery query, one roster, one rates read, one items aggregate, two
  opening-balance aggregates and one payments read — eight statements for
  five customers and eight for five hundred. Never a loop over customers.
* **Only a `delivered` quantity is a number.** A `scheduled` day is null, not
  zero: that distinction is the whole safety argument of DEMO-016, and a grid
  that showed scheduled litres would be claiming milk was delivered. A
  skipped day is null too — nothing arrived.
* **One row per (customer, product).** Flat C-1603 takes cow AND buffalo and
  appears twice in their own sheet; here it appears twice correctly, as one
  household with two standing orders, and `product=` narrows to one.
* **The money is the platform's.** The Price column is the active plan's
  rate; the milk amount is the sum of what each delivery recorded at the
  rate that applied on its day (WO-89 will let a day differ); "past due" is
  the balance carried into the month, computed the way the customer's own
  statement computes its opening figure; "received" is what was paid inside
  the month. Nothing here multiplies a quantity by a rate.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.business_time import (
    business_date_of,
    business_today,
    month_bounds,
    range_bounds,
)
from platform_core.core.errors import NotFoundError, ValidationError
from platform_core.core.money import quantize_money
from platform_core.core.org_context import tenant_currency, tenant_timezone
from platform_core.core.tenancy import enforce_customer_scope, require_current_tenant
from platform_core.modules.billing.models import (
    PAYABLE_INVOICE_STATUSES,
    CustomerInvoice,
    CustomerPayment,
)
from platform_core.modules.customer.service import CustomerService
from platform_core.modules.delivery.models import BILLABLE_STATUSES, MilkDelivery
from platform_core.modules.sale_item.models import BILLABLE_ITEM_STATUSES, SaleItem

ZERO = Decimal("0.00")


class MonthCell(BaseModel):
    """One day of one row. `quantity` is a number ONLY for a delivered day."""

    quantity: Decimal | None = None
    #: The delivery behind the cell, so the sheet can open it for correction
    #: through `record`/`amend` — never a write path of its own.
    delivery_id: uuid.UUID | None = None
    status: str | None = None
    #: On an invoice already: read-only in the editor, and the cell says why.
    billed: bool = False


class MonthRow(BaseModel):
    customer_id: uuid.UUID
    code: str
    name: str
    product: str
    #: The ACTIVE plan's rate, or null when the household has no standing
    #: order for this product any more (the deliveries still show).
    unit_price: Decimal | None
    quantity_unit: str
    #: One entry per day of the month, in order; null where nothing was delivered.
    days: list[MonthCell | None]
    total_quantity: Decimal
    milk_amount: Decimal
    #: Shop items sold to the household in the month (WO-81) — the "other
    #: item" figure. On the FIRST of a household's rows only, so a two-milk
    #: household is not charged for its dahi twice in the footer.
    items_amount: Decimal
    previous_balance: Decimal
    total_due: Decimal
    received: Decimal
    method: str | None
    received_on: date | None


class MonthTotals(BaseModel):
    quantity: Decimal
    milk_amount: Decimal
    items_amount: Decimal
    previous_balance: Decimal
    total_due: Decimal
    received: Decimal


class MonthSheet(BaseModel):
    year: int
    month: int
    date_from: date
    date_to: date
    #: The organisation's own today, so the client can mark the column.
    today: date
    currency: str
    quantity_unit: str
    product: str | None
    route_id: uuid.UUID | None
    rows: list[MonthRow]
    #: Litres per day, over every row: the sheet's bottom line.
    day_totals: list[Decimal]
    totals: MonthTotals


@dataclass(frozen=True)
class RouteScope:
    """Which households a route visits, handed in by the API layer (the
    delivery module knows nothing about routes — DEMO-037's shape)."""

    route_id: uuid.UUID
    customer_ids: frozenset[uuid.UUID]


def _period(year: int | None, month: int | None, today: date) -> tuple[date, date]:
    if (year is None) != (month is None):
        raise ValidationError("year and month go together")
    if year is None:
        return month_bounds(today)
    if not 1 <= month <= 12:  # type: ignore[operator]
        raise ValidationError("month must be 1-12")
    if not 2000 <= year <= 2100:
        raise ValidationError("year is out of range")
    return month_bounds(date(year, month, 1))  # type: ignore[arg-type]


class MonthSheetService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._customers = CustomerService(session, audit=None)  # type: ignore[arg-type]

    async def sheet(
        self,
        *,
        year: int | None = None,
        month: int | None = None,
        product: str | None = None,
        route: RouteScope | None = None,
    ) -> MonthSheet:
        tenant_id = require_current_tenant()
        timezone = await tenant_timezone(self._session)
        today = business_today(timezone)
        date_from, date_to = _period(year, month, today)
        days = (date_to - date_from).days + 1
        currency = await tenant_currency(self._session)

        def money(value: Decimal) -> Decimal:
            return quantize_money(value, currency)

        # DEMO-012: a household's own login sees its own row and nothing else.
        scope = enforce_customer_scope(None)
        customers = await self._customers.roster(status="active")
        if scope is not None:
            customers = [c for c in customers if c.id == scope]
        if route is not None:
            customers = [c for c in customers if c.id in route.customer_ids]
        by_customer = {c.id: c for c in customers}
        ids = set(by_customer)

        rates = await self._customers.plan_rates(product=product)

        # 1. Every delivery of the month, one query. Only the columns a cell
        # needs; the sums are done here, on rows already in hand.
        conditions = [
            MilkDelivery.tenant_id == tenant_id,
            MilkDelivery.delivery_date >= date_from,
            MilkDelivery.delivery_date <= date_to,
        ]
        if product is not None:
            conditions.append(MilkDelivery.product == product)
        if scope is not None:
            conditions.append(MilkDelivery.customer_id == scope)
        delivery_rows = (
            await self._session.execute(
                select(
                    MilkDelivery.id,
                    MilkDelivery.customer_id,
                    MilkDelivery.product,
                    MilkDelivery.delivery_date,
                    MilkDelivery.quantity,
                    MilkDelivery.amount,
                    MilkDelivery.status,
                    MilkDelivery.invoice_id,
                    MilkDelivery.quantity_unit,
                ).where(*conditions)
            )
        ).all()

        # 2. Items, one aggregate.
        items = dict(
            (
                await self._session.execute(
                    select(
                        SaleItem.customer_id,
                        func.coalesce(func.sum(cast(SaleItem.amount, Numeric)), 0),
                    )
                    .where(
                        SaleItem.tenant_id == tenant_id,
                        SaleItem.sale_date >= date_from,
                        SaleItem.sale_date <= date_to,
                        SaleItem.status.in_(BILLABLE_ITEM_STATUSES),
                    )
                    .group_by(SaleItem.customer_id)
                )
            ).all()
        )

        # 3. The balance carried into the month — the statement's opening
        # figure, per customer, as two aggregates instead of two per customer.
        window_start, window_end = range_bounds(date_from, date_to, timezone)
        invoiced_before = dict(
            (
                await self._session.execute(
                    select(
                        CustomerInvoice.customer_id,
                        func.coalesce(func.sum(cast(CustomerInvoice.total, Numeric)), 0),
                    )
                    .where(
                        CustomerInvoice.tenant_id == tenant_id,
                        CustomerInvoice.status.in_(PAYABLE_INVOICE_STATUSES),
                        CustomerInvoice.issued_at < window_start,
                    )
                    .group_by(CustomerInvoice.customer_id)
                )
            ).all()
        )
        paid_before = dict(
            (
                await self._session.execute(
                    select(
                        CustomerPayment.customer_id,
                        func.coalesce(func.sum(cast(CustomerPayment.amount, Numeric)), 0),
                    )
                    .where(
                        CustomerPayment.tenant_id == tenant_id,
                        CustomerPayment.status == "recorded",
                        CustomerPayment.received_at < window_start,
                    )
                    .group_by(CustomerPayment.customer_id)
                )
            ).all()
        )

        # 4. What was received inside the month: the sum, and the method and
        # date of the LATEST payment — the two cells their sheet keeps.
        payments = (
            await self._session.execute(
                select(
                    CustomerPayment.customer_id,
                    CustomerPayment.amount,
                    CustomerPayment.method,
                    CustomerPayment.received_at,
                ).where(
                    CustomerPayment.tenant_id == tenant_id,
                    CustomerPayment.status == "recorded",
                    CustomerPayment.received_at >= window_start,
                    CustomerPayment.received_at < window_end,
                )
            )
        ).all()
        received: dict[uuid.UUID, Decimal] = {}
        latest: dict[uuid.UUID, tuple[datetime, str]] = {}
        for customer_id, amount, method, received_at in payments:
            received[customer_id] = received.get(customer_id, ZERO) + Decimal(amount)
            seen = latest.get(customer_id)
            if seen is None or received_at > seen[0]:
                latest[customer_id] = (received_at, method)

        # --- assemble ------------------------------------------------------
        # Rows: every (customer, product) with an active plan, plus every pair
        # that has a delivery this month even if the plan has since gone.
        pairs: dict[tuple[uuid.UUID, str], dict[int, MonthCell]] = {}
        units: dict[tuple[uuid.UUID, str], str] = {}
        for (customer_id, prod), (_rate, unit) in rates.items():
            if customer_id in ids:
                pairs.setdefault((customer_id, prod), {})
                units[(customer_id, prod)] = unit
        amounts: dict[tuple[uuid.UUID, str], Decimal] = {}
        for (
            did,
            customer_id,
            prod,
            day,
            quantity,
            amount,
            status,
            invoice_id,
            unit,
        ) in delivery_rows:
            if customer_id not in ids:
                continue
            key = (customer_id, prod)
            cells = pairs.setdefault(key, {})
            units.setdefault(key, unit)
            index = (day - date_from).days
            delivered = status in BILLABLE_STATUSES
            cells[index] = MonthCell(
                quantity=Decimal(quantity) if delivered else None,
                delivery_id=did,
                status=status,
                billed=invoice_id is not None,
            )
            if delivered:
                amounts[key] = amounts.get(key, ZERO) + Decimal(amount)

        default_unit = next(iter(units.values()), "L")
        rows: list[MonthRow] = []
        day_totals = [Decimal("0.000") for _ in range(days)]
        totals = MonthTotals(
            quantity=Decimal("0.000"),
            milk_amount=ZERO,
            items_amount=ZERO,
            previous_balance=ZERO,
            total_due=ZERO,
            received=ZERO,
        )
        seen_customer: set[uuid.UUID] = set()
        for key in sorted(pairs, key=lambda k: (by_customer[k[0]].code, k[1])):
            customer_id, prod = key
            customer = by_customer[customer_id]
            cells = pairs[key]
            day_cells: list[MonthCell | None] = [cells.get(i) for i in range(days)]
            quantity = sum(
                (c.quantity for c in day_cells if c is not None and c.quantity is not None),
                Decimal("0.000"),
            )
            for i, c in enumerate(day_cells):
                if c is not None and c.quantity is not None:
                    day_totals[i] += c.quantity
            first = customer_id not in seen_customer
            seen_customer.add(customer_id)
            items_amount = money(Decimal(items.get(customer_id, 0))) if first else ZERO
            previous = (
                money(
                    Decimal(invoiced_before.get(customer_id, 0))
                    - Decimal(paid_before.get(customer_id, 0))
                )
                if first
                else ZERO
            )
            got = money(received.get(customer_id, ZERO)) if first else ZERO
            milk_amount = money(amounts.get(key, ZERO))
            when = latest.get(customer_id) if first else None
            rate = rates.get(key)
            row = MonthRow(
                customer_id=customer_id,
                code=customer.code,
                name=customer.name,
                product=prod,
                unit_price=rate[0] if rate else None,
                quantity_unit=units.get(key, default_unit),
                days=day_cells,
                total_quantity=quantity,
                milk_amount=milk_amount,
                items_amount=items_amount,
                previous_balance=previous,
                total_due=money(previous + milk_amount + items_amount),
                received=got,
                method=when[1] if when else None,
                received_on=business_date_of(when[0], timezone) if when else None,
            )
            rows.append(row)
            totals.quantity += quantity
            totals.milk_amount += milk_amount
            totals.items_amount += items_amount
            totals.previous_balance += previous
            totals.total_due += row.total_due
            totals.received += got

        return MonthSheet(
            year=date_from.year,
            month=date_from.month,
            date_from=date_from,
            date_to=date_to,
            today=today,
            currency=currency,
            quantity_unit=default_unit,
            product=product,
            route_id=route.route_id if route else None,
            rows=rows,
            day_totals=day_totals,
            totals=totals,
        )


def resolve_route(memberships, route_id: uuid.UUID) -> RouteScope:
    """Pick one route's households out of the memberships the API hands over."""
    for m in memberships:
        if getattr(m, "route_id", None) == route_id:
            return RouteScope(route_id=route_id, customer_ids=frozenset(m.customer_ids))
    raise NotFoundError("route not found")


# --- the file they already keep -------------------------------------------------

#: Their sheet's order, exactly: the day columns between, the totals block
#: after. Matching it is what makes a diff against `Dailymilk Delivery
#: 025.xlsx` possible during the parallel run.
LEADING = ("Sr", "Customer", "Code", "Product", "Price")
TRAILING = ("Total milk", "Other items", "Past due", "Total", "Received", "Method", "Date")


def to_csv(sheet: MonthSheet) -> str:
    """The grid as a file: a blank cell is BLANK — not 0, not a dash."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    days = (sheet.date_to - sheet.date_from).days + 1
    writer.writerow([*LEADING, *(str(d) for d in range(1, days + 1)), *TRAILING])
    for index, row in enumerate(sheet.rows, 1):
        writer.writerow(
            [
                index,
                row.name,
                row.code,
                row.product,
                "" if row.unit_price is None else str(row.unit_price),
                *("" if c is None or c.quantity is None else _plain(c.quantity) for c in row.days),
                _plain(row.total_quantity),
                str(row.milk_amount),
                str(row.items_amount) if row.items_amount != ZERO else "",
                str(row.previous_balance) if row.previous_balance != ZERO else "",
                str(row.total_due),
                str(row.received) if row.received != ZERO else "",
                row.method or "",
                row.received_on.isoformat() if row.received_on else "",
            ]
        )
    writer.writerow(
        [
            "",
            "TOTAL",
            "",
            "",
            "",
            *(_plain(q) if q else "" for q in sheet.day_totals),
            _plain(sheet.totals.quantity),
            str(sheet.totals.milk_amount),
            str(sheet.totals.items_amount),
            str(sheet.totals.previous_balance),
            str(sheet.totals.total_due),
            str(sheet.totals.received),
            "",
            "",
        ]
    )
    return buffer.getvalue()


def _plain(quantity: Decimal) -> str:
    """`1.000` reads as `1` and `1.500` as `1.5`, the way their sheet writes it."""
    text = format(quantity.normalize(), "f")
    return text if text else "0"


def filename(sheet: MonthSheet) -> str:
    suffix = f"-{sheet.product}" if sheet.product else ""
    return f"deliveries-{sheet.year}-{sheet.month:02d}{suffix}.csv"
