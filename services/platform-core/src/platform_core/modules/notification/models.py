"""Notification module — persistence models (NOT-001).

`Notification` is the aggregate AND the delivery history: one row per
(event, template, channel), carrying the rendered message, the provider that
handled it, every attempt, and the outcome. Nothing is deleted — a failed or
dead notification stays visible for operators.

`NotificationRecipient` is a rebuildable directory (a PLT-001 projection)
mapping a subject — today a supplier — to its contact details, so the
dispatch consumer never calls a business module to find out where to send.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

NOTIFICATION_STATUSES = ("pending", "sent", "failed", "dead")


class Notification(Base, IdMixin):
    __tablename__ = "notification"
    __table_args__ = (
        # Idempotency: one notification per (event, template, channel), so a
        # consumer replay or duplicate delivery can never re-send (BR-0016).
        UniqueConstraint("event_id", "template_key", "channel", name="uq_notification_event"),
        Index("ix_notification_retry", "status", "next_attempt_at"),
        Index("ix_notification_history", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    event_name: Mapped[str] = mapped_column(String(120))
    template_key: Mapped[str] = mapped_column(String(60), index=True)
    channel: Mapped[str] = mapped_column(String(10), index=True)  # sms | email
    language: Mapped[str] = mapped_column(String(8), default="en")
    # Who it is for: a subject reference (supplier/user id) and the resolved
    # address. The address may be filled in later by a retry once the
    # recipient directory has caught up.
    recipient_ref: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    recipient: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # template variables
    #: SEC-003 / F-04: template variables that are SECRETS — today, the
    #: one-time invitation token.
    #:
    #: They cannot live in `payload`, because `NotificationView` exposes it
    #: and an operator with `notification.read` could then harvest live
    #: invitation tokens from the delivery history — which would move F-04
    #: rather than close it. They cannot be left out either, because delivery
    #: retries re-render from the stored row and the token is a one-time
    #: secret that cannot be re-derived from its hash.
    #:
    #: So: a separate column, absent from every view and every API response,
    #: and CLEARED the moment the notification reaches a terminal state. A
    #: delivered invitation leaves no secret behind in the database or in any
    #: backup taken after it was sent.
    secret_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: The body as STORED, with any secret replaced by a marker. The body the
    #: provider was handed is the only place the real value ever appears.
    rendered_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationRecipient(Base, IdMixin):
    """Contact directory maintained by a projection from supplier events."""

    __tablename__ = "notification_recipient"
    __table_args__ = (
        UniqueConstraint("tenant_id", "subject_id", name="uq_notification_recipient"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    subject_type: Mapped[str] = mapped_column(String(20), default="supplier")
    display_name: Mapped[str] = mapped_column(String(200), default="")
    code: Mapped[str] = mapped_column(String(40), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    language: Mapped[str] = mapped_column(String(8), default="en")
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
