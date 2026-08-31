"""Supplier module — persistence models.

A Supplier is the platform realization of the business's Producer/Member
relationship (capability CPR.MEM / glossary "Producer"): the party that
delivers to collection centers. SPRINT-005 wall: identity, profile,
documents, banking, and placement only — no milk, pricing, FAT, settlement,
or shift semantics.

Placement rules: one supplier may deliver to MANY collection centers
(m:n assignment table); the supplier has one primary branch.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

SUPPLIER_STATUSES = ("draft", "active", "suspended", "archived")
DOCUMENT_KINDS = ("national_id", "photo", "contract", "other")


class Supplier(Base, IdMixin):
    __tablename__ = "supplier"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_supplier_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SupplierProfile(Base, IdMixin):
    __tablename__ = "supplier_profile"

    # SEC-002: denormalised from supplier. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    phone: Mapped[str] = mapped_column(String(30), default="", index=True)
    # WO-52. Optional, and empty for most: a smallholder dairy farmer is
    # reachable by phone, not by mail. It exists because some suppliers are
    # institutions — a chilling centre, a co-operative — and because the
    # notification directory has always been able to carry an address that
    # nothing populated. Email is the only channel this platform can actually
    # send on today; SMS and WhatsApp remain in the Coming-Soon register.
    email: Mapped[str] = mapped_column(String(200), default="", server_default="")
    national_id: Mapped[str] = mapped_column(String(60), default="")
    village: Mapped[str] = mapped_column(String(120), default="")
    locale: Mapped[str] = mapped_column(String(8), default="en")
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SupplierCenterAssignment(Base, IdMixin):
    __tablename__ = "supplier_center_assignment"
    __table_args__ = (UniqueConstraint("supplier_id", "center_id", name="uq_supplier_center"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    center_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupplierBankAccount(Base, IdMixin):
    __tablename__ = "supplier_bank_account"

    # SEC-002: denormalised from supplier. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    account_name: Mapped[str] = mapped_column(String(200))
    account_number: Mapped[str] = mapped_column(String(60))  # TODO(M3): encrypt at rest
    bank_code: Mapped[str] = mapped_column(String(40))
    is_primary: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupplierDocument(Base, IdMixin):
    __tablename__ = "supplier_document"

    # SEC-002: denormalised from supplier. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    object_key: Mapped[str] = mapped_column(String(300))  # object-storage reference
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
