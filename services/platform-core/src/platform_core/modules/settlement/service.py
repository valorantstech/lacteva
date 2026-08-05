"""Settlement module — application service (SET-001: Settlement Foundation).

Lifecycle: draft -> calculated -> finalized (immutable, BR-0010), with
cancel (history-preserving) from draft/calculated. Lines are built from
SERVER-VERIFIED pricing-calculation records — the durable
pricing.calculated.v1 events — so clients submit calculation ids, never
amounts. Totals are exact Decimal sums of the lines (BR-0011).

Rules (Business Rules Register): BR-0008 one settlement per calculation,
BR-0009 no overlapping settlements per supplier, BR-0010 finalized is
immutable, BR-0011 totals equal the sum of lines, BR-0012 no duplicate
transaction references.

NO payment concepts (SET-002+).
"""

import secrets
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.metrics import (
    SETTLEMENTS_CANCELLED,
    SETTLEMENTS_CREATED,
    SETTLEMENTS_FINALIZED,
)
from platform_core.core.tenancy import require_current_tenant
from platform_core.core.types import Money
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.collection_center.models import CollectionCenter
from platform_core.modules.event_relay.service import RelayService
from platform_core.modules.settlement.models import Settlement, SettlementLine
from platform_core.modules.supplier.models import Supplier

BUS_EVENTS = {
    "created": "settlement.created.v1",
    "updated": "settlement.updated.v1",
    "finalized": "settlement.finalized.v1",
    "cancelled": "settlement.cancelled.v1",
}

OPEN_STATUSES = ("draft", "calculated")  # line-editable states


# --- DTOs ------------------------------------------------------------------


class CreateSettlementCommand(BaseModel):
    supplier_id: uuid.UUID
    center_id: uuid.UUID
    period_from: date
    period_to: date
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return v.upper()

    @model_validator(mode="after")
    def _valid_period(self) -> "CreateSettlementCommand":
        if self.period_to < self.period_from:
            raise ValueError("period_to must not be before period_from")
        return self


class AddCalculationCommand(BaseModel):
    calculation_id: uuid.UUID
    transaction_id: uuid.UUID | None = None  # collection transaction, when known


class SettlementView(BaseModel):
    id: uuid.UUID
    settlement_number: str
    supplier_id: uuid.UUID
    center_id: uuid.UUID
    period_from: date
    period_to: date
    currency: str
    gross_amount: Decimal
    adjustments_amount: Decimal
    net_amount: Decimal
    status: str
    line_count: int
    created_at: datetime
    finalized_at: datetime | None
    cancelled_at: datetime | None


class SettlementLineView(BaseModel):
    id: uuid.UUID
    calculation_id: uuid.UUID
    transaction_id: uuid.UUID | None
    transaction_date: date
    quantity: Decimal
    quantity_unit: str
    unit_price: Decimal
    gross_amount: Decimal
    trace_reference: uuid.UUID

    model_config = {"from_attributes": True}


class SettlementDetailView(BaseModel):
    settlement: SettlementView
    lines: list[SettlementLineView]
    totals_match_lines: bool  # BR-0011 check, surfaced for review screens


class SettlementPage(BaseModel):
    items: list[SettlementView]
    total: int
    limit: int
    offset: int


def _periods_overlap(a_from: date, a_to: date, b_from: date, b_to: date) -> bool:
    """Settlement periods are CLOSED date ranges: sharing a day overlaps."""
    return a_from <= b_to and b_from <= a_to


