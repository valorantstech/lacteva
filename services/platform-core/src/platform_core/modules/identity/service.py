"""Identity module — application service (command/query handlers)."""

import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from platform_core.core.locales import is_valid_timezone
from platform_core.core.org_context import tenant_locale
from platform_core.core.security import hash_password
from platform_core.core.tenancy import get_current_tenant
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.identity.models import EmailChange, User
from platform_core.modules.identity.schemas import RegisterUserCommand

#: WO-87 §3: a pending email change is good for a day. Long enough for a
#: delivery boy to find the message on a phone that is out all morning; short
#: enough that a request nobody followed is forgotten by tomorrow.
EMAIL_CHANGE_TTL = timedelta(hours=24)


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

    async def set_timezone(self, user_id: uuid.UUID, timezone: str | None) -> User:
        """A person chooses the clock they READ timestamps in (DEMO-014 §4).

        Display only. It never moves a business date — `core/timezones` keeps
        that boundary by not taking a user at all — because a delivery does
        not change which day it happened on because somebody flew to London.

        `None` means "my organization's", which is the default and the answer
        for almost everyone. A zone that is not IANA is refused rather than
        stored: an unusable value here would silently fall back forever, and
        the person would never learn their setting had not taken.
        """
        user = await self._session.get(User, user_id)
        if user is None:
            raise NotFoundError("user not found")
        if timezone is not None and not is_valid_timezone(timezone):
            raise ValidationError(f"{timezone!r} is not an IANA timezone")
        user.timezone = timezone
        await self._session.flush()
        await self._audit.record(
            action="identity.timezone.changed",
            resource_type="user",
            resource_id=user.id,
            actor_id=user_id,
            detail={"timezone": timezone},
        )
        return user

    async def login_for_customer(self, customer_id: uuid.UUID) -> User | None:
        """The account bound to this customer in the current tenant, if any
        (WO-86). One household, one login: `CustomerAccessService.invite`
        refuses a second invitation while this returns a row."""
        tenant_id = get_current_tenant()
        if tenant_id is None:
            return None
        return await self._session.scalar(
            select(User)
            .where(User.tenant_id == tenant_id, User.customer_id == customer_id)
            .order_by(User.created_at)
            .limit(1)
        )

    async def register_user(
        self, cmd: RegisterUserCommand, *, tenant_id: uuid.UUID | None = None
    ) -> User:
        tenant_id = tenant_id if tenant_id is not None else get_current_tenant()
        existing = await self._session.scalar(
            select(User).where(User.tenant_id == tenant_id, User.email == cmd.email.lower())
        )
        if existing is not None:
            raise ConflictError("user already exists")
        # DEMO-013: a new member starts in their ORGANIZATION's default
        # language, not the bare `en` the command defaults to.
        #
        # Both are English for every tenant today, so nothing reads
        # differently — but `en` is not among an Indian dairy's supported
        # tags (`en-IN`, `hi-IN`), so the language chooser highlighted nothing
        # until the person picked one, and a future tenant defaulting to Hindi
        # would have had every new member start in English.
        #
        # A platform-level registration has no tenant and keeps `en`.
        locale = cmd.locale
        if tenant_id is not None and locale == RegisterUserCommand.model_fields["locale"].default:
            locale = (await tenant_locale(self._session, tenant_id)).default_language
        user = User(
            tenant_id=tenant_id,
            email=cmd.email.lower(),
            password_hash=hash_password(cmd.password),
            full_name=cmd.full_name,
            locale=locale,
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

    # --- WO-87: a login's details can be corrected --------------------------

    async def set_full_name(
        self,
        user_id: uuid.UUID,
        full_name: str,
        *,
        actor_id: uuid.UUID,
        tenant_id: uuid.UUID | None,
    ) -> User:
        """Correct a name (WO-87 §1, §2).

        A person may correct their OWN name with no permission — it is their
        name on their screen, the argument `set_language` makes — and a tenant
        admin may correct a member's, behind `organization.member.manage`
        (the route holds the gate). Both are audited with before and after,
        because a name is on every audit line and every screen, and "who
        changed it" is the first question when it looks wrong.

        A typo fix, not an identity change: the account, its sessions, its
        history are untouched. Email is a different animal (`request_email_change`).
        """
        user = await self.get_in_tenant(user_id, tenant_id)
        before = user.full_name
        after = full_name.strip()
        if not after:
            raise ValidationError("a name cannot be blank")
        if before == after:
            return user
        user.full_name = after
        await self._session.flush()
        await self._audit.record(
            action="identity.name.changed",
            resource_type="user",
            resource_id=user.id,
            actor_id=actor_id,
            detail={"before": before, "after": after, "self": actor_id == user.id},
        )
        return user

    async def pending_email_change(self, user_id: uuid.UUID) -> EmailChange | None:
        """The one live request for this user, or None. Expired, completed
        and revoked rows are history, not a pending change."""
        row = await self._session.scalar(
            select(EmailChange)
            .where(
                EmailChange.user_id == user_id,
                EmailChange.completed_at.is_(None),
                EmailChange.revoked_at.is_(None),
            )
            .order_by(EmailChange.requested_at.desc())
            .limit(1)
        )
        if row is None or as_utc(row.expires_at) < utcnow():
            return None
        return row

    async def request_email_change(
        self,
        user_id: uuid.UUID,
        new_email: str,
        *,
        actor_id: uuid.UUID,
        tenant_id: uuid.UUID | None,
    ) -> EmailChange:
        """Start an email change (WO-87 §3). Nothing about the account changes
        here: a pending row is written, the NEW address is sent the one-time
        code, and the OLD address is told — naming the new address and how to
        stop it. That notice is the whole security argument: a stolen session
        can start a change, and the real owner finds out while the old
        address still signs in.

        One pending change per user: asking again replaces it (the earlier
        code stops working) and re-notifies. A tenant admin reaches a user
        only through `get_in_tenant`, so another tenant's user and a
        platform-level account (tenant NULL) are both NOT FOUND, never
        forbidden — 403 would confirm the account exists.

        The raw code is returned to the CALLER only so the route can refuse to
        return it; it goes to the mail channel and nowhere else (SEC-003 /
        F-04): not the response, not the outbox, not a log.
        """
        user = await self.get_in_tenant(user_id, tenant_id)
        address = new_email.strip().lower()
        if address == user.email.lower():
            raise ValidationError("that is already this login's email")
        taken = await self._session.scalar(
            select(User).where(User.tenant_id == user.tenant_id, User.email == address)
        )
        if taken is not None:
            raise ConflictError("another login already uses that email")
        previous = await self.pending_email_change(user.id)
        if previous is not None:
            previous.revoked_at = utcnow()
        raw = secrets.token_urlsafe(32)
        change = EmailChange(
            user_id=user.id,
            new_email=address,
            requested_by=actor_id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=utcnow() + EMAIL_CHANGE_TTL,
        )
        self._session.add(change)
        await self._session.flush()
        await self._audit.record(
            action="identity.email-change.requested",
            resource_type="user",
            resource_id=user.id,
            actor_id=actor_id,
            detail={
                "new_email": address,
                "replaces": str(previous.id) if previous is not None else None,
                "self": actor_id == user.id,
            },
        )
        await self._bus.publish(
            EventEnvelope.new(
                "identity.email-change-requested.v1",
                {"user_id": str(user.id), "new_email": address},
                actor_id=actor_id,
            )
        )
        await self._send_email_change(change, user, raw)
        return change

    async def cancel_email_change(
        self,
        user_id: uuid.UUID,
        *,
        actor_id: uuid.UUID,
        tenant_id: uuid.UUID | None,
    ) -> EmailChange | None:
        """Stop a pending change (WO-87 §3): by the person, or by a tenant
        admin — the "how to stop it" the old address was told about. Idempotent:
        nothing pending is not an error, it is the state the caller wanted."""
        user = await self.get_in_tenant(user_id, tenant_id)
        change = await self.pending_email_change(user.id)
        if change is None:
            return None
        change.revoked_at = utcnow()
        await self._audit.record(
            action="identity.email-change.cancelled",
            resource_type="user",
            resource_id=user.id,
            actor_id=actor_id,
            detail={"new_email": change.new_email, "self": actor_id == user.id},
        )
        return change

    async def _organization_name(self, tenant_id: uuid.UUID | None) -> str:
        if tenant_id is None:
            return "Lacteva"
        from platform_core.modules.organization.models import Organization

        organization = await self._session.get(Organization, tenant_id)
        return organization.name if organization is not None else "Lacteva"

    async def _send_email_change(self, change: EmailChange, user: User, raw_token: str) -> None:
        """Two messages, sent from here for the reason `_send_invitation` and
        `_send_reset_code` give (SEC-003 / F-04): the consumer reads the
        durable outbox, and a live code must never be written there.

        To the NEW address: the code, as a secret variable. To the OLD address:
        no secret at all — the new address, who asked, and how to stop it.
        """
        from platform_core.modules.notification.links import email_change_link, portal_url
        from platform_core.modules.notification.service import (
            NotificationRequest,
            NotificationService,
        )

        organization = await self._organization_name(user.tenant_id)
        expires_hours = int(EMAIL_CHANGE_TTL.total_seconds() // 3600)
        service = NotificationService(self._session)
        await service.dispatch(
            NotificationRequest(
                event_id=change.id,
                event_name="identity.email-change-requested.v1",
                tenant_id=user.tenant_id,
                template_key="email_change_confirm",
                channel="email",
                recipient=change.new_email,
                recipient_ref=user.id,
                language=user.locale,
                variables={
                    "organization": organization,
                    "expires_hours": expires_hours,
                    "portal_url": portal_url(),
                },
                # WO-100: the link carries the token, so it is a secret too.
                secret_variables={
                    "change_token": raw_token,
                    "change_link": email_change_link(raw_token),
                },
            )
        )
        await service.dispatch(
            NotificationRequest(
                event_id=change.id,
                event_name="identity.email-change-requested.v1",
                tenant_id=user.tenant_id,
                template_key="email_change_notice",
                channel="email",
                recipient=user.email,
                recipient_ref=user.id,
                language=user.locale,
                variables={
                    "organization": organization,
                    "new_email": change.new_email,
                    "expires_hours": expires_hours,
                },
            )
        )

    # TODO(M1): password reset (token + notification), email verification,
    # invitation-based org-scoped registration (the public register endpoint
    # creates platform-level users only).
