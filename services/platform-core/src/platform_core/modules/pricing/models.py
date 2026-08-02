"""Pricing module — persistence models (Increment-001: Rate Card Foundation).

RATE CARD LIFECYCLE ONLY (Increment-001 wall): identity, workflow status,
effective dates, versioning, and scope assignments (collection centers,
products). Pricing rules, rate tables, formulas, bonuses, penalties, and
taxes are explicitly out of scope and arrive with Increment-002+.

Versioning rule: a rate card code identifies a pricing agreement; each row is
one immutable-once-published VERSION of it ((tenant, code, version) unique).
Historical versions are never updated — changes happen on a new draft version.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

RATE_CARD_STATUSES = ("draft", "under_review", "approved", "published", "archived")


class RateCard(Base, IdMixin):
    __tablename__ = "rate_card"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", "version", name="uq_rate_card_tenant_code_version"),
        # Serves the publish-overlap check and the active_on search filter.
        Index("ix_rate_card_active_window", "tenant_id", "status", "effective_from"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    code: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500), default="")
    currency: Mapped[str] = mapped_column(String(3))  # ISO 4217
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)  # None = open-ended
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RateCardCenterAssignment(Base, IdMixin):
    """Scope: which collection centers a rate card version applies to (m:n)."""

    __tablename__ = "rate_card_center_assignment"
    __table_args__ = (UniqueConstraint("rate_card_id", "center_id", name="uq_rate_card_center"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    rate_card_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RateCardProductAssignment(Base, IdMixin):
    """Scope: which products a rate card version applies to (m:n).

    Products are identified by code (e.g. RAW-COW-MILK) — the platform has no
    Product master data module yet; when one lands, product_code becomes a
    foreign reference without changing this table's shape.
    """

    __tablename__ = "rate_card_product_assignment"
    __table_args__ = (
        UniqueConstraint("rate_card_id", "product_code", name="uq_rate_card_product"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    rate_card_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    product_code: Mapped[str] = mapped_column(String(40), index=True)
    product_name: Mapped[str] = mapped_column(String(120), default="")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Future Pricing Rules live here in Increment-002 (Rate Tables): a
# rate_card_rule table referencing rate_card.id. Placeholder only — no
# calculation concepts exist in Increment-001.
