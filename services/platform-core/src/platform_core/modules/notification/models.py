"""Notification module — persistence models (NOT-001).

`Notification` is the aggregate AND the delivery history: one row per
(event, template, channel), carrying the rendered message, the provider that
handled it, every attempt, and the outcome. Nothing is deleted — a failed or
dead notification stays visible for operators.

`NotificationRecipient` is a rebuildable directory (a PLT-001 projection)
mapping a subject — today a supplier — to its contact details, so the
dispatch consumer never calls a business module to find out where to send.

`NotificationDevice` (DEMO-012 §10) is the same idea for the `push` channel:
a phone's delivery token, registered by the mobile app after sign-in. It is
NOT a projection — nothing else in the platform knows a device exists — so it
is the one contact record here that is authoritative rather than rebuildable.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

#: What LACTEVA knows about a message.
#:
#: `delivered` is new in DEMO-029 and is reachable ONLY from a signature-
#: verified provider receipt — never from a send, never from a timer, never
#: from a client. That is the same rule DEMO-027 applied to `past_due`: a state
#: the platform can set but never verify is a state it must not have.
#:
#: The vocabulary maps onto the work order's lifecycle rather than replacing
#: it: `pending` is QUEUED, `sent` is SENT, `failed`/`dead` are FAILED.
#: `dead` is failure the platform has stopped retrying.
#:
#: There is no `read`. No gateway this platform speaks to reports one.
NOTIFICATION_STATUSES = ("pending", "sent", "delivered", "failed", "dead")


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
    #: The PLATFORM's status: what Lacteva did. `sent` means the provider
    #: accepted the request — it does NOT mean anything arrived.
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: DEMO-028. The PROVIDER's own claim: `accepted` | `sent` | `delivered` |
    #: `unknown`, exactly as the adapter reported it.
    #:
    #: It was being thrown away. `DeliveryResult.status` has carried this since
    #: MSG-001 and nothing stored it, so the platform could not distinguish "the
    #: gateway took the request" from "the gateway says it arrived" even when a
    #: gateway said so — and the portal called all of it "Delivered". Two
    #: different facts need two columns; one column is how the exaggeration
    #: happened.
    provider_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    #: DEMO-028. The business record this message is ABOUT.
    #:
    #: `event_id` says which event produced it, which is the idempotency key
    #: and not an answer to "what did settlement STL-000123 tell this farmer?" —
    #: that question had to be answered through `event_outbox` payloads. These
    #: two columns make it one query, which is what §11 means by auditable.
    source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: DEMO-029. When the PROVIDER said it arrived — not when we sent it, and
    #: null unless a verified receipt said so.
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


#: What a device says it is. Constrained because the provider payload differs
#: per platform and an unknown value would be sent to a gateway that cannot
#: use it.
DEVICE_PLATFORMS = ("android", "ios", "web")


class NotificationDevice(Base, IdMixin):
    """A phone that can be reached by push (DEMO-012 §10).

    One row per (tenant, delivery token). The token is the ADDRESS, not a
    credential the platform holds on the user's behalf — but it is still
    capability-like: anyone holding it can push to that handset through a
    configured gateway. So it is never returned by any view, never logged in
    full, and is deleted rather than kept when a device is revoked. There is
    no history to preserve: a revoked token is not evidence of anything.

    Tokens rotate. The unique constraint is on the token, and registering a
    token already held by another user MOVES it, because that is what actually
    happened — the handset was signed into a different account and the old
    owner must stop receiving its notifications immediately.
    """

    __tablename__ = "notification_device"
    __table_args__ = (
        UniqueConstraint("token", name="uq_notification_device_token"),
        Index("ix_notification_device_user", "tenant_id", "user_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    #: The gateway's delivery token for this installation.
    token: Mapped[str] = mapped_column(String(400))
    #: DEMO-012: the customer this handset speaks for, when the login is a
    #: customer-scoped one. Copied from the authenticated principal by the API
    #: layer — the notification module never reads an identity table, it is
    #: told. It is what lets a bill-issued event, which knows a customer and
    #: not a user, find a phone.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    platform: Mapped[str] = mapped_column(String(10), default="android")
    #: Free-form, for an operator looking at a support call. Never trusted.
    label: Mapped[str] = mapped_column(String(80), default="")
    language: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class NotificationReceiptEvent(Base, IdMixin):
    """Every provider delivery report this platform has already acted on.

    **The replay defence, and it is a unique constraint rather than a check.**
    A gateway redelivering a report it is unsure landed is normal operation —
    every one of them does it — so the second delivery must do nothing at all.

    The shape is DEMO-027's `subscription_payment_event`, deliberately: that
    milestone established how an unauthenticated provider callback is made
    safe, and a second shape for the same idea is how two boundaries drift
    apart. What differs is only what the event is about.

    `tenant_id` is filled from the NOTIFICATION the reference names, never from
    the payload — an unauthenticated caller naming a tenant is the whole
    attack.
    """

    __tablename__ = "notification_receipt_event"
    __table_args__ = (
        # The replay key. A gateway's event id is unique per provider.
        UniqueConstraint("provider", "event_id", name="uq_notification_receipt_event"),
        Index("ix_notification_receipt_notification", "notification_id"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    provider: Mapped[str] = mapped_column(String(40))
    event_id: Mapped[str] = mapped_column(String(160))
    #: The normalised state the receipt reported: delivered | failed | unknown.
    state: Mapped[str] = mapped_column(String(20))
    #: What the platform DID about it, so an operator reading this table can
    #: tell "acted on" from "recognised and correctly ignored".
    outcome: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
