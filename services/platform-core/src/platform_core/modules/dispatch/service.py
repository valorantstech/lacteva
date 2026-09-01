"""Dispatch application service (BR-0030 · LACTEVA-STOCK-001).

Two writes and one read. There is no third write, and that is the design: a
dispatch is corrected by cancelling it and recording the right one, so the
module offers `record` and `cancel` and nothing that mutates a recorded row.
"""

import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import ConflictError, NotFoundError, ValidationError
from platform_core.core.milk import MILK_TYPES
from platform_core.core.tenancy import require_current_tenant
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.dispatch.models import (
    DESTINATION_MAX,
    MilkDispatch,
)

#: Wire names, mapped from the domain names used in this module. Nothing
#: publishes a literal.
BUS_EVENTS = {
    "DispatchRecorded": "operations.dispatch-recorded.v1",
    "DispatchCancelled": "operations.dispatch-cancelled.v1",
}

#: The scale `milk_dispatch.quantity` is stored at — `Numeric(12, 3)`.
QUANTITY = Decimal("0.001")

#: A cancellation reason short enough to be no reason at all. The same floor
#: the rate override uses (BR-0029): "x" is not an explanation, and an
#: unexplained cancellation is exactly what an auditor asks about.
MIN_REASON = 3


def kilograms(value: Decimal | None) -> Decimal:
    """A quantity back at the scale the column stores (DEMO-012).

    Kilograms, like the collection side. See the model for why this ledger
    refuses to mix units.
    """
    return Decimal(value or 0).quantize(QUANTITY, rounding=ROUND_HALF_UP)


# --- commands ----------------------------------------------------------------


