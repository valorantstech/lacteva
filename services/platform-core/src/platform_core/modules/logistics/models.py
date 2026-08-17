"""Logistics module — the physical layer under a delivery round (DEMO-034).

CAP-0003 `MCL.RTE.01` (Collection Scheduling & Route Planning) and
`MCL.LGX.01` (Transport & Carrier Management); consumed by CAP-0006
`CMA.DST.01` (Distribution & Fulfillment).

**A route is an operational concept, not a financial one.** Nothing here holds
money, quantities, balances or billing state. The delivery domain remains the
single source of truth for what was delivered and what it is worth; a run
COMPOSES `MilkDelivery` rows by customer and business date and never writes
one. That boundary is the whole design.

**Vehicles and drivers are direction-neutral on purpose.** `CMA.DST.01` depends
on `MCL.LGX.01` as "transport capability, *shared with collection*" — so a
tanker that fetches milk in the morning and a van that delivers it in the
afternoon are the same kind of thing to this module. A delivery-only vehicle
table would contradict the capability register on the day it shipped, and a
collection route later would need a second one.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

#: A run's life, deliberately three states and a cancellation — the same
#: judgement `DeliveryGenerationRun` made, and for the same reason.
#:
#: **`assigned` is deliberately absent.** A run with a driver and a vehicle is
#: assigned; that is a fact about two columns, readable at a glance and
#: impossible to disagree with itself. A status that repeats it is a second
#: copy of the same truth, and the two drift the first time somebody clears a
#: driver without moving the status back. What a dairy actually needs is the
#: guarantee that a run cannot START unassigned — which is a guard (BR-0028),
#: not a state.
RUN_STATUSES = ("planned", "in_progress", "completed", "cancelled")

#: Which transitions are legal. `completed` and `cancelled` are terminal: a
#: round that has been closed is a record of a day, and reopening it would let
#: this module disagree with the deliveries it describes.
RUN_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

#: Runs that are still work. Used to answer "is this route already out today?"
OPEN_RUN_STATUSES = ("planned", "in_progress")


class Route(Base, IdMixin):
    """A named round: which customers are visited, in what order.

    Owned by a centre when a dairy runs more than one, and by the organization
    at large otherwise — the same nullable `center_id` convention
    `DeliveryPlan` already uses, so the two agree about what "no centre" means.
    """

    __tablename__ = "route"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_route_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(200))
    #: Null means the organization at large, exactly as on `DeliveryPlan`.
    center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    #: Retired rather than deleted: yesterday's runs still point at it.
    active: Mapped[bool] = mapped_column(default=True, index=True)
    notes: Mapped[str] = mapped_column(String(500), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RouteStop(Base, IdMixin):
    """One customer's place on a route.

    Membership and order in one row, the shape `SupplierCenterAssignment`
    already uses for "this party belongs to that place", plus a `position`.

    **Uniqueness is on the customer, not the position.** One customer cannot be
    on the same route twice — that is the constraint a duplicate-association
    race must lose to. Position is deliberately *not* unique: making it unique
    turns "swap stop 3 and stop 4" into a dance around the constraint, and the
    only cost of allowing a tie is that two stops need a tiebreak, which
    `position, created_at` supplies deterministically.
    """

    __tablename__ = "route_stop"
    __table_args__ = (
        UniqueConstraint("route_id", "customer_id", name="uq_route_stop_customer"),
        Index("ix_route_stop_order", "tenant_id", "route_id", "position"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    route_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    #: By UUID only. This module never queries the customer module's tables.
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Vehicle(Base, IdMixin):
    """A vehicle a dairy uses to move milk, in either direction.

    No capacity, no odometer, no maintenance and no fuel: `MCL.LGX.02` covers
    fleet utilization and this milestone deliberately does not. Capacity
    without load planning is a column nobody reads, and the work order's
    boundaries name fleet management as a future capability.
    """

    __tablename__ = "vehicle"
    __table_args__ = (
        UniqueConstraint("tenant_id", "registration", name="uq_vehicle_tenant_registration"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    #: The plate. What a dairy actually calls the vehicle.
    registration: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    active: Mapped[bool] = mapped_column(default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Driver(Base, IdMixin):
    """Somebody who drives a round.

    **`user_id` is nullable and that is the point.** A dairy's roundsman often
    has a platform login — `SALES_OFFICER` is described in the permission
    register as "the person who runs the milk round" — and a hired tanker
    driver often does not. Requiring an account would mean either inventing
    logins for contractors or being unable to record who drove.

    No payroll, no attendance, no licence expiry. Those are named as future
    capabilities and none of them is needed to answer "who took the round out
    this morning?".
    """

    __tablename__ = "driver"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_driver_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(24), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(32), default="")
    #: The platform account this driver signs in with, when they have one.
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    active: Mapped[bool] = mapped_column(default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeliveryRun(Base, IdMixin):
    """One route, going out once, on one of the dairy's own days.

    **The unique constraint is the idempotency guard**, in the database rather
    than in Python: two operators tapping "start today's run" at the same
    moment produce one row and one loser, the same way
    `uq_generation_run_tenant_date` and `uq_delivery_customer_date_slot`
    already work. `slot` is part of it because a dairy that delivers morning
    and evening runs the same route twice a day, and those are two rounds.

    **It holds no milk and no money.** Quantities, amounts, statuses per
    customer and billing all live on `MilkDelivery`, which this composes by
    customer and business date. Completing a run creates nothing.
    """

    __tablename__ = "delivery_run"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "route_id",
            "business_date",
            "slot",
            name="uq_delivery_run_route_date_slot",
        ),
        Index("ix_delivery_run_day", "tenant_id", "business_date", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    route_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    #: The DAIRY's date, resolved from the organization's timezone — never
    #: UTC's. Two tenants running the same instant can legitimately hold
    #: different dates here, and that is the point (DEMO-013).
    business_date: Mapped[date] = mapped_column(Date, index=True)
    #: Which half of the day. The same vocabulary `MilkDelivery` uses.
    slot: Mapped[str] = mapped_column(String(10), default="morning")

    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="planned", index=True)
    notes: Mapped[str] = mapped_column(String(500), default="")

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
