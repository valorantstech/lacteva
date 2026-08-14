"""Identity module — application service (command/query handlers)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import ConflictError, ForbiddenError, NotFoundError
from platform_core.core.org_context import tenant_locale
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

    async def set_language(self, user_id: uuid.UUID, tag: str) -> User:
        """A person chooses their own language (DEMO-013 §5).

        From what their ORGANIZATION has enabled, and nothing else. The
        organization decides which languages it operates in — a dairy that has
        not translated its process into Hindi does not want a supervisor's
        screen in Hindi and their manager's in English — and this is where
        that is enforced, because it is the only place the choice is made.

        The refusal is a 403 rather than a 404: the language exists, this
        organization has not enabled it, and telling the person that is useful
        rather than dangerous. It leaks nothing about another tenant.
        """
        user = await self._session.get(User, user_id)
        if user is None:
            raise NotFoundError("user not found")
        settings = await tenant_locale(self._session, user.tenant_id)
        if tag not in settings.supported_languages:
            raise ForbiddenError(
                f"{tag!r} is not one of this organization's languages "
                f"({', '.join(settings.supported_languages)})"
            )
        user.locale = tag
        await self._session.flush()
        await self._audit.record(
            action="identity.language.changed",
            resource_type="user",
            resource_id=user.id,
            actor_id=user_id,
            detail={"locale": tag},
        )
        return user

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

    #: How many accounts one address may have before login stops trying them.
    #: A bound, not a business rule: each candidate costs a password hash
    #: verification, and an unbounded list is a way to make one request
    #: expensive.
    LOGIN_CANDIDATE_LIMIT = 5

    async def candidates_for_login(self, email: str) -> list[User]:
        """Every account this address could sign in as, across organizations.

        DEMO-010. The login form asked a dairy owner to paste their
        organization's UUID, because `get_by_email` matches on `tenant_id` and
        a tenant-scoped account is invisible without it. Nobody knows their
        tenant UUID; it was the first thing on the first screen of the demo.

        This is a DELIBERATE, NARROW cross-tenant read — the only one in the
        authentication path — and it grants nothing on its own. It returns
        candidates; `AuthService.login` still has to verify a password against
        one of them, and a caller who names no organization and knows no
        password learns exactly what they learned before: `invalid_credentials`.

        Ordered platform account first, so an address that is both a platform
        administrator and a tenant member keeps its previous behaviour.
        """
        from platform_core.core.rls import bind_platform_context

        await bind_platform_context(
            self._session, reason="login: find which organizations this address belongs to"
        )
        rows = (
            await self._session.scalars(
                select(User)
                .where(User.email == email.lower(), User.is_active.is_(True))
                .order_by(User.tenant_id.is_not(None), User.created_at)
                .limit(self.LOGIN_CANDIDATE_LIMIT)
            )
        ).all()
        return list(rows)

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