class RecordDispatchCommand(BaseModel):
    center_id: uuid.UUID
    business_date: date
    milk_type: str
    quantity: Decimal = Field(gt=0)
    quantity_unit: str = Field(default="kg", max_length=8)
    destination: str = Field(min_length=1, max_length=DESTINATION_MAX)
    reference: str = Field(default="", max_length=60)
    notes: str = Field(default="", max_length=300)

    @field_validator("milk_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        # The one vocabulary, shared with the collection side, because the day
        # book subtracts one from the other.
        if v not in MILK_TYPES:
            raise ValueError(f"milk_type must be one of {', '.join(MILK_TYPES)}")
        return v


class CancelDispatchCommand(BaseModel):
    #: Mandatory, and long enough to say something. A dispatch is immutable;
    #: cancelling one is how a mistake is corrected, and a correction nobody
    #: explained is indistinguishable from milk quietly disappearing.
    reason: str = Field(min_length=MIN_REASON, max_length=300)


# --- views -------------------------------------------------------------------


class DispatchView(BaseModel):
    id: uuid.UUID
    center_id: uuid.UUID
    business_date: date
    milk_type: str
    quantity: Decimal
    quantity_unit: str
    destination: str
    reference: str
    notes: str
    status: str
    recorded_by: uuid.UUID | None
    created_at: datetime
    cancelled_by: uuid.UUID | None
    cancelled_at: datetime | None
    cancel_reason: str


class DispatchPage(BaseModel):
    items: list[DispatchView]
    total: int
    limit: int
    offset: int


def _view(row: MilkDispatch) -> DispatchView:
    return DispatchView(
        id=row.id,
        center_id=row.center_id,
        business_date=row.business_date,
        milk_type=row.milk_type,
        quantity=kilograms(row.quantity),
        quantity_unit=row.quantity_unit,
        destination=row.destination,
        reference=row.reference,
        notes=row.notes,
        status=row.status,
        recorded_by=row.recorded_by,
        created_at=as_utc(row.created_at),
        cancelled_by=row.cancelled_by,
        cancelled_at=as_utc(row.cancelled_at) if row.cancelled_at else None,
        cancel_reason=row.cancel_reason,
    )


class DispatchService:
    def __init__(self, session: AsyncSession, bus: EventBus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit

    async def record(self, cmd: RecordDispatchCommand, *, actor_id: uuid.UUID) -> DispatchView:
        tenant_id = require_current_tenant()
        # The centre is checked by asking the module that owns it, by id, and
        # never by reading its table (baseline: modules meet by UUID).
        from platform_core.modules.collection_center.models import CollectionCenter

        centre = await self._session.get(CollectionCenter, cmd.center_id)
        if centre is None or centre.tenant_id != tenant_id:
            raise NotFoundError("collection center not found")

        dispatch = MilkDispatch(
            tenant_id=tenant_id,
            center_id=cmd.center_id,
            business_date=cmd.business_date,
            milk_type=cmd.milk_type,
            quantity=kilograms(cmd.quantity),
            quantity_unit=cmd.quantity_unit,
            destination=cmd.destination.strip(),
            reference=cmd.reference.strip(),
            notes=cmd.notes,
            recorded_by=actor_id,
        )
        self._session.add(dispatch)
        await self._session.flush()
        await self._audit.record(
            action="operations.dispatch.recorded",
            resource_type="milk_dispatch",
            resource_id=dispatch.id,
            actor_id=actor_id,
            detail={
                "center_id": str(cmd.center_id),
                "business_date": str(cmd.business_date),
                "milk_type": cmd.milk_type,
                "quantity": str(kilograms(cmd.quantity)),
                "destination": dispatch.destination,
            },
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS["DispatchRecorded"],
                {
                    "dispatch_id": str(dispatch.id),
                    "center_id": str(cmd.center_id),
                    "business_date": str(cmd.business_date),
                    "milk_type": cmd.milk_type,
                    "quantity": str(kilograms(cmd.quantity)),
                    "quantity_unit": dispatch.quantity_unit,
                    "destination": dispatch.destination,
                },
                actor_id=actor_id,
            )
        )
        return _view(dispatch)

    async def cancel(
        self, dispatch_id: uuid.UUID, cmd: CancelDispatchCommand, *, actor_id: uuid.UUID
    ) -> DispatchView:
        """Withdraw a dispatch recorded in error, with a reason.

        CAS rather than read-then-write, the platform's idiom: two managers
        cancelling the same tanker at once produce one cancellation and one
        refusal, not two audit entries claiming the same change.
        """
        dispatch = await self.get(dispatch_id)
        if not cmd.reason.strip():
            raise ValidationError("a cancellation needs a reason")
        moment = utcnow()
        result = await self._session.execute(
            update(MilkDispatch)
            .where(
                MilkDispatch.id == dispatch.id,
                MilkDispatch.tenant_id == dispatch.tenant_id,
                MilkDispatch.status == "recorded",
            )
            .values(
                status="cancelled",
                cancelled_by=actor_id,
                cancelled_at=moment,
                cancel_reason=cmd.reason.strip(),
            )
        )
        if result.rowcount != 1:
            raise ConflictError("this dispatch has already been cancelled")
        await self._session.refresh(dispatch)
        await self._audit.record(
            action="operations.dispatch.cancelled",
            resource_type="milk_dispatch",
            resource_id=dispatch.id,
            actor_id=actor_id,
            detail={"reason": cmd.reason.strip(), "quantity": str(kilograms(dispatch.quantity))},
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS["DispatchCancelled"],
                {
                    "dispatch_id": str(dispatch.id),
                    "center_id": str(dispatch.center_id),
                    "business_date": str(dispatch.business_date),
                    "milk_type": dispatch.milk_type,
                    "quantity": str(kilograms(dispatch.quantity)),
                    "reason": cmd.reason.strip(),
                },
                actor_id=actor_id,
            )
        )
        return _view(dispatch)

    async def view(self, dispatch_id: uuid.UUID) -> DispatchView:
        """One dispatch, as the API states it. The row itself stays inside
        the module — a route holding a mapped object is a route that could
        write one."""
        return _view(await self.get(dispatch_id))

    async def get(self, dispatch_id: uuid.UUID) -> MilkDispatch:
        tenant_id = require_current_tenant()
        row = await self._session.get(MilkDispatch, dispatch_id)
        if row is None or row.tenant_id != tenant_id:
            # Another tenant's dispatch is a 404, never a 403.
            raise NotFoundError("dispatch not found")
        return row

    async def list(
        self,
        *,
        center_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        milk_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> DispatchPage:
        tenant_id = require_current_tenant()
        stmt = select(MilkDispatch).where(MilkDispatch.tenant_id == tenant_id)
        if center_id:
            stmt = stmt.where(MilkDispatch.center_id == center_id)
        if date_from:
            stmt = stmt.where(MilkDispatch.business_date >= date_from)
        if date_to:
            stmt = stmt.where(MilkDispatch.business_date <= date_to)
        if milk_type:
            stmt = stmt.where(MilkDispatch.milk_type == milk_type)
        if status:
            stmt = stmt.where(MilkDispatch.status == status)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            await self._session.scalars(
                stmt.order_by(MilkDispatch.business_date.desc(), MilkDispatch.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return DispatchPage(
            items=[_view(r) for r in rows],
            total=int(total or 0),
            limit=limit,
            offset=offset,
        )
