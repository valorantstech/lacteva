"""Payment module — application service (PAY-001: Payment Execution Engine).

Lifecycle: draft -> pending -> processing -> completed (immutable), with
failure (retryable, each retry a NEW attempt) and cancellation (terminal)
from the pre-completion states. Every transition is CAS-guarded.

Payments CONSUME settlements. This service reads finalized settlements to
learn what is payable and never writes to them — the settlement module owns
that data and its immutability rule (BR-0010).

Rules (Business Rules Register): BR-0018 payments allocate only against
finalized settlements and never beyond the payable; BR-0019 a completed
payment is immutable and every execution attempt is recorded.

Scope wall (PAY-001): payment methods are metadata. No gateway, no bank
integration, no provider SDK, no credentials.
"""

import secrets
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.metrics import (
    PAYMENTS_CANCELLED,
    PAYMENTS_COMPLETED,
    PAYMENTS_CREATED,
    PAYMENTS_FAILED,
)
from platform_core.core.tenancy import require_current_tenant
from platform_core.core.types import Money
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.payment.models import (
    LIVE_STATUSES,
    PAYMENT_METHODS,
    Payment,
    PaymentAttempt,
    PaymentLine,
)
from platform_core.modules.settlement.models import Settlement
from platform_core.modules.supplier.models import Supplier, SupplierProfile

BUS_EVENTS = {
    "created": "payment.created.v1",
    "processing": "payment.processing.v1",
    "completed": "payment.completed.v1",
    "failed": "payment.failed.v1",
    "cancelled": "payment.cancelled.v1",
    "retry": "payment.retry.v1",
}

# States a payment can still be worked on from.
OPEN_STATUSES = ("draft", "pending", "failed")
CANCELLABLE_STATUSES = ("draft", "pending", "failed")


# --- DTOs ------------------------------------------------------------------


class PaymentAllocationInput(BaseModel):
    """Allocate part (or all) of a finalized settlement's payable."""

    settlement_id: uuid.UUID
    amount: Decimal | None = None  # None = the full outstanding balance


class CreatePaymentCommand(BaseModel):
    supplier_id: uuid.UUID
    currency: str = Field(min_length=3, max_length=3)
    method: str
    allocations: list[PaymentAllocationInput] = Field(min_length=1)
    reference: str | None = None
    method_details: dict = {}
    note: str | None = None
    # Client-supplied replay guard: re-posting the same key returns the
    # existing payment instead of paying twice.
    idempotency_key: str | None = Field(default=None, max_length=80)

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return v.upper()

    @field_validator("method")
    @classmethod
    def _known_method(cls, v: str) -> str:
        method = v.upper()
        if method not in PAYMENT_METHODS:
            raise ValueError(f"method must be one of {', '.join(PAYMENT_METHODS)}")
        return method


class ExecutePaymentCommand(BaseModel):
    """Start (or restart) execution. The provider is a metadata label — this
    platform records money movement, it does not perform it."""

    provider: str | None = None
    reference: str | None = None


class CompletePaymentCommand(BaseModel):
    reference: str | None = None


class FailPaymentCommand(BaseModel):
    reason: str = Field(min_length=1)


class CancelPaymentCommand(BaseModel):
    reason: str = Field(min_length=1)


class PaymentLineView(BaseModel):
    id: uuid.UUID
    settlement_id: uuid.UUID
    settlement_number: str
    amount: Decimal

    model_config = {"from_attributes": True}


class PaymentAttemptView(BaseModel):
    id: uuid.UUID
    attempt_number: int
    provider: str
    reference: str | None
    status: str
    operator_id: uuid.UUID | None
    failure_reason: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class PaymentView(BaseModel):
    id: uuid.UUID
    payment_number: str
    supplier_id: uuid.UUID
    currency: str
    method: str
    amount: Decimal
    reference: str | None
    method_details: dict
    status: str
    attempt_count: int
    failure_reason: str | None
    note: str | None
    line_count: int
    created_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    cancelled_at: datetime | None


