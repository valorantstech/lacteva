"""Milk Collection module — sessions and the transaction engine.

State machine (spec-mandated):
NEW -> SUPPLIER_IDENTIFIED -> MILK_RECEIVED -> WEIGHT_CAPTURED ->
QUALITY_PENDING -> QUALITY_CAPTURED -> PRICING_PENDING -> PRICED ->
ACCEPTED | REJECTED -> COMPLETED.  CANCELLED only before a decision.

Every step: state-guarded (optimistic — a stale caller gets 409), appended
to the ordered transaction event log, audited, and published on the bus.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import fmean, pstdev
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.business_time import business_date_of, format_in_zone
from platform_core.core.db import as_utc, utcnow
from platform_core.core.document_numbers import next_document_number
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.org_context import tenant_locale, tenant_timezone
from platform_core.core.tenancy import require_current_tenant
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.infrastructure.hardware import (
    MockHardwareRefused,
    mock_analyzer,
    mock_hardware_allowed,
    mock_scale,
)
from platform_core.modules.audit.service import AuditService
from platform_core.modules.collection_center.models import CollectionCenter
from platform_core.modules.identity.models import User
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
from platform_core.modules.organization.models import Organization
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


async def _resolve_instrument(readiness, source: str, cmd, *, center_id: uuid.UUID) -> uuid.UUID:
    """The device behind an instrument reading, or a refusal (WO-49).

    Spec §7 makes provenance a SECURITY control — "it is what makes a
    fabricated reading distinguishable after the fact". That only holds if the
    attribution is checked, so every clause below is a way of fabricating one:

    * no `device_id` — a reading that claims an instrument and names none
    * an unregistered id — a device that exists only in the caller's request
    * the wrong category — a printer reporting fat
    * a device that is not `active` — retired kills access (spec §9), and a
      device in maintenance is exactly the one whose numbers to distrust
    * another centre's device — the reading did not happen where it says
    """
    from platform_core.modules.milk_collection.models import INSTRUMENT_SOURCES

    expected_category = INSTRUMENT_SOURCES[source]
    if cmd.device_id is None:
        raise ConflictError(f"source '{source}' requires the device_id that produced the reading")
    device = await readiness.get_device(cmd.device_id)
    if device.category != expected_category:
        raise ConflictError(
            f"device {cmd.device_id} is a {device.category}, which cannot produce a "
            f"'{source}' reading"
        )
    if device.status != "active":
        raise ConflictError(f"device {cmd.device_id} is {device.status}, not active")
    if device.center_id != center_id:
        # Another centre's device is invisible rather than forbidden, the same
        # answer another tenant's resource gets.
        raise ConflictError(f"device {cmd.device_id} is not assigned to this centre")
    return device.id


def _provenance(cmd, source: str, device_id: uuid.UUID | None) -> dict[str, Any]:
    """What the event log records about where a reading came from.

    Spec §14 says no schema change for read-assist, and none is needed: the
    `WeightCaptured`/`QualityCaptured` events already carry the source, and the
    device and frame digest ride with them. The columns, states and downstream
    flow are untouched — pricing and settlement stay byte-for-byte indifferent
    to where a number came from, which is the whole point of the seam.
    """
    provenance: dict[str, Any] = {"source": source}
    if device_id is not None:
        provenance["device_id"] = str(device_id)
    if cmd.frame_hash:
        provenance["frame_hash"] = cmd.frame_hash
    return provenance


def _refuse_mock_source(source: str) -> None:
    """SEC-003 / F-01: refuse a fabricated measurement where it is not allowed.

    The adapter refuses too, and deliberately so — but refusing HERE means the
    caller gets the same answer whether it arrived over HTTP or through the
    offline sync replay, and gets it before any state is touched. Both paths
    reach this method, so this is the one place that covers both.
    """
    if not mock_hardware_allowed():
        raise MockHardwareRefused(
            f"{source} is not permitted in this environment — capture a real reading"
        )


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
    "QualityDeviationFlagged": "collection.quality-deviation-flagged.v1",
    "PricingRequested": "collection.pricing-requested.v1",
    "PricingCompleted": "collection.pricing-completed.v1",
    "PricingUnavailable": "collection.pricing-unavailable.v1",
    "TransactionAccepted": "collection.transaction-accepted.v1",
    "TransactionRejected": "collection.transaction-rejected.v1",
    "TransactionCompleted": "collection.transaction-completed.v1",
    # BR-0029. A rate a person changed is a fact other modules may need to
    # know about, so it goes on the bus like every other decision.
    "RateOverridden": "collection.rate-overridden.v1",
    "TransactionCancelled": "collection.transaction-cancelled.v1",
    # LACTEVA-BACKEND-001. A rate-pending collection priced after the fact,
    # once the rate card that was missing exists. Named for what happened,
    # like every other wire name here.
    "Repriced": "collection.transaction-repriced.v1",
}

# MVP-001: milk is priced on FAT until the multi-dimension combination policy
# lands (a future pricing increment); product codes derive from the milk type.
PRICING_DIMENSION = "FAT"


def product_code_for(milk_type: str | None) -> str | None:
    if not milk_type or milk_type == "custom":
        return None
    return f"RAW-{milk_type.upper()}-MILK"


# P0-PILOT-003 (the one AI MVP): a reading far from THIS supplier's own
# recent baseline gets a non-blocking flag. Statistics, not ML, and honest
# about it: nothing is refused, nothing is scored by a vendor — an event is
# appended for the operator and the report to see. Same-milk-type history
# only (a buffalo baseline says nothing about cow milk); a minimum history
# so a new farmer is never flagged for lacking a past; and an absolute floor
# so a supplier with an unnaturally tight baseline is not flagged for noise.
DEVIATION_MIN_HISTORY = 5
DEVIATION_WINDOW = 20
DEVIATION_SIGMA = 3.0
DEVIATION_FLOOR = 0.5

# P0-BIZ-003: the collection slip (parchi) — the eighth document series on the
# shared per-tenant-year counter, beside STL-/INV-/RCP- and their kin.
SLIP_DOC_TYPE = "collection_slip"
SLIP_PREFIX = "SLP"

#: Hindi names for the fixed milk vocabulary, used on the shareable text when
#: the organization's default language is Hindi. `custom` renders its own
#: free-text name and needs no entry.
_SLIP_MILK_HI = {"cow": "गाय", "buffalo": "भैंस", "goat": "बकरी", "mixed": "मिश्रित"}


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


class RateOverrideCommand(BaseModel):
    """An authorized departure from the resolved rate (BR-0029)."""

    unit_price: Decimal = Field(gt=0)
    #: Mandatory, and not merely non-empty: an override with no reason is an
    #: unexplained payment difference, which is what an auditor asks about.
    reason: str = Field(min_length=3, max_length=300)


class InstrumentProvenance(BaseModel):
    """Which registered device produced a reading, and what it actually said.

    WO-49. `device_id` is not decoration: an instrument source with no device
    behind it is an unattributed claim wearing a device's name, so the capture
    refuses it. `frame_hash` is a digest of the raw bytes the instrument sent,
    kept so a disputed reading can be tied back to the frame the operator's
    handset parsed — the platform never stores the frame itself, which may
    carry a serial or a calibration record it has no business holding.
    """

    device_id: uuid.UUID | None = None
    frame_hash: str | None = Field(default=None, max_length=128)


class WeightCommand(InstrumentProvenance):
    source: str = "manual"  # manual | scale | mock_scale
    unit: str = "kg"
    gross: float | None = None
    tare: float | None = None


class QualityCommand(InstrumentProvenance):
    source: str = "manual"  # manual | analyzer | mock_analyzer
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
    milk_type_custom: str | None
    container_type: str | None
    container_identifier: str | None
    arrival_temperature_c: float | None
    arrived_at: datetime | None
    weight_unit: str | None
    gross_weight: float | None
    tare_weight: float | None
    net_weight: float | None
    # DEMO-007: the capture SOURCE was stored from the first day of MVP-001 and
    # never surfaced. It is the difference between "10 kg" and "10 kg, entered
    # by hand" — the one fact that stops a reading being mistaken for a
    # certified instrument's. Withholding it made the API less honest than the
    # database underneath it.
    weight_source: str | None
    fat: float | None
    snf: float | None
    clr: float | None
    density: float | None
    quality_temperature_c: float | None
    quality_remarks: str | None
    quality_source: str | None
    pricing_status: str | None
    unit_price: Decimal | None
    gross_amount: Decimal | None
    # BR-0029. Null unless a rate was overridden — so a client can show BOTH
    # numbers, which is what "never silent" means at the point of reading.
    base_unit_price: Decimal | None = None
    override_reason: str | None = None
    overridden_by: uuid.UUID | None = None
    overridden_at: datetime | None = None
    currency: str | None
    calculation_id: uuid.UUID | None
    pricing_detail: str | None
    rejected_reason: str | None
    # Who decided, and when. The event log has always carried it; a client
    # that only reads the transaction could not see it.
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    cancelled_reason: str | None
    created_at: datetime
    completed_at: datetime | None
    # P0-BIZ-003: the parchi's number. NULL until completion, and NULL on
    # history that completed before slips existed (minted lazily on slip read).
    slip_number: str | None

    model_config = {"from_attributes": True}


class SessionPage(BaseModel):
    """API-001: sessions grow with time, so they page like every other
    unbounded list on the platform."""

    items: list["SessionView"]
    total: int
    limit: int
    offset: int


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


class SlipView(BaseModel):
    """The collection slip (parchi) — every field a farmer sees on a real
    Indian dairy receipt, composed server-side so a print, a WhatsApp text and
    the API all show the same document.

    The money fields are the transaction's OWN Decimal columns, passed through
    unmodified — the slip renders the books, it never recomputes them.
    """

    slip_number: str
    transaction_id: uuid.UUID
    organization_name: str
    center_name: str
    session_label: str
    business_date: date
    collected_at: datetime
    completed_at: datetime
    milk_type: str | None
    milk_type_custom: str | None
    quantity: float | None
    weight_unit: str | None
    gross_weight: float | None
    tare_weight: float | None
    fat: float | None
    snf: float | None
    clr: float | None
    supplier_code: str | None
    supplier_name: str | None
    operator_name: str
    decision: str  # ACCEPTED | REJECTED
    rejected_reason: str | None
    pricing_status: str | None
    unit_price: Decimal | None
    gross_amount: Decimal | None
    currency: str | None
    # BR-0029. The farmer sees BOTH numbers and why, or the override is
    # silent to the one person it costs money.
    base_unit_price: Decimal | None = None
    override_reason: str | None = None
    #: The shareable plain-text parchi — WhatsApp-pasteable, printer-plain.
    text: str


def render_slip_text(slip: SlipView, *, language: str, timezone_name: str | None) -> str:
    """The farmer's copy, as plain text: short lines, no markup, nothing to
    install. Labels are bilingual (English + Hindi) when the organization's
    default language is Hindi; amounts are the stored strings, verbatim.
    """
    hindi = (language or "").lower().startswith("hi")

    def label(en: str, hi: str) -> str:
        return f"{en} / {hi}" if hindi else en

    milk = slip.milk_type_custom or slip.milk_type or "—"
    if hindi and slip.milk_type in _SLIP_MILK_HI:
        milk = f"{slip.milk_type} / {_SLIP_MILK_HI[slip.milk_type]}"

    farmer = " · ".join(x for x in (slip.supplier_code, slip.supplier_name) if x) or "—"
    lines = [
        slip.organization_name,
        f"{slip.center_name} · {label('Shift', 'पाली')}: {slip.session_label or '—'}",
        f"{label('Slip', 'पर्ची')}: {slip.slip_number}",
        f"{label('Date', 'दिनांक')}: {format_in_zone(slip.collected_at, timezone_name)}",
        f"{label('Farmer', 'किसान')}: {farmer}",
        f"{label('Milk', 'दूध')}: {milk}",
    ]
    if slip.quantity is not None:
        lines.append(f"{label('Qty', 'मात्रा')}: {slip.quantity:g} {slip.weight_unit or 'kg'}")
    quality = "  ".join(
        f"{name} {value:g}"
        for name, value in (("FAT", slip.fat), ("SNF", slip.snf), ("CLR", slip.clr))
        if value is not None
    )
    if quality:
        lines.append(quality)
    if slip.decision == "REJECTED":
        refused = f"{label('REJECTED', 'अस्वीकृत')}"
        lines.append(f"{refused}: {slip.rejected_reason}" if slip.rejected_reason else refused)
    elif slip.unit_price is not None and slip.gross_amount is not None:
        per = f"/{slip.weight_unit}" if slip.weight_unit else ""
        lines.append(f"{label('Rate', 'दर')}: {slip.unit_price}{per}")
        # BR-0029 / D-3: an override the farmer cannot see on their own copy
        # is a silent one. Both numbers, and the reason, on the parchi.
        if slip.base_unit_price is not None:
            lines.append(f"{label('Card rate', 'कार्ड दर')}: {slip.base_unit_price}{per}")
            if slip.override_reason:
                lines.append(f"{label('Rate changed', 'दर बदली')}: {slip.override_reason}")
        amount = f"{slip.currency or ''} {slip.gross_amount}".strip()
        lines.append(f"{label('Amount', 'राशि')}: {amount}")
    else:
        # Accepted but unpriced (no published rate card covered it) — say so
        # rather than print a blank that looks like zero.
        lines.append(label("Rate pending", "दर बाद में"))
    lines.append(f"{label('Operator', 'ऑपरेटर')}: {slip.operator_name}")
    return "\n".join(lines)


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
        self,
        *,
        center_id: uuid.UUID | None,
        status: str | None,
        limit: int = 50,
        offset: int = 0,
    ) -> "SessionPage":
        """Sessions, newest first, PAGINATED.

        API-001: this was the one list on the business surface with no bound
        at all. A session is opened roughly twice per center per day and never
        deleted, so a tenant with sixty centers accumulates ~44,000 of them a
        year — and every one was serialised into a single response. The failure
        is gradual, which is why nobody notices until the response is measured
        in megabytes and the mobile app on a village connection times out.
        """
        tenant_id = require_current_tenant()
        stmt = select(CollectionSession).where(CollectionSession.tenant_id == tenant_id)
        if center_id:
            stmt = stmt.where(CollectionSession.center_id == center_id)
        if status:
            stmt = stmt.where(CollectionSession.status == status)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = await self._session.scalars(
            stmt.order_by(CollectionSession.opened_at.desc()).limit(limit).offset(offset)
        )
        return SessionPage(
            items=[SessionView.model_validate(row) for row in rows.all()],
            total=total,
            limit=limit,
            offset=offset,
        )

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
        device_id: uuid.UUID | None = None
        if cmd.unit != "kg":
            raise ConflictError("only kg is supported in this sprint")
        if cmd.source == "mock_scale":
            _refuse_mock_source("mock_scale")
            reading = mock_scale.read(tx.container_identifier or str(tx.id))
            gross, tare = reading.gross_kg, reading.tare_kg
        elif cmd.source in ("manual", "scale"):
            # Read-assist (spec §5): the instrument pre-fills the operator's
            # screen and the operator confirms, so the numbers arrive by the
            # same field, through the same endpoint, with the same validation.
            # Only the attribution differs — which is the entire design.
            if cmd.gross is None or cmd.tare is None:
                raise ConflictError(f"{cmd.source} weight requires gross and tare")
            gross, tare = cmd.gross, cmd.tare
            if cmd.source == "scale":
                device_id = await _resolve_instrument(
                    self._readiness, "scale", cmd, center_id=tx.center_id
                )
        else:
            raise ConflictError("weight source must be manual, scale or mock_scale")
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
            {
                "gross": tx.gross_weight,
                "tare": tx.tare_weight,
                "net": tx.net_weight,
                **_provenance(cmd, cmd.source, device_id),
            },
            actor_id,
        )
        tx.state = "QUALITY_PENDING"  # automatic hand-off to the quality step
        return tx

    async def capture_quality(
        self, tx_id: uuid.UUID, cmd: QualityCommand, *, actor_id: uuid.UUID
    ) -> MilkCollectionTransaction:
        tx = await self._get_mutable(tx_id, expected="QUALITY_PENDING")
        device_id: uuid.UUID | None = None
        if cmd.source == "mock_analyzer":
            _refuse_mock_source("mock_analyzer")
            r = mock_analyzer.read(tx.container_identifier or str(tx.id))
            values = {
                "fat": r.fat,
                "snf": r.snf,
                "clr": r.clr,
                "density": r.density,
                "temperature_c": r.temperature_c,
            }
        elif cmd.source in ("manual", "analyzer"):
            # Read-assist again: the analyzer fills the operator's fields and
            # the operator confirms. Identical validation, identical bounds —
            # an instrument is not trusted more than a person, it is simply
            # attributed differently.
            if cmd.fat is None or cmd.snf is None or cmd.clr is None:
                raise ConflictError(f"{cmd.source} quality requires fat, snf, and clr")
            values = {
                "fat": cmd.fat,
                "snf": cmd.snf,
                "clr": cmd.clr,
                "density": cmd.density,
                "temperature_c": cmd.temperature_c,
            }
            if cmd.source == "analyzer":
                device_id = await _resolve_instrument(
                    self._readiness, "analyzer", cmd, center_id=tx.center_id
                )
        else:
            raise ConflictError("quality source must be manual, analyzer or mock_analyzer")
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
            {
                "fat": tx.fat,
                "snf": tx.snf,
                "clr": tx.clr,
                **_provenance(cmd, cmd.source, device_id),
            },
            actor_id,
        )
        deviation = await self._quality_deviation(tx)
        if deviation:
            await self._record(
                tx,
                "QualityDeviationFlagged",
                {"supplier_id": str(tx.supplier_id), "metrics": deviation},
                actor_id,
            )
        await self._apply_pricing(tx, actor_id)
        return tx

    async def _quality_deviation(self, tx: MilkCollectionTransaction) -> dict[str, Any] | None:
        """Is this FAT/SNF far from this supplier's own recent readings?

        Baseline: the supplier's last DEVIATION_WINDOW decided (ACCEPTED or
        COMPLETED) collections of the SAME milk type, this tenant. A metric
        flags when it sits at least DEVIATION_SIGMA standard deviations AND
        at least DEVIATION_FLOOR absolute units from that baseline's mean.
        Never blocks, never prices, never reaches the parchi — the farmer's
        slip must not accuse; the operator's event trail may inform.
        """
        if tx.supplier_id is None or tx.milk_type is None:
            return None
        rows = (
            await self._session.execute(
                select(MilkCollectionTransaction.fat, MilkCollectionTransaction.snf)
                .where(
                    MilkCollectionTransaction.tenant_id == tx.tenant_id,
                    MilkCollectionTransaction.supplier_id == tx.supplier_id,
                    MilkCollectionTransaction.id != tx.id,
                    MilkCollectionTransaction.milk_type == tx.milk_type,
                    MilkCollectionTransaction.state.in_(("ACCEPTED", "COMPLETED")),
                )
                .order_by(MilkCollectionTransaction.created_at.desc())
                .limit(DEVIATION_WINDOW)
            )
        ).all()

        flags: dict[str, Any] = {}
        for metric, value in (("fat", tx.fat), ("snf", tx.snf)):
            if value is None:
                continue
            series = [getattr(row, metric) for row in rows if getattr(row, metric) is not None]
            if len(series) < DEVIATION_MIN_HISTORY:
                continue
            mean = fmean(series)
            spread = pstdev(series)
            deviation = abs(value - mean)
            if deviation >= max(DEVIATION_SIGMA * spread, DEVIATION_FLOOR):
                flags[metric] = {
                    "value": value,
                    "baseline_mean": round(mean, 2),
                    "baseline_sd": round(spread, 3),
                    "baseline_n": len(series),
                }
        return flags or None

    async def _apply_pricing(self, tx: MilkCollectionTransaction, actor_id: uuid.UUID) -> None:
        """MVP-001 integration: invoke the Pricing Platform (resolution ->
        calculator) at the pricing step. Failure to price NEVER blocks the
        collection flow — milk is perishable; the transaction proceeds with
        pricing_status='pricing_unavailable' and can be settled later once
        pricing data exists."""
        tx.state = "PRICING_PENDING"
        await self._record(tx, "PricingRequested", {"dimension": PRICING_DIMENSION}, actor_id)
        failure = await self._price(tx, actor_id)
        if failure is None:
            await self._record(tx, "PricingCompleted", self._pricing_facts(tx), actor_id)
        else:
            await self._record(tx, "PricingUnavailable", failure, actor_id)
        tx.state = "PRICED"

    def _pricing_facts(self, tx: MilkCollectionTransaction) -> dict[str, Any]:
        """What a priced transaction now says about itself, for the log."""
        return {
            "unit_price": str(tx.unit_price),
            "gross_amount": str(tx.gross_amount),
            "currency": tx.currency,
            "calculation_id": str(tx.calculation_id),
        }

    async def _price(
        self, tx: MilkCollectionTransaction, actor_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Resolve a rate and calculate, writing the money columns.

        The pricing step itself, with NOTHING around it: no state transition
        and no event. Extracted from `_apply_pricing` so that the reprice path
        (LACTEVA-BACKEND-001) runs the identical arithmetic against the
        identical inputs rather than growing a second implementation that
        would drift — and so that neither caller has to adopt the other's
        state machine. Capture still moves PRICING_PENDING -> PRICED around
        it; reprice must not move a COMPLETED transaction at all.

        Returns `None` when the transaction is priced, or the failure facts
        when the platform has no applicable rate. It never raises for a
        pricing failure: what the caller does about one differs — capture
        carries on because milk is perishable, reprice refuses because
        nothing has changed.
        """
        from platform_core.modules.pricing.calculator import (
            CalculationRequest,
            PricingCalculationError,
        )
        from platform_core.modules.pricing.resolution import (
            PricingIntegrityError,
            PricingResolutionError,
            ResolutionQuery,
        )

        product_code = product_code_for(tx.milk_type)
        # DEMO-013: which DAY this collection happened on decides which rate
        # card prices it, and a day belongs to the dairy's calendar rather
        # than to UTC's. A 05:00 collection in India is 23:30 UTC the day
        # before, so a card that took effect this morning would not have
        # applied to milk poured after it — the farmer paid yesterday's rate,
        # and nothing anywhere would look wrong. Nairobi is UTC+3, which is
        # why the Kenyan demo never showed it.
        tx_date = business_date_of(tx.created_at, await tenant_timezone(self._session))
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
            # BR-0029. A collection whose rate a person overrode is not
            # repriceable by a rate card that showed up afterwards. Silently
            # replacing it would erase a decision somebody signed for, and the
            # farmer was already paid — or told they would be — on that number.
            # Replacing an override takes the same authorized path that made it.
            if tx.base_unit_price is not None:
                return None
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
            return None
        except (PricingResolutionError, PricingIntegrityError, PricingCalculationError) as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"reason": str(exc.detail)}
            tx.pricing_status = "pricing_unavailable"
            tx.pricing_detail = str(detail.get("reason", ""))[:300]
            return {"stage": detail.get("stage"), "reason": tx.pricing_detail}

    async def override_rate(
        self, tx_id: uuid.UUID, cmd: RateOverrideCommand, *, actor_id: uuid.UUID
    ) -> MilkCollectionTransaction:
        """Pay a collection at a rate a person chose (BR-0029; D-15).

        Authorization is the ROUTE's job (`pricing.rate.override`), the way
        every other permission works here. What this owns is everything that
        makes the departure legible afterwards: the resolved rate is preserved
        rather than overwritten, the amount is recomputed from the effective
        rate so the books stay internally consistent, and the who/when/why land
        on the transaction and in its event log.

        Only before the decision. Once a collection is accepted the farmer has
        been told what they are getting, and once it is completed the record is
        immutable — a rate that can change after either is not a rate, it is a
        negotiation the farmer is not present for.
        """
        tx = await self._get_mutable(tx_id, expected="PRICED")
        if tx.unit_price is None or tx.net_weight is None:
            raise ConflictError("nothing to override: this collection has no resolved rate yet")

        # The FIRST override preserves the resolved rate; a second one must not
        # overwrite that with the first override's number, or the base becomes
        # a previous decision rather than what the rate card said.
        if tx.base_unit_price is None:
            tx.base_unit_price = tx.unit_price

        previous = tx.unit_price
        tx.unit_price = cmd.unit_price
        # BR-0005: Decimal end to end, and the amount is recomputed rather than
        # scaled, so no rounding drifts between the rate and the total.
        tx.gross_amount = (cmd.unit_price * Decimal(str(tx.net_weight))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        tx.override_reason = cmd.reason.strip()
        tx.overridden_by = actor_id
        tx.overridden_at = utcnow()

        await self._record(
            tx,
            "RateOverridden",
            {
                "base_unit_price": str(tx.base_unit_price),
                "previous_unit_price": str(previous),
                "unit_price": str(cmd.unit_price),
                "gross_amount": str(tx.gross_amount),
                "reason": tx.override_reason,
            },
            actor_id,
        )
        return tx

    async def reprice(self, tx_id: uuid.UUID, *, actor_id: uuid.UUID) -> MilkCollectionTransaction:
        """Price a collection the platform could not price at the time
        (LACTEVA-BACKEND-001; D-3).

        Capture refuses to invent a price, and settlement refuses a
        transaction with no calculation. Both are right, and together they
        stranded the collection permanently: the milk was taken, the parchi
        said "Rate pending", and no route existed to finish the sentence once
        the missing rate card was published. The first handset run met this on
        day one. A farmer could not be paid for milk the dairy already had.

        What this is NOT is a correction. The rate is resolved for the
        TRANSACTION's own business date and context — the same inputs capture
        used, through the same step — so publishing a card today cannot
        retro-price yesterday's milk at today's rate. And a transaction that
        already carries a price is refused outright: completed pricing is
        corrected by an adjustment, never by quietly recalculating, which is
        the immutability rule this module is built on.

        The eligibility list is deliberate, and reads like
        `settlement._eligible_transaction` because it answers the same kind of
        question: every reason is collected so an operator is told all of them
        at once rather than discovering them one refusal at a time.
        """
        tx = await self._get_tx(tx_id)  # tenant-checked; a foreign id is a 404
        problems = []
        if tx.state != "COMPLETED":
            problems.append(f"transaction is {tx.state}, not COMPLETED")
        if tx.rejected_reason is not None:
            problems.append("rejected milk is not payable")
        if tx.pricing_status != "pricing_unavailable":
            # Covers the already-priced case, and with it the settled one: a
            # settlement line requires a calculation_id, and a transaction
            # without a price has none — so nothing that is settled can reach
            # here. Stated rather than queried, because milk_collection does
            # not read settlement's tables.
            problems.append(
                f"pricing is {tx.pricing_status or 'not recorded'}, not pricing_unavailable"
            )
        if problems:
            raise ConflictError("; ".join(problems))

        failure = await self._price(tx, actor_id)
        if failure is not None:
            # Still nothing to price it with. Refusing leaves the transaction
            # exactly as it was — rate-pending, and honest about it.
            raise ConflictError(str(failure.get("reason")) or "no rate card covers this collection")

        await self._record(tx, "Repriced", self._pricing_facts(tx), actor_id)
        return tx

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
        # P0-BIZ-003: the parchi's number is minted at the moment the
        # transaction becomes immutable — BEFORE the snapshot freezes, so the
        # frozen record carries the number the farmer's slip will show.
        # Rejected completions get one too: proof of rejection is a document
        # the farmer is owed as much as proof of acceptance.
        tx.slip_number = await next_document_number(
            self._session, tenant_id=tx.tenant_id, doc_type=SLIP_DOC_TYPE, prefix=SLIP_PREFIX
        )
        snapshot = TransactionSnapshot(
            tenant_id=tx.tenant_id, transaction_id=tx.id, data=self._freeze(tx, decision)
        )
        self._session.add(snapshot)

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
                "slip_number": tx.slip_number,
                # WO-52. What the farmer's message says. Carried on the EVENT
                # because a consumer reads facts from the log and never from a
                # table (SPRINT-008B) — and because a message about a
                # collection must say what that collection was, not what the
                # row looks like whenever the consumer happens to run.
                "fat": tx.fat,
                "snf": tx.snf,
                "unit_price": str(tx.unit_price) if tx.unit_price is not None else None,
                # BR-0029: whether a person changed the rate. The farmer's copy
                # says so, exactly as the parchi does.
                "base_unit_price": (
                    str(tx.base_unit_price) if tx.base_unit_price is not None else None
                ),
                "quantity_unit": tx.weight_unit,
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
        milk_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        center_scope: set[uuid.UUID] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> TransactionPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        stmt = select(MilkCollectionTransaction).where(
            MilkCollectionTransaction.tenant_id == tenant_id
        )
        # DEMO-008: a centre-scoped principal sees only their own centres'
        # collections. `None` is organization-wide and is what every principal
        # was before centre scope existed, so this narrows nobody who was not
        # deliberately narrowed. Applied in SQL, next to the tenant filter,
        # because a scope enforced anywhere else is a scope that some other
        # caller will forget.
        if center_scope is not None:
            stmt = stmt.where(MilkCollectionTransaction.center_id.in_(center_scope))
        # DEMO-004: a date window, applied in SQL. Without it a portal wanting
        # "last 7 days" has to pull every collection the tenant has ever taken
        # and narrow it in the browser — which is both slow and, once a real
        # dairy has a year of history, wrong at the page boundary.
        # The range is CLOSED [date_from, date_to], expressed as half-open
        # datetimes, matching how the reporting module reads the same column.
        if date_from is not None:
            stmt = stmt.where(
                MilkCollectionTransaction.created_at
                >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            stmt = stmt.where(
                MilkCollectionTransaction.created_at
                < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
            )
        if session_id:
            stmt = stmt.where(MilkCollectionTransaction.session_id == session_id)
        if center_id:
            stmt = stmt.where(MilkCollectionTransaction.center_id == center_id)
        if supplier_id:
            stmt = stmt.where(MilkCollectionTransaction.supplier_id == supplier_id)
        if state:
            stmt = stmt.where(MilkCollectionTransaction.state == state)
        # WO-55. Filtered in SQL beside the rest: a dairy taking two kinds
        # needs to look at one of them, and filtering a fetched page would
        # show "12 results" over a page that holds three.
        if milk_type:
            stmt = stmt.where(MilkCollectionTransaction.milk_type == milk_type)
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

    async def slip(self, tx_id: uuid.UUID) -> SlipView:
        """The parchi for a completed transaction (P0-BIZ-003).

        Read-only over the books: every money figure is the transaction's own
        column, passed through. The single write this method can perform is
        minting a slip number for a transaction that completed before slips
        existed — and that touches `slip_number` alone.
        """
        tx = await self._get_tx(tx_id)
        if tx.state != "COMPLETED":
            raise ConflictError(
                f"a slip exists only for completed transactions; this one is {tx.state}"
            )
        if tx.slip_number is None:
            tx = await self._mint_historical_slip_number(tx)

        # The frozen decision, from the snapshot completion wrote. The
        # fallback covers a snapshot-less row, which should not exist.
        snapshot = await self._session.scalar(
            select(TransactionSnapshot).where(TransactionSnapshot.transaction_id == tx.id)
        )
        decision = (snapshot.data.get("decision") if snapshot else None) or (
            "REJECTED" if tx.rejected_reason else "ACCEPTED"
        )

        center = await self._session.get(CollectionCenter, tx.center_id)
        csession = await self._session.get(CollectionSession, tx.session_id)
        organization = await self._session.get(Organization, tx.tenant_id)
        operator = await self._session.get(User, tx.operator_id)
        supplier = await self._session.get(Supplier, tx.supplier_id) if tx.supplier_id else None
        profile = (
            await self._session.scalar(
                select(SupplierProfile).where(SupplierProfile.supplier_id == tx.supplier_id)
            )
            if tx.supplier_id
            else None
        )
        locale = await tenant_locale(self._session, tx.tenant_id)
        tz = await tenant_timezone(self._session, tx.tenant_id)

        collected_at = as_utc(tx.arrived_at or tx.created_at)
        view = SlipView(
            slip_number=tx.slip_number,
            transaction_id=tx.id,
            organization_name=getattr(organization, "name", "") or "",
            center_name=center.name if center else "",
            session_label=csession.label if csession else "",
            business_date=business_date_of(collected_at, tz),
            collected_at=collected_at,
            completed_at=as_utc(tx.completed_at),
            milk_type=tx.milk_type,
            milk_type_custom=tx.milk_type_custom,
            quantity=tx.net_weight,
            weight_unit=tx.weight_unit,
            gross_weight=tx.gross_weight,
            tare_weight=tx.tare_weight,
            fat=tx.fat,
            snf=tx.snf,
            clr=tx.clr,
            supplier_code=supplier.code if supplier else None,
            supplier_name=profile.full_name if profile else None,
            operator_name=operator.full_name if operator else "",
            decision=decision,
            rejected_reason=tx.rejected_reason,
            pricing_status=tx.pricing_status,
            unit_price=tx.unit_price,
            base_unit_price=tx.base_unit_price,
            override_reason=tx.override_reason,
            gross_amount=tx.gross_amount,
            currency=tx.currency,
            text="",
        )
        return view.model_copy(
            update={
                "text": render_slip_text(view, language=locale.default_language, timezone_name=tz)
            }
        )

    async def _mint_historical_slip_number(
        self, tx: MilkCollectionTransaction
    ) -> MilkCollectionTransaction:
        """First slip read of a pre-slip completed transaction mints its number.

        CAS-guarded — `WHERE slip_number IS NULL` lets exactly one of two
        concurrent readers assign. The loser ROLLS BACK, which undoes its own
        sequence increment (so the series stays gapless), rebinds the
        transaction-scoped RLS setting the rollback discarded, and reads the
        winner's number.
        """
        # Captured BEFORE the possible rollback: the rollback expires `tx`,
        # and touching an expired instance's attributes from asyncio raises
        # MissingGreenlet rather than lazily refreshing.
        tx_id = tx.id
        number = await next_document_number(
            self._session, tenant_id=tx.tenant_id, doc_type=SLIP_DOC_TYPE, prefix=SLIP_PREFIX
        )
        result = await self._session.execute(
            update(MilkCollectionTransaction)
            .where(
                MilkCollectionTransaction.id == tx_id,
                MilkCollectionTransaction.slip_number.is_(None),
            )
            .values(slip_number=number)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            from platform_core.core.rls import rebind_tenant

            await self._session.rollback()
            await rebind_tenant(self._session, require_current_tenant())
            return await self._get_tx(tx_id)
        tx.slip_number = number
        return tx

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
            "slip_number": tx.slip_number,
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
