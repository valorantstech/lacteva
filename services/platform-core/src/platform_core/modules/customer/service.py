"""Customer application service (DEMO-009 / CMA.SLS.02)."""

import uuid
from datetime import date
from decimal import Decimal

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
        """
        customer = await self.get(customer_id)
        tenant_id = require_current_tenant()
        existing = (
            await self._session.scalars(
                select(DeliveryPlan).where(
                    DeliveryPlan.tenant_id == tenant_id,
                    DeliveryPlan.customer_id == customer.id,
                    DeliveryPlan.product == plan.product,
                    DeliveryPlan.active.is_(True),
                )
            )
        ).all()
        for old in existing:
            old.active = False
        row = DeliveryPlan(
            tenant_id=tenant_id,
            customer_id=customer.id,
            product=plan.product,
            default_quantity=plan.default_quantity,
            quantity_unit=plan.quantity_unit,
            unit_price=plan.unit_price,
            currency=customer.currency,
            effective_from=plan.effective_from or await self._today(),
            active=True,
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
                "unit_price": str(row.unit_price),
            },
        )
        return row

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
        return CustomerDetailView(
            customer=CustomerView.model_validate(customer),
            plans=[DeliveryPlanView.model_validate(p) for p in plans],
        )

    async def search(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        customer_type: str | None = None,
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
