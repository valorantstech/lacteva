"""Receipt module — application service (RCP-001: Receipt Engine).

Receipts are GENERATED FROM EVENTS, never requested by a business module:
the receipt consumer reads `payment.completed.v1` off the durable log and
calls `generate()`. One completed payment produces exactly one receipt,
enforced by a unique constraint rather than by hope, so consumer replay and
duplicate delivery re-find the existing receipt instead of minting a second
one (BR-0020).

Lifecycle: generated -> delivered -> archived. That is the ONLY thing about
a receipt that can change. There is no update path and no delete path in this
service, and archived receipts stay fully queryable — a receipt is evidence,
and evidence that can be edited or removed is not evidence.

Rendering is a pure derivation of the frozen record (see `rendering.py`), so
no artifact is stored and any format can be re-derived identically forever.
"""

import secrets
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.metrics import RECEIPT_RENDER_SECONDS, RECEIPTS_GENERATED
from platform_core.core.tenancy import require_current_tenant
from platform_core.core.types import Money
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.receipt.models import (
    DEFAULT_RENDER_FORMAT,
    Receipt,
    ReceiptLine,
)
from platform_core.modules.receipt.rendering import (
    RenderedReceipt,
    available_formats,
    get_renderer,
)

BUS_EVENTS = {
    "generated": "receipt.generated.v1",
    "delivered": "receipt.delivered.v1",
    "archived": "receipt.archived.v1",
}


# --- DTOs ------------------------------------------------------------------


class ReceiptLineView(BaseModel):
    id: uuid.UUID
    settlement_id: uuid.UUID
    settlement_number: str
    center_id: uuid.UUID | None
    period_from: date | None
    period_to: date | None
    gross_amount: Decimal
    adjustments_amount: Decimal
    net_amount: Decimal
    amount_paid: Decimal

    model_config = {"from_attributes": True}


class ReceiptReference(BaseModel):
    """Everything this artifact points back to — the audit path from a piece
    of paper to the events that justify it. A value object, per the platform
    convention for validated scalars (see `Money`, `Quantity`)."""

    payment_id: uuid.UUID
    payment_number: str
    payment_reference: str | None
    settlement_ids: list[uuid.UUID]
    settlement_numbers: list[str]
    center_ids: list[uuid.UUID]
    source_event_id: uuid.UUID | None
    correlation_id: uuid.UUID | None


class ReceiptMetadata(BaseModel):
    """The artifact's own bookkeeping, separate from its business content."""

    version: int
    render_format: str
    available_formats: list[str]
    generated_at: datetime
    delivered_at: datetime | None
    archived_at: datetime | None


class ReceiptView(BaseModel):
    id: uuid.UUID
    receipt_number: str
    payment_id: uuid.UUID
    payment_number: str
    payment_reference: str | None
    payment_method: str
    payment_date: datetime | None
    supplier_id: uuid.UUID
    supplier_name: str
    supplier_code: str
    currency: str
    gross_amount: Decimal
    adjustments_amount: Decimal
    net_amount: Decimal
    status: str
    render_format: str
    version: int
    line_count: int
    generated_at: datetime
    delivered_at: datetime | None
    archived_at: datetime | None


class ReceiptDetailView(BaseModel):
    receipt: ReceiptView
    lines: list[ReceiptLineView]
    reference: ReceiptReference
    metadata: ReceiptMetadata


class ReceiptPage(BaseModel):
    items: list[ReceiptView]
    total: int
    limit: int
    offset: int


class RenderedReceiptView(BaseModel):
    receipt_id: uuid.UUID
    receipt_number: str
    format: str
    content_type: str
    filename: str
    body: str
    placeholder: bool