class SettlementService:
    def __init__(
        self, session: AsyncSession, bus: EventBus, audit: AuditService, relay: RelayService
    ):
        self._session = session
        self._bus = bus
        self._audit = audit
        self._relay = relay

    # --- lifecycle --------------------------------------------------------

    async def create(self, cmd: CreateSettlementCommand, *, actor_id: uuid.UUID) -> Settlement:
        tenant_id = require_current_tenant()
        supplier = await self._session.get(Supplier, cmd.supplier_id)
        if supplier is None or supplier.tenant_id != tenant_id:
            raise NotFoundError("supplier not found")
        center = await self._session.get(CollectionCenter, cmd.center_id)
        if center is None or center.tenant_id != tenant_id:
            raise NotFoundError("collection center not found")
        await self._assert_no_period_overlap(tenant_id, cmd)
        settlement = Settlement(
            tenant_id=tenant_id,
            supplier_id=cmd.supplier_id,
            center_id=cmd.center_id,
            settlement_number=await self._generate_number(tenant_id),
            period_from=cmd.period_from,
            period_to=cmd.period_to,
            currency=cmd.currency,
        )
        self._session.add(settlement)
        await self._session.flush()
        await self._record(settlement, "created", {}, actor_id)
        SETTLEMENTS_CREATED.inc()
        return settlement

    async def add_calculation(
        self, settlement_id: uuid.UUID, cmd: AddCalculationCommand, *, actor_id: uuid.UUID
    ) -> SettlementLine:
        settlement = await self.get(settlement_id)
        self._require_open(settlement)
        record = await self._verified_calculation(settlement, cmd.calculation_id)
        await self._assert_calculation_unsettled(settlement, cmd.calculation_id)
        if cmd.transaction_id is not None:
            await self._assert_transaction_unsettled(settlement, cmd.transaction_id)
        tx_date = date.fromisoformat(record["transaction_date"])
        if not (settlement.period_from <= tx_date <= settlement.period_to):
            raise ConflictError(
                f"calculation transaction date {tx_date.isoformat()} is outside "
                f"the settlement period"
            )
        line = SettlementLine(
            settlement_id=settlement.id,
            calculation_id=cmd.calculation_id,
            transaction_id=cmd.transaction_id,
            transaction_date=tx_date,
            quantity=Decimal(record["quantity"]),
            quantity_unit=record.get("quantity_unit", "kg"),
            unit_price=Decimal(record["unit_price"]),
            gross_amount=Decimal(record["gross_amount"]),
            trace_reference=record["event_id"],
        )
        self._session.add(line)
        # Any line change makes the stored totals stale (BR-0011): back to draft.
        settlement.status = "draft"
        await self._session.flush()
        await self._record(settlement, "updated", {"line_added": str(cmd.calculation_id)}, actor_id)
        return line

    async def add_transaction(
        self, settlement_id: uuid.UUID, transaction_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> SettlementLine:
        """MVP-001 integration: settle a completed, accepted, priced milk
        transaction — delegates to add_calculation with the transaction's own
        verified calculation."""
        settlement = await self.get(settlement_id)
        tx = await self._eligible_transaction(settlement, transaction_id)
        return await self.add_calculation(
            settlement_id,
            AddCalculationCommand(calculation_id=tx.calculation_id, transaction_id=tx.id),
            actor_id=actor_id,
        )

    async def collect_period(
        self, settlement_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> dict[str, int]:
        """MVP-001 integration: add every eligible (completed, accepted,
        priced, unsettled) milk transaction of the settlement's supplier,
        center, and period. Already-settled and conflicting transactions are
        skipped, not errors — the operation is idempotent."""
        from datetime import timedelta

        from platform_core.modules.milk_collection.models import MilkCollectionTransaction

        settlement = await self.get(settlement_id)
        self._require_open(settlement)
        rows = await self._session.scalars(
            select(MilkCollectionTransaction).where(
                MilkCollectionTransaction.tenant_id == settlement.tenant_id,
                MilkCollectionTransaction.supplier_id == settlement.supplier_id,
                MilkCollectionTransaction.center_id == settlement.center_id,
                MilkCollectionTransaction.state == "COMPLETED",
                MilkCollectionTransaction.rejected_reason.is_(None),
                MilkCollectionTransaction.calculation_id.is_not(None),
                MilkCollectionTransaction.created_at
                >= datetime.combine(settlement.period_from, datetime.min.time()),
                MilkCollectionTransaction.created_at
                < datetime.combine(settlement.period_to + timedelta(days=1), datetime.min.time()),
            )
        )
        added = skipped = 0
        for tx in rows.all():
            try:
                await self.add_calculation(
                    settlement_id,
                    AddCalculationCommand(calculation_id=tx.calculation_id, transaction_id=tx.id),
                    actor_id=actor_id,
                )
                added += 1
            except ConflictError:
                skipped += 1  # already settled elsewhere or duplicate reference
        return {"added": added, "skipped": skipped}

    async def _eligible_transaction(self, settlement: Settlement, transaction_id: uuid.UUID):
        from platform_core.modules.milk_collection.models import MilkCollectionTransaction

        tx = await self._session.get(MilkCollectionTransaction, transaction_id)
        if tx is None or tx.tenant_id != settlement.tenant_id:
            raise NotFoundError("milk transaction not found")
        problems = []
        if tx.state != "COMPLETED":
            problems.append(f"transaction is {tx.state}, not COMPLETED")
        if tx.rejected_reason is not None:
            problems.append("rejected milk is not payable")
        if tx.calculation_id is None:
            problems.append("transaction has no pricing calculation")
        if tx.supplier_id != settlement.supplier_id:
            problems.append("transaction belongs to a different supplier")
        if tx.center_id != settlement.center_id:
            problems.append("transaction belongs to a different center")
        if problems:
            raise ConflictError("; ".join(problems))
        return tx

    async def remove_line(
        self, settlement_id: uuid.UUID, line_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        settlement = await self.get(settlement_id)
        self._require_open(settlement)
        line = await self._session.get(SettlementLine, line_id)
        if line is None or line.settlement_id != settlement.id:
            raise NotFoundError("settlement line not found")
        await self._session.delete(line)
        settlement.status = "draft"
        await self._record(
            settlement, "updated", {"line_removed": str(line.calculation_id)}, actor_id
        )

    async def calculate_totals(
        self, settlement_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> Settlement:
        settlement = await self.get(settlement_id)
        self._require_open(settlement)
        gross = await self._sum_lines(settlement)
        settlement.gross_amount = gross.amount
        settlement.adjustments_amount = Decimal("0.00")  # placeholder (bonus/penalty/tax later)
        settlement.net_amount = gross.plus(
            Money(amount=Decimal("0.00"), currency=settlement.currency)
        ).amount
        settlement.status = "calculated"
        await self._record(
            settlement,
            "updated",
            {
                "totals_calculated": True,
                "gross_amount": str(settlement.gross_amount),
                "net_amount": str(settlement.net_amount),
            },
            actor_id,
        )
        return settlement

    async def finalize(self, settlement_id: uuid.UUID, *, actor_id: uuid.UUID) -> Settlement:
        settlement = await self.get(settlement_id)
        if settlement.status != "calculated":
            raise ConflictError(
                "only calculated settlements can be finalized — calculate totals first"
            )
        line_count = await self._line_count(settlement.id)
        if line_count == 0:
            raise ConflictError("cannot finalize a settlement with no lines")
        # BR-0011 integrity gate: stored totals must still equal the lines.
        gross = await self._sum_lines(settlement)
        if gross.amount != Decimal(settlement.gross_amount):
            raise ConflictError("settlement totals no longer match the lines — recalculate totals")
        now = utcnow()
        claim = await self._session.execute(  # CAS: no double-finalize
            update(Settlement)
            .where(Settlement.id == settlement.id, Settlement.status == "calculated")
            .values(status="finalized", finalized_at=now, updated_at=now)
        )
        if claim.rowcount != 1:
            raise ConflictError("settlement is no longer in calculated state")
        await self._session.refresh(settlement)
        await self._record(
            settlement,
            "finalized",
            {
                "gross_amount": str(settlement.gross_amount),
                "net_amount": str(settlement.net_amount),
                "currency": settlement.currency,
                "line_count": line_count,
            },
            actor_id,
        )
        SETTLEMENTS_FINALIZED.inc()
        return settlement

    async def cancel(
        self, settlement_id: uuid.UUID, reason: str, *, actor_id: uuid.UUID
    ) -> Settlement:
        settlement = await self.get(settlement_id)
        # BR-0010: finalized is immutable — it cannot even be cancelled.
        self._require_open(settlement)
        settlement.status = "cancelled"
        settlement.cancelled_at = utcnow()
        await self._record(settlement, "cancelled", {"reason": reason}, actor_id)
        SETTLEMENTS_CANCELLED.inc()
        return settlement

    # --- queries -----------------------------------------------------------

    async def get(self, settlement_id: uuid.UUID) -> Settlement:
        tenant_id = require_current_tenant()
        settlement = await self._session.get(Settlement, settlement_id)
        if settlement is None or settlement.tenant_id != tenant_id:
            raise NotFoundError("settlement not found")
        return settlement

    async def detail(self, settlement_id: uuid.UUID) -> SettlementDetailView:
        settlement = await self.get(settlement_id)
        lines = await self._lines(settlement.id)
        line_sum = sum((Decimal(line.gross_amount) for line in lines), Decimal("0"))
        return SettlementDetailView(
            settlement=self._view(settlement, len(lines)),
            lines=[SettlementLineView.model_validate(line) for line in lines],
            totals_match_lines=Decimal(settlement.gross_amount) == line_sum,
        )

    async def search(
        self,
        *,
        q: str | None = None,
        supplier_id: uuid.UUID | None = None,
        center_id: uuid.UUID | None = None,
        status: str | None = None,
        overlapping_on: date | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SettlementPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        stmt = select(Settlement).where(Settlement.tenant_id == tenant_id)
        if q:
            stmt = stmt.where(func.lower(Settlement.settlement_number).like(f"%{q.lower()}%"))
        if supplier_id:
            stmt = stmt.where(Settlement.supplier_id == supplier_id)
        if center_id:
            stmt = stmt.where(Settlement.center_id == center_id)
        if status:
            stmt = stmt.where(Settlement.status == status)
        if overlapping_on:
            stmt = stmt.where(
                Settlement.period_from <= overlapping_on,
                Settlement.period_to >= overlapping_on,
            )
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = list(
            (
                await self._session.scalars(
                    stmt.order_by(Settlement.created_at.desc()).limit(limit).offset(offset)
                )
            ).all()
        )
        counts = await self._line_counts([s.id for s in rows])
        return SettlementPage(
            items=[self._view(s, counts.get(s.id, 0)) for s in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    # --- helpers ------------------------------------------------------------

    async def _verified_calculation(
        self, settlement: Settlement, calculation_id: uuid.UUID
    ) -> dict:
        """BR: amounts are never client-supplied — the line is built from the
        durable pricing.calculated.v1 record (the outbox event)."""
        event = await self._relay.find_aggregate_event(
            "pricing_calculation", calculation_id, tenant_id=settlement.tenant_id
        )
        if event is None:
            raise NotFoundError("pricing calculation not found")
        payload = dict(event.payload)
        if payload.get("currency") != settlement.currency:
            raise ConflictError(
                f"calculation currency {payload.get('currency')} does not match "
                f"settlement currency {settlement.currency}"
            )
        payload["event_id"] = event.id
        return payload

    async def _assert_calculation_unsettled(
        self, settlement: Settlement, calculation_id: uuid.UUID
    ) -> None:
        """BR-0008: a pricing calculation belongs to at most ONE live
        settlement (cancelled settlements release their calculations)."""
        existing = await self._session.scalar(
            select(SettlementLine, Settlement.status)
            .join(Settlement, Settlement.id == SettlementLine.settlement_id)
            .where(
                SettlementLine.calculation_id == calculation_id,
                Settlement.status != "cancelled",
                Settlement.tenant_id == settlement.tenant_id,
            )
        )
        if existing is not None:
            raise ConflictError("this pricing calculation is already settled")

    async def _assert_transaction_unsettled(
        self, settlement: Settlement, transaction_id: uuid.UUID
    ) -> None:
        """BR-0012: a collection transaction may be referenced by at most one
        live settlement line."""
        existing = await self._session.scalar(
            select(SettlementLine)
            .join(Settlement, Settlement.id == SettlementLine.settlement_id)
            .where(
                SettlementLine.transaction_id == transaction_id,
                Settlement.status != "cancelled",
                Settlement.tenant_id == settlement.tenant_id,
            )
        )
        if existing is not None:
            raise ConflictError("this collection transaction is already settled")

    async def _assert_no_period_overlap(
        self, tenant_id: uuid.UUID, cmd: CreateSettlementCommand
    ) -> None:
        """BR-0009: settlements must not overlap for the same supplier and
        period (cancelled settlements do not block)."""
        others = await self._session.scalars(
            select(Settlement).where(
                Settlement.tenant_id == tenant_id,
                Settlement.supplier_id == cmd.supplier_id,
                Settlement.status != "cancelled",
            )
        )
        for other in others.all():
            if _periods_overlap(cmd.period_from, cmd.period_to, other.period_from, other.period_to):
                raise ConflictError(
                    f"period overlaps settlement {other.settlement_number} "
                    f"({other.period_from} to {other.period_to}) for this supplier"
                )

    async def _sum_lines(self, settlement: Settlement) -> Money:
        """Exact Decimal sum of line gross amounts (BR-0011, BR-0005)."""
        total = Money(amount=Decimal("0.00"), currency=settlement.currency)
        for line in await self._lines(settlement.id):
            total = total.plus(
                Money(amount=Decimal(line.gross_amount), currency=settlement.currency)
            )
        return total

    async def _lines(self, settlement_id: uuid.UUID) -> list[SettlementLine]:
        rows = await self._session.scalars(
            select(SettlementLine)
            .where(SettlementLine.settlement_id == settlement_id)
            .order_by(SettlementLine.transaction_date, SettlementLine.created_at)
        )
        return list(rows.all())

    async def _line_count(self, settlement_id: uuid.UUID) -> int:
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(SettlementLine)
                .where(SettlementLine.settlement_id == settlement_id)
            )
            or 0
        )

    async def _line_counts(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not ids:
            return {}
        rows = await self._session.execute(
            select(SettlementLine.settlement_id, func.count())
            .where(SettlementLine.settlement_id.in_(ids))
            .group_by(SettlementLine.settlement_id)
        )
        return dict(rows.all())

    def _view(self, settlement: Settlement, line_count: int) -> SettlementView:
        return SettlementView(
            id=settlement.id,
            settlement_number=settlement.settlement_number,
            supplier_id=settlement.supplier_id,
            center_id=settlement.center_id,
            period_from=settlement.period_from,
            period_to=settlement.period_to,
            currency=settlement.currency,
            gross_amount=Decimal(settlement.gross_amount),
            adjustments_amount=Decimal(settlement.adjustments_amount),
            net_amount=Decimal(settlement.net_amount),
            status=settlement.status,
            line_count=line_count,
            created_at=settlement.created_at,
            finalized_at=settlement.finalized_at,
            cancelled_at=settlement.cancelled_at,
        )

    @staticmethod
    def _require_open(settlement: Settlement) -> None:
        # BR-0010: finalized settlements are immutable; cancelled is terminal.
        if settlement.status == "finalized":
            raise ConflictError("finalized settlements are immutable")
        if settlement.status == "cancelled":
            raise ConflictError("cancelled settlements cannot be modified")

    async def _record(
        self, settlement: Settlement, event: str, data: dict, actor_id: uuid.UUID
    ) -> None:
        await self._audit.record(
            action=f"settlement.{event}",
            resource_type="settlement",
            resource_id=settlement.id,
            actor_id=actor_id,
            detail={"number": settlement.settlement_number, **data},
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS[event],
                {
                    "settlement_id": str(settlement.id),
                    "settlement_number": settlement.settlement_number,
                    "supplier_id": str(settlement.supplier_id),
                    "status": settlement.status,
                    **data,
                },
                actor_id=actor_id,
                aggregate_type="settlement",
                aggregate_id=settlement.id,
            )
        )

    async def _generate_number(self, tenant_id: uuid.UUID) -> str:
        for _ in range(5):
            candidate = "STL-" + secrets.token_hex(3).upper()
            exists = await self._session.scalar(
                select(Settlement).where(
                    Settlement.tenant_id == tenant_id,
                    Settlement.settlement_number == candidate,
                )
            )
            if exists is None:
                return candidate
        raise ConflictError("could not generate a unique settlement number")
