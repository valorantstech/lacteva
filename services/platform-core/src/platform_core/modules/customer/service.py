"""Customer application service (DEMO-009 / CMA.SLS.02)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.document_numbers import next_document_number
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.org_context import tenant_currency
from platform_core.core.tenancy import enforce_customer_scope, require_current_tenant
from platform_core.modules.audit.service import AuditService
from platform_core.modules.customer.models import (
    BILLING_MODES,
    CUSTOMER_STATUSES,
    CUSTOMER_TYPES,
    Customer,
    DeliveryPlan,
)
from platform_core.modules.customer.schedule import (
    EVERY_DAY,
    WEEK,
    describe,
    next_due,
    normalise_weekdays,
)
from platform_core.modules.delivery.models import DELIVERY_SLOTS

# --- commands ----------------------------------------------------------------


class CreateCustomerCommand(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    customer_type: str = "household"
    phone: str = Field(default="", max_length=32)
    alternate_phone: str = Field(default="", max_length=32)
    address: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=500)
    billing_mode: str = "credit"
    billing_day: int = Field(default=1, ge=1, le=28)
    #: DEMO-013: absent means "this organization's currency", resolved at
    #: creation. It was `"KES"`, which made every dairy on the platform Kenyan
    #: by default — including an Indian one, whose first customer would have
    #: been billed in shillings by a field nobody filled in.
    #:
    #: Still overridable per customer, because the column already existed and
    #: a customer paying in another currency is a real, if rare, arrangement.
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    #: Optional: give the customer their standing order in the same request,
    #: because a customer without one cannot receive a delivery.
    plan: "DeliveryPlanInput | None" = None

    @field_validator("customer_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in CUSTOMER_TYPES:
            raise ValueError(f"customer_type must be one of {', '.join(CUSTOMER_TYPES)}")
        return v

    @field_validator("billing_mode")
    @classmethod
    def _known_mode(cls, v: str) -> str:
        if v not in BILLING_MODES:
            raise ValueError(f"billing_mode must be one of {', '.join(BILLING_MODES)}")
        return v

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class CustomerImportRowResult(BaseModel):
    row: int
    status: str  # created | error
    customer_id: uuid.UUID | None = None
    code: str | None = None
    error: str | None = None


#: Same ceiling as the supplier import: a pilot's outlet list is tens of rows,
#: and anything past this belongs in batches, not one request.
MAX_IMPORT_ROWS = 500


class UpdateCustomerCommand(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    customer_type: str = "household"
    phone: str = Field(default="", max_length=32)
    alternate_phone: str = Field(default="", max_length=32)
    address: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=500)
    billing_mode: str = "credit"
    billing_day: int = Field(default=1, ge=1, le=28)


class DeliveryPlanInput(BaseModel):
    product: str = Field(default="RAW-COW-MILK", max_length=40)
    default_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    quantity_unit: str = Field(default="L", max_length=8)
    #: The agreed selling price. Sent as a string by every client, because it
    #: is money and a float would have already lost by the time it arrived.
    unit_price: Decimal = Field(gt=0)
    effective_from: date | None = None

    # --- the schedule (DEMO-016) ------------------------------------------
    #: Null means ongoing, which is what a standing order usually is.
    effective_to: date | None = None
    #: Seven characters, Monday first. Defaults to every day.
    weekdays: str = Field(default=EVERY_DAY)
    slot: str = Field(default="morning")
    center_id: uuid.UUID | None = None
    #: `{"5": "30.000"}` — thirty litres on Saturday. Sparse by design.
    quantity_overrides: dict[str, Decimal] | None = None

    @field_validator("weekdays")
    @classmethod
    def _seven_days(cls, v: str) -> str:
        try:
            return normalise_weekdays(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("slot")
    @classmethod
    def _known_slot(cls, v: str) -> str:
        if v not in DELIVERY_SLOTS:
            raise ValueError(f"slot must be one of {', '.join(DELIVERY_SLOTS)}")
        return v

    @field_validator("quantity_overrides")
    @classmethod
    def _plausible_overrides(cls, v: dict | None) -> dict | None:
        """Refuse a key that is not a weekday.

        `quantity_for` falls back to the standing quantity for a key it does
        not recognise — which is right at generation time, where the round has
        to go out regardless. It is wrong HERE: a manager typing `{"7": ...}`
        meaning Sunday should be told, not silently given the default every
        week until somebody notices the bill.
        """
        if not v:
            return None
        for key in v:
            if key not in {str(i) for i in range(WEEK)}:
                raise ValueError(f"weekday key {key!r} must be '0' (Monday) to '6' (Sunday)")
        return v


class PausePlanCommand(BaseModel):
    """A holiday. Both ends inclusive; no end means until further notice."""

    paused_from: date
    paused_to: date | None = None


# --- views -------------------------------------------------------------------


class DeliveryPlanView(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    product: str
    default_quantity: Decimal
    quantity_unit: str
    unit_price: Decimal
    currency: str
    effective_from: date
    active: bool

    # --- the schedule (DEMO-016) ------------------------------------------
    effective_to: date | None = None
    weekdays: str = EVERY_DAY
    slot: str = "morning"
    center_id: uuid.UUID | None = None
    quantity_overrides: dict | None = None
    paused_from: date | None = None
    paused_to: date | None = None

    #: A translation KEY for the mask — `schedule.daily`, `schedule.mon_sat`,
    #: `schedule.weekdays`, `schedule.custom`. Never a sentence: the platform
    #: does not decide what a Hindi-speaking manager reads (DEMO-013).
    schedule_key: str = "schedule.daily"
    #: When this plan next delivers, or null if not within the year. The one
    #: thing a plan screen must say that cannot be read off the row (§9).
    next_delivery: date | None = None

    model_config = {"from_attributes": True}


class CustomerView(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    customer_type: str
    phone: str
    alternate_phone: str
    address: str
    notes: str
    status: str
    billing_mode: str
    billing_day: int
    currency: str
    created_at: object
    updated_at: object

    model_config = {"from_attributes": True}


class CustomerContact(BaseModel):
    """A customer as a DRIVER at the gate needs them (P0-MOB-002).

    `CustomerName` plus how to find and reach the household — a driver on an
    unfamiliar round needs the address, and "customer not answering" is solved
    by a phone number, not a support ticket. Still deliberately narrow: no
    balance, no plan, no billing state, because a stop is not a ledger.
    """

    id: uuid.UUID
    code: str
    name: str
    phone: str
    address: str


class CustomerName(BaseModel):
    """Just enough of a customer to label a row somebody else owns.

    Deliberately three fields. A neighbouring module reporting on its own data
    needs a name against an id and nothing else, and handing it the whole
    customer would let a report grow a dependency on a column this module is
    still free to change.
    """

    id: uuid.UUID
    code: str
    name: str


class CustomerPage(BaseModel):
    items: list[CustomerView]
    total: int
    limit: int
    offset: int


class CustomerDetailView(BaseModel):
    customer: CustomerView
    plans: list[DeliveryPlanView]


class CustomerService:
    def __init__(self, session: AsyncSession, audit: AuditService):
        self._session = session
        self._audit = audit

    async def _today(self):
        """Today, as the ORGANIZATION reckons it (DEMO-013 §8).

        Not UTC's today. A report asked for "today" at 04:00 in Bengaluru is
        asking about a day that began four hours ago locally and does not
        start in UTC for another twenty; answering with UTC's date would show
        a dairy manager yesterday's round and call it today.
        """
        from platform_core.core.business_time import business_today
        from platform_core.core.org_context import tenant_timezone

        return business_today(await tenant_timezone(self._session))

    # --- commands ----------------------------------------------------------

    async def create(self, cmd: CreateCustomerCommand, *, actor_id: uuid.UUID) -> Customer:
        tenant_id = require_current_tenant()
        customer = Customer(
            tenant_id=tenant_id,
            code=await next_document_number(
                self._session, tenant_id=tenant_id, doc_type="customer", prefix="CUS"
            ),
            name=cmd.name,
            customer_type=cmd.customer_type,
            phone=cmd.phone,
            alternate_phone=cmd.alternate_phone,
            address=cmd.address,
            notes=cmd.notes,
            billing_mode=cmd.billing_mode,
            billing_day=cmd.billing_day,
            currency=cmd.currency or await tenant_currency(self._session),
        )
        self._session.add(customer)
        await self._session.flush()
        if cmd.plan is not None:
            await self.set_plan(customer.id, cmd.plan, actor_id=actor_id)
        await self._audit.record(
            action="sales.customer.registered",
            resource_type="customer",
            resource_id=customer.id,
            actor_id=actor_id,
            detail={"code": customer.code, "name": customer.name},
        )
        return customer

    async def import_rows(
        self, rows: list[dict[str, Any]], *, actor_id: uuid.UUID
    ) -> list[CustomerImportRowResult]:
        """P0-PILOT-002: the outlet list, loaded the way the farmer list is.

        Rows are validated individually so one bad row cannot fail the batch —
        the same contract as the supplier import. A row may carry an inline
        `plan`, so an outlet arrives with its standing order in one line.
        Every created customer goes through `create()`, which numbers, prices
        and audits it exactly as a hand-entered one.
        """
        if len(rows) > MAX_IMPORT_ROWS:
            raise ConflictError(f"import limited to {MAX_IMPORT_ROWS} rows")
        tenant_id = require_current_tenant()
        results: list[CustomerImportRowResult] = []
        for index, raw in enumerate(rows):
            try:
                cmd = CreateCustomerCommand(**raw)
                # P0-PILOT-003: a re-run of the same file must not mint the
                # outlet twice. Customers have no natural code in the source
                # list, so exact (name, phone) against a live customer is the
                # duplicate signal — surfaced as a row error NAMING the
                # existing code, never a silent skip and never a merge: the
                # operator decides. Flushed rows count, so a duplicate within
                # one batch is caught the same way.
                duplicate = await self._session.scalar(
                    select(Customer).where(
                        Customer.tenant_id == tenant_id,
                        Customer.name == cmd.name,
                        Customer.phone == cmd.phone,
                    )
                )
                if duplicate is not None:
                    raise ConflictError(
                        f"duplicate of existing customer {duplicate.code} ({duplicate.name})"
                    )
                customer = await self.create(cmd, actor_id=actor_id)
                results.append(
                    CustomerImportRowResult(
                        row=index,
                        status="created",
                        customer_id=customer.id,
                        code=customer.code,
                    )
                )
            except Exception as exc:
                results.append(CustomerImportRowResult(row=index, status="error", error=str(exc)))
        return results

    async def update(
        self, customer_id: uuid.UUID, cmd: UpdateCustomerCommand, *, actor_id: uuid.UUID
    ) -> Customer:
        customer = await self.get(customer_id)
        customer.name = cmd.name
        customer.customer_type = cmd.customer_type
        customer.phone = cmd.phone
        customer.alternate_phone = cmd.alternate_phone
        customer.address = cmd.address
        customer.notes = cmd.notes
        customer.billing_mode = cmd.billing_mode
        customer.billing_day = cmd.billing_day
        await self._audit.record(
            action="sales.customer.updated",
            resource_type="customer",
            resource_id=customer.id,
            actor_id=actor_id,
            detail={"code": customer.code},
        )
        return customer

    async def set_status(
        self, customer_id: uuid.UUID, status: str, *, actor_id: uuid.UUID
    ) -> Customer:
        """An end state, not a verb — setting the status twice is not an error."""
        if status not in CUSTOMER_STATUSES:
            raise ConflictError(f"status must be one of {', '.join(CUSTOMER_STATUSES)}")
        customer = await self.get(customer_id)
        customer.status = status
        await self._audit.record(
            action="sales.customer.status_changed",
            resource_type="customer",
            resource_id=customer.id,
            actor_id=actor_id,
            detail={"code": customer.code, "status": status},
        )
        return customer

    async def set_plan(
        self, customer_id: uuid.UUID, plan: DeliveryPlanInput, *, actor_id: uuid.UUID
    ) -> DeliveryPlan:
        """Agree (or re-agree) what this customer takes and at what rate.

        A rate change SUPERSEDES the previous plan rather than editing it: a
        delivery priced last week has to remain explainable, and it points at
        the plan that priced it.

        **Superseding is per SLOT (found by DEMO-035).** It used to match on
        `(customer, product)` alone, which made the model's own documented
        intent impossible to express: `DeliveryPlan` says "a customer taking
        milk twice a day has two plans", and setting an evening plan silently
        deactivated the morning one. A household on a twice-daily round then
        stopped receiving its morning milk because somebody agreed an evening
        rate, with nothing anywhere saying so.

        A plan is stopped deliberately, by `effective_to` or by pausing it —
        never as a side effect of agreeing a different slot.
        """
        customer = await self.get(customer_id)
        tenant_id = require_current_tenant()
        existing = (
            await self._session.scalars(
                select(DeliveryPlan).where(
                    DeliveryPlan.tenant_id == tenant_id,
                    DeliveryPlan.customer_id == customer.id,
                    DeliveryPlan.product == plan.product,
                    DeliveryPlan.slot == plan.slot,
                    DeliveryPlan.active.is_(True),
                )
            )
        ).all()
        for old in existing:
            old.active = False
        effective_from = plan.effective_from or await self._today()
        if plan.effective_to is not None and plan.effective_to < effective_from:
            raise ConflictError("a plan cannot end before it begins")
        row = DeliveryPlan(
            tenant_id=tenant_id,
            customer_id=customer.id,
            product=plan.product,
            default_quantity=plan.default_quantity,
            quantity_unit=plan.quantity_unit,
            unit_price=plan.unit_price,
            currency=customer.currency,
            effective_from=effective_from,
            effective_to=plan.effective_to,
            weekdays=plan.weekdays,
            slot=plan.slot,
            center_id=plan.center_id,
            # Decimals are not JSON, and the column is. Stored as the exact
            # strings they arrived as, which is also how `quantity_for` reads
            # them back — the value never becomes a float in between.
            quantity_overrides=(
                {k: str(v) for k, v in plan.quantity_overrides.items()}
                if plan.quantity_overrides
                else None
            ),
            active=True,
            created_by=actor_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._audit.record(
            action="sales.customer.plan_set",
            resource_type="delivery_plan",
            resource_id=row.id,
            actor_id=actor_id,
            detail={
                "customer": customer.code,
                "product": row.product,
                "slot": row.slot,
                "unit_price": str(row.unit_price),
                "weekdays": row.weekdays,
                "quantity": str(row.default_quantity),
                "effective_from": str(row.effective_from),
                "superseded": [str(old.id) for old in existing],
            },
        )
        return row

    async def pause_plan(
        self, plan_id: uuid.UUID, cmd: PausePlanCommand, *, actor_id: uuid.UUID
    ) -> DeliveryPlan:
        """Send a standing order on holiday (DEMO-016 §7).

        Pausing does NOT deactivate the plan and does not touch a single
        delivery that has already happened: the household is coming back, and
        their August is still their August. It only stops the generator from
        producing new instances inside the window.
        """
        plan = await self.get_plan(plan_id)
        if cmd.paused_to is not None and cmd.paused_to < cmd.paused_from:
            raise ConflictError("a pause cannot end before it begins")
        plan.paused_from = cmd.paused_from
        plan.paused_to = cmd.paused_to
        await self._audit.record(
            action="sales.customer.plan_paused",
            resource_type="delivery_plan",
            resource_id=plan.id,
            actor_id=actor_id,
            detail={"from": str(cmd.paused_from), "to": str(cmd.paused_to or "")},
        )
        return plan

    async def resume_plan(self, plan_id: uuid.UUID, *, actor_id: uuid.UUID) -> DeliveryPlan:
        """Back from holiday.

        Clearing the window rather than setting `paused_to` to yesterday: a
        plan that is running should say it is running, and a reader should not
        have to compare a date against today to find out.

        Generation resumes from the next day the schedule is due — which may
        be today. It does NOT backfill the pause: milk that was not delivered
        is not delivered later, and inventing those rows would put a fortnight
        of holiday on the customer's next bill.
        """
        plan = await self.get_plan(plan_id)
        plan.paused_from = None
        plan.paused_to = None
        await self._audit.record(
            action="sales.customer.plan_resumed",
            resource_type="delivery_plan",
            resource_id=plan.id,
            actor_id=actor_id,
            detail={"plan": str(plan.id)},
        )
        return plan

    async def business_today(self) -> date:
        """The dairy's today, for anything that has to date a plan view."""
        return await self._today()

    async def get_plan(self, plan_id: uuid.UUID) -> DeliveryPlan:
        tenant_id = require_current_tenant()
        plan = await self._session.scalar(
            select(DeliveryPlan).where(
                DeliveryPlan.id == plan_id, DeliveryPlan.tenant_id == tenant_id
            )
        )
        if plan is None:
            raise NotFoundError("delivery plan not found")
        return plan

    # --- queries -----------------------------------------------------------

    async def get(self, customer_id: uuid.UUID) -> Customer:
        tenant_id = require_current_tenant()
        customer = await self._session.scalar(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        )
        if customer is None:
            raise NotFoundError("customer not found")
        return customer

    async def directory(self, customer_ids: set[uuid.UUID]) -> dict[uuid.UUID, CustomerName]:
        """Names for a set of ids, in ONE query (DEMO-015).

        The module boundary says a delivery references a customer by UUID and
        asks this module for anything else. Honoured literally, that turns a
        report of two hundred rows into two hundred lookups — so the shape the
        boundary needs is a batch, and this is it.

        A caller with no ids gets an empty map without touching the database,
        because an `IN ()` is a query asked in order to learn nothing.
        """
        if not customer_ids:
            return {}
        tenant_id = require_current_tenant()
        rows = (
            await self._session.execute(
                select(Customer.id, Customer.code, Customer.name).where(
                    Customer.tenant_id == tenant_id, Customer.id.in_(customer_ids)
                )
            )
        ).all()
        return {row[0]: CustomerName(id=row[0], code=row[1], name=row[2]) for row in rows}

    async def contact_directory(
        self, customer_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, CustomerContact]:
        """`directory`, plus phone and address, in ONE query (P0-MOB-002).

        The batch shape the module boundary needs, exactly as `directory`
        established it: a run view naming its stops asks once for the set,
        never once per stop.
        """
        if not customer_ids:
            return {}
        tenant_id = require_current_tenant()
        rows = (
            await self._session.execute(
                select(
                    Customer.id, Customer.code, Customer.name, Customer.phone, Customer.address
                ).where(Customer.tenant_id == tenant_id, Customer.id.in_(customer_ids))
            )
        ).all()
        return {
            row[0]: CustomerContact(
                id=row[0], code=row[1], name=row[2], phone=row[3], address=row[4]
            )
            for row in rows
        }

    async def active_plan(self, customer_id: uuid.UUID, product: str) -> DeliveryPlan | None:
        tenant_id = require_current_tenant()
        return await self._session.scalar(
            select(DeliveryPlan).where(
                DeliveryPlan.tenant_id == tenant_id,
                DeliveryPlan.customer_id == customer_id,
                DeliveryPlan.product == product,
                DeliveryPlan.active.is_(True),
            )
        )

    async def detail(self, customer_id: uuid.UUID) -> CustomerDetailView:
        # DEMO-012: fetching by ID must respect the scope as well as searching
        # does — otherwise a customer reads any household's record by guessing
        # a UUID. `enforce_customer_scope` answers NOT FOUND for somebody
        # else's id, never FORBIDDEN.
        enforce_customer_scope(customer_id)
        customer = await self.get(customer_id)
        plans = (
            await self._session.scalars(
                select(DeliveryPlan)
                .where(DeliveryPlan.customer_id == customer.id)
                .order_by(DeliveryPlan.active.desc(), DeliveryPlan.effective_from.desc())
            )
        ).all()
        today = await self._today()
        return CustomerDetailView(
            customer=CustomerView.model_validate(customer),
            plans=[self.plan_view(p, today=today) for p in plans],
        )

    @staticmethod
    def plan_view(plan: DeliveryPlan, *, today: date) -> DeliveryPlanView:
        """A plan, plus the two things that are computed rather than stored.

        `schedule_key` and `next_delivery` are derived on every read instead of
        being columns, because both are functions of the row and of today —
        a stored `next_delivery` is a cache that goes stale overnight, silently,
        on the one screen whose whole job is to say when the milk is coming.

        A superseded plan reports no next delivery whatever its dates say. It
        is not going to deliver anything: the generator only reads active ones.
        """
        view = DeliveryPlanView.model_validate(plan)
        view.schedule_key = describe(plan.weekdays)
        view.next_delivery = (
            next_due(
                today,
                weekdays=plan.weekdays,
                effective_from=plan.effective_from,
                effective_to=plan.effective_to,
                paused_from=plan.paused_from,
                paused_to=plan.paused_to,
            )
            if plan.active
            else None
        )
        return view

    async def search(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        customer_type: str | None = None,
        ids: list[uuid.UUID] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> CustomerPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        # DEMO-012: a customer-scoped principal sees exactly one customer.
        scope = enforce_customer_scope(None)
        conditions = [Customer.tenant_id == tenant_id]
        if scope is not None:
            conditions.append(Customer.id == scope)
        if ids:
            # P1-PORTAL-SCALE-001: batch display-name resolution (see the
            # supplier twin). A narrowing on top of the tenant filter — and on
            # top of the customer scope: a household login still resolves only
            # itself.
            conditions.append(Customer.id.in_(ids))
        if q:
            like = f"%{q.lower()}%"
            conditions.append(
                or_(
                    func.lower(Customer.name).like(like),
                    func.lower(Customer.code).like(like),
                    func.lower(Customer.phone).like(like),
                )
            )
        if status:
            conditions.append(Customer.status == status)
        if customer_type:
            conditions.append(Customer.customer_type == customer_type)

        total = await self._session.scalar(
            select(func.count()).select_from(Customer).where(*conditions)
        )
        rows = (
            await self._session.scalars(
                select(Customer)
                .where(*conditions)
                .order_by(Customer.name)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return CustomerPage(
            items=[CustomerView.model_validate(r) for r in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
        )


CreateCustomerCommand.model_rebuild()
