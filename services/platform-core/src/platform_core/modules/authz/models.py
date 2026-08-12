"""Authorization module — RBAC persistence model.

System roles have tenant_id NULL and are shared; tenant roles are tenant-
defined. A user's effective permissions = union over role assignments in the
current tenant (+ platform-level assignments).
"""

import uuid

from sqlalchemy import Index, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin


class Role(Base, IdMixin):
    __tablename__ = "role"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),
        # DEMO-008: the composite constraint above enforces nothing for SYSTEM
        # roles. Every one of them has `tenant_id IS NULL`, and in SQL NULL is
        # not equal to NULL — so the database happily accepted three copies of
        # `tenant-admin`, one per racing startup. A PARTIAL unique index is the
        # only thing that actually makes the name unique among system roles.
        Index(
            "uq_role_system_name",
            "name",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
            sqlite_where=text("tenant_id IS NULL"),
        ),
    )

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
    #: DEMO-008 — optional CENTRE scope on the grant.
    #:
    #: NULL means organization-wide, which is what every grant made before this
    #: column existed means, so adding it changed nobody's access. A non-null
    #: value narrows this grant to one collection centre: it is how a centre
    #: manager differs from an organization manager holding the same
    #: permissions.
    #:
    #: The scope lives on the GRANT rather than on the role, because the same
    #: role is worth granting at different scopes — a person can run centre A
    #: and, later, centre B, without a second role being invented for them.
    #:
    #: Deliberately NOT reusing `operator_assignment`: that table records that
    #: somebody works at a centre (and the readiness engine reads it as such),
    #: which is a different statement from "may only act at this centre".
    center_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
