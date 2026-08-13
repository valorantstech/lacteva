"""Delivery application service (DEMO-009 / CMA.DST.01).

Recording a delivery is the busiest thing this side of the platform does: a
dairy with three hundred households does it six hundred times a day. So the
call is small — customer, date, slot, quantity — and everything else is
resolved by the domain:

  * the RATE comes from the customer's active delivery plan, never from the
    client. A round-book operator does not type prices, and a client that
    could send one could sell milk at any price it liked;
  * the AMOUNT is quantity multiplied by unit_price, computed once here in
    `Decimal` and stored. Nothing recomputes it afterwards.
"""

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.tenancy import enforce_customer_scope, require_current_tenant
from platform_core.infrastructure.events import EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.customer.service import CustomerService
from platform_core.modules.delivery.models import (
    BILLABLE_STATUSES,
    DELIVERY_SLOTS,
    DELIVERY_STATUSES,
    MilkDelivery,
)

#: Wire names, mapped from the domain name — the platform's convention.
BUS_EVENTS = {
    "DeliveryRecorded": "sales.delivery-recorded.v1",
    "DeliveryCancelled": "sales.delivery-cancelled.v1",
}

MONEY = Decimal("0.01")
#: The scale `milk_delivery.quantity` is stored at — `Numeric(12, 3)`.
QUANTITY = Decimal("0.001")


def money(value: Decimal) -> Decimal:
    """Quantise once, explicitly, HALF_UP — the platform's rounding policy."""
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def litres(value: Decimal) -> Decimal:
    """A summed volume, back at the scale the column stores.

    DEMO-012 found this by running the mobile app against real data: the
    customer's monthly card read **"23.0000000000 L"**. Aggregation casts to
    unconstrained NUMERIC — deliberately, so the sum is exact and cannot
    overflow the column's own scale — and every money figure was then
    quantised on the way out while the quantities were not. So the platform
    was publishing ten decimal places of a figure it stores to three, and both
    clients rendered it faithfully.

    Rounding here rather than in the app is the point: a client that formats a
    number has decided how many decimals a litre has, and the two clients
    would eventually disagree. The scale belongs to the column.
    """
    return Decimal(value or 0).quantize(QUANTITY, rounding=ROUND_HALF_UP)


# --- commands ----------------------------------------------------------------


class RecordDeliveryCommand(BaseModel):
    customer_id: uuid.UUID
    delivery_date: date
    slot: str = "morning"
    #: Omit to use the customer's standing quantity from their plan.
    quantity: Decimal | None = Field(default=None, ge=0)
    product: str = Field(default="RAW-COW-MILK", max_length=40)
    status: str = "delivered"
    notes: str = Field(default="", max_length=300)

    @field_validator("slot")
    @classmethod
    def _known_slot(cls, v: str) -> str:
        if v not in DELIVERY_SLOTS:
            raise ValueError(f"slot must be one of {', '.join(DELIVERY_SLOTS)}")
        return v

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in DELIVERY_STATUSES:
            raise ValueError(f"status must be one of {', '.join(DELIVERY_STATUSES)}")
        return v


class AmendDeliveryCommand(BaseModel):
    quantity: Decimal | None = Field(default=None, ge=0)
    status: str | None = None
    notes: str | None = Field(default=None, max_length=300)

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str | None) -> str | None:
        if v is not None and v not in DELIVERY_STATUSES:
            raise ValueError(f"status must be one of {', '.join(DELIVERY_STATUSES)}")
        return v


# --- views -------------------------------------------------------------------


