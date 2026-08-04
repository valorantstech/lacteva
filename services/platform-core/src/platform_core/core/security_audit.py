"""Security audit trail (SEC-001).

Security events are recorded in the SAME immutable audit table as business
events, deliberately: an investigator reconstructing an incident should not
have to correlate two stores, and the audit trail's append-only guarantee
already holds. What this module adds is a fixed vocabulary of security actions
and a helper that writes them without a tenant context — because the most
important security events (a failed login, an unknown key) happen precisely
when there is no authenticated tenant to attribute them to.

Nothing here logs a credential, a token, or a key. Events name the SUBJECT and
the OUTCOME; the payload carries identifiers and reasons an operator can act
on, never material an attacker could use.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.tenancy import get_current_tenant
from platform_core.modules.audit.models import AuditRecord

log = structlog.get_logger("security.audit")

# The security vocabulary. Fixed, so alerting can be written against it.
LOGIN_SUCCEEDED = "security.login.succeeded"
LOGIN_FAILED = "security.login.failed"
TOKEN_REFRESHED = "security.token.refreshed"  # noqa: S105 - event name
TOKEN_REUSE_DETECTED = "security.token.reuse_detected"  # noqa: S105 - event name
LOGOUT = "security.logout"
PASSWORD_RESET_REQUESTED = "security.password_reset.requested"  # noqa: S105 - event name
PASSWORD_RESET_COMPLETED = "security.password_reset.completed"  # noqa: S105 - event name
PERMISSION_DENIED = "security.permission.denied"
RLS_DENIAL = "security.rls.denied"
KEY_ROTATED = "security.key.rotated"
RATE_LIMIT_EXCEEDED = "security.rate_limit.exceeded"
CONFIGURATION_CHANGED = "security.configuration.changed"


async def record_security_event(
    session: AsyncSession,
    *,
    action: str,
    subject: str,
    actor_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditRecord:
    """Append one security event.

    `subject` is what the event is ABOUT (an email, an ip, a permission key, a
    kid) rather than a resource id, because security events routinely concern
    things that are not platform resources at all.
    """
    ctx = structlog.contextvars.get_contextvars()
    record = AuditRecord(
        tenant_id=get_current_tenant(),  # may be None: pre-authentication events
        actor_id=actor_id,
        action=action,
        resource_type="security",
        resource_id=subject,
        detail=detail or {},
        request_id=ctx.get("request_id"),
    )
    session.add(record)
    # Also emit to the log stream: an attacker who reaches the database still
    # cannot erase what already left the host.
    log.info(
        "security_event",
        action=action,
        subject=subject,
        actor_id=str(actor_id) if actor_id else None,
        **{k: v for k, v in (detail or {}).items() if k != "password"},
    )
    return record
