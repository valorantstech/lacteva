"""Logistics module — routes, vehicles, drivers and the daily run (DEMO-034).

The rule this file exists to keep: **a run composes the delivery domain, it
does not restate it.** Every quantity, amount, per-customer outcome and billing
fact on a run view is read from `MilkDelivery` at the moment it is asked for.
Nothing is copied into a `delivery_run` row, so nothing here can disagree with
the deliveries it describes, and completing a run creates no financial event.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.business_time import business_today
from platform_core.core.db import utcnow
from platform_core.core.errors import ConflictError, NotFoundError, ValidationError
from platform_core.core.org_context import tenant_timezone
from platform_core.core.tenancy import require_current_tenant
from platform_core.modules.audit.service import AuditService
from platform_core.modules.business_calendar.service import WorkingDayResolver
from platform_core.modules.customer.service import CustomerService
from platform_core.modules.delivery.generation import RoundScope
from platform_core.modules.delivery.models import DELIVERY_SLOTS
from platform_core.modules.delivery.service import DeliveryService, RouteMembership
from platform_core.modules.logistics.models import (
    OPEN_RUN_STATUSES,
    RUN_STATUSES,
    RUN_TRANSITIONS,
    DeliveryRun,
    Driver,
    Route,
    RouteStop,
    Vehicle,
)

# --- DTOs ------------------------------------------------------------------


class RouteInput(BaseModel):
    code: str = Field(min_length=1, max_length=24)
    name: str = Field(min_length=1, max_length=200)
    center_id: uuid.UUID | None = None
    notes: str = Field(default="", max_length=500)


class RouteView(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    center_id: uuid.UUID | None
    active: bool
    notes: str
    stop_count: int = 0

    model_config = {"from_attributes": True}


class StopView(BaseModel):
    customer_id: uuid.UUID
    position: int
    #: Named here so a screen never has to fetch customers separately. Read
    #: from the customer module through its own model, not joined into it.
    code: str = ""
    name: str = ""


class RouteDetailView(RouteView):
    stops: list[StopView] = []


class VehicleInput(BaseModel):
    registration: str = Field(min_length=1, max_length=32)
    label: str = Field(default="", max_length=120)
    center_id: uuid.UUID | None = None


class VehicleView(BaseModel):
    id: uuid.UUID
    registration: str
    label: str
    center_id: uuid.UUID | None
    active: bool

    model_config = {"from_attributes": True}


class DriverInput(BaseModel):
    code: str = Field(min_length=1, max_length=24)
    full_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default="", max_length=32)
    user_id: uuid.UUID | None = None
    center_id: uuid.UUID | None = None


class DriverView(BaseModel):
    id: uuid.UUID
    code: str
    full_name: str
    phone: str
    user_id: uuid.UUID | None
    center_id: uuid.UUID | None
    active: bool

    model_config = {"from_attributes": True}


class RunInput(BaseModel):
    route_id: uuid.UUID
    #: Omit it and the platform resolves the DAIRY's today. A client that sends
    #: its own date is planning ahead deliberately; a client that sends none
    #: must not get UTC's answer (DEMO-013).
    business_date: date | None = None
    slot: str = "morning"
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None

    @field_validator("slot")
    @classmethod
    def _known_slot(cls, value: str) -> str:
        if value not in DELIVERY_SLOTS:
            raise ValueError(f"slot must be one of {', '.join(DELIVERY_SLOTS)}")
        return value


class RouteStopsInput(BaseModel):
    """The route's stops, in visiting order. The list IS the order."""

    customer_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class RunStatusInput(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str) -> str:
        if value not in RUN_STATUSES:
            raise ValueError(f"status must be one of {', '.join(RUN_STATUSES)}")
        return value


class DriverUserLink(BaseModel):
    """`null` clears the link — a driver who left keeps their record, not a login."""

    user_id: uuid.UUID | None = None


class RunAssignment(BaseModel):
    """Either or both. `None` means "leave it alone", not "clear it"."""

    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None


class RunGenerationView(BaseModel):
    """What generating a run's round did (DEMO-035).

    The delivery domain's own counts, passed through unaltered, plus the route
    facts that say WHICH round they describe. `created == 0` on a second call is
    idempotency holding, not a failure — and `stops` beside `due` is how an
    operator sees that a route of forty households produced twelve deliveries
    because twenty-eight plans were not due today.
    """

    run_id: uuid.UUID
    route_code: str
    business_date: date
    slot: str
    #: Stops on the route — the size of the round somebody planned.
    stops: int
    #: Plans that were actually due for those stops in this slot.
    due: int
    created: int
    already_present: int
    not_due: int
    inactive_customers: int
    skipped_holiday: int


