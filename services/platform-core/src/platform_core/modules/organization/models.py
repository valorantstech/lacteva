"""Organization module — persistence model.

An Organization IS the tenant: its id is the tenant_id used across the
platform (realizes the business rule that a tenant is a verified dairy
business — ETE.ONB.01 at business level).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow


class Organization(Base, IdMixin):
    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    country_code: Mapped[str] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    org_type: Mapped[str] = mapped_column(String(40))  # cooperative|processor|collector|farm|other
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|suspended|closed
    default_locale: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # TODO(M1): verification workflow fields (status pending_verification,
    # verification evidence refs) realizing ETE.ONB.01 proportionate checks.


class Workspace(Base, IdMixin):
    """Organizational subdivision (region, union, business unit)."""

    __tablename__ = "workspace"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_workspace_tenant_slug"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Branch(Base, IdMixin):
    """Physical location under a workspace (office, plant, village site).

    Business facilities (e.g. Lacteva Collect's collection centers) will
    ATTACH to branches later — no dairy semantics live here.
    """

    __tablename__ = "branch"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_branch_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|closed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base, IdMixin):
    """A user's membership state within their organization.

    Note: user identity is tenant-scoped (one user row per tenant, baseline
    §1.5), so membership does not model multi-org users — it models lifecycle
    (active/suspended) and provenance of the user inside the org.
    """

    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|suspended
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class Invitation(Base, IdMixin):
    """Pending invitation for a person to join an organization."""

    __tablename__ = "invitation"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    role_name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