class PaymentDetailView(BaseModel):
    payment: PaymentView
    lines: list[PaymentLineView]
    attempts: list[PaymentAttemptView]
    totals_match_lines: bool  # the stored amount still equals its allocations


class PaymentPage(BaseModel):
    items: list[PaymentView]
    total: int
    limit: int
    offset: int


class SettlementBalanceView(BaseModel):
    """What is still owed on a finalized settlement.

    ``allocated`` counts every LIVE payment (draft included — an intent
    reserves the money); ``paid`` counts only completed ones. Outstanding is
    payable minus allocated, so a second payment can never be built on money
    another payment already claims.
    """

    settlement_id: uuid.UUID
    settlement_number: str
    supplier_id: uuid.UUID
    currency: str
    payable: Decimal
    allocated: Decimal
    paid: Decimal
    outstanding: Decimal
    fully_paid: bool


class BalancePage(BaseModel):
    items: list[SettlementBalanceView]
    total: int
    limit: int
    offset: int


class PaymentService:
    def __init__(self, session: AsyncSession, bus: EventBus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit_service = audit

    # --- creation ----------------------------------------------------------

    async def create(self, cmd: CreatePaymentCommand, *, actor_id: uuid.UUID) -> Payment:
        tenant_id = require_current_tenant()
        if cmd.idempotency_key:
            existing = await self._session.scalar(
                select(Payment).where(
                    Payment.tenant_id == tenant_id,
                    Payment.idempotency_key == cmd.idempotency_key,
                )
            )
            if existing is not None:
                return existing  # idempotent execution: no second money movement

        supplier = await self._session.get(Supplier, cmd.supplier_id)
        if supplier is None or supplier.tenant_id != tenant_id:
            raise NotFoundError("supplier not found")

        seen: set[uuid.UUID] = set()
        resolved: list[tuple[Settlement, Decimal]] = []
        total = Money(amount=Decimal("0.00"), currency=cmd.currency)
        for allocation in cmd.allocations:
            if allocation.settlement_id in seen:
                raise ConflictError("the same settlement appears twice in one payment")
            seen.add(allocation.settlement_id)
            settlement = await self._payable_settlement(
                allocation.settlement_id, tenant_id, cmd.supplier_id, cmd.currency
            )
            amount = await self._resolve_allocation(settlement, allocation.amount)
            resolved.append((settlement, amount))
            total = total.plus(Money(amount=amount, currency=cmd.currency))

        if total.amount <= 0:
            raise ConflictError("a payment must move a positive amount")

        payment = Payment(
            tenant_id=tenant_id,
            supplier_id=cmd.supplier_id,
            payment_number=await self._generate_number(tenant_id),
            currency=cmd.currency,
            method=cmd.method,
            amount=total.amount,
            reference=cmd.reference,
            method_details=cmd.method_details,
            note=cmd.note,
            idempotency_key=cmd.idempotency_key,
        )
        self._session.add(payment)
        await self._session.flush()
        for settlement, amount in resolved:
            self._session.add(
                PaymentLine(
                    tenant_id=payment.tenant_id,
                    payment_id=payment.id,
                    settlement_id=settlement.id,
                    settlement_number=settlement.settlement_number,
                    amount=amount,
                )
            )
        await self._session.flush()
        await self._record(
            payment,
            "created",
            {"amount": str(payment.amount), "line_count": len(resolved)},
            actor_id,
        )
        PAYMENTS_CREATED.labels(payment.method).inc()
        return payment

    # --- lifecycle ---------------------------------------------------------

    async def submit(self, payment_id: uuid.UUID, *, actor_id: uuid.UUID) -> Payment:
        """draft -> pending: the payment is approved for execution."""
        payment = await self.get(payment_id)
        await self._transition(payment, expected=("draft",), to="pending")
        # No payment.submitted.v1 exists in the PAY-001 event register, and
        # inventing one would put an unregistered name on the wire: audit only.
        await self._audit(payment, "submitted", {"amount": str(payment.amount)}, actor_id)
        return payment

    async def execute(
        self, payment_id: uuid.UUID, cmd: ExecutePaymentCommand, *, actor_id: uuid.UUID
    ) -> Payment:
        """pending|failed -> processing, opening a new attempt.

        A retry from `failed` is the SAME operation with a new attempt row —
        attempts are never reused (BR-0019)."""
        payment = await self.get(payment_id)
        retry = payment.status == "failed"
        await self._transition(payment, expected=("pending", "failed"), to="processing")
        payment.failure_reason = None
        attempt = await self._open_attempt(payment, cmd, actor_id)
        await self._record(
            payment,
            "processing",
            {"attempt_number": attempt.attempt_number, "provider": attempt.provider},
            actor_id,
        )
        if retry:
            await self._record(
                payment, "retry", {"attempt_number": attempt.attempt_number}, actor_id
            )
        return payment

    async def retry(
        self, payment_id: uuid.UUID, cmd: ExecutePaymentCommand, *, actor_id: uuid.UUID
    ) -> Payment:
        """failed -> processing. A separate entry point because retrying is a
        separate permission (payment.retry) — the execution path is the same."""
        payment = await self.get(payment_id)
        if payment.status != "failed":
            raise ConflictError(
                f"only a failed payment can be retried — this one is {payment.status}"
            )
        return await self.execute(payment_id, cmd, actor_id=actor_id)

    async def complete(
        self, payment_id: uuid.UUID, cmd: CompletePaymentCommand, *, actor_id: uuid.UUID
    ) -> Payment:
        """processing -> completed. Terminal and immutable (BR-0019)."""
        payment = await self.get(payment_id)
        await self._transition(payment, expected=("processing",), to="completed")
        now = utcnow()
        payment.completed_at = now
        if cmd.reference:
            payment.reference = cmd.reference
        await self._close_attempt(payment, "completed", reference=cmd.reference, now=now)
        lines = await self._lines(payment.id)
        await self._record(
            payment,
            "completed",
            {
                "amount": str(payment.amount),
                "currency": payment.currency,
                "reference": payment.reference or "",
                "method": payment.method,
                "paid_at": now.isoformat(),
                # The notification consumer names one settlement; a multi-
                # settlement payment names itself instead (PAY-001 decision).
                "settlement_number": (
                    lines[0].settlement_number if len(lines) == 1 else payment.payment_number
                ),
                "settlement_ids": [str(line.settlement_id) for line in lines],
                # RCP-001: a receipt is built from this event alone, so it
                # carries the payee and the settlement facts it must show.
                # Re-reading finalized settlements here is safe by BR-0010 —
                # they are immutable, so the values cannot have moved since
                # allocation.
                **await self._receipt_facts(payment, lines),
            },
            actor_id,
        )
        PAYMENTS_COMPLETED.labels(payment.method).inc()
        return payment

    async def _receipt_facts(self, payment: Payment, lines: list[PaymentLine]) -> dict:
        """Payee and per-settlement detail for downstream consumers (RCP-001).

        Consumers never call business modules, so everything a receipt needs
        must travel in the event.
        """
        supplier = await self._session.get(Supplier, payment.supplier_id)
        # The payee's display name lives on the profile, not the aggregate root.
        profile = await self._session.scalar(
            select(SupplierProfile).where(SupplierProfile.supplier_id == payment.supplier_id)
        )
        settlements = {}
        if lines:
            rows = await self._session.scalars(
                select(Settlement).where(Settlement.id.in_([line.settlement_id for line in lines]))
            )
            settlements = {s.id: s for s in rows.all()}
        detail = []
        for line in lines:
            settlement = settlements.get(line.settlement_id)
            detail.append(
                {
                    "settlement_id": str(line.settlement_id),
                    "settlement_number": line.settlement_number,
                    "center_id": str(settlement.center_id) if settlement else None,
                    "gross_amount": str(settlement.gross_amount) if settlement else "0.00",
                    "adjustments_amount": (
                        str(settlement.adjustments_amount) if settlement else "0.00"
                    ),
                    "net_amount": str(settlement.net_amount) if settlement else "0.00",
                    "amount_paid": str(line.amount),
                    "period_from": settlement.period_from.isoformat() if settlement else None,
                    "period_to": settlement.period_to.isoformat() if settlement else None,
                }
            )
        return {
            "supplier_name": getattr(profile, "full_name", None) or "",
            "supplier_code": getattr(supplier, "code", None) or "",
            "lines": detail,
        }

    async def fail(
        self, payment_id: uuid.UUID, cmd: FailPaymentCommand, *, actor_id: uuid.UUID
    ) -> Payment:
        """processing -> failed. Retryable; the allocation is released."""
        payment = await self.get(payment_id)
        await self._transition(payment, expected=("processing",), to="failed")
        now = utcnow()
        payment.failed_at = now
        payment.failure_reason = cmd.reason
        await self._close_attempt(payment, "failed", reason=cmd.reason, now=now)
        await self._record(payment, "failed", {"reason": cmd.reason}, actor_id)
        PAYMENTS_FAILED.labels(payment.method).inc()
        return payment

    async def cancel(
        self, payment_id: uuid.UUID, cmd: CancelPaymentCommand, *, actor_id: uuid.UUID
    ) -> Payment:
        """draft|pending|failed -> cancelled. Terminal; releases the money.

        Cancelling from `processing` is deliberately impossible: money may
        already be in flight, and the truthful sequence is fail-then-cancel.
        """
        payment = await self.get(payment_id)
        if payment.status == "processing":
            raise ConflictError(
                "a processing payment cannot be cancelled — record the failure first"
            )
        await self._transition(payment, expected=CANCELLABLE_STATUSES, to="cancelled")
        payment.cancelled_at = utcnow()
        await self._record(payment, "cancelled", {"reason": cmd.reason}, actor_id)
        PAYMENTS_CANCELLED.labels(payment.method).inc()
        return payment

    # --- queries -----------------------------------------------------------

    async def get(self, payment_id: uuid.UUID) -> Payment:
        tenant_id = require_current_tenant()
        payment = await self._session.get(Payment, payment_id)
        if payment is None or payment.tenant_id != tenant_id:
            raise NotFoundError("payment not found")
        return payment

    async def detail(self, payment_id: uuid.UUID) -> PaymentDetailView:
        payment = await self.get(payment_id)
        lines = await self._lines(payment.id)
        attempts = await self._attempts(payment.id)
        line_sum = sum((Decimal(line.amount) for line in lines), Decimal("0"))
        return PaymentDetailView(
            payment=self._view(payment, len(lines)),
            lines=[PaymentLineView.model_validate(line) for line in lines],
            attempts=[PaymentAttemptView.model_validate(a) for a in attempts],
            totals_match_lines=Decimal(payment.amount) == line_sum,
        )

    async def search(
        self,
        *,
        q: str | None = None,
        supplier_id: uuid.UUID | None = None,
        settlement_id: uuid.UUID | None = None,
        status: str | None = None,
        method: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PaymentPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        stmt = select(Payment).where(Payment.tenant_id == tenant_id)
        if q:
            term = f"%{q.lower()}%"
            stmt = stmt.where(
                func.lower(Payment.payment_number).like(term)
                | func.lower(func.coalesce(Payment.reference, "")).like(term)
            )
        if supplier_id:
            stmt = stmt.where(Payment.supplier_id == supplier_id)
        if status:
            stmt = stmt.where(Payment.status == status)
        if method:
            stmt = stmt.where(Payment.method == method.upper())
        if settlement_id:
            stmt = stmt.where(
                Payment.id.in_(
                    select(PaymentLine.payment_id).where(PaymentLine.settlement_id == settlement_id)
                )
            )
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = list(
            (
                await self._session.scalars(
                    stmt.order_by(Payment.created_at.desc()).limit(limit).offset(offset)
                )
            ).all()
        )
        counts = await self._line_counts([p.id for p in rows])
        return PaymentPage(
            items=[self._view(p, counts.get(p.id, 0)) for p in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    async def balance(self, settlement_id: uuid.UUID) -> SettlementBalanceView:
        """Outstanding balance of one finalized settlement."""
        tenant_id = require_current_tenant()
        settlement = await self._session.get(Settlement, settlement_id)
        if settlement is None or settlement.tenant_id != tenant_id:
            raise NotFoundError("settlement not found")
        allocated, paid = await self._allocations(settlement.id)
        return self._balance_view(settlement, allocated, paid)

    async def balances(
        self,
        *,
        supplier_id: uuid.UUID | None = None,
        outstanding_only: bool = True,
        limit: int = 20,
        offset: int = 0,
    ) -> BalancePage:
        """Every finalized settlement with its outstanding balance — the
        selector a payment is built from.

        Allocation sums are joined in SQL and the outstanding filter runs in
        the database: the payables list grows with every period of every
        supplier, so it must never be fetched whole to be paginated."""
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        allocated_col = func.coalesce(func.sum(PaymentLine.amount), 0)
        paid_col = func.coalesce(
            func.sum(case((Payment.status == "completed", PaymentLine.amount), else_=Decimal("0"))),
            0,
        )
        sums = (
            select(
                PaymentLine.settlement_id.label("settlement_id"),
                allocated_col.label("allocated"),
                paid_col.label("paid"),
            )
            .join(Payment, Payment.id == PaymentLine.payment_id)
            .where(Payment.status.in_(LIVE_STATUSES))
            .group_by(PaymentLine.settlement_id)
            .subquery()
        )
        allocated = func.coalesce(sums.c.allocated, 0)
        stmt = (
            select(Settlement, allocated, func.coalesce(sums.c.paid, 0))
            .outerjoin(sums, sums.c.settlement_id == Settlement.id)
            .where(Settlement.tenant_id == tenant_id, Settlement.status == "finalized")
        )
        if supplier_id:
            stmt = stmt.where(Settlement.supplier_id == supplier_id)
        if outstanding_only:
            stmt = stmt.where(Settlement.net_amount > allocated)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.execute(
            stmt.order_by(Settlement.period_from.desc()).limit(limit).offset(offset)
        )
        views = [
            self._balance_view(settlement, Decimal(allocated_sum), Decimal(paid_sum))
            for settlement, allocated_sum, paid_sum in rows.all()
        ]
        return BalancePage(items=views, total=total or 0, limit=limit, offset=offset)

    # --- helpers ------------------------------------------------------------

    async def _payable_settlement(
        self,
        settlement_id: uuid.UUID,
        tenant_id: uuid.UUID,
        supplier_id: uuid.UUID,
        currency: str,
    ) -> Settlement:
        """BR-0018: only a FINALIZED settlement is payable, and it must belong
        to this payment's payee and currency.

        ARCH-001: the row is locked FOR UPDATE, and that is not incidental.

        Allocating a payment is a read-modify-write — read the live
        allocations, compute what is outstanding, refuse anything larger,
        then insert the line. Without a lock two concurrent payments against
        the same settlement both read the same sum, both see the full
        balance, both pass the check, and both insert. **The settlement is
        paid twice**, and nothing detects it: partial payment is legitimate,
        so there is no unique constraint that could collide.

        READ COMMITTED does not help here — a `SELECT sum(...)` takes no
        locks, so the two transactions never conflict. Locking the settlement
        serialises payments against THAT settlement only, which is the exact
        granularity the invariant needs: two payments to different
        settlements still run concurrently.

        The lock is taken before the balance is read, so it covers the whole
        check-then-act, and it is released by the request's commit.
        """
        settlement = await self._session.get(Settlement, settlement_id, with_for_update=True)
        if settlement is None or settlement.tenant_id != tenant_id:
            raise NotFoundError("settlement not found")
        if settlement.status != "finalized":
            raise ConflictError(
                f"settlement {settlement.settlement_number} is {settlement.status} — "
                "only finalized settlements can be paid"
            )
        if settlement.supplier_id != supplier_id:
            raise ConflictError(
                f"settlement {settlement.settlement_number} belongs to a different supplier"
            )
        if settlement.currency != currency:
            raise ConflictError(
                f"settlement {settlement.settlement_number} is in {settlement.currency}, "
                f"not {currency} — currency conversion is not a payment operation"
            )
        return settlement

    async def _resolve_allocation(
        self, settlement: Settlement, requested: Decimal | None
    ) -> Decimal:
        """BR-0018: live allocations must never exceed the payable. An omitted
        amount means 'the rest of it' — the common case."""
        allocated, _paid = await self._allocations(settlement.id)
        payable = Money(amount=Decimal(settlement.net_amount), currency=settlement.currency)
        outstanding = payable.minus(Money(amount=allocated, currency=settlement.currency)).amount
        if outstanding <= 0:
            raise ConflictError(
                f"settlement {settlement.settlement_number} is already fully paid or allocated"
            )
        if requested is None:
            return outstanding
        amount = Decimal(requested).quantize(Decimal("0.01"))
        if amount <= 0:
            raise ConflictError("an allocation must be a positive amount")
        if amount > outstanding:
            raise ConflictError(
                f"allocation {amount} exceeds the outstanding {outstanding} on "
                f"settlement {settlement.settlement_number}"
            )
        return amount

    async def _allocations(self, settlement_id: uuid.UUID) -> tuple[Decimal, Decimal]:
        """(allocated by live payments, paid by completed payments)."""
        result = await self._allocations_for([settlement_id])
        return result.get(settlement_id, (Decimal("0.00"), Decimal("0.00")))

    async def _allocations_for(
        self, settlement_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
        if not settlement_ids:
            return {}
        rows = await self._session.execute(
            select(PaymentLine.settlement_id, Payment.status, func.sum(PaymentLine.amount))
            .join(Payment, Payment.id == PaymentLine.payment_id)
            .where(
                PaymentLine.settlement_id.in_(settlement_ids),
                Payment.status.in_(LIVE_STATUSES),
            )
            .group_by(PaymentLine.settlement_id, Payment.status)
        )
        totals: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
        for settlement_id, status, amount in rows.all():
            allocated, paid = totals.get(settlement_id, (Decimal("0.00"), Decimal("0.00")))
            amount = Decimal(amount or 0)
            allocated += amount
            if status == "completed":
                paid += amount
            totals[settlement_id] = (allocated, paid)
        return totals

    def _balance_view(
        self, settlement: Settlement, allocated: Decimal, paid: Decimal
    ) -> SettlementBalanceView:
        payable = Money(amount=Decimal(settlement.net_amount), currency=settlement.currency)
        outstanding = payable.minus(Money(amount=allocated, currency=settlement.currency)).amount
        return SettlementBalanceView(
            settlement_id=settlement.id,
            settlement_number=settlement.settlement_number,
            supplier_id=settlement.supplier_id,
            currency=settlement.currency,
            payable=payable.amount,
            allocated=allocated,
            paid=paid,
            outstanding=outstanding,
            fully_paid=outstanding <= 0,
        )

    async def _transition(self, payment: Payment, *, expected: tuple[str, ...], to: str) -> None:
        """CAS state change — the platform's concurrency pattern. Two callers
        racing the same transition: exactly one wins."""
        if payment.status == "completed":
            raise ConflictError("completed payments are immutable")
        if payment.status == "cancelled":
            raise ConflictError("cancelled payments are terminal")
        if payment.status not in expected:
            raise ConflictError(
                f"a {payment.status} payment cannot become {to} — expected {' or '.join(expected)}"
            )
        now = utcnow()
        claim = await self._session.execute(
            update(Payment)
            .where(Payment.id == payment.id, Payment.status.in_(expected))
            .values(status=to, updated_at=now)
        )
        if claim.rowcount != 1:
            raise ConflictError("payment status changed concurrently — reload and retry")
        await self._session.refresh(payment)

    async def _open_attempt(
        self, payment: Payment, cmd: ExecutePaymentCommand, actor_id: uuid.UUID
    ) -> PaymentAttempt:
        attempt = PaymentAttempt(
            tenant_id=payment.tenant_id,
            payment_id=payment.id,
            attempt_number=payment.attempt_count + 1,
            # Metadata only: the "provider" defaults to the payment method,
            # because nothing here talks to an external system.
            provider=(cmd.provider or payment.method).upper(),
            reference=cmd.reference,
            status="processing",
            operator_id=actor_id,
        )
        self._session.add(attempt)
        payment.attempt_count = attempt.attempt_number
        if cmd.reference:
            payment.reference = cmd.reference
        await self._session.flush()
        return attempt

    async def _close_attempt(
        self,
        payment: Payment,
        status: str,
        *,
        reference: str | None = None,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> None:
        attempt = await self._session.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment.id, PaymentAttempt.status == "processing")
            .order_by(PaymentAttempt.attempt_number.desc())
        )
        if attempt is None:
            return  # nothing open — the payment carries the outcome itself
        attempt.status = status
        attempt.completed_at = now or utcnow()
        if reference:
            attempt.reference = reference
        if reason:
            attempt.failure_reason = reason

    async def _lines(self, payment_id: uuid.UUID) -> list[PaymentLine]:
        rows = await self._session.scalars(
            select(PaymentLine)
            .where(PaymentLine.payment_id == payment_id)
            .order_by(PaymentLine.created_at, PaymentLine.settlement_number)
        )
        return list(rows.all())

    async def _attempts(self, payment_id: uuid.UUID) -> list[PaymentAttempt]:
        rows = await self._session.scalars(
            select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment_id)
            .order_by(PaymentAttempt.attempt_number)
        )
        return list(rows.all())

    async def _line_counts(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not ids:
            return {}
        rows = await self._session.execute(
            select(PaymentLine.payment_id, func.count())
            .where(PaymentLine.payment_id.in_(ids))
            .group_by(PaymentLine.payment_id)
        )
        return dict(rows.all())

    def _view(self, payment: Payment, line_count: int) -> PaymentView:
        return PaymentView(
            id=payment.id,
            payment_number=payment.payment_number,
            supplier_id=payment.supplier_id,
            currency=payment.currency,
            method=payment.method,
            amount=Decimal(payment.amount),
            reference=payment.reference,
            method_details=payment.method_details or {},
            status=payment.status,
            attempt_count=payment.attempt_count,
            failure_reason=payment.failure_reason,
            note=payment.note,
            line_count=line_count,
            created_at=payment.created_at,
            completed_at=payment.completed_at,
            failed_at=payment.failed_at,
            cancelled_at=payment.cancelled_at,
        )

    async def _audit(self, payment: Payment, action: str, data: dict, actor_id: uuid.UUID) -> None:
        await self._audit_service.record(
            action=f"payment.{action}",
            resource_type="payment",
            resource_id=payment.id,
            actor_id=actor_id,
            detail={"number": payment.payment_number, **data},
        )

    async def _record(self, payment: Payment, event: str, data: dict, actor_id: uuid.UUID) -> None:
        await self._audit(payment, event, data, actor_id)
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS[event],
                {
                    "payment_id": str(payment.id),
                    "payment_number": payment.payment_number,
                    "supplier_id": str(payment.supplier_id),
                    "status": payment.status,
                    **data,
                },
                actor_id=actor_id,
                aggregate_type="payment",
                aggregate_id=payment.id,
            )
        )

    async def _generate_number(self, tenant_id: uuid.UUID) -> str:
        for _ in range(5):
            candidate = "PAY-" + secrets.token_hex(3).upper()
            exists = await self._session.scalar(
                select(Payment).where(
                    Payment.tenant_id == tenant_id, Payment.payment_number == candidate
                )
            )
            if exists is None:
                return candidate
        raise ConflictError("could not generate a unique payment number")
