"""Organization module — persistence model.

An Organization IS the tenant: its id is the tenant_id used across the
platform (realizes the business rule that a tenant is a verified dairy
business — ETE.ONB.01 at business level).
"""

from datetime import datetime

from sqlalchemy import DateTime, String
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
