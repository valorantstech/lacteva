"""Organization module — persistence model.

An Organization IS the tenant: its id is the tenant_id used across the
platform (realizes the business rule that a tenant is a verified dairy
business — ETE.ONB.01 at business level).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow


class Organization(Base, IdMixin):
    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    country_code: Mapped[str] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    org_type: Mapped[str] = mapped_column(String(40))  # cooperative|processor|collector|farm|other
    # active|suspended|closed|offboarded. `offboarded` is terminal: the tenant's
    # operational data is gone and only anonymized financial records remain
    # (PROD-001, core/tenant_lifecycle.py).
    status: Mapped[str] = mapped_column(String(20), default="active")
    #: DEMO-013. The organization's locale context: what it counts money in,
    #: what clock its business days run on, and what languages its people may
    #: work in. Resolved from `country_code` at onboarding via
    #: `core/locales.resolve`, and overridable afterwards — a country proposes,
    #: an organization decides.
    #:
    #: These are COLUMNS rather than lookups through `country_code` because an
    #: organization's settings must not move when the world does. If a country
    #: redenominates, or the registry's principal timezone is corrected, every
    #: historical report of every tenant in that country would silently change
    #: meaning. The country is where they are; these are what they agreed to.
    currency_code: Mapped[str] = mapped_column(String(3))  # ISO 4217; resolved at creation
    #: IANA. Authoritative for this organization's business dates — see
    #: `core/business_time.py`. Never the server's zone, never the browser's.
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    #: BCP-47 tags this organization has enabled. A user may choose any of
    #: these and nothing else (DEMO-013 §5).
    supported_languages: Mapped[list] = mapped_column(JSON, default=lambda: ["en"])
    #: BCP-47. Widened from the pre-DEMO-013 `en` to hold `en-IN`.
    default_locale: Mapped[str] = mapped_column(String(16), default="en")
    #: D-21 / WO-70. The unit this organisation MEASURES intake in — `litre`
    #: or `kg` (`core/units.UNITS`) — resolved from `country_code` at creation
    #: exactly as `currency_code` is, and written onto every transaction at
    #: capture. Columns, for the same reason the currency is: a later change
    #: applies to FUTURE transactions only, and history keeps the unit it was
    #: actually measured in.
    #:
    #: The ORM and server defaults are `kg` because that is what every
    #: organisation created before WO-70 measured — a row that predates the
    #: column was weighed. New organisations never see this default: the
    #: service resolves the country's unit before the INSERT.
    quantity_unit: Mapped[str] = mapped_column(String(8), default="kg", server_default="kg")
    #: D-21 ruling 3. Where the dairy TRADES in the other unit, that unit, the
    #: owner-declared kilograms-per-litre factor, and the date it took effect.
    #: All null in the ordinary case (trade unit = measured unit), when
    #: nothing converts and nothing is printed. `core/units.validate_terms`
    #: is the one place the three are allowed to disagree or agree.
    trade_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)
    conversion_factor: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    conversion_effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    #: When the tenant was offboarded. The tombstone's timestamp — retained
    #: financial records point at a tenant_id that must still resolve to
    #: something, and "when did this dairy leave" is an audit question.
    offboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
