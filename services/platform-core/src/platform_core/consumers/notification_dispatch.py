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
from platform_core.modules.notification.service import (
    NotificationRequest,
    NotificationService,
    resolve_channel,
)

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
MEMBER_ADDED = "organization.member-added.v1"
TRANSACTION_REJECTED = "collection.transaction-rejected.v1"
# DEMO-012 §10 — the customer-facing half, delivered to the mobile app.
INVOICE_ISSUED = "sales.invoice-issued.v1"
CUSTOMER_PAYMENT_RECORDED = "sales.customer-payment-recorded.v1"


def _non_zero(value) -> str:
    """A money string, or empty when it is zero (DEMO-028).

    Optional template segments drop on an empty value, so this is how a line
    that only matters when it is non-zero disappears when it is not.
    """
    if value is None:
        return ""
    try:
        from decimal import Decimal

        return "" if Decimal(str(value)) == 0 else str(value)
    except (ArithmeticError, ValueError):
        return ""


@dataclass(frozen=True)
class EventMapping:
    template_key: str
    channel: str
    build: Callable[[EventEnvelope], dict | None]  # None = this event needs no message
    #: May a tenant choose a different channel for this message? (DEMO-025)
    #:
    #: True for BUSINESS messages a dairy sends its farmers and customers.
    #: False for platform messages — a password reset is an email because the
    #: reset link goes to an inbox, and a tenant electing to SMS it would be
    #: changing a security decision rather than a delivery preference.
    selectable: bool = False


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
        # DEMO-028: which settlement this slip is about, so "what did STL-000123
        # tell this farmer?" is one query rather than a walk through the outbox.
        "source_type": "settlement",
        "source_id": _uuid(data.get("settlement_id")),
        "variables": {
            "number": data.get("settlement_number", ""),
            # DEMO-028: how much milk. OPTIONAL in the template — an event
            # published before this milestone carries none, and the slip then
            # reads exactly as it did rather than failing to render.
            "quantity": data.get("quantity", ""),
            "quantity_unit": data.get("quantity_unit", ""),
            # Both figures, read from the settlement. Nothing here computes
            # money — the slip reports a settlement that already exists.
            "gross_amount": data.get("gross_amount", ""),
            "net_amount": data.get("net_amount", ""),
            "currency": data.get("currency", ""),
            "line_count": data.get("line_count", 0),
            # BUSINESS dates, carried on the event (DEMO-025).
            "period_from": data.get("period_from", ""),
            "period_to": data.get("period_to", ""),
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


def _invoice_issued(envelope: EventEnvelope) -> dict | None:
    """A household's bill is ready.

    The recipient reference is the CUSTOMER, not a user: this event has never
    heard of a user account, and the device registry knows which handset a
    customer-scoped login registered. A household with no mobile login
    resolves to no device and the notification fails visibly in the history
    rather than being silently dropped here — which is the difference between
    "nobody has the app" and "the push channel is broken", and an operator
    needs to be able to tell those apart.
    """
    data = envelope.data
    period_from = data.get("period_from", "")
    period_to = data.get("period_to", "")
    return {
        "recipient_ref": _uuid(data.get("customer_id")),
        "source_type": "customer_invoice",
        "source_id": _uuid(data.get("invoice_id")),
        # A household has no directory entry — the directory is built from
        # supplier events and customers emit none. The event carries the
        # number instead (DEMO-025).
        "recipient": data.get("phone") or None,
        "variables": {
            "name": data.get("customer_name") or "customer",
            "number": data.get("invoice_number", ""),
            "amount": data.get("amount_due", ""),
            # DEMO-028. Both OPTIONAL, and both authoritative on the invoice.
            #
            # `amount_due` is this period's total PLUS anything carried
            # forward. A household with a balance was shown one number that
            # matched neither, with no way to tell which — the two lines below
            # are what make the bill explicable. A zero carried balance renders
            # nothing, because "brought forward: 0.00" is noise.
            "quantity": data.get("quantity", ""),
            "quantity_unit": data.get("quantity_unit", ""),
            "previous_balance": _non_zero(data.get("previous_balance")),
            "currency": data.get("currency", ""),
            "period_from": period_from,
            "period_to": period_to,
            # The push templates still say `{period}`. It is now built from
            # the invoice's own BUSINESS dates rather than from a slice of a
            # UTC timestamp, which named the wrong day for any dairy east of
            # UTC billing late in its own evening (DEMO-025).
            "period": f"{period_from} - {period_to}" if period_from else envelope.time[:10],
        },
    }


def _customer_payment_recorded(envelope: EventEnvelope) -> dict | None:
    data = envelope.data
    return {
        "recipient_ref": _uuid(data.get("customer_id")),
        "variables": {"number": data.get("payment_number", "")},
    }


MAPPINGS: dict[str, EventMapping] = {
    SUPPLIER_REGISTERED: EventMapping("supplier_registered", "sms", _supplier_registered),
    SUPPLIER_STATUS_CHANGED: EventMapping("supplier_archived", "sms", _supplier_archived),
    SETTLEMENT_FINALIZED: EventMapping(
        "settlement_finalized", "sms", _settlement_finalized, selectable=True
    ),
    PAYMENT_COMPLETED: EventMapping("payment_completed", "sms", _payment_completed),
    RECEIPT_GENERATED: EventMapping("receipt_available", "sms", _receipt_generated),
    PASSWORD_RESET_REQUESTED: EventMapping("password_reset", "email", _password_reset),
    # SEC-003 / F-04: `INVITATION_ISSUED` is deliberately NOT mapped here.
    # The invitation email carries a one-time token, and a consumer can only
    # read what the event payload carries — which would put that token in
    # `event_outbox`, a table that is never pruned and is in every backup.
    # `InvitationService._send_invitation` sends it instead, through this same
    # NotificationService, with the token as a secret variable. The event is
    # still published: it is the record that an invitation was issued, and
    # other consumers may read it.
    MEMBER_ADDED: EventMapping("invitation_accepted", "email", _member_added),
    TRANSACTION_REJECTED: EventMapping("milk_rejected", "sms", _transaction_rejected),
    # DEMO-025: the DEFAULT stays `push`, and that is deliberate. DEMO-012
    # built the push journey for households that have the app, and changing
    # the default would have silently taken it away from them. What DEMO-025
    # adds is the ABILITY to reach the households that do not — a dairy sets
    # `notification.channel.invoice_issued` to `sms` or `whatsapp` and its
    # bills go there instead. New capability, no behaviour removed.
    INVOICE_ISSUED: EventMapping("invoice_issued", "push", _invoice_issued, selectable=True),
    CUSTOMER_PAYMENT_RECORDED: EventMapping(
        "customer_payment_recorded", "push", _customer_payment_recorded
    ),
}


class NotificationDispatchConsumer(EventConsumer):
    name = "notification-dispatch"
    event_types = tuple(MAPPINGS)

    async def handle(self, envelope: EventEnvelope, session: AsyncSession) -> None:
        mapping = MAPPINGS[envelope.type]
        built = mapping.build(envelope)
        if built is None:
            return
        # DEMO-025: the tenant may prefer a different channel for this kind of
        # message. Resolved from configuration, never from the country — an
        # Indian dairy on WhatsApp and a Kenyan one on SMS differ by a row.
        channel = (
            await resolve_channel(
                session, mapping.template_key, mapping.channel, envelope.tenant_id
            )
            if mapping.selectable
            else mapping.channel
        )
        await NotificationService(session).dispatch(
            NotificationRequest(
                event_id=envelope.id,
                event_name=envelope.type,
                tenant_id=envelope.tenant_id,
                template_key=mapping.template_key,
                channel=channel,
                **built,
            )
        )


def _uuid(value) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


register_consumer(NotificationDispatchConsumer())
