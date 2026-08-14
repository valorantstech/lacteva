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
