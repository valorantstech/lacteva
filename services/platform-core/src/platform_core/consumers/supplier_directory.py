"""Recipient directory projection (NOT-001).

Maintains contact details for notification subjects from supplier events, so
the dispatch consumer can resolve "where do I send this?" WITHOUT calling a
business module. It is a PLT-001 projection: rebuildable from the log, and
verifiable for drift like any other read model.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.infrastructure.events import EventEnvelope
from platform_core.modules.event_relay.projections import Projection, register_projection
from platform_core.modules.notification.models import NotificationRecipient

SUPPLIER_REGISTERED = "supplier.supplier-registered.v1"
SUPPLIER_STATUS_CHANGED = "supplier.supplier-status-changed.v1"


class SupplierDirectoryProjection(Projection):
    name = "notification-recipient-directory"
    version = 1
    owner_module = "notification"
    description = "Contact directory (name, phone, email, language) for notification subjects."
    event_types = (SUPPLIER_REGISTERED, SUPPLIER_STATUS_CHANGED)
    rebuild_strategy = "full-replay"
    replay_order = 5  # before dispatch-dependent projections
    models = (NotificationRecipient,)

    async def handle(self, envelope: EventEnvelope, session: AsyncSession) -> None:
        data = envelope.data
        if envelope.tenant_id is None or not data.get("supplier_id"):
            return
        subject_id = uuid.UUID(data["supplier_id"])
        entry = await session.scalar(
            select(NotificationRecipient).where(
                NotificationRecipient.tenant_id == envelope.tenant_id,
                NotificationRecipient.subject_id == subject_id,
            )
        )
        if entry is None:
            entry = NotificationRecipient(
                tenant_id=envelope.tenant_id, subject_id=subject_id, subject_type="supplier"
            )
            session.add(entry)
            await session.flush()
        if envelope.type == SUPPLIER_REGISTERED:
            entry.display_name = data.get("full_name") or entry.display_name
            entry.code = data.get("code") or entry.code
            entry.phone = data.get("phone") or entry.phone
            entry.email = data.get("email") or entry.email
            entry.language = data.get("locale") or entry.language
        else:  # status change
            entry.active = data.get("to") not in ("archived", "suspended")


register_projection(SupplierDirectoryProjection())
