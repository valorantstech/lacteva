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

    # TODO(M1): deactivate_user, password reset (token + notification),
    # email verification, invitation-based org-scoped registration (the
    # public register endpoint creates platform-level users only).
