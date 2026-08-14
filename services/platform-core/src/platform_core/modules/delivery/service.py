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

from platform_core.core.business_time import business_today
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.money import quantize_money
from platform_core.core.org_context import tenant_currency, tenant_timezone
from platform_core.core.tenancy import enforce_customer_scope, require_current_tenant
from platform_core.infrastructure.events import EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.customer.service import CustomerName, CustomerService
from platform_core.modules.delivery.generation import GenerationResult
from platform_core.modules.delivery.models import (
    BILLABLE_STATUSES,
    DELIVERY_SLOTS,
    DELIVERY_STATUSES,
    PENDING_STATUSES,
    DeliveryGenerationRun,
    MilkDelivery,
)
from platform_core.modules.delivery.scheduler import record_run

#: Wire names, mapped from the domain name — the platform's convention.
BUS_EVENTS = {
    "DeliveryRecorded": "sales.delivery-recorded.v1",
    "DeliveryCancelled": "sales.delivery-cancelled.v1",
}

#: The scale `milk_delivery.quantity` is stored at — `Numeric(12, 3)`.
QUANTITY = Decimal("0.001")

#: What a report says the volume is measured in when there is nothing to
#: measure. An empty day still has to answer the question, and "L" is what
#: every delivery plan on this platform uses; a window with deliveries in it
#: reports THEIR unit instead, read from the rows.
DEFAULT_QUANTITY_UNIT = "L"

#: How many rows one download may carry. A year of a three-hundred-household
#: round is two hundred thousand deliveries; a file that large is neither
#: openable nor a thing to build in memory on request. A capped export says so
#: in its own last line — see `modules/delivery/export.py`.
EXPORT_LIMIT = 20_000

#: A customer whose record has gone while their deliveries remain. Not
#: expected — customers are deactivated, never deleted — but a report that
#: raised here would be a report a dairy could not run, and the row's money is
#: correct whatever the label says.
_UNKNOWN = CustomerName(id=uuid.UUID(int=0), code="—", name="(unknown customer)")


def money(value: Decimal, currency: str | None = None) -> Decimal:
    """Quantise once, explicitly, HALF_UP, at the CURRENCY's scale (DEMO-014).

    `currency=None` keeps the platform default of two decimals — what this
    module assumed before, and what every onboarded currency uses.
    """
    return quantize_money(value, currency)


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


class DeliveryCustomerRow(BaseModel):
    """One customer's share of the window (DEMO-015 §7).

    The dairy owner's second question, after "how much milk went out today?",
    is "to whom?" — and the answer has to come from the database for the same
    reason the first one does: a browser that groups the visible page produces
    a report that changes when you turn to page two.

    `unit_price` is the rate on this customer's deliveries when they all agree,
    and NULL when they do not. A single average would be arithmetic nobody
    asked for: a customer whose rate changed mid-month has two rates, and one
    blended number would hide that while looking authoritative.
    """

    customer_id: uuid.UUID
    code: str
    name: str
    product: str
    deliveries: int
    quantity: Decimal
    unit_price: Decimal | None
    amount: Decimal
    skipped: int


class DeliveryReport(BaseModel):
    date_from: date
    date_to: date
    #: The ORGANIZATION's currency. Present so a client never has to decide
    #: what these figures are denominated in — DEMO-013's rule, and the reason
    #: no screen carries a hard-coded symbol.
    currency: str
    quantity_unit: str
    deliveries: int
    customers_served: int
    total_quantity: Decimal
    total_amount: Decimal
    skipped: int
    #: Generated from a standing order and not yet acted on (DEMO-016 §13).
    #: The operator's "how many are left?" — and the reason `deliveries`
    #: counts only completed ones: a round that has been generated but not
    #: delivered is work outstanding, not milk sold.
    scheduled: int
    #: Generated + completed + skipped: the size of the day's round, whether
    #: it came from standing orders or was typed.
    planned: int
    by_day: list[DeliveryDayRow]
    by_customer: list[DeliveryCustomerRow]


