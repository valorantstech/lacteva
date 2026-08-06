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

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

RATE_CARD_STATUSES = ("draft", "under_review", "approved", "published", "archived")
MATRIX_STATUSES = ("draft", "active", "archived")


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


class QualityDimension(Base, IdMixin):
    """Configurable quality dimension (Increment-002) — business DATA, not code.

    FAT is not special: dimensions (FAT, SNF, CLR, density, protein, …) are
    tenant-editable rows; future dimensions need no schema or code change.
    min/max bound the values pricing-matrix rows may use (None = unbounded).
    """

    __tablename__ = "quality_dimension"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_quality_dimension_tenant_code"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(20), default="")
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PricingMatrix(Base, IdMixin):
    """Pricing data for ONE product of ONE rate card along ONE quality dimension.

    Lifecycle follows the owning rate card: editable only while the card is
    draft, `active` once the card publishes (immutable), `archived` with the
    card. New rate card versions copy their matrices forward. Stores pricing
    DEFINITIONS only — no calculation (Increment-002 wall).
    """

    __tablename__ = "pricing_matrix"
    __table_args__ = (
        UniqueConstraint(
            "rate_card_id",
            "product_code",
            "dimension_code",
            name="uq_matrix_card_product_dimension",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    rate_card_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(200))
    product_code: Mapped[str] = mapped_column(String(40), index=True)
    product_name: Mapped[str] = mapped_column(String(120), default="")
    dimension_code: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # = rate card version
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PricingMatrixRow(Base, IdMixin):
    """One price band: half-open range [from_value, to_value) on the matrix's
    dimension. Half-open ranges make overlap and continuity checks exact —
    adjacent bands share a boundary value without colliding."""

    __tablename__ = "pricing_matrix_row"
    __table_args__ = (
        CheckConstraint("to_value > from_value", name="ck_matrix_row_range"),
        CheckConstraint("unit_price > 0", name="ck_matrix_row_price"),
        Index("ix_matrix_row_lookup", "matrix_id", "active", "from_value"),
    )

    # SEC-002: denormalised from matrix. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    matrix_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    from_value: Mapped[float] = mapped_column(Float)
    to_value: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