class StopOutcomeInput(BaseModel):
    """What a driver says happened at a stop (P0-MOB-002).

    `cancelled` is deliberately not offered: that status means "recorded in
    error" and is an office correction, not a doorstep outcome. Quantity is
    optional — omitted, the delivery domain uses the plan's standing quantity,
    exactly as the operator round does.
    """

    status: str
    quantity: Decimal | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=300)

    @field_validator("status")
    @classmethod
    def _driver_outcome(cls, value: str) -> str:
        allowed = ("delivered", "skipped", "returned")
        if value not in allowed:
            raise ValueError(f"a driver outcome must be one of {', '.join(allowed)}")
        return value


class RunStopView(BaseModel):
    """A stop, with whatever the delivery domain says happened at it.

    `delivery_status` is `MilkDelivery.status` — this module does not have its
    own per-stop state machine, because the delivery domain already has the
    only one that matters and a second would have to be kept in step.
    """

    customer_id: uuid.UUID
    position: int
    code: str = ""
    name: str = ""
    #: How a driver finds and reaches the household (P0-MOB-002). Read from the
    #: customer module's own contact batch, never joined into it.
    phone: str = ""
    address: str = ""
    delivery_status: str | None = None


class RunView(BaseModel):
    id: uuid.UUID
    route_id: uuid.UUID
    route_code: str = ""
    route_name: str = ""
    business_date: date
    slot: str
    vehicle_id: uuid.UUID | None
    vehicle_registration: str | None = None
    driver_id: uuid.UUID | None
    driver_name: str | None = None
    status: str
    notes: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stops: list[RunStopView] = []

    model_config = {"from_attributes": True}


# --- service ---------------------------------------------------------------


async def scheduled_round_scopes(
    session: AsyncSession, tenant_id: uuid.UUID, day: date
) -> list[RoundScope]:
    """Which routes this dairy has planned for this day (DEMO-036).

    The answer the scheduler is handed, as VALUES — the module that owns routes
    works it out, and the delivery module never learns that routes exist. Same
    shape as DEMO-022's `is_working`, and for the same reason: `logistics`
    depends on `delivery`, so the reverse import would be a cycle.

    **An empty list is the fallback signal**, and it is the honest one: a dairy
    with no routes, only inactive ones, or only empty ones has planned no
    rounds, and the scheduler then generates the whole tenant exactly as it did
    before this function existed. Route adoption stays optional.

    A module-level function rather than a method because the scheduler has no
    request, no audit trail and no actor — it is a read, and constructing a
    service with a null audit to perform it would be furniture.

    Scoped to the tenant explicitly as well as by RLS. The scheduler runs
    inside the tenant's own binding, so the policies filter this anyway; the
    predicate is the defence-in-depth the platform applies everywhere.
    """
    routes = (
        await session.scalars(
            select(Route)
            .where(Route.tenant_id == tenant_id, Route.active.is_(True))
            # Ordered by code so a dairy's rounds are generated in a stable,
            # human-recognisable sequence — and so a log of two runs reads the
            # same way twice.
            .order_by(Route.code)
        )
    ).all()
    if not routes:
        return []

    stops = (
        await session.execute(
            select(RouteStop.route_id, RouteStop.customer_id)
            .where(
                RouteStop.tenant_id == tenant_id,
                RouteStop.route_id.in_([r.id for r in routes]),
            )
            .order_by(RouteStop.route_id, RouteStop.position, RouteStop.created_at)
        )
    ).all()
    by_route: dict[uuid.UUID, set[uuid.UUID]] = {}
    for route_id, customer_id in stops:
        by_route.setdefault(route_id, set()).add(customer_id)

    scopes: list[RoundScope] = []
    for route in routes:
        customers = by_route.get(route.id)
        if not customers:
            # A route with no stops is not a round. Skipped rather than
            # refused: the scheduler is generating every route a dairy has, and
            # one unfinished route must not stop the others going out. The
            # operator-facing endpoint still refuses it loudly (DEMO-035).
            continue
        for slot in DELIVERY_SLOTS:
            scopes.append(
                RoundScope(
                    label=f"{route.code}/{slot}",
                    customer_ids=frozenset(customers),
                    slot=slot,
                    center_id=route.center_id,
                )
            )
    return scopes


async def route_memberships(session: AsyncSession, tenant_id: uuid.UUID) -> list[RouteMembership]:
    """Which households each active route visits (DEMO-037).

    The answer the delivery REPORT is handed, as values — the same arrangement
    as `scheduled_round_scopes`, and for the same reason: the delivery module
    owns `milk_delivery` and must not learn that routes exist.

    Unlike the scheduler's scopes this is per ROUTE rather than per route and
    slot: a report groups a round, and a dairy asking "how did R-01 do?" means
    the route, not its morning half.

    Empty for a dairy with no routes, which is the signal the report reads as
    "no route breakdown to show" — the same fallback shape DEMO-036 uses.
    """
    routes = (
        await session.scalars(
            select(Route)
            .where(Route.tenant_id == tenant_id, Route.active.is_(True))
            .order_by(Route.code)
        )
    ).all()
    if not routes:
        return []

    stops = (
        await session.execute(
            select(RouteStop.route_id, RouteStop.customer_id).where(
                RouteStop.tenant_id == tenant_id,
                RouteStop.route_id.in_([r.id for r in routes]),
            )
        )
    ).all()
    by_route: dict[uuid.UUID, set[uuid.UUID]] = {}
    for route_id, customer_id in stops:
        by_route.setdefault(route_id, set()).add(customer_id)

    return [
        RouteMembership(
            code=route.code,
            name=route.name,
            customer_ids=frozenset(by_route.get(route.id, set())),
        )
        for route in routes
    ]


