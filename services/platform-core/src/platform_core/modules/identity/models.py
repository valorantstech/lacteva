"""Identity module — persistence model.

Pragmatic clean-architecture note: SQLAlchemy mapped classes double as domain
entities at foundation size; when a module's rules grow past CRUD-with-
invariants, split into dataclass entities + mappers (tracked in the roadmap).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow


class User(Base, IdMixin):
    __tablename__ = "user_account"
    # One identity may exist per tenant per email; platform-level users
    # (operators of Lacteva itself) have tenant_id NULL.
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    #: The user's own language, as a BCP-47 tag (DEMO-013 §5). Widened from
    #: String(8) to hold a tag like `hi-IN`.
    #:
    #: Constrained by the ORGANIZATION's `supported_languages`, not by this
    #: column: what a person may read is a decision their dairy makes, and a
    #: column cannot express "one of whatever that tenant enabled". The
    #: enforcement is in `IdentityService.set_language`.
    locale: Mapped[str] = mapped_column(String(16), default="en")

    #: DEMO-014 — the clock this person wants timestamps SHOWN in, or NULL for
    #: their organization's.
    #:
    #: Display only, and that is a hard boundary: a business date is measured
    #: on the organization's clock (`core/timezones.business_timezone`, which
    #: never reads this column), because a delivery does not change which day
    #: it happened on because somebody flew to London.
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: DEMO-008 §9 — when this account last authenticated successfully.
    #: Written by `AuthService.login`; never by a client. An administrator
    #: reviewing access needs to see a dormant account, and "never" is a
    #: meaningful answer, so it is nullable rather than defaulted to creation.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: DEMO-012 — the customer this login speaks for, or NULL for staff.
    #:
    #: A dairy's household signing in on the mobile app must see its own
    #: deliveries and its own bill and nothing else. Every `sales.*` permission
    #: is tenant-wide, so a customer granted `sales.invoice.read` to see their
    #: own bill would see every other household's too. This is the missing
    #: boundary: tenancy says which organization, this says which customer
    #: inside it.
    #:
    #: Referenced by id only, never joined — `customer` is another module's
    #: table (baseline rule 3). NULL for every existing account, which is why
    #: this is additive and changes nothing for staff.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailChange(Base, IdMixin):
    """A PENDING change of a login's email (WO-87 §3).

    Email is the login and the password-reset destination, so whoever can set
    it owns the account — which is why there is no route that writes
    `User.email` directly, from anybody. A change is requested here, the NEW
    address is sent a one-time code, the OLD address is told, and only the new
    address following through makes it real. Until then the old email signs
    in and nothing about the account has changed.

    Same shape and the same secrecy discipline as `Invitation` and
    `PasswordResetToken`: a hash of the code, never the code; the raw value
    goes to the mail channel only (SEC-003 / F-04). No `tenant_id` — the
    confirming caller is anonymous and discovers the tenant FROM the row, the
    argument `password_reset_token` already makes in `core/rls.py`.
    """

    __tablename__ = "email_change"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    new_email: Mapped[str] = mapped_column(String(320))
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
