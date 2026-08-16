"""Billing application service (DEMO-009).

Invoice → customer payment → receipt. The receivable mirror of settlement →
payment → receipt, with the same guarantees and the opposite direction of
money.

Two rules carry the weight:

  * **An invoice is generated FROM deliveries, never typed.** Its lines are
    copies of real delivery rows, its subtotal is the sum of those lines
    computed in `Decimal`, and generating it stamps each delivery with the
    invoice id so the same milk cannot be billed twice.
  * **An issued invoice is immutable** — the same rule BR-0010 applies to a
    finalized settlement. A correction is a new document, not an edit.
"""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.business_time import (
    business_date_of,
    business_today,
    month_bounds,
    range_bounds,
)
from platform_core.core.db import utcnow
from platform_core.core.document_numbers import next_document_number
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.money import quantize_money
from platform_core.core.org_context import tenant_currency, tenant_timezone
from platform_core.core.tenancy import enforce_customer_scope, require_current_tenant
from platform_core.infrastructure.events import EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.billing.models import (
    PAYABLE_INVOICE_STATUSES,
    PAYMENT_METHODS,
    CustomerInvoice,
    CustomerInvoiceLine,
    CustomerPayment,
    CustomerPaymentAllocation,
    CustomerReceipt,
)
from platform_core.modules.business_calendar.service import assert_period_open
from platform_core.modules.customer.models import Customer
from platform_core.modules.delivery.models import BILLABLE_STATUSES, MilkDelivery

BUS_EVENTS = {
    "InvoiceIssued": "sales.invoice-issued.v1",
    "CustomerPaymentRecorded": "sales.customer-payment-recorded.v1",
}

ZERO = Decimal("0.00")


def money(value: Decimal, currency: str | None = None) -> Decimal:
    """Quantise once, at the CURRENCY's scale (DEMO-014).

    `currency=None` keeps the platform default of two decimals, which is what
    this module assumed before and what every onboarded currency uses. Callers
    that know the currency pass it, and a zero-decimal currency then rounds
    correctly instead of gaining a hundredth that does not exist.
    """
    return quantize_money(value, currency)


# --- commands ----------------------------------------------------------------


class GenerateInvoiceCommand(BaseModel):
    customer_id: uuid.UUID
    period_from: date
    period_to: date


class RecordCustomerPaymentCommand(BaseModel):
    customer_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    method: str = "CASH"
    reference: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=300)
    #: Which invoices this money settles. Omit to let the domain apply it to
    #: the oldest unpaid invoices first, which is what a dairy actually does.
    invoice_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("method")
    @classmethod
    def _known_method(cls, v: str) -> str:
        if v not in PAYMENT_METHODS:
            raise ValueError(f"method must be one of {', '.join(PAYMENT_METHODS)}")
        return v


# --- views -------------------------------------------------------------------


class InvoiceLineView(BaseModel):
    id: uuid.UUID
    delivery_id: uuid.UUID
    delivery_date: date
    slot: str
    product: str
    quantity: Decimal
    quantity_unit: str
    unit_price: Decimal
    amount: Decimal

    model_config = {"from_attributes": True}