class DeliveryExportRow(BaseModel):
    """One delivery, flattened, with its customer already named."""

    customer_code: str
    customer_name: str
    delivery_date: date
    slot: str
    product: str
    quantity: Decimal
    quantity_unit: str
    unit_price: Decimal
    amount: Decimal
    currency: str
    status: str
    #: Whether this milk is already on a bill. The invoice NUMBER would be more
    #: useful and is deliberately absent: it belongs to the billing module, and
    #: a delivery references it by UUID only. Yes/no answers the question this
    #: file is downloaded to answer — "what have we not billed yet?"
    billed: bool


class DeliveryExport(BaseModel):
    """Everything a file of this report needs, and nothing about its format.

    The rows and the aggregate travel together on purpose: the totals a
    downloaded file shows must be the totals the screen showed, and the only
    way to guarantee that is for both to be the same object.
    """

    report: DeliveryReport
    rows: list[DeliveryExportRow]
    matched: int  #: deliveries in the window, before any cap
    truncated: bool


class GenerationRunView(BaseModel):
    """What the scheduler did, in the terms §5 asks for."""

    id: uuid.UUID
    business_date: date
    status: str
    trigger: str
    plans_due: int
    created: int
    already_present: int
    not_due: int
    inactive_customers: int
    attempts: int
    error: str
    started_at: object
    finished_at: object | None
    duration_ms: int

    model_config = {"from_attributes": True}


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
        if existing is not None and existing.status in PENDING_STATUSES:
            # DEMO-016. The round was generated from a standing order and this
            # is the operator confirming it. Recording over a SCHEDULED row
            # fills it in rather than colliding with it — which is what lets
            # §11 be true: an operator does not need to know, and cannot tell
            # from the call they make, whether the delivery was generated or
            # typed. One code path serves the portal, the phone and the
            # offline queue replaying a call made in a village with no signal.
            return await self._confirm(existing, cmd, plan=plan, actor_id=actor_id)
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

    async def _confirm(
        self,
        delivery: MilkDelivery,
        cmd: RecordDeliveryCommand,
        *,
        plan,
        actor_id: uuid.UUID,
    ) -> MilkDelivery:
        """An operator acting on a delivery the generator produced.

        The quantity is the operator's when they gave one and the scheduled
        quantity otherwise, because the common case on a round is "yes, the
        usual" and making somebody retype it is how a round gets slower rather
        than faster.

        The RATE is not re-resolved. It is the one the plan carried when the
        round was generated, already sitting on the row — re-reading the plan
        here would let a rate agreed at lunchtime reprice a delivery made at
        six in the morning. The amount is then computed exactly as `record`
        computes it, from `Decimal`, by the domain.
        """
        if cmd.quantity is not None:
            delivery.quantity = cmd.quantity
        if cmd.status == "delivered" and Decimal(delivery.quantity) <= 0:
            raise ConflictError("a delivered quantity must be greater than zero")
        delivery.status = cmd.status
        if cmd.notes:
            delivery.notes = cmd.notes
        delivery.amount = (
            money(Decimal(delivery.quantity) * Decimal(delivery.unit_price), delivery.currency)
            if delivery.status in BILLABLE_STATUSES
            else Decimal("0.00")
        )
        await self._session.flush()

        await self._audit.record(
            action="sales.delivery.confirmed",
            resource_type="milk_delivery",
            resource_id=delivery.id,
            actor_id=actor_id,
            detail={
                "date": str(delivery.delivery_date),
                "slot": delivery.slot,
                "status": delivery.status,
                "quantity": str(delivery.quantity),
                "amount": str(delivery.amount),
                "from_plan": str(delivery.plan_id) if delivery.plan_id else "",
            },
        )
        await self._bus.publish(
            EventEnvelope.new(
                BUS_EVENTS["DeliveryRecorded"],
                {
                    "delivery_id": str(delivery.id),
                    "customer_id": str(delivery.customer_id),
                    "delivery_date": str(delivery.delivery_date),
                    "quantity": str(delivery.quantity),
                    "amount": str(delivery.amount),
                    "currency": delivery.currency,
                },
                actor_id=actor_id,
            )
        )
        return delivery

    async def generation_runs(self, *, limit: int = 14) -> list[GenerationRunView]:
        """The recent runs, newest first (DEMO-017 §10).

        Fourteen by default: a fortnight is enough to see a pattern and short
        enough that the answer is one indexed read. This is an operational
        record, not an analytics surface.
        """
        tenant_id = require_current_tenant()
        rows = (
            await self._session.scalars(
                select(DeliveryGenerationRun)
                .where(DeliveryGenerationRun.tenant_id == tenant_id)
                .order_by(DeliveryGenerationRun.business_date.desc())
                .limit(max(1, min(limit, 60)))
            )
        ).all()
        return [GenerationRunView.model_validate(r) for r in rows]

    async def generate(
        self, *, for_date: date | None = None, actor_id: uuid.UUID
    ) -> GenerationResult:
        """Run today's round from the standing orders (DEMO-016 §4).

        `for_date` is optional and defaults to the ORGANIZATION's today, for
        the same reason the daily report's dates do: a caller cannot compute an
        IANA calendar date without a timezone database, and a scheduler firing
        at 00:30 IST must produce the Indian day that has just begun rather
        than the UTC day that is still yesterday (§6).
        """
        tenant_id = require_current_tenant()
        day = for_date or business_today(await tenant_timezone(self._session))
        # DEMO-017: the SAME path the scheduler uses, so a manual run is
        # recorded exactly as an automatic one and the two cannot drift. The
        # work order forbids a second generation implementation and this is
        # what honouring that looks like at the call site.
        run = await record_run(self._session, tenant_id=tenant_id, day=day, trigger="manual")
        result = GenerationResult(
            business_date=run.business_date,
            due=run.plans_due,
            created=run.created,
            already_present=run.already_present,
            not_due=run.not_due,
            inactive_customers=run.inactive_customers,
        )
        await self._audit.record(
            action="sales.delivery.generated",
            resource_type="milk_delivery",
            resource_id=None,
            actor_id=actor_id,
            detail={
                "date": str(result.business_date),
                "due": result.due,
                "created": result.created,
                # Recorded because §18 asks for it by name, and because a run
                # that created nothing is the interesting one: it means the
                # round was already there, not that the generator failed.
                "already_present": result.already_present,
                "not_due": result.not_due,
                "inactive_customers": result.inactive_customers,
            },
        )
        return result

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
        date_from: date | None = None,
        date_to: date | None = None,
        customer_id: uuid.UUID | None = None,
    ) -> DeliveryReport:
        """ "What was delivered, to whom, and what is it worth?" — in SQL.

        Five grouped queries whatever the size of the window: a day, a month,
        or a year of a three-hundred-household round. A report that pulled the
        deliveries into a browser to total them would be wrong at the page
        boundary and slow everywhere else.
        """
        # DEMO-013: "today" is the ORGANIZATION's today. A dairy at UTC+5:30
        # asking for today at 04:00 local is asking about a day UTC has not
        # begun; answering in UTC would show them yesterday's round.
        today = business_today(await tenant_timezone(self._session))
        date_from = date_from or today
        date_to = date_to or today

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
                    # The unit these deliveries are actually in, rather than a
                    # constant a client would have to trust. Every plan on this
                    # platform says litres; the day one says kilograms, the
                    # report says kilograms too.
                    func.min(MilkDelivery.quantity_unit),
                ).where(*billable, MilkDelivery.status.in_(BILLABLE_STATUSES))
            )
        ).one()
        skipped = await self._session.scalar(
            select(func.count())
            .select_from(MilkDelivery)
            .where(*billable, MilkDelivery.status == "skipped")
        )
        scheduled = await self._session.scalar(
            select(func.count())
            .select_from(MilkDelivery)
            .where(*billable, MilkDelivery.status == "scheduled")
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

        # DEMO-015 §7: and to WHOM. Grouped over this module's OWN table and
        # then named through `CustomerService`, rather than joined to the
        # customer table — a delivery references a customer by UUID and asks
        # the owning module for anything else, which is the platform's module
        # boundary and not a formality here: the reporting module is the one
        # place allowed to SELECT across contexts, and it is allowed to because
        # it owns nothing and writes nothing.
        #
        # Two queries, not one per row. The N+1 §23 forbids is what a client
        # resolving these names itself would produce.
        #
        # `min = max` is how "they all agree" is asked in SQL. Two rates in one
        # window leave `unit_price` null rather than averaging them; see
        # DeliveryCustomerRow.
        by_customer = (
            await self._session.execute(
                select(
                    MilkDelivery.customer_id,
                    func.min(MilkDelivery.product),
                    func.count(),
                    func.coalesce(func.sum(cast(MilkDelivery.quantity, Numeric)), 0),
                    func.min(MilkDelivery.unit_price),
                    func.max(MilkDelivery.unit_price),
                    func.coalesce(func.sum(cast(MilkDelivery.amount, Numeric)), 0),
                )
                .where(*billable, MilkDelivery.status.in_(BILLABLE_STATUSES))
                .group_by(MilkDelivery.customer_id)
                .order_by(func.coalesce(func.sum(cast(MilkDelivery.amount, Numeric)), 0).desc())
            )
        ).all()
        # Skips are counted separately rather than joined in: a customer who
        # took nothing all week has no billable row to hang the count on, and
        # dropping them from the report is how a dairy stops noticing that a
        # household has quietly stopped buying milk.
        skipped_by_customer = dict(
            (
                await self._session.execute(
                    select(MilkDelivery.customer_id, func.count())
                    .where(*billable, MilkDelivery.status == "skipped")
                    .group_by(MilkDelivery.customer_id)
                )
            ).all()
        )
        named = await self._customers.directory(
            {row[0] for row in by_customer} | set(skipped_by_customer)
        )

        return DeliveryReport(
            date_from=date_from,
            date_to=date_to,
            currency=await tenant_currency(self._session),
            quantity_unit=headline[4] or DEFAULT_QUANTITY_UNIT,
            deliveries=headline[0] or 0,
            customers_served=headline[1] or 0,
            total_quantity=litres(headline[2]),
            total_amount=money(Decimal(headline[3] or 0)),
            skipped=skipped or 0,
            scheduled=scheduled or 0,
            planned=(headline[0] or 0) + (skipped or 0) + (scheduled or 0),
            by_customer=[
                DeliveryCustomerRow(
                    customer_id=row[0],
                    code=named.get(row[0], _UNKNOWN).code,
                    name=named.get(row[0], _UNKNOWN).name,
                    product=row[1],
                    deliveries=row[2],
                    quantity=litres(row[3]),
                    unit_price=Decimal(row[4]) if row[4] == row[5] else None,
                    amount=money(Decimal(row[6] or 0)),
                    skipped=skipped_by_customer.get(row[0], 0),
                )
                for row in by_customer
            ],
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

    async def export(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        customer_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> DeliveryExport:
        """Every delivery in the window, named, with the report's own totals.

        The cap is real and deliberate. A year of a three-hundred-household
        round is two hundred thousand rows, and building that string in memory
        to hand to a browser is a way to take the platform down from a screen
        that looks harmless. `EXPORT_LIMIT` rows come back and `truncated`
        says the rest were left — §23's rule against silent caps, and the
        renderer writes the fact into the file itself.
        """
        report = await self.report(date_from=date_from, date_to=date_to, customer_id=customer_id)
        tenant_id = require_current_tenant()
        conditions = self._conditions(
            tenant_id,
            customer_id=customer_id,
            date_from=report.date_from,
            date_to=report.date_to,
            status=status,
            invoiced=None,
        )
        matched = await self._session.scalar(
            select(func.count()).select_from(MilkDelivery).where(*conditions)
        )
        rows = (
            await self._session.scalars(
                select(MilkDelivery)
                .where(*conditions)
                .order_by(
                    MilkDelivery.delivery_date,
                    MilkDelivery.slot,
                    MilkDelivery.created_at,
                )
                .limit(EXPORT_LIMIT)
            )
        ).all()
        named = await self._customers.directory({row.customer_id for row in rows})
        return DeliveryExport(
            report=report,
            matched=matched or 0,
            truncated=(matched or 0) > len(rows),
            rows=[
                DeliveryExportRow(
                    customer_code=named.get(row.customer_id, _UNKNOWN).code,
                    customer_name=named.get(row.customer_id, _UNKNOWN).name,
                    delivery_date=row.delivery_date,
                    slot=row.slot,
                    product=row.product,
                    quantity=Decimal(row.quantity),
                    quantity_unit=row.quantity_unit,
                    unit_price=Decimal(row.unit_price),
                    amount=Decimal(row.amount),
                    currency=row.currency,
                    status=row.status,
                    billed=row.invoice_id is not None,
                )
                for row in rows
            ],
        )
