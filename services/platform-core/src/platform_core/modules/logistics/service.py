"""Logistics module — routes, vehicles, drivers and the daily run (DEMO-034).

The rule this file exists to keep: **a run composes the delivery domain, it
does not restate it.** Every quantity, amount, per-customer outcome and billing
fact on a run view is read from `MilkDelivery` at the moment it is asked for.
Nothing is copied into a `delivery_run` row, so nothing here can disagree with
the deliveries it describes, and completing a run creates no financial event.
"""

import uuid
from datetime import date, datetime

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
from platform_core.modules.delivery.models import DELIVERY_SLOTS
from platform_core.modules.delivery.service import DeliveryService
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


class RunAssignment(BaseModel):
    """Either or both. `None` means "leave it alone", not "clear it"."""

    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None


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
            stops = [
                RunStopView(
                    customer_id=s.customer_id,
                    position=s.position,
                    code=s.code,
                    name=s.name,
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
