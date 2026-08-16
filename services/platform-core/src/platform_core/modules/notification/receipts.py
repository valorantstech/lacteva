"""Provider delivery receipts (DEMO-029).

The second unauthenticated write path in the platform, and it is built as a
copy of the first rather than as an alternative to it. DEMO-027 established how
an unauthenticated provider callback is made safe; DEMO-028 said that boundary
should be reused, and this is the reuse:

    POST /v1/notifications/receipts/{provider}
        signature verified   ─┐  (core/webhook_security — ONE mechanism)
        event id claimed      ├─  or nothing happens at all
        notification found   ─┘   by provider reference, never from the payload
        transition applied        only forwards, only from a verified receipt
        provider's word kept

Four things it never does, the same four the payment webhook never does.

*It never reads a tenant from the payload.* The tenant comes from the
`notification` row the provider reference names.

*It never creates a notification.* A receipt naming a reference this platform
does not know is dropped and nothing is recorded, so an unauthenticated
endpoint cannot be used to fill a table.

*It never acts twice.* `(provider, event_id)` is unique.

*It never moves a message backwards.* See `_next_status`.

And one thing specific to this milestone: **it never touches a business date.**
A receipt may arrive a day after the message — an invoice issued on 15 August
in India can be reported delivered on the 16th — and the notification keeps the
business dates of the event that produced it. Nothing here recomputes a period,
a settlement date or an invoice date from the arrival time of a gateway
callback.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from platform_core.core.db import utcnow
from platform_core.core.rls import platform_factory
from platform_core.modules.notification.models import (
    Notification,
    NotificationReceiptEvent,
)
from platform_core.modules.notification.providers import (
    DeliveryReceipt,
    ReceiptVerificationError,
    find_receipt_provider,
)

log = structlog.get_logger(__name__)


class UnknownReceiptProvider(Exception):
    """No provider by that name, or one that does not do receipts."""


@dataclass(frozen=True)
class ReceiptResult:
    """What the platform did about one delivery report."""

    outcome: str
    notification_id: uuid.UUID | None = None


#: Statuses that mean the platform never successfully handed the message over.
#:
#: Such a message has no provider reference, so no receipt can name it — this
#: is belt to that brace.
#:
#: Kept SEPARATE from the terminal-`delivered` rule below, and the separation
#: matters: the first draft folded `delivered` into this tuple as well, so the
#: explicit terminal check became dead code that still LOOKED load-bearing.
#: Mutation testing caught it — disabling the terminal rule failed no test —
#: and a future editor "simplifying" this tuple would have silently removed the
#: protection they thought was elsewhere.
_NEVER_SENT = ("pending", "dead")


def _next_status(current: str, reported: str) -> str | None:
    """The transition rule, in one place. `None` means "do not move".

    §4 asks for transitions that a duplicate or out-of-order callback cannot
    corrupt, and the two directions are not symmetric:

    * **`delivered` is terminal.** A later `failed` report does not undo an
      arrival, and `delivered → sent` is explicitly forbidden. Gateways
      routinely send an intermediate report after a final one; treating that as
      news would tell an operator a delivered message had un-delivered.

    * **`failed → delivered` IS allowed.** A gateway that reported a temporary
      failure and then delivered has told us something true and later, and
      refusing it would leave a farmer's message permanently recorded as failed
      when it arrived.

    * A report the adapter could not classify (`unknown`) moves nothing. It is
      still recorded, because "the gateway said something we cannot read" is
      worth an operator seeing.
    """
    if current == "delivered":
        return None  # terminal: nothing a later report says moves it
    if current in _NEVER_SENT:
        return None  # no verified send for a report to be about
    if reported == "delivered":
        return "delivered"
    if reported == "failed":
        return "failed" if current != "failed" else None
    return None  # unknown


async def process_receipt(
    *, provider_name: str, body: bytes, headers: dict[str, str], factory=None
) -> ReceiptResult:
    """Verify, de-duplicate and apply one delivery report.

    Raises `ReceiptVerificationError` (bad signature) or
    `UnknownReceiptProvider` — the route turns those into 401 and 404 without
    saying which check refused, because an attacker probing the endpoint learns
    from the difference.
    """
    provider = _provider(provider_name)
    receipt = provider.parse_receipt(body=body, headers=headers)

    sessions = factory or platform_factory("notification delivery receipt")
    async with sessions() as session:
        notification = await session.scalar(
            select(Notification).where(
                Notification.provider == provider.name,
                Notification.provider_reference == receipt.provider_reference,
            )
        )
        if notification is None:
            # Nothing recorded. There is no notification by that reference, so
            # no tenant to attribute the event to and nothing an attacker could
            # accumulate here.
            return ReceiptResult(outcome="unknown_reference")

        claimed = await _claim(
            session, notification=notification, provider=provider.name, receipt=receipt
        )
        if not claimed:
            await session.commit()
            return ReceiptResult(outcome="replayed", notification_id=notification.id)

        outcome = _apply(notification, receipt)
        await _stamp(session, provider.name, receipt.event_id, outcome)
        await session.commit()
        return ReceiptResult(outcome=outcome, notification_id=notification.id)


def _provider(name: str):
    """The named provider, if it exists AND does receipts.

    A provider without `parse_receipt` has no receipt endpoint at all — the
    platform does not invent a capability a gateway does not have.
    """
    provider = find_receipt_provider(name)
    if provider is None:
        raise UnknownReceiptProvider(name)
    return provider


async def _claim(
    session, *, notification: Notification, provider: str, receipt: DeliveryReceipt
) -> bool:
    """Claim this event id, or discover somebody already did.

    Returns False on a replay. The `add` sits INSIDE the savepoint — entering
    `begin_nested()` can autoflush the pending insert first, which would put
    the unique violation outside the savepoint and poison the transaction.
    That exact bug shipped in DEMO-025 and only real PostgreSQL found it.
    """
    row = NotificationReceiptEvent(
        tenant_id=notification.tenant_id,
        notification_id=notification.id,
        provider=provider,
        event_id=receipt.event_id,
        state=receipt.state,
        outcome="received",
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        return False
    return True


def _apply(notification: Notification, receipt: DeliveryReceipt) -> str:
    """Move the notification, or record that we deliberately did not.

    The provider's own word is kept on `provider_status` whatever happens: even
    a report that changes nothing is the gateway telling us something, and
    DEMO-028 added that column precisely so the two facts stay separate.
    """
    if receipt.provider_status:
        notification.provider_status = receipt.provider_status[:20]

    target = _next_status(notification.status, receipt.state)
    if target is None:
        log.info(
            "delivery_receipt_ignored",
            notification_id=str(notification.id),
            current=notification.status,
            reported=receipt.state,
        )
        return f"ignored_{notification.status}"

    notification.status = target
    if target == "delivered":
        notification.delivered_at = utcnow()
        notification.error = None
    else:
        notification.failed_at = utcnow()
        if receipt.reason:
            notification.error = receipt.reason[:500]
    return target


async def _stamp(session, provider: str, event_id: str, outcome: str) -> None:
    """Record what was DONE, so the ledger distinguishes 'acted on' from
    'recognised and correctly ignored'."""
    row = await session.scalar(
        select(NotificationReceiptEvent).where(
            NotificationReceiptEvent.provider == provider,
            NotificationReceiptEvent.event_id == event_id,
        )
    )
    if row is not None:
        row.outcome = outcome
        await session.flush()


__all__ = [
    "ReceiptResult",
    "ReceiptVerificationError",
    "UnknownReceiptProvider",
    "process_receipt",
]
