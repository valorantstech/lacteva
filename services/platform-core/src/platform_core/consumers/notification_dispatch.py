"""Notification dispatch consumer (NOT-001).

The ONLY path from a business fact to a message. It consumes durable domain
events and asks the notification dispatcher for a template-rendered send —
it never calls a business module, never reads a business table, and never
writes a message string of its own.

Mapping an event to a notification is declarative: each entry names the
template, the channel, how to find the recipient, and which variables the
template needs. Adding a notification for a new event is one entry here plus
one template — no changes anywhere in the producing module.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.infrastructure.events import EventEnvelope
from platform_core.modules.event_relay.consumers import EventConsumer, register_consumer
from platform_core.modules.notification.service import NotificationRequest, NotificationService

# Event names as the platform actually emits them (the work order's names map
# onto these): supplier.created -> supplier-registered, supplier.archived ->
# supplier-status-changed(to=archived), invitation.accepted -> member-added,
# milk.transaction-rejected -> collection.transaction-rejected.
SUPPLIER_REGISTERED = "supplier.supplier-registered.v1"
SUPPLIER_STATUS_CHANGED = "supplier.supplier-status-changed.v1"
SETTLEMENT_FINALIZED = "settlement.finalized.v1"
PAYMENT_COMPLETED = "payment.completed.v1"  # emitted by PAY-001
RECEIPT_GENERATED = "receipt.generated.v1"  # emitted by RCP-001
PASSWORD_RESET_REQUESTED = "identity.password-reset-requested.v1"  # noqa: S105
INVITATION_ISSUED = "organization.invitation-issued.v1"
MEMBER_ADDED = "organization.member-added.v1"
TRANSACTION_REJECTED = "collection.transaction-rejected.v1"


@dataclass(frozen=True)
class EventMapping:
    template_key: str
    channel: str
    build: Callable[[EventEnvelope], dict | None]  # None = this event needs no message


def _supplier_registered(envelope: EventEnvelope) -> dict | None:
    data = envelope.data
    return {
        "recipient_ref": _uuid(data.get("supplier_id")),
        "recipient": data.get("phone"),
        "language": data.get("locale"),
        "variables": {
            "name": data.get("full_name") or "supplier",
            "code": data.get("code", ""),
            "organization": data.get("organization", "Lacteva"),
        },
    }


def _supplier_archived(envelope: EventEnvelope) -> dict | None:
    data = envelope.data
    if data.get("to") != "archived":
        return None  # only the archival transition notifies
    return {
        "recipient_ref": _uuid(data.get("supplier_id")),
        "variables": {"code": data.get("code", "")},
    }


def _settlement_finalized(envelope: EventEnvelope) -> dict | None:
    data = envelope.data
    return {
        "recipient_ref": _uuid(data.get("supplier_id")),
        "variables": {
            "number": data.get("settlement_number", ""),
            "net_amount": data.get("net_amount", ""),
            "currency": data.get("currency", ""),
            "line_count": data.get("line_count", 0),
        },
    }


def _payment_completed(envelope: EventEnvelope) -> dict | None:
    data = envelope.data
    return {
        "recipient_ref": _uuid(data.get("supplier_id")),
        "variables": {
            "amount": data.get("amount", ""),
            "currency": data.get("currency", ""),
            "number": data.get("settlement_number", ""),
            "reference": data.get("reference", ""),
        },
    }


def _receipt_generated(envelope: EventEnvelope) -> dict | None:
    data = envelope.data
    return {
        "recipient_ref": _uuid(data.get("supplier_id")),
        "variables": {
            "number": data.get("receipt_number", ""),
            "amount": data.get("amount", ""),
            "currency": data.get("currency", ""),
        },
    }


def _password_reset(envelope: EventEnvelope) -> dict | None:
    data = envelope.data
    return {
        "recipient_ref": _uuid(data.get("user_id")),
        "recipient": data.get("email"),
        "language": data.get("locale"),
        "variables": {"expires_hours": data.get("expires_hours", 2)},
    }


def _invitation_issued(envelope: EventEnvelope) -> dict | None:
    data = envelope.data
    return {
        "recipient": data.get("email"),
        "variables": {
            "role": data.get("role", ""),
            "organization": data.get("organization", "Lacteva"),
            "expires_days": data.get("expires_days", 7),
        },
    }


def _member_added(envelope: EventEnvelope) -> dict | None:
    data = envelope.data
    return {
        "recipient_ref": _uuid(data.get("user_id")),
        "recipient": data.get("email"),
        "language": data.get("locale"),
        "variables": {
            "role": data.get("role", ""),
            "organization": data.get("organization", "Lacteva"),
        },
    }


def _transaction_rejected(envelope: EventEnvelope) -> dict | None:
    data = envelope.data
    if not data.get("supplier_id"):
        return None  # unidentified delivery — nobody to notify
    return {
        "recipient_ref": _uuid(data.get("supplier_id")),
        "variables": {
            "reason": data.get("reason", "quality"),
            "date": envelope.time[:10],
        },
    }


MAPPINGS: dict[str, EventMapping] = {
    SUPPLIER_REGISTERED: EventMapping("supplier_registered", "sms", _supplier_registered),
    SUPPLIER_STATUS_CHANGED: EventMapping("supplier_archived", "sms", _supplier_archived),
    SETTLEMENT_FINALIZED: EventMapping("settlement_finalized", "sms", _settlement_finalized),
    PAYMENT_COMPLETED: EventMapping("payment_completed", "sms", _payment_completed),
    RECEIPT_GENERATED: EventMapping("receipt_available", "sms", _receipt_generated),
    PASSWORD_RESET_REQUESTED: EventMapping("password_reset", "email", _password_reset),
    INVITATION_ISSUED: EventMapping("invitation", "email", _invitation_issued),
    MEMBER_ADDED: EventMapping("invitation_accepted", "email", _member_added),
    TRANSACTION_REJECTED: EventMapping("milk_rejected", "sms", _transaction_rejected),
}


class NotificationDispatchConsumer(EventConsumer):
    name = "notification-dispatch"
    event_types = tuple(MAPPINGS)

    async def handle(self, envelope: EventEnvelope, session: AsyncSession) -> None:
        mapping = MAPPINGS[envelope.type]
        built = mapping.build(envelope)
        if built is None:
            return
        await NotificationService(session).dispatch(
            NotificationRequest(
                event_id=envelope.id,
                event_name=envelope.type,
                tenant_id=envelope.tenant_id,
                template_key=mapping.template_key,
                channel=mapping.channel,
                **built,
            )
        )


def _uuid(value) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


register_consumer(NotificationDispatchConsumer())
