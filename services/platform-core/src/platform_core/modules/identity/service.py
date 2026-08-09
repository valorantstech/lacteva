"""Identity module — application service (command/query handlers)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.security import hash_password
from platform_core.core.tenancy import get_current_tenant
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.identity.models import User
from platform_core.modules.identity.schemas import RegisterUserCommand


class IdentityService:
    def __init__(self, session: AsyncSession, bus: EventBus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit

    async def register_user(
        self, cmd: RegisterUserCommand, *, tenant_id: uuid.UUID | None = None
    ) -> User:
        tenant_id = tenant_id if tenant_id is not None else get_current_tenant()
        existing = await self._session.scalar(
            select(User).where(User.tenant_id == tenant_id, User.email == cmd.email.lower())
        )
        if existing is not None:
            raise ConflictError("user already exists")
        user = User(
            tenant_id=tenant_id,
            email=cmd.email.lower(),
            password_hash=hash_password(cmd.password),
            full_name=cmd.full_name,
            locale=cmd.locale,
        )
        self._session.add(user)
        await self._session.flush()
        await self._audit.record(
            action="identity.user.registered",
            resource_type="user",
            resource_id=user.id,
            actor_id=user.id,
        )
        # TODO(M1): outbox — see infrastructure/events.py.
        await self._bus.publish(
            EventEnvelope.new(
                "identity.user-registered.v1",
                {"user_id": str(user.id), "email": user.email},
                actor_id=user.id,
            )
        )
        return user

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self._session.get(User, user_id)
        if user is None:
            raise NotFoundError("user not found")
        return user

    async def get_by_email(self, email: str, tenant_id: uuid.UUID | None) -> User | None:
        return await self._session.scalar(
            select(User).where(User.tenant_id == tenant_id, User.email == email.lower())
        )

    async def get_in_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID | None) -> User:
        """Read a user that the caller's tenant is allowed to see.

        RLS makes another tenant's row invisible, so `get_user` would already
        answer 404 in production — but the test stack has no RLS, and the
        house rule is that the application filter is defence in depth rather
        than a formality. A user belonging to another organization is NOT
        FOUND here, never FORBIDDEN: 403 would confirm the account exists.
        """
        user = await self._session.get(User, user_id)
        if user is None or user.tenant_id != tenant_id:
            raise NotFoundError("user not found")
        return user

    async def set_active(
        self,
        user_id: uuid.UUID,
        *,
        active: bool,
        actor_id: uuid.UUID,
        tenant_id: uuid.UUID | None,
    ) -> User:
        """Deactivate or reactivate a user (SEC-003 / F-02).

        FINAL-001 found `is_active` enforced in five places and settable in
        none: an offboarded employee kept working credentials for as long as
        the account existed, because logout only ends the session they are
        holding and they can simply log in again.

        Deactivation does NOT delete anything. The audit trail, the
        collections they recorded and the settlements they finalized are
        business history and stay exactly as they are — this closes the door,
        it does not rewrite what happened while it was open.

        Revoking the live sessions is deliberately NOT done here: sessions
        belong to the auth module. `AuthService.set_user_active` is the one
        call that does both, and it is what the route uses.
        """
        user = await self.get_in_tenant(user_id, tenant_id)
        if user.is_active == active:
            return user  # idempotent: the same request twice is not an error
        user.is_active = active
        action = "identity.user.reactivated" if active else "identity.user.deactivated"
        await self._audit.record(
            action=action,
            resource_type="user",
            resource_id=user.id,
            actor_id=actor_id,
            detail={"email": user.email},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "identity.user-reactivated.v1" if active else "identity.user-deactivated.v1",
                {"user_id": str(user.id), "email": user.email},
                actor_id=actor_id,
            )
        )
        return user

    # TODO(M1): password reset (token + notification), email verification,
    # invitation-based org-scoped registration (the public register endpoint
    # creates platform-level users only).