class ReceiptService:
    def __init__(self, session: AsyncSession, bus: EventBus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit

    # --- generation -------------------------------------------------------

    async def generate(
        self,
        *,
        tenant_id: uuid.UUID,
        payment_id: uuid.UUID,
        data: dict,
        source_event_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> Receipt | None:
        """Create the receipt for a completed payment, idempotently.

        Everything shown is COPIED from the event: re-deriving it later could
        show a different world, and a receipt must show the world as it was
        when the money moved.
        """
        existing = await self._session.scalar(
            select(Receipt).where(Receipt.tenant_id == tenant_id, Receipt.payment_id == payment_id)
        )
        if existing is not None:
            return existing  # one payment, one receipt — replay finds this

        currency = data.get("currency") or "XXX"
        lines = data.get("lines") or []
        gross = Money(amount=Decimal("0.00"), currency=currency)
        adjustments = Money(amount=Decimal("0.00"), currency=currency)
        for line in lines:
            gross = gross.plus(
                Money(amount=Decimal(str(line.get("gross_amount", "0"))), currency=currency)
            )
            adjustments = adjustments.plus(
                Money(
                    amount=Decimal(str(line.get("adjustments_amount", "0"))),
                    currency=currency,
                )
            )

        receipt = Receipt(
            tenant_id=tenant_id,
            receipt_number=await self._generate_number(tenant_id),
            payment_id=payment_id,
            supplier_id=uuid.UUID(data["supplier_id"]),
            supplier_name=data.get("supplier_name") or "",
            supplier_code=data.get("supplier_code") or "",
            payment_number=data.get("payment_number") or "",
            payment_reference=data.get("reference") or None,
            payment_method=data.get("method") or "",
            payment_date=_parse_datetime(data.get("paid_at")),
            currency=currency,
            gross_amount=gross.amount,
            adjustments_amount=adjustments.amount,
            # What was ACTUALLY paid — the number this artifact exists to prove.
            net_amount=Decimal(str(data.get("amount", "0"))),
            source_event_id=source_event_id,
            correlation_id=correlation_id,
        )
        self._session.add(receipt)
        await self._session.flush()
        for line in lines:
            self._session.add(
                ReceiptLine(
                    tenant_id=receipt.tenant_id,
                    receipt_id=receipt.id,
                    settlement_id=uuid.UUID(line["settlement_id"]),
                    settlement_number=line.get("settlement_number") or "",
                    center_id=_parse_uuid(line.get("center_id")),
                    period_from=_parse_date(line.get("period_from")),
                    period_to=_parse_date(line.get("period_to")),
                    gross_amount=Decimal(str(line.get("gross_amount", "0"))),
                    adjustments_amount=Decimal(str(line.get("adjustments_amount", "0"))),
                    net_amount=Decimal(str(line.get("net_amount", "0"))),
                    amount_paid=Decimal(str(line.get("amount_paid", "0"))),
                )
            )
        await self._session.flush()
        await self._record(
            receipt,
            "generated",
            {
                "payment_number": receipt.payment_number,
                "supplier_id": str(receipt.supplier_id),
                "supplier_name": receipt.supplier_name,
                "amount": str(receipt.net_amount),
                "currency": receipt.currency,
                "line_count": len(lines),
            },
            actor_id,
        )
        RECEIPTS_GENERATED.inc()
        return receipt

    # --- lifecycle --------------------------------------------------------

    async def deliver(self, receipt_id: uuid.UUID, *, actor_id: uuid.UUID) -> Receipt:
        """generated -> delivered. Records that the artifact reached the payee."""
        receipt = await self.get(receipt_id)
        await self._transition(receipt, expected=("generated",), to="delivered")
        receipt.delivered_at = utcnow()
        await self._record(receipt, "delivered", {}, actor_id)
        return receipt

    async def archive(self, receipt_id: uuid.UUID, *, actor_id: uuid.UUID) -> Receipt:
        """-> archived. Still fully queryable; nothing is deleted, ever."""
        receipt = await self.get(receipt_id)
        await self._transition(receipt, expected=("generated", "delivered"), to="archived")
        receipt.archived_at = utcnow()
        await self._record(receipt, "archived", {}, actor_id)
        return receipt

    # --- queries ----------------------------------------------------------

    async def get(self, receipt_id: uuid.UUID) -> Receipt:
        tenant_id = require_current_tenant()
        receipt = await self._session.get(Receipt, receipt_id)
        if receipt is None or receipt.tenant_id != tenant_id:
            raise NotFoundError("receipt not found")
        return receipt

    async def detail(self, receipt_id: uuid.UUID) -> ReceiptDetailView:
        receipt = await self.get(receipt_id)
        lines = await self._lines(receipt.id)
        return ReceiptDetailView(
            receipt=self._view(receipt, len(lines)),
            lines=[ReceiptLineView.model_validate(line) for line in lines],
            reference=self._reference(receipt, lines),
            metadata=self._metadata(receipt),
        )

    async def search(
        self,
        *,
        q: str | None = None,
        supplier_id: uuid.UUID | None = None,
        payment_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ReceiptPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        stmt = select(Receipt).where(Receipt.tenant_id == tenant_id)
        if q:
            term = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Receipt.receipt_number).like(term),
                    func.lower(Receipt.payment_number).like(term),
                    func.lower(Receipt.supplier_name).like(term),
                    func.lower(func.coalesce(Receipt.payment_reference, "")).like(term),
                )
            )
        if supplier_id:
            stmt = stmt.where(Receipt.supplier_id == supplier_id)
        if payment_id:
            stmt = stmt.where(Receipt.payment_id == payment_id)
        if status:
            stmt = stmt.where(Receipt.status == status)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = list(
            (
                await self._session.scalars(
                    stmt.order_by(Receipt.generated_at.desc()).limit(limit).offset(offset)
                )
            ).all()
        )
        counts = await self._line_counts([r.id for r in rows])
        return ReceiptPage(
            items=[self._view(r, counts.get(r.id, 0)) for r in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    async def render(self, receipt_id: uuid.UUID, fmt: str | None = None) -> RenderedReceiptView:
        """Render through the format's registered renderer. Pure derivation of
        an immutable record, so the same receipt always renders identically."""
        receipt = await self.get(receipt_id)
        lines = await self._lines(receipt.id)
        payload = self._render_payload(receipt, lines)
        chosen = (fmt or receipt.render_format).lower()
        with RECEIPT_RENDER_SECONDS.labels(chosen).time():
            rendered: RenderedReceipt = get_renderer(chosen).render(payload)
        return RenderedReceiptView(
            receipt_id=receipt.id,
            receipt_number=receipt.receipt_number,
            format=rendered.format,
            content_type=rendered.content_type,
            filename=rendered.filename,
            body=rendered.body,
            placeholder=rendered.placeholder,
        )

    # --- helpers ----------------------------------------------------------

    def _render_payload(self, receipt: Receipt, lines: list[ReceiptLine]) -> dict:
        """The plain dict renderers see — no ORM, no transport concerns."""
        return {
            "id": str(receipt.id),
            "receipt_number": receipt.receipt_number,
            "status": receipt.status,
            "version": receipt.version,
            "supplier_name": receipt.supplier_name,
            "supplier_code": receipt.supplier_code,
            "payment_id": str(receipt.payment_id),
            "payment_number": receipt.payment_number,
            "payment_reference": receipt.payment_reference,
            "payment_method": receipt.payment_method,
            "payment_date": receipt.payment_date,
            "currency": receipt.currency,
            "gross_amount": str(receipt.gross_amount),
            "adjustments_amount": str(receipt.adjustments_amount),
            "net_amount": str(receipt.net_amount),
            "generated_at": receipt.generated_at,
            "lines": [
                {
                    "settlement_number": line.settlement_number,
                    "settlement_id": str(line.settlement_id),
                    "center_id": str(line.center_id) if line.center_id else None,
                    "period_from": line.period_from,
                    "period_to": line.period_to,
                    "gross_amount": str(line.gross_amount),
                    "adjustments_amount": str(line.adjustments_amount),
                    "net_amount": str(line.net_amount),
                    "amount_paid": str(line.amount_paid),
                }
                for line in lines
            ],
        }

    def _reference(self, receipt: Receipt, lines: list[ReceiptLine]) -> ReceiptReference:
        return ReceiptReference(
            payment_id=receipt.payment_id,
            payment_number=receipt.payment_number,
            payment_reference=receipt.payment_reference,
            settlement_ids=[line.settlement_id for line in lines],
            settlement_numbers=[line.settlement_number for line in lines],
            center_ids=[line.center_id for line in lines if line.center_id],
            source_event_id=receipt.source_event_id,
            correlation_id=receipt.correlation_id,
        )

    def _metadata(self, receipt: Receipt) -> ReceiptMetadata:
        return ReceiptMetadata(
            version=receipt.version,
            render_format=receipt.render_format,
            available_formats=available_formats(),
            generated_at=receipt.generated_at,
            delivered_at=receipt.delivered_at,
            archived_at=receipt.archived_at,
        )

    async def _transition(self, receipt: Receipt, *, expected: tuple[str, ...], to: str) -> None:
        """CAS lifecycle change. The ONLY mutation a receipt permits."""
        if receipt.status == "archived":
            raise ConflictError("archived receipts are terminal — they remain queryable")
        if receipt.status not in expected:
            raise ConflictError(
                f"a {receipt.status} receipt cannot become {to} — expected {' or '.join(expected)}"
            )
        claim = await self._session.execute(
            update(Receipt)
            .where(Receipt.id == receipt.id, Receipt.status.in_(expected))
            .values(status=to)
        )
        if claim.rowcount != 1:
            raise ConflictError("receipt status changed concurrently — reload and retry")
        await self._session.refresh(receipt)

    async def _lines(self, receipt_id: uuid.UUID) -> list[ReceiptLine]:
        rows = await self._session.scalars(
            select(ReceiptLine)
            .where(ReceiptLine.receipt_id == receipt_id)
            .order_by(ReceiptLine.settlement_number)
        )
        return list(rows.all())

    async def _line_counts(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not ids:
            return {}
        rows = await self._session.execute(
            select(ReceiptLine.receipt_id, func.count())
            .where(ReceiptLine.receipt_id.in_(ids))
            .group_by(ReceiptLine.receipt_id)
        )
        return dict(rows.all())

    def _view(self, receipt: Receipt, line_count: int) -> ReceiptView:
        return ReceiptView(
            id=receipt.id,
            receipt_number=receipt.receipt_number,
            payment_id=receipt.payment_id,
            payment_number=receipt.payment_number,
            payment_reference=receipt.payment_reference,
            payment_method=receipt.payment_method,
            payment_date=receipt.payment_date,
            supplier_id=receipt.supplier_id,
            supplier_name=receipt.supplier_name,
            supplier_code=receipt.supplier_code,
            currency=receipt.currency,
            gross_amount=Decimal(receipt.gross_amount),
            adjustments_amount=Decimal(receipt.adjustments_amount),
            net_amount=Decimal(receipt.net_amount),
            status=receipt.status,
            render_format=receipt.render_format or DEFAULT_RENDER_FORMAT,
            version=receipt.version,
            line_count=line_count,
            generated_at=receipt.generated_at,
            delivered_at=receipt.delivered_at,
            archived_at=receipt.archived_at,
        )

    async def _record(
        self, receipt: Receipt, event: str, data: dict, actor_id: uuid.UUID | None
    ) -> None:
        await self._audit.record(
            action=f"receipt.{event}",
            resource_type="receipt",
            resource_id=receipt.id,
            actor_id=actor_id,
            detail={"number": receipt.receipt_number, **data},
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS[event],
                {
                    "receipt_id": str(receipt.id),
                    "receipt_number": receipt.receipt_number,
                    "payment_id": str(receipt.payment_id),
                    "status": receipt.status,
                    **data,
                },
                actor_id=actor_id,
                aggregate_type="receipt",
                aggregate_id=receipt.id,
            )
        )

    async def _generate_number(self, tenant_id: uuid.UUID) -> str:
        for _ in range(5):
            candidate = "RCP-" + secrets.token_hex(3).upper()
            exists = await self._session.scalar(
                select(Receipt).where(
                    Receipt.tenant_id == tenant_id, Receipt.receipt_number == candidate
                )
            )
            if exists is None:
                return candidate
        raise ConflictError("could not generate a unique receipt number")


def _parse_uuid(value) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


def _parse_date(value) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_datetime(value) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