class InvoiceView(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    invoice_number: str
    period_from: date
    period_to: date
    currency: str
    subtotal: Decimal
    adjustments: Decimal
    total: Decimal
    previous_balance: Decimal
    amount_due: Decimal
    status: str
    line_count: int
    issued_at: object | None
    created_at: object

    model_config = {"from_attributes": True}


class InvoicePage(BaseModel):
    items: list[InvoiceView]
    total: int
    limit: int
    offset: int


class InvoiceDetailView(BaseModel):
    invoice: InvoiceView
    lines: list[InvoiceLineView]
    #: Payments applied to THIS invoice, and what is left.
    paid: Decimal
    outstanding: Decimal
    #: The platform's own answer to "do the lines still add up to the total?"
    totals_match_lines: bool


class CustomerPaymentView(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    payment_number: str
    amount: Decimal
    currency: str
    method: str
    reference: str
    status: str
    notes: str
    received_at: object
    created_at: object

    model_config = {"from_attributes": True}


class PaymentAllocationView(BaseModel):
    invoice_id: uuid.UUID
    invoice_number: str
    amount: Decimal

    model_config = {"from_attributes": True}


class CustomerPaymentPage(BaseModel):
    items: list[CustomerPaymentView]
    total: int
    limit: int
    offset: int


class CustomerPaymentDetailView(BaseModel):
    payment: CustomerPaymentView
    allocations: list[PaymentAllocationView]
    receipt_number: str | None


class CustomerBalanceView(BaseModel):
    """What one customer owes, as the platform computes it."""

    customer_id: uuid.UUID
    currency: str
    invoiced: Decimal
    paid: Decimal
    outstanding: Decimal
    #: Delivered but not yet on any invoice — the bill still forming.
    unbilled_amount: Decimal
    unbilled_deliveries: int
    open_invoices: int


class StatementEntry(BaseModel):
    """One line of a customer's ledger — a bill or a payment, never both."""

    entry_date: date
    #: `invoice` or `payment`. Two columns rather than one signed number,
    #: because that is how a dairy's own ledger book is written and what a
    #: customer disputing a line will point at.
    kind: str
    reference: str  #: the invoice or payment number
    detail: str  #: the period billed, or how the money arrived
    debit: Decimal  #: what they were billed
    credit: Decimal  #: what they paid
    balance: Decimal  #: what they owed after this line


class CustomerStatement(BaseModel):
    """What a customer owes and how they came to owe it (DEMO-015 §13).

    `balance()` answers "what is owed **now**", which is the right answer to
    the dairy owner's morning question and the wrong one to the customer's:
    *"I paid you in August — what is this for?"* A statement answers that by
    showing the movement, and it has to start from an OPENING BALANCE or the
    arithmetic on the page will not add up for any window that does not begin
    at the beginning of time.

    The identity this holds to, and what its test asserts:

        opening + billed - paid = closing

    and, when the window ends today, `closing == balance().outstanding` — so a
    customer's statement and the dairy's receivables report can never tell two
    different stories about the same money.

    Deliberately NOT a general ledger. No accounts, no journals, no ageing
    buckets: a dairy's statement is a list of bills and the money against them,
    and DEMO-015 §13 says so in as many words.
    """

    customer_id: uuid.UUID
    code: str
    name: str
    currency: str
    date_from: date
    date_to: date
    opening_balance: Decimal
    billed: Decimal
    paid: Decimal
    closing_balance: Decimal
    #: How much milk this customer actually took in the window (DEMO-019 §7).
    #:
    #: On the statement rather than only on the delivery report because the
    #: question a dairy is answering here is "124 L, ₹7,440 billed, ₹5,000
    #: paid, ₹2,440 outstanding" — one sentence, and until now the litres came
    #: from a different screen. Counted over BILLABLE deliveries, so it is the
    #: milk the money refers to.
    delivered_quantity: Decimal
    quantity_unit: str
    entries: list[StatementEntry]


class CustomerReceiptView(BaseModel):
    id: uuid.UUID
    receipt_number: str
    payment_id: uuid.UUID
    payment_number: str
    customer_id: uuid.UUID
    customer_name: str
    customer_code: str
    amount: Decimal
    currency: str
    method: str
    reference: str
    applied_to: str
    generated_at: object

    model_config = {"from_attributes": True}


class BillingService:
    def __init__(self, session: AsyncSession, bus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit

    # --- invoices ----------------------------------------------------------

    async def generate_invoice(
        self, cmd: GenerateInvoiceCommand, *, actor_id: uuid.UUID
    ) -> CustomerInvoice:
        """Build a draft statement from the period's unbilled deliveries."""
        tenant_id = require_current_tenant()
        if cmd.period_to < cmd.period_from:
            raise ConflictError("the period ends before it begins")
        # DEMO-021: the period the bill COVERS, not today. Guarding by today
        # would let somebody bill a closed August from an open September.
        await assert_period_open(
            self._session, tenant_id, cmd.period_to, operation="generating an invoice"
        )
        customer = await self._customer(cmd.customer_id)

        clash = await self._session.scalar(
            select(CustomerInvoice).where(
                CustomerInvoice.tenant_id == tenant_id,
                CustomerInvoice.customer_id == customer.id,
                CustomerInvoice.period_from == cmd.period_from,
                CustomerInvoice.period_to == cmd.period_to,
                CustomerInvoice.status != "cancelled",
            )
        )
        if clash is not None:
            raise ConflictError(
                f"{customer.code} already has invoice {clash.invoice_number} for this period"
            )

        deliveries = (
            await self._session.scalars(
                select(MilkDelivery)
                .where(
                    MilkDelivery.tenant_id == tenant_id,
                    MilkDelivery.customer_id == customer.id,
                    MilkDelivery.delivery_date >= cmd.period_from,
                    MilkDelivery.delivery_date <= cmd.period_to,
                    MilkDelivery.status.in_(BILLABLE_STATUSES),
                    MilkDelivery.invoice_id.is_(None),
                )
                .order_by(MilkDelivery.delivery_date, MilkDelivery.slot)
            )
        ).all()
        if not deliveries:
            raise ConflictError("no unbilled deliveries in this period")

        previous_balance = (await self.balance(customer.id)).outstanding

        invoice = CustomerInvoice(
            tenant_id=tenant_id,
            customer_id=customer.id,
            invoice_number=await next_document_number(
                self._session, tenant_id=tenant_id, doc_type="customer_invoice", prefix="INV"
            ),
            period_from=cmd.period_from,
            period_to=cmd.period_to,
            currency=customer.currency,
            previous_balance=previous_balance,
        )
        self._session.add(invoice)
        await self._session.flush()

        subtotal = ZERO
        for delivery in deliveries:
            self._session.add(
                CustomerInvoiceLine(
                    tenant_id=tenant_id,
                    invoice_id=invoice.id,
                    delivery_id=delivery.id,
                    delivery_date=delivery.delivery_date,
                    slot=delivery.slot,
                    product=delivery.product,
                    quantity=delivery.quantity,
                    quantity_unit=delivery.quantity_unit,
                    unit_price=delivery.unit_price,
                    amount=delivery.amount,
                )
            )
            # Stamped now, so the same milk cannot appear on a second invoice
            # even if two are generated concurrently — the unique constraint on
            # (tenant, delivery) is the backstop.
            delivery.invoice_id = invoice.id
            subtotal += Decimal(delivery.amount)

        invoice.subtotal = money(subtotal)
        invoice.adjustments = ZERO
        invoice.total = money(subtotal + invoice.adjustments)
        invoice.amount_due = money(invoice.total + Decimal(invoice.previous_balance))
        invoice.line_count = len(deliveries)
        await self._session.flush()

        await self._audit.record(
            action="sales.invoice.generated",
            resource_type="customer_invoice",
            resource_id=invoice.id,
            actor_id=actor_id,
            detail={
                "customer": customer.code,
                "invoice": invoice.invoice_number,
                "lines": invoice.line_count,
                "total": str(invoice.total),
            },
        )
        return invoice

    async def issue_invoice(self, invoice_id: uuid.UUID, *, actor_id: uuid.UUID) -> CustomerInvoice:
        """Hand it to the customer. Irreversible: it becomes immutable and payable."""
        invoice = await self.get_invoice(invoice_id)
        if invoice.status != "draft":
            raise ConflictError(
                f"only a draft invoice can be issued — this one is {invoice.status}"
            )
        if invoice.line_count == 0:
            raise ConflictError("cannot issue an invoice with no lines")
        # DEMO-021: issuing is the irreversible act, so it is the one that must
        # not reach into a closed month.
        await assert_period_open(
            self._session, invoice.tenant_id, invoice.period_to, operation="issuing an invoice"
        )

        lines_total = await self._session.scalar(
            select(func.coalesce(func.sum(cast(CustomerInvoiceLine.amount, Numeric)), 0)).where(
                CustomerInvoiceLine.invoice_id == invoice.id
            )
        )
        if money(Decimal(lines_total or 0)) != Decimal(invoice.subtotal):
            raise ConflictError("invoice totals no longer match the lines — regenerate it")

        invoice.status = "issued"
        invoice.issued_at = utcnow()
        await self._audit.record(
            action="sales.invoice.issued",
            resource_type="customer_invoice",
            resource_id=invoice.id,
            actor_id=actor_id,
            detail={"invoice": invoice.invoice_number, "amount_due": str(invoice.amount_due)},
        )
        # The household this bill belongs to — needed so the event can carry
        # where to reach them (DEMO-025).
        customer = await self._customer(invoice.customer_id)
        quantity, quantity_unit = await self._sum_invoice_quantity(invoice.id)
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS["InvoiceIssued"],
                {
                    "invoice_id": str(invoice.id),
                    "customer_id": str(invoice.customer_id),
                    "invoice_number": invoice.invoice_number,
                    "amount_due": str(invoice.amount_due),
                    "currency": invoice.currency,
                    # DEMO-025: the BUSINESS dates this invoice bills, carried
                    # so a notification never has to guess them. The dispatch
                    # consumer previously fell back to `envelope.time[:10]` —
                    # a slice of a UTC timestamp — which for an Indian dairy
                    # billing after 18:30 local names the wrong day on the
                    # customer's own bill.
                    "period_from": str(invoice.period_from),
                    "period_to": str(invoice.period_to),
                    "total": str(invoice.total),
                    # DEMO-025: where to reach the household, and what to call
                    # them. Carried on the event exactly as the supplier
                    # events already carry contact details — the notification
                    # module has a directory for suppliers and none for
                    # customers, and a household with no directory entry could
                    # not be billed by SMS at all.
                    #
                    # This is contact information, not a credential: it is
                    # already in the customer row and in every backup. The one
                    # thing that must never travel this way is a secret, which
                    # is why the invitation token does not (see the dispatch
                    # consumer's note on INVITATION_ISSUED).
                    "customer_name": customer.name,
                    "phone": customer.phone,
                    # DEMO-028. Two more authoritative figures, so a bill can
                    # be explained rather than merely stated.
                    #
                    # `amount_due` already carried is total + previous_balance.
                    # A household with anything carried forward was being shown
                    # one number that matched neither what it was billed this
                    # period nor what it thought it owed, and had no way to
                    # tell which. Both halves are on the invoice already;
                    # nothing here computes money.
                    "previous_balance": str(invoice.previous_balance),
                    # And how much milk it is for. Read from the lines, stored
                    # nowhere — the same reason the settlement slip gained it.
                    "quantity": str(quantity),
                    "quantity_unit": quantity_unit,
                },
                actor_id=actor_id,
            )
        )
        return invoice

    async def _sum_invoice_quantity(self, invoice_id: uuid.UUID) -> tuple[Decimal, str]:
        """How much was delivered on this invoice, and in what unit (DEMO-028).

        **A read.** Nothing is stored, no total moves, and the invoice's own
        arithmetic is untouched — this exists so a bill can say what it is for.

        Mixed units are reported as no quantity rather than as a sum: adding
        litres to kilograms produces a number that means nothing, and a
        meaningless number on a customer's bill is worse than a missing one.
        """
        rows = (
            await self._session.execute(
                select(CustomerInvoiceLine.quantity, CustomerInvoiceLine.quantity_unit).where(
                    CustomerInvoiceLine.invoice_id == invoice_id
                )
            )
        ).all()
        units = {unit for _q, unit in rows}
        if len(units) != 1:
            return Decimal("0"), ""
        return sum((Decimal(q) for q, _u in rows), Decimal("0")), units.pop()

    async def cancel_invoice(
        self, invoice_id: uuid.UUID, reason: str, *, actor_id: uuid.UUID
    ) -> CustomerInvoice:
        invoice = await self.get_invoice(invoice_id)
        if invoice.status != "draft":
            raise ConflictError(
                f"only a draft invoice can be cancelled — this one is {invoice.status}"
            )
        await assert_period_open(
            self._session,
            invoice.tenant_id,
            invoice.period_to,
            operation="cancelling an invoice",
        )
        # Release the deliveries so they can be billed again, and delete the
        # lines with them. A cancelled DRAFT was never issued, so its lines are
        # working material rather than a document anybody was given — and
        # leaving them behind would hold the (tenant, delivery) uniqueness and
        # make the released deliveries unbillable, which is the opposite of
        # what cancelling is for.
        lines = (
            await self._session.scalars(
                select(CustomerInvoiceLine).where(CustomerInvoiceLine.invoice_id == invoice.id)
            )
        ).all()
        for line in lines:
            delivery = await self._session.get(MilkDelivery, line.delivery_id)
            if delivery is not None:
                delivery.invoice_id = None
            await self._session.delete(line)
        invoice.line_count = 0
        await self._session.flush()
        invoice.status = "cancelled"
        invoice.cancelled_at = utcnow()
        await self._audit.record(
            action="sales.invoice.cancelled",
            resource_type="customer_invoice",
            resource_id=invoice.id,
            actor_id=actor_id,
            detail={"invoice": invoice.invoice_number, "reason": reason},
        )
        return invoice

    # --- payments ----------------------------------------------------------

    async def record_payment(
        self, cmd: RecordCustomerPaymentCommand, *, actor_id: uuid.UUID
    ) -> CustomerPayment:
        """Money received. It has already arrived, so there is one state."""
        tenant_id = require_current_tenant()
        # DEMO-021: money belongs to the day it ARRIVED, which for a payment
        # being recorded now is the dairy's today. A closed month must not
        # acquire new receipts after the books were shut.
        await assert_period_open(
            self._session,
            tenant_id,
            business_today(await tenant_timezone(self._session, tenant_id)),
            operation="recording a payment",
        )
        customer = await self._customer(cmd.customer_id)

        targets = await self._invoices_to_settle(customer.id, cmd.invoice_ids)
        payment = CustomerPayment(
            tenant_id=tenant_id,
            customer_id=customer.id,
            payment_number=await next_document_number(
                self._session, tenant_id=tenant_id, doc_type="customer_payment", prefix="CPY"
            ),
            amount=money(cmd.amount),
            currency=customer.currency,
            method=cmd.method,
            reference=cmd.reference,
            notes=cmd.notes,
            recorded_by=actor_id,
        )
        self._session.add(payment)
        await self._session.flush()

        # Apply oldest first. Anything left over is credit on the account and
        # reduces the next invoice's previous balance — it is not lost, and it
        # is not silently discarded either.
        remaining = Decimal(payment.amount)
        applied: list[str] = []
        for invoice in targets:
            if remaining <= 0:
                break
            outstanding = await self._invoice_outstanding(invoice)
            if outstanding <= 0:
                continue
            portion = min(remaining, outstanding)
            self._session.add(
                CustomerPaymentAllocation(
                    tenant_id=tenant_id,
                    payment_id=payment.id,
                    invoice_id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    amount=money(portion),
                )
            )
            remaining -= portion
            applied.append(invoice.invoice_number)
            if portion >= outstanding:
                invoice.status = "paid"
        await self._session.flush()

        await self._audit.record(
            action="sales.payment.recorded",
            resource_type="customer_payment",
            resource_id=payment.id,
            actor_id=actor_id,
            detail={
                "customer": customer.code,
                "payment": payment.payment_number,
                "amount": str(payment.amount),
                "applied_to": applied,
            },
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS["CustomerPaymentRecorded"],
                {
                    "payment_id": str(payment.id),
                    "payment_number": payment.payment_number,
                    "customer_id": str(customer.id),
                    "customer_name": customer.name,
                    "customer_code": customer.code,
                    "amount": str(payment.amount),
                    "currency": payment.currency,
                    "method": payment.method,
                    "reference": payment.reference,
                    "applied_to": ", ".join(applied),
                },
                actor_id=actor_id,
            )
        )
        return payment

    async def _invoices_to_settle(
        self, customer_id: uuid.UUID, invoice_ids: list[uuid.UUID]
    ) -> list[CustomerInvoice]:
        tenant_id = require_current_tenant()
        stmt = select(CustomerInvoice).where(
            CustomerInvoice.tenant_id == tenant_id,
            CustomerInvoice.customer_id == customer_id,
            CustomerInvoice.status.in_(PAYABLE_INVOICE_STATUSES),
        )
        if invoice_ids:
            stmt = stmt.where(CustomerInvoice.id.in_(invoice_ids))
        return list((await self._session.scalars(stmt.order_by(CustomerInvoice.period_from))).all())

    async def _invoice_outstanding(self, invoice: CustomerInvoice) -> Decimal:
        allocated = await self._session.scalar(
            select(func.coalesce(func.sum(cast(CustomerPaymentAllocation.amount, Numeric)), 0))
            .join(CustomerPayment, CustomerPayment.id == CustomerPaymentAllocation.payment_id)
            .where(
                CustomerPaymentAllocation.invoice_id == invoice.id,
                CustomerPayment.status == "recorded",
            )
        )
        return money(Decimal(invoice.total) - Decimal(allocated or 0))

    # --- queries -----------------------------------------------------------

    async def _customer(self, customer_id: uuid.UUID) -> Customer:
        tenant_id = require_current_tenant()
        customer = await self._session.scalar(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        )
        if customer is None:
            raise NotFoundError("customer not found")
        return customer

    async def get_invoice(self, invoice_id: uuid.UUID) -> CustomerInvoice:
        tenant_id = require_current_tenant()
        invoice = await self._session.scalar(
            select(CustomerInvoice).where(
                CustomerInvoice.id == invoice_id, CustomerInvoice.tenant_id == tenant_id
            )
        )
        if invoice is None:
            raise NotFoundError("invoice not found")
        return invoice

    async def invoice_detail(self, invoice_id: uuid.UUID) -> InvoiceDetailView:
        invoice = await self.get_invoice(invoice_id)
        # DEMO-012: the bill is fetched by ITS id, so the scope is checked
        # against the invoice's customer once it is known. A customer asking
        # for another household's bill gets NOT FOUND.
        enforce_customer_scope(invoice.customer_id)
        lines = (
            await self._session.scalars(
                select(CustomerInvoiceLine)
                .where(CustomerInvoiceLine.invoice_id == invoice.id)
                .order_by(CustomerInvoiceLine.delivery_date, CustomerInvoiceLine.slot)
            )
        ).all()
        lines_total = money(sum((Decimal(line.amount) for line in lines), ZERO))
        paid = money(Decimal(invoice.total) - await self._invoice_outstanding(invoice))
        return InvoiceDetailView(
            invoice=InvoiceView.model_validate(invoice),
            lines=[InvoiceLineView.model_validate(line) for line in lines],
            paid=paid,
            outstanding=await self._invoice_outstanding(invoice),
            totals_match_lines=lines_total == Decimal(invoice.subtotal),
        )

    async def search_invoices(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> InvoicePage:
        tenant_id = require_current_tenant()
        # DEMO-012: narrowed to this principal's customer, if it has one.
        customer_id = enforce_customer_scope(customer_id)
        limit = max(1, min(limit, 100))
        conditions = [CustomerInvoice.tenant_id == tenant_id]
        if customer_id is not None:
            conditions.append(CustomerInvoice.customer_id == customer_id)
        if status:
            conditions.append(CustomerInvoice.status == status)
        if q:
            conditions.append(func.lower(CustomerInvoice.invoice_number).like(f"%{q.lower()}%"))
        total = await self._session.scalar(
            select(func.count()).select_from(CustomerInvoice).where(*conditions)
        )
        rows = (
            await self._session.scalars(
                select(CustomerInvoice)
                .where(*conditions)
                .order_by(CustomerInvoice.period_from.desc(), CustomerInvoice.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return InvoicePage(
            items=[InvoiceView.model_validate(r) for r in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    async def balance(self, customer_id: uuid.UUID) -> CustomerBalanceView:
        """What this customer owes. Four grouped queries, never a scan per row."""
        tenant_id = require_current_tenant()
        # DEMO-012: a customer may ask for its own balance and no other.
        customer_id = enforce_customer_scope(customer_id) or customer_id
        customer = await self._customer(customer_id)

        invoiced = await self._session.scalar(
            select(func.coalesce(func.sum(cast(CustomerInvoice.total, Numeric)), 0)).where(
                CustomerInvoice.tenant_id == tenant_id,
                CustomerInvoice.customer_id == customer_id,
                CustomerInvoice.status.in_(PAYABLE_INVOICE_STATUSES),
            )
        )
        paid = await self._session.scalar(
            select(func.coalesce(func.sum(cast(CustomerPayment.amount, Numeric)), 0)).where(
                CustomerPayment.tenant_id == tenant_id,
                CustomerPayment.customer_id == customer_id,
                CustomerPayment.status == "recorded",
            )
        )
        unbilled = (
            await self._session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(cast(MilkDelivery.amount, Numeric)), 0),
                ).where(
                    MilkDelivery.tenant_id == tenant_id,
                    MilkDelivery.customer_id == customer_id,
                    MilkDelivery.status.in_(BILLABLE_STATUSES),
                    MilkDelivery.invoice_id.is_(None),
                )
            )
        ).one()
        open_invoices = await self._session.scalar(
            select(func.count())
            .select_from(CustomerInvoice)
            .where(
                CustomerInvoice.tenant_id == tenant_id,
                CustomerInvoice.customer_id == customer_id,
                CustomerInvoice.status == "issued",
            )
        )
        return CustomerBalanceView(
            customer_id=customer_id,
            currency=customer.currency,
            invoiced=money(Decimal(invoiced or 0)),
            paid=money(Decimal(paid or 0)),
            outstanding=money(Decimal(invoiced or 0) - Decimal(paid or 0)),
            unbilled_amount=money(Decimal(unbilled[1] or 0)),
            unbilled_deliveries=unbilled[0] or 0,
            open_invoices=open_invoices or 0,
        )

    async def statement(
        self,
        customer_id: uuid.UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> CustomerStatement:
        """Opening balance, the movement, closing balance. Four queries.

        Two for the opening — aggregates, so a customer with ten years of
        history costs the same as one with ten days — and two for the rows
        inside the window, which is the only part anybody reads.

        **Dates are the dairy's, not UTC's.** An invoice issued at 03:00 on the
        first of September in Bengaluru is stored as 21:30 on the 31st of
        August, and a statement for August that included it would bill the
        customer for a document they had not yet been handed.
        """
        tenant_id = require_current_tenant()
        # DEMO-012: a customer may read its own statement and no other's.
        customer_id = enforce_customer_scope(customer_id) or customer_id
        customer = await self._customer(customer_id)

        timezone = await tenant_timezone(self._session)
        today = business_today(timezone)
        # A month back, which is the window a dairy actually asks for, and the
        # one the printed statement a household receives covers.
        date_from = date_from or month_bounds(today)[0]
        date_to = date_to or today
        if date_to < date_from:
            raise ConflictError("the statement ends before it begins")
        window_start, window_end = range_bounds(date_from, date_to, timezone)

        invoiced_before = await self._session.scalar(
            select(func.coalesce(func.sum(cast(CustomerInvoice.total, Numeric)), 0)).where(
                CustomerInvoice.tenant_id == tenant_id,
                CustomerInvoice.customer_id == customer_id,
                CustomerInvoice.status.in_(PAYABLE_INVOICE_STATUSES),
                CustomerInvoice.issued_at < window_start,
            )
        )
        paid_before = await self._session.scalar(
            select(func.coalesce(func.sum(cast(CustomerPayment.amount, Numeric)), 0)).where(
                CustomerPayment.tenant_id == tenant_id,
                CustomerPayment.customer_id == customer_id,
                CustomerPayment.status == "recorded",
                CustomerPayment.received_at < window_start,
            )
        )
        opening = money(Decimal(invoiced_before or 0) - Decimal(paid_before or 0))

        invoices = (
            await self._session.scalars(
                select(CustomerInvoice).where(
                    CustomerInvoice.tenant_id == tenant_id,
                    CustomerInvoice.customer_id == customer_id,
                    CustomerInvoice.status.in_(PAYABLE_INVOICE_STATUSES),
                    CustomerInvoice.issued_at >= window_start,
                    CustomerInvoice.issued_at < window_end,
                )
            )
        ).all()
        payments = (
            await self._session.scalars(
                select(CustomerPayment).where(
                    CustomerPayment.tenant_id == tenant_id,
                    CustomerPayment.customer_id == customer_id,
                    CustomerPayment.status == "recorded",
                    CustomerPayment.received_at >= window_start,
                    CustomerPayment.received_at < window_end,
                )
            )
        ).all()

        # The milk behind the money, over the same window. One aggregate; the
        # deliveries themselves are the delivery module's to list.
        volume = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(cast(MilkDelivery.quantity, Numeric)), 0),
                    func.min(MilkDelivery.quantity_unit),
                ).where(
                    MilkDelivery.tenant_id == tenant_id,
                    MilkDelivery.customer_id == customer_id,
                    MilkDelivery.status.in_(BILLABLE_STATUSES),
                    MilkDelivery.delivery_date >= date_from,
                    MilkDelivery.delivery_date <= date_to,
                )
            )
        ).one()

        movements: list[tuple[date, int, StatementEntry]] = []
        for invoice in invoices:
            movements.append(
                (
                    business_date_of(invoice.issued_at, timezone),
                    0,  # a bill before the money against it, on the same day
                    StatementEntry(
                        entry_date=business_date_of(invoice.issued_at, timezone),
                        kind="invoice",
                        reference=invoice.invoice_number,
                        detail=f"{invoice.period_from} — {invoice.period_to}",
                        debit=money(Decimal(invoice.total)),
                        credit=ZERO,
                        balance=ZERO,  # filled by the running total below
                    ),
                )
            )
        for payment in payments:
            movements.append(
                (
                    business_date_of(payment.received_at, timezone),
                    1,
                    StatementEntry(
                        entry_date=business_date_of(payment.received_at, timezone),
                        kind="payment",
                        reference=payment.payment_number,
                        detail=payment.method,
                        debit=ZERO,
                        credit=money(Decimal(payment.amount)),
                        balance=ZERO,
                    ),
                )
            )
        movements.sort(key=lambda m: (m[0], m[1], m[2].reference))

        running = opening
        entries = []
        billed = ZERO
        paid = ZERO
        for _day, _order, entry in movements:
            running = money(running + entry.debit - entry.credit)
            entry.balance = running
            billed += entry.debit
            paid += entry.credit
            entries.append(entry)

        return CustomerStatement(
            customer_id=customer.id,
            code=customer.code,
            name=customer.name,
            currency=customer.currency,
            date_from=date_from,
            date_to=date_to,
            opening_balance=opening,
            billed=money(billed),
            paid=money(paid),
            closing_balance=running,
            delivered_quantity=Decimal(volume[0] or 0).quantize(Decimal("0.001")),
            quantity_unit=volume[1] or "L",
            entries=entries,
        )

    async def search_payments(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        method: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> CustomerPaymentPage:
        tenant_id = require_current_tenant()
        # DEMO-012: narrowed to this principal's customer, if it has one.
        customer_id = enforce_customer_scope(customer_id)
        limit = max(1, min(limit, 100))
        conditions = [CustomerPayment.tenant_id == tenant_id]
        if customer_id is not None:
            conditions.append(CustomerPayment.customer_id == customer_id)
        if method:
            conditions.append(CustomerPayment.method == method)
        if q:
            like = f"%{q.lower()}%"
            conditions.append(
                func.lower(CustomerPayment.payment_number).like(like)
                | func.lower(CustomerPayment.reference).like(like)
            )
        total = await self._session.scalar(
            select(func.count()).select_from(CustomerPayment).where(*conditions)
        )
        rows = (
            await self._session.scalars(
                select(CustomerPayment)
                .where(*conditions)
                .order_by(CustomerPayment.received_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return CustomerPaymentPage(
            items=[CustomerPaymentView.model_validate(r) for r in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    async def payment_detail(self, payment_id: uuid.UUID) -> CustomerPaymentDetailView:
        tenant_id = require_current_tenant()
        payment = await self._session.scalar(
            select(CustomerPayment).where(
                CustomerPayment.id == payment_id, CustomerPayment.tenant_id == tenant_id
            )
        )
        if payment is None:
            raise NotFoundError("payment not found")
        allocations = (
            await self._session.scalars(
                select(CustomerPaymentAllocation).where(
                    CustomerPaymentAllocation.payment_id == payment.id
                )
            )
        ).all()
        receipt = await self._session.scalar(
            select(CustomerReceipt).where(
                CustomerReceipt.tenant_id == tenant_id, CustomerReceipt.payment_id == payment.id
            )
        )
        return CustomerPaymentDetailView(
            payment=CustomerPaymentView.model_validate(payment),
            allocations=[PaymentAllocationView.model_validate(a) for a in allocations],
            receipt_number=receipt.receipt_number if receipt else None,
        )

    # --- receipts ----------------------------------------------------------

    async def generate_receipt(
        self,
        *,
        tenant_id: uuid.UUID,
        payment_id: uuid.UUID,
        data: dict,
        source_event_id: uuid.UUID | None,
    ) -> CustomerReceipt | None:
        """Called by the consumer, never by a business module (BR-0020's rule).

        Idempotent: a redelivered event finds the receipt already there and
        returns it rather than minting a second proof of the same money.
        """
        existing = await self._session.scalar(
            select(CustomerReceipt).where(
                CustomerReceipt.tenant_id == tenant_id, CustomerReceipt.payment_id == payment_id
            )
        )
        if existing is not None:
            return existing
        receipt = CustomerReceipt(
            tenant_id=tenant_id,
            receipt_number=await next_document_number(
                self._session, tenant_id=tenant_id, doc_type="customer_receipt", prefix="CRC"
            ),
            payment_id=payment_id,
            payment_number=data.get("payment_number", ""),
            customer_id=uuid.UUID(data["customer_id"]),
            customer_name=data.get("customer_name", ""),
            customer_code=data.get("customer_code", ""),
            amount=Decimal(str(data["amount"])),
            # DEMO-013: the event always carries the currency the payment was
            # taken in, and THAT is what the receipt must say — a receipt is a
            # record of what happened, not of what this tenant usually does.
            # The fallback is for a malformed event and is the organization's
            # currency rather than the literal "KES" it used to be.
            currency=data.get("currency") or await tenant_currency(self._session),
            method=data.get("method", "CASH"),
            reference=data.get("reference", ""),
            applied_to=data.get("applied_to", ""),
            source_event_id=source_event_id,
        )
        self._session.add(receipt)
        await self._session.flush()
        return receipt

    async def search_receipts(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        tenant_id = require_current_tenant()
        # DEMO-012: narrowed to this principal's customer, if it has one.
        customer_id = enforce_customer_scope(customer_id)
        limit = max(1, min(limit, 100))
        conditions = [CustomerReceipt.tenant_id == tenant_id]
        if customer_id is not None:
            conditions.append(CustomerReceipt.customer_id == customer_id)
        if q:
            conditions.append(func.lower(CustomerReceipt.receipt_number).like(f"%{q.lower()}%"))
        total = await self._session.scalar(
            select(func.count()).select_from(CustomerReceipt).where(*conditions)
        )
        rows = (
            await self._session.scalars(
                select(CustomerReceipt)
                .where(*conditions)
                .order_by(CustomerReceipt.generated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return {
            "items": [CustomerReceiptView.model_validate(r) for r in rows],
            "total": total or 0,
            "limit": limit,
            "offset": offset,
        }
