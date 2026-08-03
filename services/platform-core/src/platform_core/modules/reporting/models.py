"""Reporting module — projection tables (SPRINT-008B).

Read models maintained by the reporting-projection CONSUMER (the reporting
module owns its read models; the consumer framework is their maintainer).
Populated exclusively from event payloads — never by querying transactional
tables — so they scale independently of the collection hot path and are the
evolutionary alternative to a data warehouse (see REP-001 performance notes).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow


class _TotalsColumns:
    transactions: Mapped[int] = mapped_column(Integer, default=0)
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    total_net_weight: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=0)
    payable_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)  # "MIX" on conflict
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DailyTotalsProjection(Base, IdMixin, _TotalsColumns):
    __tablename__ = "projection_daily_totals"
    __table_args__ = (UniqueConstraint("tenant_id", "day", name="uq_projection_daily"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    day: Mapped[date] = mapped_column(Date, index=True)


class CenterTotalsProjection(Base, IdMixin, _TotalsColumns):
    __tablename__ = "projection_center_totals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "day", "center_id", name="uq_projection_center"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)


class SupplierTotalsProjection(Base, IdMixin, _TotalsColumns):
    __tablename__ = "projection_supplier_totals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "day", "supplier_id", name="uq_projection_supplier"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
