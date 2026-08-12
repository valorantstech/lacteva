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
    locale: Mapped[str] = mapped_column(String(8), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: DEMO-008 §9 — when this account last authenticated successfully.
    #: Written by `AuthService.login`; never by a client. An administrator
    #: reviewing access needs to see a dormant account, and "never" is a
    #: meaningful answer, so it is nullable rather than defaulted to creation.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
