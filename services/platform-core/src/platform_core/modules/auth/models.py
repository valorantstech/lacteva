"""Authentication module — persistence models.

Sessions are the server-side anchor of authentication: access tokens carry a
session id (`sid`) and die with it; refresh tokens are opaque secrets stored
hashed, rotated on every use. Presenting a *previous* (already-rotated) token
is treated as theft and revokes the session.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow


class AuthSession(Base, IdMixin):
    __tablename__ = "auth_session"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    previous_token_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # TODO(M2): user_agent/device fields for a "my sessions" listing.


class PasswordResetToken(Base, IdMixin):
    __tablename__ = "password_reset_token"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
