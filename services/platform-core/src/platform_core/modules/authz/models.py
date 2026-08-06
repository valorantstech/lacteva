"""Authorization module — RBAC persistence model.

System roles have tenant_id NULL and are shared; tenant roles are tenant-
defined. A user's effective permissions = union over role assignments in the
current tenant (+ platform-level assignments).
"""

import uuid

from sqlalchemy import String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin


class Role(Base, IdMixin):
    __tablename__ = "role"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),)

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300), default="")


class RolePermission(Base, IdMixin):
    __tablename__ = "role_permission"
    __table_args__ = (UniqueConstraint("role_id", "permission_key", name="uq_role_permission"),)

    # SEC-002: denormalised from role. This table is tenant-owned but had
    # no tenant_id, so no RLS policy could apply and a query that forgot its
    # join returned every tenant's rows. Safe to denormalise because rows are
    # never reparented; the composite FK in DBD-0001 §7.1 makes that provable.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    permission_key: Mapped[str] = mapped_column(String(120))  # registry key or "*"


class UserRole(Base, IdMixin):
    __tablename__ = "user_role"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "tenant_id", name="uq_user_role_tenant"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
