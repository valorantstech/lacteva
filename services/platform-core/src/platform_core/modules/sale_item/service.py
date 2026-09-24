"""Sale item application service (WO-81 · LACTEVA-SALES-001).

Two writes and the reads. `record` prices the item — from the catalogue, or
from the caller when the caller may — and `cancel` withdraws one with a
reason; there is no edit, for the same reason a delivery has none: a bill
somebody has read cannot change shape behind them.
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Numeric, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import ConflictError, ForbiddenError, NotFoundError
from platform_core.core.money import quantize_money
from platform_core.core.tenancy import enforce_customer_scope, require_current_tenant
from platform_core.infrastructure.events import EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.catalog.service import CatalogService
from platform_core.modules.customer.models import Customer
from platform_core.modules.sale_item.models import (
    BILLABLE_ITEM_STATUSES,
    RECORDED_VIA,
    SaleItem,
)

#: Wire names, mapped from the domain names used in this module.
BUS_EVENTS = {
    "SaleItemRecorded": "sales.item-recorded.v1",
    "SaleItemCancelled": "sales.item-cancelled.v1",
}

QUANTITY = Decimal("0.001")
MIN_REASON = 3


def quantised(value: Decimal) -> Decimal:
    return Decimal(value).quantize(QUANTITY, rounding=ROUND_HALF_UP)


# --- commands ----------------------------------------------------------------


class RecordItemCommand(BaseModel):
    sale_date: date
    product_code: str = Field(min_length=1, max_length=40)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    #: Optional. Absent, the catalogue prices it. Present, the caller must hold
    #: `sales.item.price` — checked by the service from what the route tells
    #: it, so the rule has one home.
    unit_price: Decimal | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=300)
    #: The phone's key. Replay returns the row it made the first time.
    idempotency_key: str | None = Field(default=None, max_length=80)
    recorded_via: str = "portal"

    @field_validator("product_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("recorded_via")
    @classmethod
    def _known_channel(cls, v: str) -> str:
        if v not in RECORDED_VIA:
            raise ValueError(f"recorded_via must be one of {', '.join(RECORDED_VIA)}")
        return v


class CancelItemCommand(BaseModel):
    reason: str = Field(min_length=MIN_REASON, max_length=300)


# --- views -------------------------------------------------------------------


class SaleItemView(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    sale_date: date
    product_code: str
    product_name: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    amount: Decimal
    currency: str
    status: str
    notes: str
    recorded_by: uuid.UUID | None
    recorded_via: str
    invoice_id: uuid.UUID | None
    created_at: datetime
    cancelled_at: datetime | None
    cancel_reason: str


class SaleItemPage(BaseModel):
    items: list[SaleItemView]
    total: int
    #: Recorded (not cancelled) value across the whole filtered set.
    total_amount: Decimal
    currency: str | None


def _view(row: SaleItem, name: str) -> SaleItemView:
    return SaleItemView(
        id=row.id,
        customer_id=row.customer_id,
        sale_date=row.sale_date,
        product_code=row.product_code,
        product_name=name,
        quantity=quantised(row.quantity),
        unit=row.unit,
        unit_price=quantize_money(Decimal(row.unit_price), row.currency),
        amount=quantize_money(Decimal(row.amount), row.currency),
        currency=row.currency,
        status=row.status,
        notes=row.notes,
        recorded_by=row.recorded_by,
        recorded_via=row.recorded_via,
        invoice_id=row.invoice_id,
        created_at=as_utc(row.created_at),
        cancelled_at=as_utc(row.cancelled_at) if row.cancelled_at else None,
        cancel_reason=row.cancel_reason,
    )


class SaleItemService:
    def __init__(self, session: AsyncSession, bus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit
        self._catalog = CatalogService(session, audit)

    async def _customer(self, customer_id: uuid.UUID) -> Customer:
        tenant_id = require_current_tenant()
        customer = await self._session.get(Customer, customer_id)
        if customer is None or customer.tenant_id != tenant_id:
            raise NotFoundError("customer not found")
        return customer

    # --- writes ------------------------------------------------------------------

    async def record(
        self,
        customer_id: uuid.UUID,
        cmd: RecordItemCommand,
        *,
        actor_id: uuid.UUID,
        may_price: bool,
    ) -> SaleItemView:
        """Sell one thing to one household on one day.

        `may_price` is whether the caller holds `sales.item.price`. A price in
        the command without it is refused outright — not ignored, because a
        driver whose typed price was silently replaced by the catalogue's
        would tell the household one figure and bill another.
        """
        tenant_id = require_current_tenant()
        customer = await self._customer(customer_id)
        if customer.status != "active":
            raise ConflictError(f"customer {customer.code} is {customer.status}")

        if cmd.idempotency_key:
            replay = await self._session.scalar(
                select(SaleItem).where(
                    SaleItem.tenant_id == tenant_id,
                    SaleItem.idempotency_key == cmd.idempotency_key,
                )
            )
            if replay is not None:
                names = await self._catalog.names_for({replay.product_code})
                return _view(replay, names[replay.product_code])

        product = await self._catalog.require_active(cmd.product_code)
        if cmd.unit_price is not None and not may_price:
            raise ForbiddenError("sales.item.price")
        if cmd.unit_price is not None:
            unit_price = quantize_money(cmd.unit_price, customer.currency)
        elif product.default_price is not None:
            unit_price = quantize_money(Decimal(product.default_price), customer.currency)
        else:
            raise ConflictError(
                f"{product.name} has no price in the catalogue — the owner must set one, "
                "or record this item with a price"
            )
        quantity = quantised(cmd.quantity)
        amount = quantize_money(quantity * unit_price, customer.currency)

        item = SaleItem(
            tenant_id=tenant_id,
            customer_id=customer.id,
            sale_date=cmd.sale_date,
            product_code=product.code,
            quantity=quantity,
            unit=product.unit,
            unit_price=unit_price,
            amount=amount,
            currency=customer.currency,
            status="recorded",
            notes=cmd.notes.strip(),
            recorded_by=actor_id,
            recorded_via=cmd.recorded_via,
            idempotency_key=cmd.idempotency_key,
        )
        self._session.add(item)
        await self._session.flush()

        await self._audit.record(
            action="sales.item.recorded",
            resource_type="sale_item",
            resource_id=item.id,
            actor_id=actor_id,
            detail={
                "customer": customer.code,
                "date": str(cmd.sale_date),
                "product": product.code,
                "quantity": str(quantity),
                "amount": str(amount),
                "priced_by": "caller" if cmd.unit_price is not None else "catalogue",
            },
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS["SaleItemRecorded"],
                {
                    "item_id": str(item.id),
                    "customer_id": str(customer.id),
                    "sale_date": str(cmd.sale_date),
                    "product": product.code,
                    "quantity": str(quantity),
                    "amount": str(amount),
                    "currency": item.currency,
                },
                actor_id=actor_id,
            )
        )
        return _view(item, product.name)

    async def cancel(
        self, item_id: uuid.UUID, cmd: CancelItemCommand, *, actor_id: uuid.UUID
    ) -> SaleItemView:
        """Withdraw an item, releasing it from billing. Refused once billed:
        the invoice that carries it is the record now."""
        item = await self.get(item_id)
        if item.invoice_id is not None:
            raise ConflictError("this item is on an invoice — cancel the draft invoice first")
        moment = utcnow()
        result = await self._session.execute(
            update(SaleItem)
            .where(
                SaleItem.id == item.id,
                SaleItem.tenant_id == item.tenant_id,
                SaleItem.status == "recorded",
                SaleItem.invoice_id.is_(None),
            )
            .values(status="cancelled", cancelled_at=moment, cancel_reason=cmd.reason.strip())
        )
        if result.rowcount != 1:
            raise ConflictError("this item has already been cancelled")
        await self._session.refresh(item)
        await self._audit.record(
            action="sales.item.cancelled",
            resource_type="sale_item",
            resource_id=item.id,
            actor_id=actor_id,
            detail={"reason": cmd.reason.strip(), "amount": str(item.amount)},
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS["SaleItemCancelled"],
                {
                    "item_id": str(item.id),
                    "customer_id": str(item.customer_id),
                    "sale_date": str(item.sale_date),
                    "product": item.product_code,
                    "amount": str(item.amount),
                    "reason": cmd.reason.strip(),
                },
                actor_id=actor_id,
            )
        )
        names = await self._catalog.names_for({item.product_code})
        return _view(item, names[item.product_code])

    # --- reads -------------------------------------------------------------------

    async def get(self, item_id: uuid.UUID) -> SaleItem:
        tenant_id = require_current_tenant()
        row = await self._session.get(SaleItem, item_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError("item not found")
        # DEMO-012: a household reads its own items and nobody else's.
        enforce_customer_scope(row.customer_id)
        return row

    async def list(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        invoiced: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> SaleItemPage:
        tenant_id = require_current_tenant()
        customer_id = enforce_customer_scope(customer_id)
        conditions = [SaleItem.tenant_id == tenant_id]
        if customer_id is not None:
            conditions.append(SaleItem.customer_id == customer_id)
        if date_from is not None:
            conditions.append(SaleItem.sale_date >= date_from)
        if date_to is not None:
            conditions.append(SaleItem.sale_date <= date_to)
        if status is not None:
            conditions.append(SaleItem.status == status)
        if invoiced is True:
            conditions.append(SaleItem.invoice_id.is_not(None))
        elif invoiced is False:
            conditions.append(SaleItem.invoice_id.is_(None))
        stmt = select(SaleItem).where(*conditions)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        # The value of the whole filtered set, recorded items only — cast to
        # unconstrained NUMERIC inside the aggregate (DB-002), rounded once.
        value = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(cast(SaleItem.amount, Numeric)), 0),
                    func.max(SaleItem.currency),
                ).where(*conditions, SaleItem.status.in_(BILLABLE_ITEM_STATUSES))
            )
        ).one()
        rows = (
            await self._session.scalars(
                stmt.order_by(SaleItem.sale_date.desc(), SaleItem.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        names = await self._catalog.names_for({r.product_code for r in rows})
        currency = value[1]
        return SaleItemPage(
            items=[_view(r, names[r.product_code]) for r in rows],
            total=int(total or 0),
            total_amount=quantize_money(Decimal(value[0] or 0), currency),
            currency=currency,
        )

    async def unbilled_for_period(
        self, customer_id: uuid.UUID, period_from: date, period_to: date
    ) -> Sequence[SaleItem]:
        """What billing picks up: recorded, unbilled, inside the period, in date
        order. Billing stamps `invoice_id` on each; it does not edit anything
        else here."""
        tenant_id = require_current_tenant()
        return list(
            (
                await self._session.scalars(
                    select(SaleItem)
                    .where(
                        SaleItem.tenant_id == tenant_id,
                        SaleItem.customer_id == customer_id,
                        SaleItem.sale_date >= period_from,
                        SaleItem.sale_date <= period_to,
                        SaleItem.status.in_(BILLABLE_ITEM_STATUSES),
                        SaleItem.invoice_id.is_(None),
                    )
                    .order_by(SaleItem.sale_date, SaleItem.created_at)
                )
            ).all()
        )
