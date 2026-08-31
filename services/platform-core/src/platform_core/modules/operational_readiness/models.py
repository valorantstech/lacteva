"""Operational Readiness module — persistence models.

PLATFORM MODELING ONLY: no hardware communication exists or is stubbed here.
Device health is a *reported* fact (by operators/technicians via API); device
integration protocols are a future concern behind the same model.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

DEVICE_CATEGORIES: dict[str, dict] = {
    "scale": {"label": "Weighing scale", "readiness": "blocking"},
    "milk_analyzer": {"label": "Milk analyzer", "readiness": "warning"},
    "printer": {"label": "Receipt printer", "readiness": "warning"},
    "qr_scanner": {"label": "QR scanner", "readiness": "none"},
    "rfid_reader": {"label": "RFID reader", "readiness": "none"},
    "camera": {"label": "Camera", "readiness": "none"},
}

DEVICE_STATUSES = ("registered", "assigned", "active", "maintenance", "retired")
HEALTH_STATES = ("ok", "degraded", "failed")


class Device(Base, IdMixin):
    __tablename__ = "device"
    __table_args__ = (UniqueConstraint("tenant_id", "serial_number", name="uq_device_serial"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(200))
    serial_number: Mapped[str] = mapped_column(String(80))
    # WO-53. What the label on the machine says. The hardware discovery
    # checklist (§10) collects make and model for every instrument, and a
    # per-model driver (D-16) is selected by exactly this pair — so a registry
    # that cannot record them is one a connector cannot be built on. Optional,
    # because a dairy registering a device it has not yet photographed should
    # not be blocked from registering it.
    make: Mapped[str] = mapped_column(String(80), default="", server_default="")
    model: Mapped[str] = mapped_column(String(80), default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), default="registered", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeviceHealthReport(Base, IdMixin):
    """Point-in-time reported health; the latest report per device counts."""

    __tablename__ = "device_health_report"

    # SEC-002: denormalised from device. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    state: Mapped[str] = mapped_column(String(20))  # ok | degraded | failed
    note: Mapped[str] = mapped_column(String(300), default="")
    reported_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class OperatorAssignment(Base, IdMixin):
    """A tenant member assigned to work a collection center."""

    __tablename__ = "operator_assignment"
    __table_args__ = (UniqueConstraint("center_id", "user_id", name="uq_operator_center_user"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    role_label: Mapped[str] = mapped_column(String(20), default="operator")  # operator|supervisor
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
