"""Milk Collection module — sessions and the transaction engine.

State machine (spec-mandated):
NEW -> SUPPLIER_IDENTIFIED -> MILK_RECEIVED -> WEIGHT_CAPTURED ->
QUALITY_PENDING -> QUALITY_CAPTURED -> PRICING_PENDING -> PRICED ->
ACCEPTED | REJECTED -> COMPLETED.  CANCELLED only before a decision.

Every step: state-guarded (optimistic — a stale caller gets 409), appended
to the ordered transaction event log, audited, and published on the bus.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.tenancy import require_current_tenant
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.infrastructure.hardware import mock_analyzer, mock_scale
from platform_core.modules.audit.service import AuditService
from platform_core.modules.collection_center.models import CollectionCenter
from platform_core.modules.milk_collection.models import (
    MILK_TYPES,
    TERMINAL_STATES,
    CollectionSession,
    MilkCollectionTransaction,
    TransactionEvent,
    TransactionMetrics,
    TransactionSnapshot,
)
from platform_core.modules.operational_readiness.service import OperationalReadinessService
from platform_core.modules.supplier.models import (
    Supplier,
    SupplierCenterAssignment,
    SupplierProfile,
)
from platform_core.modules.supplier.service import parse_qr_payload

if TYPE_CHECKING:
    from platform_core.modules.pricing.calculator import PricingCalculationService
    from platform_core.modules.pricing.resolution import PricingResolutionService

MAX_GROSS_KG = 200.0
QUALITY_RANGES = {  # raw plausibility bounds; grading/calculations come later
    "fat": (0.0, 15.0),
    "snf": (0.0, 15.0),
    "clr": (20.0, 40.0),
    "density": (1.000, 1.150),
    "temperature_c": (0.0, 50.0),
}

# Envelope event types on the bus, keyed by the log event name.
BUS_EVENTS = {
    "TransactionCreated": "collection.transaction-created.v1",
    "SupplierIdentified": "collection.supplier-identified.v1",
    "MilkReceived": "collection.milk-received.v1",
    "WeightCaptured": "collection.weight-captured.v1",
    "QualityCaptured": "collection.quality-captured.v1",
    "PricingRequested": "collection.pricing-requested.v1",
    "PricingCompleted": "collection.pricing-completed.v1",
    "PricingUnavailable": "collection.pricing-unavailable.v1",
    "TransactionAccepted": "collection.transaction-accepted.v1",
    "TransactionRejected": "collection.transaction-rejected.v1",
    "TransactionCompleted": "collection.transaction-completed.v1",
    "TransactionCancelled": "collection.transaction-cancelled.v1",
}

# MVP-001: milk is priced on FAT until the multi-dimension combination policy
# lands (a future pricing increment); product codes derive from the milk type.
PRICING_DIMENSION = "FAT"


def product_code_for(milk_type: str | None) -> str | None:
    if not milk_type or milk_type == "custom":
        return None
    return f"RAW-{milk_type.upper()}-MILK"


# --- DTOs ------------------------------------------------------------------


class SessionView(BaseModel):
    id: uuid.UUID
    center_id: uuid.UUID
    status: str
    label: str
    opened_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class IdentifySupplierCommand(BaseModel):
    method: str  # qr | code | phone | manual
    value: str | None = None  # qr payload / code / phone
    supplier_id: uuid.UUID | None = None  # manual


class MilkInfoCommand(BaseModel):
    milk_type: str
    milk_type_custom: str | None = Field(default=None, max_length=60)
    container_type: str = Field(min_length=1, max_length=40)
    container_identifier: str = Field(min_length=1, max_length=80)
    temperature_c: float | None = Field(default=None, ge=0, le=50)
    arrived_at: datetime | None = None


class WeightCommand(BaseModel):
    source: str = "manual"  # manual | mock_scale
    unit: str = "kg"
    gross: float | None = None
    tare: float | None = None


class QualityCommand(BaseModel):
    source: str = "manual"  # manual | mock_analyzer
    fat: float | None = None
    snf: float | None = None
    clr: float | None = None
    density: float | None = None
    temperature_c: float | None = None
    remarks: str = Field(default="", max_length=300)


class RejectCommand(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class TransactionView(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    center_id: uuid.UUID
    supplier_id: uuid.UUID | None
    operator_id: uuid.UUID
    state: str
    milk_type: str | None
    container_type: str | None
    container_identifier: str | None
    weight_unit: str | None
    gross_weight: float | None
    tare_weight: float | None
    net_weight: float | None
    fat: float | None
    snf: float | None
    clr: float | None
    density: float | None
    pricing_status: str | None
    unit_price: Decimal | None
    gross_amount: Decimal | None
    currency: str | None
    calculation_id: uuid.UUID | None
    pricing_detail: str | None
    rejected_reason: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class TransactionPage(BaseModel):
    items: list[TransactionView]
    total: int
    limit: int
    offset: int


class TransactionEventView(BaseModel):
    sequence: int
    event_type: str
    data: dict[str, Any]
    actor_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MilkCollectionService:
    def __init__(
        self,
        session: AsyncSession,
        bus: EventBus,
        audit: AuditService,
        readiness: OperationalReadinessService,
        pricing_resolution: "PricingResolutionService",
        pricing_calculator: "PricingCalculationService",
    ):
        self._session = session
        self._bus = bus
        self._audit = audit
        self._readiness = readiness
        self._pricing_resolution = pricing_resolution
        self._pricing_calculator = pricing_calculator

    # --- collection sessions ----------------------------------------------

    async def open_session(
        self, center_id: uuid.UUID, label: str, *, actor_id: uuid.UUID
    ) -> CollectionSession:
        tenant_id = require_current_tenant()
        center = await self._session.get(CollectionCenter, center_id)
        if center is None or center.tenant_id != tenant_id:
            raise NotFoundError("collection center not found")
        if center.status != "active":
            raise ConflictError("collection center is not active")
        existing = await self._session.scalar(
            select(CollectionSession).where(
                CollectionSession.center_id == center_id,
                CollectionSession.status == "open",
            )
        )
        if existing is not None:
            raise ConflictError("center already has an open session")
        readiness = await self._readiness.evaluate_readiness(center_id)
        if readiness.status == "NOT_READY":
            failed = [c.rule for c in readiness.checks if not c.passed]
            raise ConflictError(f"center is NOT_READY ({', '.join(failed)})")
        session = CollectionSession(
            tenant_id=tenant_id, center_id=center_id, label=label, opened_by=actor_id
        )
        self._session.add(session)
        await self._session.flush()
        await self._audit.record(
            action="collection.session.opened",
            resource_type="collection_session",
            resource_id=session.id,
            actor_id=actor_id,
            detail={"center_id": str(center_id), "readiness": readiness.status},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "collection.session-opened.v1",
                {"session_id": str(session.id), "center_id": str(center_id)},
                actor_id=actor_id,
            )
        )
        return session

    async def close_session(
        self, session_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> CollectionSession:
        session = await self._get_session(session_id)
        if session.status == "closed":
            raise ConflictError("session already closed")
        in_flight = await self._session.scalar(
            select(func.count())
            .select_from(MilkCollectionTransaction)
            .where(
                MilkCollectionTransaction.session_id == session.id,
                MilkCollectionTransaction.state.notin_(TERMINAL_STATES),
            )
        )
        if in_flight:
            raise ConflictError(f"{in_flight} transaction(s) still in flight")
        session.status = "closed"
        session.closed_by = actor_id
        session.closed_at = utcnow()
        await self._audit.record(
            action="collection.session.closed",
            resource_type="collection_session",
            resource_id=session.id,
            actor_id=actor_id,
        )
        await self._bus.publish(
            EventEnvelope.new(
                "collection.session-closed.v1",
                {"session_id": str(session.id)},
                actor_id=actor_id,
            )
        )
        return session

    async def list_sessions(
        self, *, center_id: uuid.UUID | None, status: str | None
    ) -> list[CollectionSession]:
        tenant_id = require_current_tenant()
        stmt = select(CollectionSession).where(CollectionSession.tenant_id == tenant_id)
        if center_id:
            stmt = stmt.where(CollectionSession.center_id == center_id)
        if status:
            stmt = stmt.where(CollectionSession.status == status)
        rows = await self._session.scalars(stmt.order_by(CollectionSession.opened_at.desc()))
        return list(rows.all())

    # --- transaction lifecycle --------------------------------------------

    async def create_transaction(
        self, session_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> MilkCollectionTransaction:
        session = await self._get_session(session_id)
        if session.status != "open":
            raise ConflictError("collection session is not open")
        tx = MilkCollectionTransaction(
            tenant_id=session.tenant_id,
            session_id=session.id,
            center_id=session.center_id,
            operator_id=actor_id,
        )
        self._session.add(tx)
        await self._session.flush()
        await self._record(
            tx,
            "TransactionCreated",
            {"session_id": str(session.id), "center_id": str(session.center_id)},
            actor_id,
        )
        return tx

    async def identify_supplier(
        self, tx_id: uuid.UUID, cmd: IdentifySupplierCommand, *, actor_id: uuid.UUID
    ) -> MilkCollectionTransaction:
        tx = await self._get_mutable(tx_id, expected="NEW")
        supplier = await self._resolve_supplier(cmd)
        if supplier.status != "active":
            raise ConflictError(f"supplier is {supplier.status}, not active")
        assigned = await self._session.scalar(
            select(SupplierCenterAssignment).where(
                SupplierCenterAssignment.supplier_id == supplier.id,
                SupplierCenterAssignment.center_id == tx.center_id,
            )
        )
        if assigned is None:
            raise ConflictError("supplier is not assigned to this collection center")
        tx.supplier_id = supplier.id
        tx.state = "SUPPLIER_IDENTIFIED"
        await self._record(
            tx,
            "SupplierIdentified",
            {"supplier_id": str(supplier.id), "method": cmd.method},
            actor_id,
        )
        return tx

    async def receive_milk(
        self, tx_id: uuid.UUID, cmd: MilkInfoCommand, *, actor_id: uuid.UUID
    ) -> MilkCollectionTransaction:
        tx = await self._get_mutable(tx_id, expected="SUPPLIER_IDENTIFIED")
        if cmd.milk_type not in MILK_TYPES:
            raise ConflictError(f"milk_type must be one of {MILK_TYPES}")
        if cmd.milk_type == "custom" and not cmd.milk_type_custom:
            raise ConflictError("milk_type_custom is required for custom milk type")
        tx.milk_type = cmd.milk_type
        tx.milk_type_custom = cmd.milk_type_custom
        tx.container_type = cmd.container_type
        tx.container_identifier = cmd.container_identifier
        tx.arrival_temperature_c = cmd.temperature_c
        tx.arrived_at = cmd.arrived_at or utcnow()
        tx.state = "MILK_RECEIVED"
        await self._record(
            tx,
            "MilkReceived",
            {
                "milk_type": cmd.milk_type,
                "container": f"{cmd.container_type}:{cmd.container_identifier}",
            },
            actor_id,
        )
        return tx

    async def capture_weight(
        self, tx_id: uuid.UUID, cmd: WeightCommand, *, actor_id: uuid.UUID
    ) -> MilkCollectionTransaction:
        tx = await self._get_mutable(tx_id, expected="MILK_RECEIVED")
        if cmd.unit != "kg":
            raise ConflictError("only kg is supported in this sprint")
        if cmd.source == "mock_scale":
            reading = mock_scale.read(tx.container_identifier or str(tx.id))
            gross, tare = reading.gross_kg, reading.tare_kg
        elif cmd.source == "manual":
            if cmd.gross is None or cmd.tare is None:
                raise ConflictError("manual weight requires gross and tare")
            gross, tare = cmd.gross, cmd.tare
        else:
            raise ConflictError("weight source must be manual or mock_scale")
        if gross <= 0 or tare < 0:
            raise ConflictError("gross must be > 0 and tare >= 0")
        if gross > MAX_GROSS_KG:
            raise ConflictError(f"gross weight exceeds {MAX_GROSS_KG} kg limit")
        if tare >= gross:
            raise ConflictError("tare must be less than gross")
        tx.weight_unit = "kg"
        tx.gross_weight = round(gross, 3)
        tx.tare_weight = round(tare, 3)
        tx.net_weight = round(gross - tare, 3)
        tx.weight_source = cmd.source
        tx.state = "WEIGHT_CAPTURED"
        await self._record(
            tx,
            "WeightCaptured",
            {"gross": tx.gross_weight, "tare": tx.tare_weight, "net": tx.net_weight},
            actor_id,
        )
        tx.state = "QUALITY_PENDING"  # automatic hand-off to the quality step
        return tx

    async def capture_quality(
        self, tx_id: uuid.UUID, cmd: QualityCommand, *, actor_id: uuid.UUID
    ) -> MilkCollectionTransaction:
        tx = await self._get_mutable(tx_id, expected="QUALITY_PENDING")
        if cmd.source == "mock_analyzer":
            r = mock_analyzer.read(tx.container_identifier or str(tx.id))
            values = {
                "fat": r.fat,
                "snf": r.snf,
                "clr": r.clr,
                "density": r.density,
                "temperature_c": r.temperature_c,
            }
        elif cmd.source == "manual":
            if cmd.fat is None or cmd.snf is None or cmd.clr is None:
                raise ConflictError("manual quality requires fat, snf, and clr")
            values = {
                "fat": cmd.fat,
                "snf": cmd.snf,
                "clr": cmd.clr,
                "density": cmd.density,
                "temperature_c": cmd.temperature_c,
            }
        else:
            raise ConflictError("quality source must be manual or mock_analyzer")
        for key, value in values.items():
            if value is None:
                continue
            lo, hi = QUALITY_RANGES[key]
            if not (lo <= value <= hi):
                raise ConflictError(f"{key} out of range [{lo}, {hi}]")
        tx.fat = values["fat"]
        tx.snf = values["snf"]
        tx.clr = values["clr"]
        tx.density = values.get("density")
        tx.quality_temperature_c = values.get("temperature_c")
        tx.quality_remarks = cmd.remarks
        tx.quality_source = cmd.source
        tx.state = "QUALITY_CAPTURED"
        await self._record(
            tx,
            "QualityCaptured",
            {"fat": tx.fat, "snf": tx.snf, "clr": tx.clr},
            actor_id,
        )
        await self._apply_pricing(tx, actor_id)
        return tx

    async def _apply_pricing(self, tx: MilkCollectionTransaction, actor_id: uuid.UUID) -> None:
        """MVP-001 integration: invoke the Pricing Platform (resolution ->
        calculator) at the pricing step. Failure to price NEVER blocks the
        collection flow — milk is perishable; the transaction proceeds with
        pricing_status='pricing_unavailable' and can be settled later once
        pricing data exists."""
        from platform_core.modules.pricing.calculator import (
            CalculationRequest,
            PricingCalculationError,
        )
        from platform_core.modules.pricing.resolution import (
            PricingIntegrityError,
            PricingResolutionError,
            ResolutionQuery,
        )

        tx.state = "PRICING_PENDING"
        await self._record(tx, "PricingRequested", {"dimension": PRICING_DIMENSION}, actor_id)
        product_code = product_code_for(tx.milk_type)
        tx_date = as_utc(tx.created_at).date()
        try:
            if product_code is None:
                raise PricingResolutionError(
                    {"stage": "product", "reason": "no product mapping for this milk type"}
                )
            resolution = await self._pricing_resolution.resolve(
                ResolutionQuery(
                    center_id=tx.center_id,
                    product_code=product_code,
                    transaction_date=tx_date,
                    dimension_code=PRICING_DIMENSION,
                    value=tx.fat,
                )
            )
            calculation = await self._pricing_calculator.calculate(
                CalculationRequest(
                    row_id=resolution.row_id,
                    quantity=tx.net_weight,
                    quantity_unit=tx.weight_unit or "kg",
                    transaction_date=tx_date,
                ),
                actor_id=actor_id,
            )
            tx.pricing_status = "priced"
            tx.unit_price = calculation.unit_price.amount
            tx.gross_amount = calculation.gross_amount.amount
            tx.currency = calculation.currency
            tx.calculation_id = calculation.calculation_id
            tx.pricing_detail = (
                f"{calculation.resolution.rate_card_code} "
                f"v{calculation.resolution.rate_card_version} band "
                f"[{calculation.resolution.range_from}, {calculation.resolution.range_to})"
            )
            await self._record(
                tx,
                "PricingCompleted",
                {
                    "unit_price": str(tx.unit_price),
                    "gross_amount": str(tx.gross_amount),
                    "currency": tx.currency,
                    "calculation_id": str(tx.calculation_id),
                },
                actor_id,
            )
        except (PricingResolutionError, PricingIntegrityError, PricingCalculationError) as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"reason": str(exc.detail)}
            tx.pricing_status = "pricing_unavailable"
            tx.pricing_detail = str(detail.get("reason", ""))[:300]
            await self._record(
                tx,
                "PricingUnavailable",
                {"stage": detail.get("stage"), "reason": tx.pricing_detail},
                actor_id,
            )
        tx.state = "PRICED"

    async def accept(self, tx_id: uuid.UUID, *, actor_id: uuid.UUID) -> MilkCollectionTransaction:
        tx = await self._decide(tx_id, "ACCEPTED", actor_id=actor_id)
        await self._record(tx, "TransactionAccepted", {}, actor_id)
        return tx

    async def reject(
        self, tx_id: uuid.UUID, cmd: RejectCommand, *, actor_id: uuid.UUID
    ) -> MilkCollectionTransaction:
        tx = await self._decide(tx_id, "REJECTED", actor_id=actor_id, reason=cmd.reason)
        await self._record(
            tx,
            "TransactionRejected",
            {
                "reason": cmd.reason,
                # Who to tell (NOT-001) — consumers resolve contact details
                # from their own directory, never from this module.
                "supplier_id": str(tx.supplier_id) if tx.supplier_id else None,
            },
            actor_id,
        )
        return tx

    async def _decide(
        self,
        tx_id: uuid.UUID,
        decision: str,
        *,
        actor_id: uuid.UUID,
        reason: str | None = None,
    ) -> MilkCollectionTransaction:
        """The decision is the concurrency-critical transition: applied as an
        atomic compare-and-swap (UPDATE … WHERE state='PRICED'), so two
        concurrent deciders cannot both win — the loser gets 409."""
        from sqlalchemy import update

        tx = await self._get_tx(tx_id)
        result = await self._session.execute(
            update(MilkCollectionTransaction)
            .where(
                MilkCollectionTransaction.id == tx.id,
                MilkCollectionTransaction.state == "PRICED",
            )
            .values(
                state=decision,
                decided_by=actor_id,
                decided_at=utcnow(),
                rejected_reason=reason,
            )
        )
        if result.rowcount != 1:
            await self._session.refresh(tx)
            raise ConflictError(f"expected state PRICED, transaction is {tx.state}")
        await self._session.refresh(tx)
        return tx

    async def complete(self, tx_id: uuid.UUID, *, actor_id: uuid.UUID) -> MilkCollectionTransaction:
        tx = await self._get_tx(tx_id)
        if tx.state not in ("ACCEPTED", "REJECTED"):
            raise ConflictError(f"cannot complete a transaction in state {tx.state}")
        decision = tx.state
        tx.completed_at = utcnow()
        tx.state = "COMPLETED"
        snapshot = TransactionSnapshot(
            tenant_id=tx.tenant_id, transaction_id=tx.id, data=self._freeze(tx, decision)
        )
        self._session.add(snapshot)
        from platform_core.core.db import as_utc

        duration = (as_utc(tx.completed_at) - as_utc(tx.created_at)).total_seconds()
        self._session.add(
            TransactionMetrics(
                tenant_id=tx.tenant_id,
                transaction_id=tx.id,
                session_id=tx.session_id,
                center_id=tx.center_id,
                supplier_id=tx.supplier_id,
                operator_id=tx.operator_id,
                started_at=tx.created_at,
                completed_at=tx.completed_at,
                duration_seconds=round(duration, 3),
                final_state=decision,
            )
        )
        await self._record(
            tx,
            "TransactionCompleted",
            {
                # Enriched for downstream consumers (SPRINT-008B): projections
                # and notifications read the FACT from the event, never tables.
                "decision": decision,
                "duration_s": duration,
                "center_id": str(tx.center_id),
                "supplier_id": str(tx.supplier_id) if tx.supplier_id else None,
                "net_weight": tx.net_weight,
                "gross_amount": str(tx.gross_amount) if tx.gross_amount is not None else None,
                "currency": tx.currency,
                "rejected": tx.rejected_reason is not None,
            },
            actor_id,
        )
        return tx

    async def cancel(
        self, tx_id: uuid.UUID, reason: str, *, actor_id: uuid.UUID
    ) -> MilkCollectionTransaction:
        tx = await self._get_tx(tx_id)
        if tx.state in ("ACCEPTED", "REJECTED", *TERMINAL_STATES):
            raise ConflictError(f"cannot cancel a transaction in state {tx.state}")
        tx.state = "CANCELLED"
        tx.cancelled_reason = reason[:300]
        tx.completed_at = utcnow()
        await self._record(tx, "TransactionCancelled", {"reason": reason[:300]}, actor_id)
        return tx

    # --- queries -----------------------------------------------------------

    async def get_tx_view(self, tx_id: uuid.UUID) -> MilkCollectionTransaction:
        return await self._get_tx(tx_id)

    async def list_transactions(
        self,
        *,
        session_id: uuid.UUID | None = None,
        center_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
        state: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> TransactionPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        stmt = select(MilkCollectionTransaction).where(
            MilkCollectionTransaction.tenant_id == tenant_id
        )
        if session_id:
            stmt = stmt.where(MilkCollectionTransaction.session_id == session_id)
        if center_id:
            stmt = stmt.where(MilkCollectionTransaction.center_id == center_id)
        if supplier_id:
            stmt = stmt.where(MilkCollectionTransaction.supplier_id == supplier_id)
        if state:
            stmt = stmt.where(MilkCollectionTransaction.state == state)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.scalars(
            stmt.order_by(MilkCollectionTransaction.created_at.desc()).limit(limit).offset(offset)
        )
        return TransactionPage(
            items=[TransactionView.model_validate(t) for t in rows.all()],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    async def list_events(self, tx_id: uuid.UUID) -> list[TransactionEvent]:
        tx = await self._get_tx(tx_id)
        rows = await self._session.scalars(
            select(TransactionEvent)
            .where(TransactionEvent.transaction_id == tx.id)
            .order_by(TransactionEvent.sequence)
        )
        return list(rows.all())

    # --- internals ----------------------------------------------------------

    async def _resolve_supplier(self, cmd: IdentifySupplierCommand) -> Supplier:
        tenant_id = require_current_tenant()
        if cmd.method == "manual":
            if cmd.supplier_id is None:
                raise ConflictError("manual identification requires supplier_id")
            supplier = await self._session.get(Supplier, cmd.supplier_id)
        elif cmd.method == "qr":
            if not cmd.value:
                raise ConflictError("qr identification requires value")
            supplier = await self._session.get(Supplier, parse_qr_payload(cmd.value))
        elif cmd.method == "code":
            if not cmd.value:
                raise ConflictError("code identification requires value")
            supplier = await self._session.scalar(
                select(Supplier).where(
                    Supplier.tenant_id == tenant_id, Supplier.code == cmd.value.strip()
                )
            )
        elif cmd.method == "phone":
            if not cmd.value:
                raise ConflictError("phone identification requires value")
            supplier = await self._session.scalar(
                select(Supplier)
                .join(SupplierProfile, SupplierProfile.supplier_id == Supplier.id)
                .where(
                    Supplier.tenant_id == tenant_id,
                    SupplierProfile.phone == cmd.value.strip(),
                )
            )
        else:
            raise ConflictError("method must be qr, code, phone, or manual")
        if supplier is None or supplier.tenant_id != tenant_id:
            raise NotFoundError("supplier not found")
        return supplier

    async def _record(
        self,
        tx: MilkCollectionTransaction,
        event_type: str,
        data: dict[str, Any],
        actor_id: uuid.UUID | None,
    ) -> None:
        sequence = (
            await self._session.scalar(
                select(func.count())
                .select_from(TransactionEvent)
                .where(TransactionEvent.transaction_id == tx.id)
            )
            or 0
        ) + 1
        self._session.add(
            TransactionEvent(
                tenant_id=tx.tenant_id,
                transaction_id=tx.id,
                sequence=sequence,
                event_type=event_type,
                data={**data, "state": tx.state},
                actor_id=actor_id,
            )
        )
        await self._audit.record(
            action=f"collection.transaction.{event_type}",
            resource_type="milk_collection_transaction",
            resource_id=tx.id,
            actor_id=actor_id,
            detail={**data, "state": tx.state},
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS[event_type],
                {"transaction_id": str(tx.id), **data},
                actor_id=actor_id,
                aggregate_type="milk_collection_transaction",
                aggregate_id=tx.id,
            )
        )

    def _freeze(self, tx: MilkCollectionTransaction, decision: str) -> dict[str, Any]:
        return {
            "transaction_id": str(tx.id),
            "session_id": str(tx.session_id),
            "center_id": str(tx.center_id),
            "supplier_id": str(tx.supplier_id) if tx.supplier_id else None,
            "operator_id": str(tx.operator_id),
            "decision": decision,
            "milk": {
                "type": tx.milk_type,
                "type_custom": tx.milk_type_custom,
                "container_type": tx.container_type,
                "container_identifier": tx.container_identifier,
                "arrival_temperature_c": tx.arrival_temperature_c,
                "arrived_at": tx.arrived_at.isoformat() if tx.arrived_at else None,
            },
            "weight": {
                "unit": tx.weight_unit,
                "gross": tx.gross_weight,
                "tare": tx.tare_weight,
                "net": tx.net_weight,
                "source": tx.weight_source,
            },
            "quality": {
                "fat": tx.fat,
                "snf": tx.snf,
                "clr": tx.clr,
                "density": tx.density,
                "temperature_c": tx.quality_temperature_c,
                "remarks": tx.quality_remarks,
                "source": tx.quality_source,
            },
            "pricing": {
                "status": tx.pricing_status,
                "unit_price": str(tx.unit_price) if tx.unit_price is not None else None,
                "gross_amount": str(tx.gross_amount) if tx.gross_amount is not None else None,
                "currency": tx.currency,
                "calculation_id": str(tx.calculation_id) if tx.calculation_id else None,
                "detail": tx.pricing_detail,
            },
            "rejected_reason": tx.rejected_reason,
            "created_at": tx.created_at.isoformat(),
            "completed_at": tx.completed_at.isoformat() if tx.completed_at else None,
        }

    async def _get_tx(self, tx_id: uuid.UUID) -> MilkCollectionTransaction:
        tenant_id = require_current_tenant()
        tx = await self._session.get(MilkCollectionTransaction, tx_id)
        if tx is None or tx.tenant_id != tenant_id:
            raise NotFoundError("transaction not found")
        return tx

    async def _get_mutable(self, tx_id: uuid.UUID, *, expected: str) -> MilkCollectionTransaction:
        tx = await self._get_tx(tx_id)
        if tx.state in TERMINAL_STATES:
            raise ConflictError(f"transaction is {tx.state} and immutable")
        if tx.state != expected:
            raise ConflictError(f"expected state {expected}, transaction is {tx.state}")
        return tx

    async def _get_session(self, session_id: uuid.UUID) -> CollectionSession:
        tenant_id = require_current_tenant()
        session = await self._session.get(CollectionSession, session_id)
        if session is None or session.tenant_id != tenant_id:
            raise NotFoundError("collection session not found")
        return session