class LogisticsService:
    """Routes, fleet and runs.

    It holds the customer and delivery SERVICES, not their tables. A stop is a
    `customer_id` and a stop's outcome is the delivery domain's answer; this
    module never selects from `customer` or `milk_delivery`, which is the same
    boundary DEMO-030 was caught crossing and the reason `DeliveryService`
    composes `CustomerService` the same way one line further up the tree.
    """

    def __init__(self, session: AsyncSession, bus, audit: AuditService) -> None:
        self._session = session
        self._customers = CustomerService(session, audit)
        # The bus is threaded through because `DeliveryService` takes one, not
        # because this module publishes: a run changes no delivery and emits no
        # delivery event. Built in `api/deps.py`, the one composition root.
        self._deliveries = DeliveryService(session, bus, audit)

    # --- routes ------------------------------------------------------------

    async def create_route(self, data: RouteInput, *, actor_id: uuid.UUID, audit: AuditService):
        tenant_id = require_current_tenant()
        if await self._session.scalar(
            select(Route.id).where(Route.tenant_id == tenant_id, Route.code == data.code)
        ):
            raise ConflictError(f"route {data.code!r} already exists")

        route = Route(tenant_id=tenant_id, **data.model_dump())
        self._session.add(route)
        await self._session.flush()
        await audit.record(
            action="logistics.route_created",
            resource_type="route",
            resource_id=route.id,
            actor_id=actor_id,
            detail={"code": route.code, "center_id": str(data.center_id or "")},
        )
        return route

    async def list_routes(self, *, active: bool | None = None) -> list[RouteView]:
        tenant_id = require_current_tenant()
        conditions = [Route.tenant_id == tenant_id]
        if active is not None:
            conditions.append(Route.active == active)
        routes = (
            await self._session.scalars(select(Route).where(*conditions).order_by(Route.code))
        ).all()
        counts = await self._stop_counts([r.id for r in routes])
        views = []
        for route in routes:
            view = RouteView.model_validate(route)
            view.stop_count = counts.get(route.id, 0)
            views.append(view)
        return views

    async def _stop_counts(self, route_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not route_ids:
            return {}
        rows = await self._session.execute(
            select(RouteStop.route_id, func.count())
            .where(RouteStop.route_id.in_(route_ids))
            .group_by(RouteStop.route_id)
        )
        return {row[0]: row[1] for row in rows}

    async def get_route(self, route_id: uuid.UUID) -> RouteDetailView:
        route = await self._route(route_id)
        stops = await self._stops(route_id)
        return RouteDetailView(
            **RouteView.model_validate(route).model_dump(exclude={"stop_count"}),
            stop_count=len(stops),
            stops=stops,
        )

    async def set_route_active(
        self, route_id: uuid.UUID, *, active: bool, actor_id: uuid.UUID, audit: AuditService
    ) -> RouteView:
        route = await self._route(route_id)
        if route.active != active:
            route.active = active
            await audit.record(
                action="logistics.route_updated",
                resource_type="route",
                resource_id=route.id,
                actor_id=actor_id,
                detail={"active": active},
            )
        return RouteView.model_validate(route)

    async def set_stops(
        self,
        route_id: uuid.UUID,
        customer_ids: list[uuid.UUID],
        *,
        actor_id: uuid.UUID,
        audit: AuditService,
    ) -> RouteDetailView:
        """Replace the route's stops with this ordered list.

        Replacement rather than add/remove endpoints, because the order IS the
        payload: a screen that lets an operator drag stops into sequence sends
        the sequence, and two endpoints would need a third to reorder.

        A customer named twice is refused rather than silently de-duplicated —
        a round that visits the same household twice is a mistake somebody
        should see, and the unique constraint would refuse it anyway.
        """
        tenant_id = require_current_tenant()
        route = await self._route(route_id)

        if len(set(customer_ids)) != len(customer_ids):
            raise ValidationError("a customer appears more than once on this route")

        # Every stop must be a customer of THIS tenant. Read through the
        # customer model rather than trusting the caller's ids: a stop
        # pointing at another tenant's customer would be a cross-tenant
        # reference this module could not otherwise refuse.
        if customer_ids:
            known = await self._customers.directory(set(customer_ids))
            unknown = [str(c) for c in customer_ids if c not in known]
            if unknown:
                raise NotFoundError(f"unknown customer(s): {', '.join(sorted(unknown))}")

        existing = (
            await self._session.scalars(select(RouteStop).where(RouteStop.route_id == route_id))
        ).all()
        for stop in existing:
            await self._session.delete(stop)
        await self._session.flush()

        for position, customer_id in enumerate(customer_ids, start=1):
            self._session.add(
                RouteStop(
                    tenant_id=tenant_id,
                    route_id=route_id,
                    customer_id=customer_id,
                    position=position,
                )
            )
        await self._session.flush()

        await audit.record(
            action="logistics.route_stops_set",
            resource_type="route",
            resource_id=route.id,
            actor_id=actor_id,
            detail={"stops": len(customer_ids)},
        )
        stops = await self._stops(route_id)
        return RouteDetailView(
            **RouteView.model_validate(route).model_dump(exclude={"stop_count"}),
            stop_count=len(stops),
            stops=stops,
        )

    async def _stops(self, route_id: uuid.UUID) -> list[StopView]:
        rows = (
            await self._session.scalars(
                select(RouteStop)
                .where(RouteStop.route_id == route_id)
                # `position, created_at` — position is not unique on purpose
                # (see the model), so the tiebreak has to be deterministic.
                .order_by(RouteStop.position, RouteStop.created_at)
            )
        ).all()
        # One batch call for the names, the shape `directory` exists to serve.
        named = await self._customers.directory({r.customer_id for r in rows})
        return [
            StopView(
                customer_id=r.customer_id,
                position=r.position,
                code=named[r.customer_id].code if r.customer_id in named else "",
                name=named[r.customer_id].name if r.customer_id in named else "",
            )
            for r in rows
        ]

    async def _route(self, route_id: uuid.UUID) -> Route:
        route = await self._session.scalar(
            select(Route).where(Route.tenant_id == require_current_tenant(), Route.id == route_id)
        )
        if route is None:
            # Another tenant's route is a 404, never a 403 — the platform's
            # rule, and the reason a probe cannot enumerate what exists.
            raise NotFoundError("route not found")
        return route

    # --- fleet -------------------------------------------------------------

    async def create_vehicle(self, data: VehicleInput, *, actor_id: uuid.UUID, audit: AuditService):
        tenant_id = require_current_tenant()
        if await self._session.scalar(
            select(Vehicle.id).where(
                Vehicle.tenant_id == tenant_id, Vehicle.registration == data.registration
            )
        ):
            raise ConflictError(f"vehicle {data.registration!r} already exists")
        vehicle = Vehicle(tenant_id=tenant_id, **data.model_dump())
        self._session.add(vehicle)
        await self._session.flush()
        await audit.record(
            action="logistics.vehicle_created",
            resource_type="vehicle",
            resource_id=vehicle.id,
            actor_id=actor_id,
            detail={"registration": vehicle.registration},
        )
        return vehicle

    async def list_vehicles(self, *, active: bool | None = None) -> list[VehicleView]:
        conditions = [Vehicle.tenant_id == require_current_tenant()]
        if active is not None:
            conditions.append(Vehicle.active == active)
        rows = (
            await self._session.scalars(
                select(Vehicle).where(*conditions).order_by(Vehicle.registration)
            )
        ).all()
        return [VehicleView.model_validate(v) for v in rows]

    async def create_driver(self, data: DriverInput, *, actor_id: uuid.UUID, audit: AuditService):
        tenant_id = require_current_tenant()
        if await self._session.scalar(
            select(Driver.id).where(Driver.tenant_id == tenant_id, Driver.code == data.code)
        ):
            raise ConflictError(f"driver {data.code!r} already exists")
        driver = Driver(tenant_id=tenant_id, **data.model_dump())
        self._session.add(driver)
        await self._session.flush()
        await audit.record(
            action="logistics.driver_created",
            resource_type="driver",
            resource_id=driver.id,
            actor_id=actor_id,
            # The phone is not recorded in the audit detail: an audit trail is
            # read by more people than the record it describes.
            detail={"code": driver.code, "has_login": data.user_id is not None},
        )
        return driver

    async def list_drivers(self, *, active: bool | None = None) -> list[DriverView]:
        conditions = [Driver.tenant_id == require_current_tenant()]
        if active is not None:
            conditions.append(Driver.active == active)
        rows = (
            await self._session.scalars(select(Driver).where(*conditions).order_by(Driver.code))
        ).all()
        return [DriverView.model_validate(d) for d in rows]

    # --- runs --------------------------------------------------------------

    async def create_run(
        self, data: RunInput, *, actor_id: uuid.UUID, audit: AuditService
    ) -> RunView:
        """Plan one route's round for one of the dairy's own days.

        The business date comes from the ORGANIZATION's timezone when the
        client omits it. A phone in Nairobi and a browser in Delhi asking "make
        today's run" must both get the dairy's today, not their own.
        """
        tenant_id = require_current_tenant()
        route = await self._route(data.route_id)
        if not route.active:
            raise ConflictError("route is not active")

        timezone = await tenant_timezone(self._session, tenant_id)
        business_date = data.business_date or business_today(timezone)

        # The one working-day answer (DEMO-022), asked at the route's centre.
        # Generation already skips a non-working day; a run that could be
        # planned on one would disagree with the round it describes.
        resolver = WorkingDayResolver(self._session, tenant_id, business_date)
        if not await resolver.is_working(route.center_id):
            raise ConflictError(f"{business_date.isoformat()} is not a working day for this route")

        await self._assert_assignable(data.vehicle_id, data.driver_id)

        conflict = ConflictError(
            f"a {data.slot} run for this route already exists on {business_date.isoformat()}"
        )
        # The ordinary case: somebody already made today's run and this caller
        # wants a clear answer rather than a database error.
        if await self._session.scalar(
            select(DeliveryRun.id).where(
                DeliveryRun.tenant_id == tenant_id,
                DeliveryRun.route_id == route.id,
                DeliveryRun.business_date == business_date,
                DeliveryRun.slot == data.slot,
            )
        ):
            raise conflict

        run = DeliveryRun(
            tenant_id=tenant_id,
            route_id=route.id,
            business_date=business_date,
            slot=data.slot,
            vehicle_id=data.vehicle_id,
            driver_id=data.driver_id,
            created_by=actor_id,
        )
        # The RACE is what the constraint is for, and the savepoint is what
        # lets this transaction survive losing it — a failed flush without one
        # poisons the session, which is the defect DEMO-025 found. The insert
        # goes INSIDE `begin_nested`, not merely the flush.
        #
        # Matching on the constraint NAME would be a PostgreSQL habit: SQLite
        # reports `UNIQUE constraint failed: delivery_run.tenant_id, …` and
        # names no constraint at all. `uq_delivery_run_route_date_slot` is the
        # only unique constraint on this table, so an IntegrityError here has
        # exactly one meaning on either engine.
        try:
            async with self._session.begin_nested():
                self._session.add(run)
                await self._session.flush()
        except IntegrityError as exc:
            raise conflict from exc

        await audit.record(
            action="logistics.run_created",
            resource_type="delivery_run",
            resource_id=run.id,
            actor_id=actor_id,
            detail={
                "route": route.code,
                "business_date": business_date.isoformat(),
                "slot": data.slot,
            },
        )
        return await self._run_view(run)

    async def assign(
        self,
        run_id: uuid.UUID,
        data: RunAssignment,
        *,
        actor_id: uuid.UUID,
        audit: AuditService,
    ) -> RunView:
        run = await self._run(run_id)
        if run.status not in OPEN_RUN_STATUSES:
            raise ConflictError(f"a {run.status} run cannot be reassigned")

        await self._assert_assignable(data.vehicle_id, data.driver_id)
        changed: dict[str, str] = {}
        if data.vehicle_id is not None and data.vehicle_id != run.vehicle_id:
            run.vehicle_id = data.vehicle_id
            changed["vehicle_id"] = str(data.vehicle_id)
        if data.driver_id is not None and data.driver_id != run.driver_id:
            run.driver_id = data.driver_id
            changed["driver_id"] = str(data.driver_id)

        if changed:
            await audit.record(
                action="logistics.run_assigned",
                resource_type="delivery_run",
                resource_id=run.id,
                actor_id=actor_id,
                detail=changed,
            )
        return await self._run_view(run)

    async def set_run_status(
        self, run_id: uuid.UUID, status: str, *, actor_id: uuid.UUID, audit: AuditService
    ) -> RunView:
        """Move a run through its life, with CAS rather than a read-then-write.

        `UPDATE … WHERE status = <expected>` and a rowcount check — the
        platform's concurrency idiom, portable to the SQLite test stack. Two
        operators tapping "complete" at the same moment produce one transition
        and one refusal, not two audit entries claiming the same change.
        """
        run = await self._run(run_id)
        previous = run.status
        allowed = RUN_TRANSITIONS.get(previous, set())
        if status not in allowed:
            raise ConflictError(
                f"a {previous} run cannot become {status}"
                + (f"; allowed: {', '.join(sorted(allowed))}" if allowed else " (terminal)")
            )

        # BR-0028. A round that goes out without a driver and a vehicle is a
        # round nobody can be asked about afterwards. This is the guarantee
        # that makes an `assigned` STATUS unnecessary: assignment is two
        # columns, and starting is what checks them.
        if status == "in_progress" and (run.driver_id is None or run.vehicle_id is None):
            raise ConflictError("a run needs both a driver and a vehicle before it can start")

        values: dict[str, object] = {"status": status, "updated_at": utcnow()}
        if status == "in_progress":
            values["started_at"] = utcnow()
        if status in ("completed", "cancelled"):
            values["finished_at"] = utcnow()

        result = await self._session.execute(
            update(DeliveryRun)
            .where(
                DeliveryRun.id == run.id,
                DeliveryRun.tenant_id == run.tenant_id,
                DeliveryRun.status == previous,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise ConflictError("the run changed while this transition was being applied")

        await self._session.refresh(run)
        await audit.record(
            action="logistics.run_status_changed",
            resource_type="delivery_run",
            resource_id=run.id,
            actor_id=actor_id,
            detail={"from": previous, "to": status},
        )
        return await self._run_view(run)

    async def generate_for_run(
        self, run_id: uuid.UUID, *, actor_id: uuid.UUID, audit: AuditService
    ) -> RunGenerationView:
        """Generate the deliveries this run's route is for (DEMO-035).

        The call that makes the route layer load-bearing rather than
        descriptive. Everything it does is a composition of things that already
        existed:

        * the run supplies the route, the slot and the DAIRY's business date;
        * the route supplies the ordered households;
        * the delivery domain supplies the round — quantity from the plan, rate
          from the plan, `scheduled` status, and the ON CONFLICT that makes a
          re-run a no-op.

        This module computes no quantity, no price and no date arithmetic. It
        names a set of customers and asks the module that owns deliveries.
        """
        tenant_id = require_current_tenant()
        run = await self._run(run_id)
        route = await self._route(run.route_id)

        if not route.active:
            raise ConflictError("route is not active")
        if run.status in ("completed", "cancelled"):
            # Generating into a closed round would add work to a day somebody
            # has already signed off.
            raise ConflictError(f"a {run.status} run cannot generate deliveries")

        stops = await self._stops(route.id)
        if not stops:
            # A route with no stops is not a round. Refused rather than
            # returning a cheerful zero, because "generated 0 of 0" reads like
            # success to whoever is waiting for a van.
            raise ConflictError("route has no stops to generate for")

        # The one working-day answer (DEMO-022), asked at the route's centre.
        # `create_run` already checked this, and it is checked AGAIN here: a
        # holiday can be declared between planning a run and generating it, and
        # the work order is explicit that nothing generates on a non-working
        # day.
        resolver = WorkingDayResolver(self._session, tenant_id, run.business_date)
        if not await resolver.is_working(route.center_id):
            raise ConflictError(
                f"{run.business_date.isoformat()} is not a working day for this route"
            )

        result = await self._deliveries.generate_for_customers(
            day=run.business_date,
            customer_ids={s.customer_id for s in stops},
            slot=run.slot,
            actor_id=actor_id,
            # Handed the resolver as a callable, the way generation already
            # takes it — this module gains no dependency on either calendar.
            is_working=resolver.is_working,
            reference=f"route:{route.code}",
        )

        await audit.record(
            action="logistics.run_generated",
            resource_type="delivery_run",
            resource_id=run.id,
            actor_id=actor_id,
            detail={
                "route": route.code,
                "business_date": run.business_date.isoformat(),
                "slot": run.slot,
                "stops": len(stops),
                "created": result.created,
                "already_present": result.already_present,
            },
        )

        return RunGenerationView(
            run_id=run.id,
            route_code=route.code,
            business_date=run.business_date,
            slot=run.slot,
            stops=len(stops),
            due=result.due,
            created=result.created,
            already_present=result.already_present,
            not_due=result.not_due,
            inactive_customers=result.inactive_customers,
            skipped_holiday=result.skipped_holiday,
        )

    async def list_runs(
        self,
        *,
        business_date: date | None = None,
        route_id: uuid.UUID | None = None,
        status: str | None = None,
        driver_id: uuid.UUID | None = None,
    ) -> list[RunView]:
        tenant_id = require_current_tenant()
        conditions = [DeliveryRun.tenant_id == tenant_id]
        if business_date is None:
            business_date = business_today(await tenant_timezone(self._session, tenant_id))
        conditions.append(DeliveryRun.business_date == business_date)
        if route_id is not None:
            conditions.append(DeliveryRun.route_id == route_id)
        if status is not None:
            conditions.append(DeliveryRun.status == status)
        if driver_id is not None:
            conditions.append(DeliveryRun.driver_id == driver_id)

        runs = (
            await self._session.scalars(
                select(DeliveryRun).where(*conditions).order_by(DeliveryRun.created_at)
            )
        ).all()
        return [await self._run_view(r, with_stops=False) for r in runs]

    async def get_run(self, run_id: uuid.UUID) -> RunView:
        return await self._run_view(await self._run(run_id))

    async def _run(self, run_id: uuid.UUID) -> DeliveryRun:
        run = await self._session.scalar(
            select(DeliveryRun).where(
                DeliveryRun.tenant_id == require_current_tenant(), DeliveryRun.id == run_id
            )
        )
        if run is None:
            raise NotFoundError("delivery run not found")
        return run

    # --- the driver's own surface (P0-MOB-001/002) --------------------------
    #
    # Everything below is scoped to the caller's OWN driver profile, resolved
    # from their user id — never from a client-supplied driver id. Another
    # driver's run is a 404, never a 403, exactly as another tenant's is: a
    # probe must not learn that the run exists.

    async def link_driver_user(
        self,
        driver_id: uuid.UUID,
        user_id: uuid.UUID | None,
        *,
        actor_id: uuid.UUID,
        audit: AuditService,
    ) -> DriverView:
        """Give a driver a login, or take it away (P0-MOB-001).

        One login drives at most one active driver per dairy. Without that
        rule, "my runs" would be ambiguous the day a user was linked twice —
        enforced here rather than by a schema constraint because the column
        predates this milestone and NULLs (drivers without logins) are the
        common case a partial unique index would have to dance around.
        """
        tenant_id = require_current_tenant()
        driver = await self._session.scalar(
            select(Driver).where(Driver.tenant_id == tenant_id, Driver.id == driver_id)
        )
        if driver is None:
            raise NotFoundError("driver not found")
        if user_id is not None:
            already = await self._session.scalar(
                select(Driver.code).where(
                    Driver.tenant_id == tenant_id,
                    Driver.user_id == user_id,
                    Driver.id != driver_id,
                    Driver.active.is_(True),
                )
            )
            if already:
                raise ConflictError(f"that login already drives as {already!r}")
        previous = driver.user_id
        driver.user_id = user_id
        await audit.record(
            action="logistics.driver_user_linked",
            resource_type="driver",
            resource_id=driver.id,
            actor_id=actor_id,
            detail={
                "code": driver.code,
                "linked": user_id is not None,
                "changed": str(previous) != str(user_id),
            },
        )
        return DriverView.model_validate(driver)

    async def driver_for_user(self, user_id: uuid.UUID) -> Driver | None:
        """The caller's own driver profile, or None when the login drives nobody."""
        return await self._session.scalar(
            select(Driver).where(
                Driver.tenant_id == require_current_tenant(),
                Driver.user_id == user_id,
                Driver.active.is_(True),
            )
        )

    async def _my_driver(self, user_id: uuid.UUID) -> Driver:
        driver = await self.driver_for_user(user_id)
        if driver is None:
            # The clear empty state the app renders: the login exists and holds
            # the permission, but no driver profile is linked to it yet.
            raise NotFoundError("no driver profile is linked to this login")
        return driver

    async def my_runs(self, *, user_id: uuid.UUID) -> list[RunView]:
        """Today's runs for the caller's own driver profile — the DAIRY's today.

        Full views including stops: a driver has one or two runs, and the round
        IS the stops. An unlinked login gets an empty list rather than an
        error, because "nothing assigned" and "not a driver yet" are both
        states the screen has to render calmly; `/drivers/me` is how the app
        tells them apart.
        """
        driver = await self.driver_for_user(user_id)
        if driver is None:
            return []
        tenant_id = require_current_tenant()
        today = business_today(await tenant_timezone(self._session, tenant_id))
        runs = (
            await self._session.scalars(
                select(DeliveryRun)
                .where(
                    DeliveryRun.tenant_id == tenant_id,
                    DeliveryRun.driver_id == driver.id,
                    DeliveryRun.business_date == today,
                )
                .order_by(DeliveryRun.slot, DeliveryRun.created_at)
            )
        ).all()
        return [await self._run_view(run) for run in runs]

    async def _my_run(self, run_id: uuid.UUID, *, user_id: uuid.UUID) -> DeliveryRun:
        """The run, if and only if it is assigned to the caller's own driver."""
        driver = await self._my_driver(user_id)
        run = await self._session.scalar(
            select(DeliveryRun).where(
                DeliveryRun.tenant_id == require_current_tenant(),
                DeliveryRun.id == run_id,
                DeliveryRun.driver_id == driver.id,
            )
        )
        if run is None:
            # Not distinguishable from "does not exist" on purpose.
            raise NotFoundError("delivery run not found")
        return run

    async def start_my_run(
        self, run_id: uuid.UUID, *, user_id: uuid.UUID, audit: AuditService
    ) -> RunView:
        """planned → in_progress, for the caller's own run.

        Composes the existing transition — CAS, BR-0028's driver-and-vehicle
        guard, the audit entry — after the ownership check. No second state
        machine.
        """
        run = await self._my_run(run_id, user_id=user_id)
        return await self.set_run_status(run.id, "in_progress", actor_id=user_id, audit=audit)

    async def complete_my_run(
        self, run_id: uuid.UUID, *, user_id: uuid.UUID, audit: AuditService
    ) -> RunView:
        """in_progress → completed, for the caller's own run."""
        run = await self._my_run(run_id, user_id=user_id)
        return await self.set_run_status(run.id, "completed", actor_id=user_id, audit=audit)

    async def record_stop_outcome(
        self,
        run_id: uuid.UUID,
        customer_id: uuid.UUID,
        outcome: StopOutcomeInput,
        *,
        user_id: uuid.UUID,
        audit: AuditService,
    ) -> RunStopView:
        """What happened at one stop, said by the driver who was there.

        The narrow door that makes the broad `sales.delivery.record` grant
        unnecessary for a driver: the run must be the caller's own and OPEN,
        the customer must be ON the route, the date and slot are the RUN's —
        and then the delivery domain records it exactly as it records the
        operator's round, filling in a generated row rather than colliding
        with it. This module still computes no quantity, no price and no date.
        """
        run = await self._my_run(run_id, user_id=user_id)
        if run.status not in OPEN_RUN_STATUSES:
            raise ConflictError(f"a {run.status} run cannot record outcomes")

        on_route = await self._session.scalar(
            select(RouteStop.id).where(
                RouteStop.tenant_id == run.tenant_id,
                RouteStop.route_id == run.route_id,
                RouteStop.customer_id == customer_id,
            )
        )
        if on_route is None:
            raise NotFoundError("that customer is not a stop on this run")

        from platform_core.modules.delivery.service import RecordDeliveryCommand

        delivery = await self._deliveries.record(
            RecordDeliveryCommand(
                customer_id=customer_id,
                delivery_date=run.business_date,
                slot=run.slot,
                status=outcome.status,
                quantity=outcome.quantity,
                notes=outcome.notes,
            ),
            actor_id=user_id,
        )

        contacts = await self._customers.contact_directory({customer_id})
        contact = contacts.get(customer_id)
        position = await self._session.scalar(
            select(RouteStop.position).where(RouteStop.id == on_route)
        )
        return RunStopView(
            customer_id=customer_id,
            position=position or 0,
            code=contact.code if contact else "",
            name=contact.name if contact else "",
            phone=contact.phone if contact else "",
            address=contact.address if contact else "",
            delivery_status=delivery.status,
        )

    async def _assert_assignable(
        self, vehicle_id: uuid.UUID | None, driver_id: uuid.UUID | None
    ) -> None:
        """Both must exist, belong to this tenant, and be active.

        Refusing an inactive one here rather than at the point of departure is
        deliberate: a retired van assigned in the evening is discovered at six
        the next morning by the person who cannot drive it.
        """
        tenant_id = require_current_tenant()
        if vehicle_id is not None:
            vehicle = await self._session.scalar(
                select(Vehicle).where(Vehicle.tenant_id == tenant_id, Vehicle.id == vehicle_id)
            )
            if vehicle is None:
                raise NotFoundError("vehicle not found")
            if not vehicle.active:
                raise ConflictError("vehicle is not active")
        if driver_id is not None:
            driver = await self._session.scalar(
                select(Driver).where(Driver.tenant_id == tenant_id, Driver.id == driver_id)
            )
            if driver is None:
                raise NotFoundError("driver not found")
            if not driver.active:
                raise ConflictError("driver is not active")

    async def _run_view(self, run: DeliveryRun, *, with_stops: bool = True) -> RunView:
        """Everything a run shows, composed at read time.

        Nothing below is stored on the run. The stop list is the ROUTE's, and
        each stop's outcome is the DELIVERY domain's — so a delivery recorded
        after this run started shows up the next time somebody looks, and a run
        can never carry a stale copy of what happened.
        """
        route = await self._session.get(Route, run.route_id)
        vehicle = await self._session.get(Vehicle, run.vehicle_id) if run.vehicle_id else None
        driver = await self._session.get(Driver, run.driver_id) if run.driver_id else None

        stops: list[RunStopView] = []
        if with_stops:
            route_stops = await self._stops(run.route_id)
            outcomes = await self._deliveries.status_by_customer(
                [s.customer_id for s in route_stops], run.business_date, run.slot
            )
            # One batch for how to find and reach each household (P0-MOB-002),
            # through the module that owns customers — never a join, never a
            # query per stop.
            contacts = await self._customers.contact_directory({s.customer_id for s in route_stops})
            stops = [
                RunStopView(
                    customer_id=s.customer_id,
                    position=s.position,
                    code=s.code,
                    name=s.name,
                    phone=contacts[s.customer_id].phone if s.customer_id in contacts else "",
                    address=contacts[s.customer_id].address if s.customer_id in contacts else "",
                    delivery_status=outcomes.get(s.customer_id),
                )
                for s in route_stops
            ]

        return RunView(
            id=run.id,
            route_id=run.route_id,
            route_code=route.code if route else "",
            route_name=route.name if route else "",
            business_date=run.business_date,
            slot=run.slot,
            vehicle_id=run.vehicle_id,
            vehicle_registration=vehicle.registration if vehicle else None,
            driver_id=run.driver_id,
            driver_name=driver.full_name if driver else None,
            status=run.status,
            notes=run.notes,
            started_at=run.started_at,
            finished_at=run.finished_at,
            stops=stops,
        )
