"""Collection Center module — persistence models.

FACILITY MANAGEMENT ONLY (Sprint-003 wall): a collection center here is a
managed asset of a branch — identity, status, configuration, operating hours,
calendar. Collection operations (shifts, deliveries, testing — PSP-0003…0006)
are explicitly out of scope and arrive only after the Collect package approval.

Ownership rule: a Branch owns many Collection Centers; a center belongs to
exactly one branch (same tenant), for its whole life.
"""

import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Integer, String, Time, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

CENTER_STATUSES = ("active", "inactive", "maintenance", "archived")


class CollectionCenter(Base, IdMixin):
    __tablename__ = "collection_center"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_center_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="inactive", index=True)
    timezone: Mapped[str] = mapped_column(String(40), default="UTC")  # IANA name
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CollectionCenterConfig(Base, IdMixin):
    """Per-center configuration document (schema-free for now).

    TODO(M2): typed configuration schema once real settings exist; market-
    parameterized values resolve through the platform ConfigurationService.
    """

    __tablename__ = "collection_center_config"

    # SEC-002: denormalised from center. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, index=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OperatingWindow(Base, IdMixin):
    """A weekly recurring opening window (e.g. Mon 06:00-09:30).

    Multiple windows per day model morning/evening openings. These are
    opening HOURS of the facility — operational shifts are a different,
    future concept (PSP-0003) and do not live here.
    """

    __tablename__ = "center_operating_window"
    __table_args__ = (
        UniqueConstraint("center_id", "day_of_week", "opens", name="uq_window_center_day_open"),
    )

    # SEC-002: denormalised from center. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Monday … 6=Sunday
    opens: Mapped[time] = mapped_column(Time)
    closes: Mapped[time] = mapped_column(Time)


class CalendarEntry(Base, IdMixin):
    """Business-calendar exception for a center: holiday/closure/special day."""

    __tablename__ = "center_calendar_entry"
    __table_args__ = (UniqueConstraint("center_id", "day", name="uq_calendar_center_day"),)

    # SEC-002: denormalised from center. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))  # holiday | closure | special
    note: Mapped[str] = mapped_column(String(300), default="")
