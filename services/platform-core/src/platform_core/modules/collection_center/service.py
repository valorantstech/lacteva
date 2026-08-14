"""Collection Center module — application service (facility lifecycle only)."""

import uuid
from datetime import date, time
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.tenancy import require_current_tenant
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.collection_center.models import (
    CENTER_STATUSES,
    CalendarEntry,
    CollectionCenter,
    CollectionCenterConfig,
    OperatingWindow,
)
from platform_core.modules.organization.models import Branch

# archived is terminal; the three live states move freely between each other.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "inactive": {"active", "maintenance", "archived"},
    "active": {"inactive", "maintenance", "archived"},
    "maintenance": {"active", "inactive", "archived"},
    "archived": set(),
}


class CreateCenterCommand(BaseModel):
    branch_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
    #: DEMO-014: NULL means "my organization's clock", which is what almost
    #: every centre means. A value here is a deliberate override for a
    #: cooperative that spans a border.
    timezone: str | None = None


class UpdateCenterCommand(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)


class OperatingWindowInput(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    opens: time
    closes: time

    @model_validator(mode="after")
    def _opens_before_closes(self) -> "OperatingWindowInput":
        if self.opens >= self.closes:
            raise ValueError("opens must be before closes")
        return self


class CalendarEntryInput(BaseModel):
    day: date
    kind: str
    note: str = Field(default="", max_length=300)

    @field_validator("kind")
    @classmethod
    def _valid_kind(cls, v: str) -> str:
        if v not in ("holiday", "closure", "special"):
            raise ValueError("kind must be holiday, closure, or special")
        return v


class CenterView(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    code: str
    status: str
    timezone: str | None

    model_config = {"from_attributes": True}


class OperatingWindowView(BaseModel):
    day_of_week: int
    opens: time
    closes: time

    model_config = {"from_attributes": True}


class CalendarEntryView(BaseModel):
    id: uuid.UUID
    day: date
    kind: str
    note: str

    model_config = {"from_attributes": True}


class CenterDetailView(BaseModel):
    center: CenterView
    settings: dict[str, Any]
    operating_windows: list[OperatingWindowView]
    calendar: list[CalendarEntryView]


class CenterPage(BaseModel):
    items: list[CenterView]
    total: int
    limit: int
    offset: int


class CollectionCenterService:
    def __init__(self, session: AsyncSession, bus: EventBus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit

    # --- lifecycle --------------------------------------------------------

    async def create(self, cmd: CreateCenterCommand, *, actor_id: uuid.UUID) -> CollectionCenter:
        tenant_id = require_current_tenant()
        branch = await self._session.get(Branch, cmd.branch_id)
        if branch is None or branch.tenant_id != tenant_id:
            raise NotFoundError("branch not found")
        existing = await self._session.scalar(
            select(CollectionCenter).where(
                CollectionCenter.tenant_id == tenant_id, CollectionCenter.code == cmd.code
            )
        )
        if existing is not None:
            raise ConflictError("center code already exists")
        center = CollectionCenter(
            tenant_id=tenant_id,
            branch_id=cmd.branch_id,
            name=cmd.name,
            code=cmd.code,
            timezone=cmd.timezone,
        )
        self._session.add(center)
        await self._session.flush()
        await self._audit.record(
            action="collection.center.created",
            resource_type="collection_center",
            resource_id=center.id,
            actor_id=actor_id,
            detail={"branch_id": str(cmd.branch_id), "code": cmd.code},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "collection.center-created.v1",
                {"center_id": str(center.id), "branch_id": str(cmd.branch_id), "code": cmd.code},
                actor_id=actor_id,
            )
        )
        return center

    async def update(
        self, center_id: uuid.UUID, cmd: UpdateCenterCommand, *, actor_id: uuid.UUID
    ) -> CollectionCenter:
        center = await self.get(center_id)
        if center.status == "archived":
            raise ConflictError("archived centers are immutable")
        center.name = cmd.name
        center.timezone = cmd.timezone
        await self._audit.record(
            action="collection.center.updated",
            resource_type="collection_center",
            resource_id=center.id,
            actor_id=actor_id,
        )
        return center

    async def set_status(
        self, center_id: uuid.UUID, new_status: str, *, actor_id: uuid.UUID
    ) -> CollectionCenter:
        if new_status not in CENTER_STATUSES:
            raise ConflictError(f"unknown status: {new_status}")
        center = await self.get(center_id)
        if new_status == center.status:
            return center
        if new_status not in ALLOWED_TRANSITIONS[center.status]:
            raise ConflictError(f"cannot move from {center.status} to {new_status}")
        if new_status == "active":
            # Activation requires the facility to actually open sometime.
            windows = await self._session.scalar(
                select(func.count())
                .select_from(OperatingWindow)
                .where(OperatingWindow.center_id == center.id)
            )
            if not windows:
                raise ConflictError("cannot activate a center without operating hours")
        previous = center.status
        center.status = new_status
        await self._audit.record(
            action="collection.center.status_changed",
            resource_type="collection_center",
            resource_id=center.id,
            actor_id=actor_id,
            detail={"from": previous, "to": new_status},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "collection.center-status-changed.v1",
                {"center_id": str(center.id), "from": previous, "to": new_status},
                actor_id=actor_id,
            )
        )
        return center

    # --- queries ----------------------------------------------------------

    async def get(self, center_id: uuid.UUID) -> CollectionCenter:
        tenant_id = require_current_tenant()
        center = await self._session.get(CollectionCenter, center_id)
        if center is None or center.tenant_id != tenant_id:
            raise NotFoundError("collection center not found")
        return center

    async def list_page(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        branch_id: uuid.UUID | None = None,
        center_scope: set[uuid.UUID] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> CenterPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        stmt = select(CollectionCenter).where(CollectionCenter.tenant_id == tenant_id)
        # DEMO-008: a centre-scoped principal lists only their own centres.
        # `None` means organization-wide — the answer for every principal that
        # existed before centre scope did.
        if center_scope is not None:
            stmt = stmt.where(CollectionCenter.id.in_(center_scope))
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(CollectionCenter.name).like(like),
                    func.lower(CollectionCenter.code).like(like),
                )
            )
        if status:
            stmt = stmt.where(CollectionCenter.status == status)
        if branch_id:
            stmt = stmt.where(CollectionCenter.branch_id == branch_id)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.scalars(
            stmt.order_by(CollectionCenter.code).limit(limit).offset(offset)
        )
        return CenterPage(
            items=[CenterView.model_validate(c) for c in rows.all()],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    async def detail(self, center_id: uuid.UUID) -> CenterDetailView:
        center = await self.get(center_id)
        config = await self._session.scalar(
            select(CollectionCenterConfig).where(CollectionCenterConfig.center_id == center.id)
        )
        windows = await self._session.scalars(
            select(OperatingWindow)
            .where(OperatingWindow.center_id == center.id)
            .order_by(OperatingWindow.day_of_week, OperatingWindow.opens)
        )
        calendar = await self._session.scalars(
            select(CalendarEntry)
            .where(CalendarEntry.center_id == center.id)
            .order_by(CalendarEntry.day)
        )
        return CenterDetailView(
            center=CenterView.model_validate(center),
            settings=(config.settings if config else {}),
            operating_windows=[OperatingWindowView.model_validate(w) for w in windows.all()],
            calendar=[CalendarEntryView.model_validate(e) for e in calendar.all()],
        )

    # --- configuration ----------------------------------------------------

    async def set_config(
        self, center_id: uuid.UUID, settings: dict[str, Any], *, actor_id: uuid.UUID
    ) -> dict[str, Any]:
        center = await self.get(center_id)
        config = await self._session.scalar(
            select(CollectionCenterConfig).where(CollectionCenterConfig.center_id == center.id)
        )
        if config is None:
            config = CollectionCenterConfig(
                tenant_id=center.tenant_id, center_id=center.id, settings=settings
            )
            self._session.add(config)
        else:
            config.settings = settings
        await self._audit.record(
            action="collection.center.configured",
            resource_type="collection_center",
            resource_id=center.id,
            actor_id=actor_id,
        )
        return settings

    async def set_operating_hours(
        self, center_id: uuid.UUID, windows: list[OperatingWindowInput], *, actor_id: uuid.UUID
    ) -> list[OperatingWindowView]:
        """Replace-all semantics: the submitted set becomes the schedule."""
        center = await self.get(center_id)
        # Reject overlapping windows on the same day.
        by_day: dict[int, list[OperatingWindowInput]] = {}
        for w in windows:
            for other in by_day.get(w.day_of_week, []):
                if w.opens < other.closes and other.opens < w.closes:
                    raise ConflictError("overlapping operating windows on the same day")
            by_day.setdefault(w.day_of_week, []).append(w)
        existing = await self._session.scalars(
            select(OperatingWindow).where(OperatingWindow.center_id == center.id)
        )
        for row in existing.all():
            await self._session.delete(row)
        for w in windows:
            self._session.add(
                OperatingWindow(
                    tenant_id=center.tenant_id,
                    center_id=center.id,
                    day_of_week=w.day_of_week,
                    opens=w.opens,
                    closes=w.closes,
                )
            )
        await self._audit.record(
            action="collection.center.hours_set",
            resource_type="collection_center",
            resource_id=center.id,
            actor_id=actor_id,
            detail={"windows": len(windows)},
        )
        return [
            OperatingWindowView(day_of_week=w.day_of_week, opens=w.opens, closes=w.closes)
            for w in windows
        ]

    # --- business calendar ------------------------------------------------

    async def add_calendar_entry(
        self, center_id: uuid.UUID, entry: CalendarEntryInput, *, actor_id: uuid.UUID
    ) -> CalendarEntry:
        center = await self.get(center_id)
        existing = await self._session.scalar(
            select(CalendarEntry).where(
                CalendarEntry.center_id == center.id, CalendarEntry.day == entry.day
            )
        )
        if existing is not None:
            raise ConflictError("calendar entry for this day already exists")
        row = CalendarEntry(
            tenant_id=center.tenant_id,
            center_id=center.id,
            day=entry.day,
            kind=entry.kind,
            note=entry.note,
        )
        self._session.add(row)
        await self._session.flush()
        await self._audit.record(
            action="collection.center.calendar_added",
            resource_type="collection_center",
            resource_id=center.id,
            actor_id=actor_id,
            detail={"day": entry.day.isoformat(), "kind": entry.kind},
        )
        return row

    async def remove_calendar_entry(
        self, center_id: uuid.UUID, entry_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        center = await self.get(center_id)
        row = await self._session.get(CalendarEntry, entry_id)
        if row is None or row.center_id != center.id:
            raise NotFoundError("calendar entry not found")
        await self._session.delete(row)
        await self._audit.record(
            action="collection.center.calendar_removed",
            resource_type="collection_center",
            resource_id=center.id,
            actor_id=actor_id,
        )
