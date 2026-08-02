"""Operational Readiness module — devices, operators, and the readiness engine."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.core.errors import ConflictError, ForbiddenError, NotFoundError
from platform_core.core.tenancy import get_current_tenant
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.collection_center.models import CalendarEntry, CollectionCenter
from platform_core.modules.identity.models import User
from platform_core.modules.operational_readiness.models import (
    DEVICE_CATEGORIES,
    DEVICE_STATUSES,
    HEALTH_STATES,
    Device,
    DeviceHealthReport,
    OperatorAssignment,
)

DEVICE_TRANSITIONS: dict[str, set[str]] = {
    "registered": {"retired"},  # assignment happens via assign(), not set_status
    "assigned": {"active", "retired"},
    "active": {"maintenance", "retired"},
    "maintenance": {"active", "retired"},
    "retired": set(),
}


# --- DTOs ------------------------------------------------------------------


class RegisterDeviceCommand(BaseModel):
    category: str
    name: str = Field(min_length=2, max_length=200)
    serial_number: str = Field(min_length=2, max_length=80)

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        if v not in DEVICE_CATEGORIES:
            raise ValueError(f"unknown category (expected one of {sorted(DEVICE_CATEGORIES)})")
        return v


class DeviceView(BaseModel):
    id: uuid.UUID
    center_id: uuid.UUID | None
    category: str
    name: str
    serial_number: str
    status: str

    model_config = {"from_attributes": True}


class DeviceDetailView(BaseModel):
    device: DeviceView
    latest_health: str | None
    health_note: str | None
    health_reported_at: datetime | None


class DevicePage(BaseModel):
    items: list[DeviceView]
    total: int
    limit: int
    offset: int


class OperatorView(BaseModel):
    user_id: uuid.UUID
    role_label: str
    assigned_at: datetime

    model_config = {"from_attributes": True}


class ReadinessCheck(BaseModel):
    rule: str
    severity: str  # blocking | warning
    passed: bool
    detail: str


class ReadinessResult(BaseModel):
    center_id: uuid.UUID
    status: str  # READY | NOT_READY | WARNING
    evaluated_at: datetime
    checks: list[ReadinessCheck]


READINESS_RULES: dict[str, dict] = {
    "center.active": {"severity": "blocking", "description": "Center status is active"},
    "center.calendar": {
        "severity": "blocking",
        "description": "No closure/holiday for today; 'special' days yield a warning",
    },
    "operator.assigned": {
        "severity": "blocking",
        "description": "At least one operator is assigned to the center",
    },
    "device.scale": {
        "severity": "blocking",
        "description": "An active, non-failed scale is present",
    },
    "device.milk_analyzer": {
        "severity": "warning",
        "description": (
            "An active, non-failed milk analyzer is present "
            "(Basic-profile centers may run without one)"
        ),
    },
    "device.printer": {
        "severity": "warning",
        "description": "An active, non-failed printer is present (fallback: written receipts)",
    },
}
# TODO(M3): per-center rule-severity overrides via center config once market
# packs define which profiles treat analyzer/printer as mandatory.


class OperationalReadinessService:
    def __init__(self, session: AsyncSession, bus: EventBus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit

    # --- device registry --------------------------------------------------

    async def register_device(self, cmd: RegisterDeviceCommand, *, actor_id: uuid.UUID) -> Device:
        tenant_id = self._require_tenant()
        existing = await self._session.scalar(
            select(Device).where(
                Device.tenant_id == tenant_id, Device.serial_number == cmd.serial_number
            )
        )
        if existing is not None:
            raise ConflictError("serial number already registered")
        device = Device(
            tenant_id=tenant_id,
            category=cmd.category,
            name=cmd.name,
            serial_number=cmd.serial_number,
        )
        self._session.add(device)
        await self._session.flush()
        await self._audit.record(
            action="operations.device.registered",
            resource_type="device",
            resource_id=device.id,
            actor_id=actor_id,
            detail={"category": cmd.category, "serial": cmd.serial_number},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "operations.device-registered.v1",
                {"device_id": str(device.id), "category": cmd.category},
                actor_id=actor_id,
            )
        )
        return device

    async def assign_device(
        self, device_id: uuid.UUID, center_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> Device:
        device = await self.get_device(device_id)
        if device.status not in ("registered", "assigned"):
            raise ConflictError(f"cannot assign a device in status {device.status}")
        center = await self._get_center(center_id)
        device.center_id = center.id
        device.status = "assigned"
        await self._audit.record(
            action="operations.device.assigned",
            resource_type="device",
            resource_id=device.id,
            actor_id=actor_id,
            detail={"center_id": str(center.id)},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "operations.device-assigned.v1",
                {"device_id": str(device.id), "center_id": str(center.id)},
                actor_id=actor_id,
            )
        )
        return device

    async def set_device_status(
        self, device_id: uuid.UUID, new_status: str, *, actor_id: uuid.UUID
    ) -> Device:
        if new_status not in DEVICE_STATUSES:
            raise ConflictError(f"unknown status: {new_status}")
        device = await self.get_device(device_id)
        if new_status == device.status:
            return device
        if new_status not in DEVICE_TRANSITIONS[device.status]:
            raise ConflictError(f"cannot move from {device.status} to {new_status}")
        previous = device.status
        device.status = new_status
        await self._audit.record(
            action="operations.device.status_changed",
            resource_type="device",
            resource_id=device.id,
            actor_id=actor_id,
            detail={"from": previous, "to": new_status},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "operations.device-status-changed.v1",
                {"device_id": str(device.id), "from": previous, "to": new_status},
                actor_id=actor_id,
            )
        )
        return device

    async def report_health(
        self, device_id: uuid.UUID, state: str, note: str, *, actor_id: uuid.UUID
    ) -> DeviceHealthReport:
        if state not in HEALTH_STATES:
            raise ConflictError(f"unknown health state: {state}")
        device = await self.get_device(device_id)
        if device.status == "retired":
            raise ConflictError("retired devices do not accept health reports")
        report = DeviceHealthReport(
            device_id=device.id, state=state, note=note[:300], reported_by=actor_id
        )
        self._session.add(report)
        await self._session.flush()
        await self._bus.publish(
            EventEnvelope.new(
                "operations.device-health-reported.v1",
                {"device_id": str(device.id), "state": state},
                actor_id=actor_id,
            )
        )
        return report

    async def get_device(self, device_id: uuid.UUID) -> Device:
        tenant_id = self._require_tenant()
        device = await self._session.get(Device, device_id)
        if device is None or device.tenant_id != tenant_id:
            raise NotFoundError("device not found")
        return device

    async def device_detail(self, device_id: uuid.UUID) -> DeviceDetailView:
        device = await self.get_device(device_id)
        latest = await self._latest_health(device.id)
        return DeviceDetailView(
            device=DeviceView.model_validate(device),
            latest_health=latest.state if latest else None,
            health_note=latest.note if latest else None,
            health_reported_at=latest.reported_at if latest else None,
        )

    async def list_devices(
        self,
        *,
        center_id: uuid.UUID | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> DevicePage:
        tenant_id = self._require_tenant()
        limit = max(1, min(limit, 100))
        stmt = select(Device).where(Device.tenant_id == tenant_id)
        if center_id:
            stmt = stmt.where(Device.center_id == center_id)
        if category:
            stmt = stmt.where(Device.category == category)
        if status:
            stmt = stmt.where(Device.status == status)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.scalars(
            stmt.order_by(Device.category, Device.serial_number).limit(limit).offset(offset)
        )
        return DevicePage(
            items=[DeviceView.model_validate(d) for d in rows.all()],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    # --- operator assignment ----------------------------------------------

    async def assign_operator(
        self,
        center_id: uuid.UUID,
        user_id: uuid.UUID,
        role_label: str,
        *,
        actor_id: uuid.UUID,
    ) -> OperatorAssignment:
        tenant_id = self._require_tenant()
        if role_label not in ("operator", "supervisor"):
            raise ConflictError("role_label must be operator or supervisor")
        center = await self._get_center(center_id)
        user = await self._session.get(User, user_id)
        if user is None or user.tenant_id != tenant_id or not user.is_active:
            raise NotFoundError("user is not an active member of this organization")
        existing = await self._session.scalar(
            select(OperatorAssignment).where(
                OperatorAssignment.center_id == center.id,
                OperatorAssignment.user_id == user_id,
            )
        )
        if existing is not None:
            raise ConflictError("user is already assigned to this center")
        assignment = OperatorAssignment(
            tenant_id=tenant_id, center_id=center.id, user_id=user_id, role_label=role_label
        )
        self._session.add(assignment)
        await self._session.flush()
        await self._audit.record(
            action="operations.operator.assigned",
            resource_type="collection_center",
            resource_id=center.id,
            actor_id=actor_id,
            detail={"user_id": str(user_id), "role": role_label},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "operations.operator-assigned.v1",
                {"center_id": str(center.id), "user_id": str(user_id), "role": role_label},
                actor_id=actor_id,
            )
        )
        return assignment

    async def list_operators(self, center_id: uuid.UUID) -> list[OperatorAssignment]:
        center = await self._get_center(center_id)
        rows = await self._session.scalars(
            select(OperatorAssignment)
            .where(OperatorAssignment.center_id == center.id)
            .order_by(OperatorAssignment.assigned_at)
        )
        return list(rows.all())

    async def remove_operator(
        self, center_id: uuid.UUID, user_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        center = await self._get_center(center_id)
        assignment = await self._session.scalar(
            select(OperatorAssignment).where(
                OperatorAssignment.center_id == center.id,
                OperatorAssignment.user_id == user_id,
            )
        )
        if assignment is None:
            raise NotFoundError("operator assignment not found")
        await self._session.delete(assignment)
        await self._audit.record(
            action="operations.operator.removed",
            resource_type="collection_center",
            resource_id=center.id,
            actor_id=actor_id,
            detail={"user_id": str(user_id)},
        )

    # --- readiness engine --------------------------------------------------

    async def evaluate_readiness(self, center_id: uuid.UUID) -> ReadinessResult:
        center = await self._get_center(center_id)
        checks: list[ReadinessCheck] = []

        checks.append(
            ReadinessCheck(
                rule="center.active",
                severity="blocking",
                passed=center.status == "active",
                detail=f"center status is {center.status}",
            )
        )

        checks.append(await self._calendar_check(center))
        checks.append(await self._operator_check(center))
        for category in ("scale", "milk_analyzer", "printer"):
            checks.append(await self._device_check(center, category))

        blocking_failed = any(c.severity == "blocking" and not c.passed for c in checks)
        warnings = any(c.severity == "warning" and not c.passed for c in checks)
        status = "NOT_READY" if blocking_failed else ("WARNING" if warnings else "READY")
        return ReadinessResult(
            center_id=center.id, status=status, evaluated_at=utcnow(), checks=checks
        )

    async def _calendar_check(self, center: CollectionCenter) -> ReadinessCheck:
        try:
            tz = ZoneInfo(center.timezone)
        except Exception:
            tz = ZoneInfo("UTC")
        today = utcnow().astimezone(tz).date()
        entry = await self._session.scalar(
            select(CalendarEntry).where(
                CalendarEntry.center_id == center.id, CalendarEntry.day == today
            )
        )
        if entry is None:
            return ReadinessCheck(
                rule="center.calendar",
                severity="blocking",
                passed=True,
                detail="no calendar exception today",
            )
        if entry.kind == "special":
            return ReadinessCheck(
                rule="center.calendar",
                severity="warning",
                passed=False,
                detail=f"special day today: {entry.note or 'unnamed'}",
            )
        return ReadinessCheck(
            rule="center.calendar",
            severity="blocking",
            passed=False,
            detail=f"center closed today ({entry.kind}: {entry.note or 'unnamed'})",
        )

    async def _operator_check(self, center: CollectionCenter) -> ReadinessCheck:
        count = (
            await self._session.scalar(
                select(func.count())
                .select_from(OperatorAssignment)
                .where(OperatorAssignment.center_id == center.id)
            )
            or 0
        )
        return ReadinessCheck(
            rule="operator.assigned",
            severity="blocking",
            passed=count > 0,
            detail=f"{count} operator(s) assigned",
        )

    async def _device_check(self, center: CollectionCenter, category: str) -> ReadinessCheck:
        severity = READINESS_RULES[f"device.{category}"]["severity"]
        devices = (
            await self._session.scalars(
                select(Device).where(
                    Device.center_id == center.id,
                    Device.category == category,
                    Device.status == "active",
                )
            )
        ).all()
        usable = 0
        for device in devices:
            latest = await self._latest_health(device.id)
            if latest is None or latest.state != "failed":
                usable += 1
        detail = f"{usable} usable {category}(s) of {len(devices)} active"
        return ReadinessCheck(
            rule=f"device.{category}", severity=severity, passed=usable > 0, detail=detail
        )

    async def _latest_health(self, device_id: uuid.UUID) -> DeviceHealthReport | None:
        return await self._session.scalar(
            select(DeviceHealthReport)
            .where(DeviceHealthReport.device_id == device_id)
            .order_by(DeviceHealthReport.reported_at.desc(), DeviceHealthReport.id.desc())
            .limit(1)
        )

    # --- helpers -----------------------------------------------------------

    async def _get_center(self, center_id: uuid.UUID) -> CollectionCenter:
        tenant_id = self._require_tenant()
        center = await self._session.get(CollectionCenter, center_id)
        if center is None or center.tenant_id != tenant_id:
            raise NotFoundError("collection center not found")
        return center

    @staticmethod
    def _require_tenant() -> uuid.UUID:
        tenant_id = get_current_tenant()
        if tenant_id is None:
            raise ForbiddenError("tenant context required")
        return tenant_id