class DeliveryView(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    delivery_date: date
    slot: str
    product: str
    quantity: Decimal
    quantity_unit: str
    unit_price: Decimal
    currency: str
    amount: Decimal
    status: str
    notes: str
    invoice_id: uuid.UUID | None
    plan_id: uuid.UUID | None
    recorded_by: uuid.UUID | None
    created_at: object

    model_config = {"from_attributes": True}


class DeliveryPage(BaseModel):
    items: list[DeliveryView]
    total: int
    limit: int
    offset: int
    #: Totals for the WHOLE filtered set, not the visible page — computed by
    #: the database, because a report that adds up one page is not a report.
    total_quantity: Decimal
    total_amount: Decimal


class DeliveryDayRow(BaseModel):
    delivery_date: date
    deliveries: int
    customers: int
    quantity: Decimal
    amount: Decimal


class DeliveryReport(BaseModel):
    date_from: date
    date_to: date
    deliveries: int
    customers_served: int
    total_quantity: Decimal
    total_amount: Decimal
    skipped: int
    by_day: list[DeliveryDayRow]


class DeliveryService:
    def __init__(self, session: AsyncSession, bus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit
        self._customers = CustomerService(session, audit)

    # --- commands ----------------------------------------------------------

    async def record(self, cmd: RecordDeliveryCommand, *, actor_id: uuid.UUID) -> MilkDelivery:
        tenant_id = require_current_tenant()
        customer = await self._customers.get(cmd.customer_id)
        if customer.status != "active":
            raise ConflictError(f"customer {customer.code} is {customer.status}")

        plan = await self._customers.active_plan(customer.id, cmd.product)
        if plan is None:
            raise ConflictError(
                f"{customer.code} has no active delivery plan for {cmd.product} — "
                "agree a rate before recording a delivery"
            )

        quantity = cmd.quantity if cmd.quantity is not None else Decimal(plan.default_quantity)
        if quantity <= 0 and cmd.status == "delivered":
            raise ConflictError("a delivered quantity must be greater than zero")

        existing = await self._session.scalar(
            select(MilkDelivery).where(
                MilkDelivery.tenant_id == tenant_id,
                MilkDelivery.customer_id == customer.id,
                MilkDelivery.delivery_date == cmd.delivery_date,
                MilkDelivery.slot == cmd.slot,
            )
        )
        if existing is not None:
            raise ConflictError(
                f"{customer.code} already has a {cmd.slot} delivery on {cmd.delivery_date}"
            )

        unit_price = Decimal(plan.unit_price)
        # The one place this figure is ever computed.
        amount = (
            money(quantity * unit_price) if cmd.status in BILLABLE_STATUSES else Decimal("0.00")
        )

        delivery = MilkDelivery(
            tenant_id=tenant_id,
            customer_id=customer.id,
            delivery_date=cmd.delivery_date,
            slot=cmd.slot,
            product=cmd.product,
            quantity=quantity,
            quantity_unit=plan.quantity_unit,
            unit_price=unit_price,
            currency=plan.currency,
            amount=amount,
            status=cmd.status,
            notes=cmd.notes,
            plan_id=plan.id,
            recorded_by=actor_id,
        )
        self._session.add(delivery)
        await self._session.flush()

        await self._audit.record(
            action="sales.delivery.recorded",
            resource_type="milk_delivery",
            resource_id=delivery.id,
            actor_id=actor_id,
            detail={
                "customer": customer.code,
                "date": str(cmd.delivery_date),
                "slot": cmd.slot,
                "quantity": str(quantity),
                "amount": str(amount),
            },
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS["DeliveryRecorded"],
                {
                    "delivery_id": str(delivery.id),
                    "customer_id": str(customer.id),
                    "delivery_date": str(cmd.delivery_date),
                    "quantity": str(quantity),
                    "amount": str(amount),
                    "currency": delivery.currency,
                },
                actor_id=actor_id,
            )
        )
        return delivery

    async def amend(
        self, delivery_id: uuid.UUID, cmd: AmendDeliveryCommand, *, actor_id: uuid.UUID
    ) -> MilkDelivery:
        """Correct a delivery that has not been billed.

        A billed delivery is frozen: it is a line on a statement the customer
        has been given, and changing it would change a document that has
        already been handed over. The correction for that is an adjustment on
        the next invoice, which this domain does not yet have (see
        DEMO-009-FINAL §14).
        """
        delivery = await self.get(delivery_id)
        if delivery.invoice_id is not None:
            raise ConflictError(
                "this delivery has been billed — correct it with an adjustment, not an edit"
            )
        if cmd.quantity is not None:
            delivery.quantity = cmd.quantity
        if cmd.status is not None:
            delivery.status = cmd.status
        if cmd.notes is not None:
            delivery.notes = cmd.notes
        delivery.amount = (
            money(Decimal(delivery.quantity) * Decimal(delivery.unit_price))
            if delivery.status in BILLABLE_STATUSES
            else Decimal("0.00")
        )
        await self._audit.record(
            action="sales.delivery.amended",
            resource_type="milk_delivery",
            resource_id=delivery.id,
            actor_id=actor_id,
            detail={"quantity": str(delivery.quantity), "status": delivery.status},
        )
        return delivery

    # --- queries -----------------------------------------------------------

    async def get(self, delivery_id: uuid.UUID) -> MilkDelivery:
        tenant_id = require_current_tenant()
        delivery = await self._session.scalar(
            select(MilkDelivery).where(
                MilkDelivery.id == delivery_id, MilkDelivery.tenant_id == tenant_id
            )
        )
        if delivery is None:
            raise NotFoundError("delivery not found")
        return delivery

    def _conditions(
        self,
        tenant_id: uuid.UUID,
        *,
        customer_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
        status: str | None,
        invoiced: bool | None,
    ) -> list:
        # DEMO-012: a customer-scoped principal sees only its own deliveries.
        # Applied here, in the one place every delivery query builds its
        # filters, so no caller can bypass it by forgetting.
        customer_id = enforce_customer_scope(customer_id)
        conditions = [MilkDelivery.tenant_id == tenant_id]
        if customer_id is not None:
            conditions.append(MilkDelivery.customer_id == customer_id)
        if date_from is not None:
            conditions.append(MilkDelivery.delivery_date >= date_from)
        if date_to is not None:
            conditions.append(MilkDelivery.delivery_date <= date_to)
        if status:
            conditions.append(MilkDelivery.status == status)
        if invoiced is True:
            conditions.append(MilkDelivery.invoice_id.isnot(None))
        if invoiced is False:
            conditions.append(MilkDelivery.invoice_id.is_(None))
        return conditions

    async def search(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        invoiced: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> DeliveryPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 200))
        conditions = self._conditions(
            tenant_id,
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            invoiced=invoiced,
        )
        total = await self._session.scalar(
            select(func.count()).select_from(MilkDelivery).where(*conditions)
        )
        # Totals over the WHOLE filtered set. Cast to unconstrained NUMERIC
        # inside the aggregate, the way every other exact sum on this platform
        # does, so a large period cannot overflow the column's precision.
        sums = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(cast(MilkDelivery.quantity, Numeric)), 0),
                    func.coalesce(func.sum(cast(MilkDelivery.amount, Numeric)), 0),
                ).where(*conditions)
            )
        ).one()
        rows = (
            await self._session.scalars(
                select(MilkDelivery)
                .where(*conditions)
                .order_by(MilkDelivery.delivery_date.desc(), MilkDelivery.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return DeliveryPage(
            items=[DeliveryView.model_validate(r) for r in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
            total_quantity=litres(sums[0]),
            total_amount=money(Decimal(sums[1] or 0)),
        )

    async def report(
        self,
        *,
        date_from: date,
        date_to: date,
        customer_id: uuid.UUID | None = None,
    ) -> DeliveryReport:
        """ "What was delivered, and what is it worth?" — answered in SQL.

        Four grouped queries whatever the size of the window. A report that
        pulled the deliveries into a browser to total them would be wrong at
        the page boundary and slow everywhere else.
        """
        tenant_id = require_current_tenant()
        billable = self._conditions(
            tenant_id,
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            status=None,
            invoiced=None,
        )

        headline = (
            await self._session.execute(
                select(
                    func.count(),
                    func.count(func.distinct(MilkDelivery.customer_id)),
                    func.coalesce(func.sum(cast(MilkDelivery.quantity, Numeric)), 0),
                    func.coalesce(func.sum(cast(MilkDelivery.amount, Numeric)), 0),
                ).where(*billable, MilkDelivery.status.in_(BILLABLE_STATUSES))
            )
        ).one()
        skipped = await self._session.scalar(
            select(func.count())
            .select_from(MilkDelivery)
            .where(*billable, MilkDelivery.status == "skipped")
        )
        by_day = (
            await self._session.execute(
                select(
                    MilkDelivery.delivery_date,
                    func.count(),
                    func.count(func.distinct(MilkDelivery.customer_id)),
                    func.coalesce(func.sum(cast(MilkDelivery.quantity, Numeric)), 0),
                    func.coalesce(func.sum(cast(MilkDelivery.amount, Numeric)), 0),
                )
                .where(*billable, MilkDelivery.status.in_(BILLABLE_STATUSES))
                .group_by(MilkDelivery.delivery_date)
                .order_by(MilkDelivery.delivery_date)
            )
        ).all()

        return DeliveryReport(
            date_from=date_from,
            date_to=date_to,
            deliveries=headline[0] or 0,
            customers_served=headline[1] or 0,
            total_quantity=litres(headline[2]),
            total_amount=money(Decimal(headline[3] or 0)),
            skipped=skipped or 0,
            by_day=[
                DeliveryDayRow(
                    delivery_date=row[0],
                    deliveries=row[1],
                    customers=row[2],
                    quantity=litres(row[3]),
                    amount=money(Decimal(row[4] or 0)),
                )
                for row in by_day
            ],
        )
