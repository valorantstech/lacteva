"""Authentication module — login, sessions, refresh rotation, logout, reset."""

import hashlib
import secrets
import uuid
from datetime import timedelta

from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.config import get_settings
from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import (
    AmbiguousTenantError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from platform_core.core.security import create_token, hash_password, verify_password
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.auth.models import AuthSession, PasswordResetToken
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.organization.service import MembershipService

RESET_TOKEN_TTL = timedelta(hours=2)


def _placeholder_hash() -> str:
    """A value no real token can collide with, and no OTHER placeholder can.

    `_hash_secret` returns 64 hex characters; this is deliberately shorter and
    prefixed, so a stranded row is both inert and obvious to whoever finds it.
    """
    return f"unissued:{secrets.token_hex(16)}"


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class LoginCommand(BaseModel):
    email: EmailStr
    password: str
    tenant_id: uuid.UUID | None = None  # omit for platform-level login


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        identity: IdentityService,
        membership: MembershipService,
        audit: AuditService,
        bus: EventBus,
    ):
        self._session = session
        self._identity = identity
        self._membership = membership
        self._audit = audit
        self._bus = bus

    # --- sessions ---------------------------------------------------------

    async def _issue_pair(self, auth_session: AuthSession) -> TokenPair:
        refresh_secret = secrets.token_urlsafe(48)
        auth_session.previous_token_hash = auth_session.refresh_token_hash
        auth_session.refresh_token_hash = _hash_secret(refresh_secret)
        auth_session.last_used_at = utcnow()
        auth_session.expires_at = utcnow() + timedelta(
            seconds=get_settings().jwt_refresh_ttl_seconds
        )
        access = create_token(
            subject=auth_session.user_id,
            token_type="access",
            tenant_id=auth_session.tenant_id,
            extra_claims={"sid": str(auth_session.id)},
        )
        return TokenPair(access_token=access, refresh_token=refresh_secret)

    async def get_active_session(self, session_id: uuid.UUID) -> AuthSession | None:
        s = await self._session.get(AuthSession, session_id)
        if s is None or s.revoked_at is not None or as_utc(s.expires_at) < utcnow():
            return None
        return s

    async def login(self, cmd: LoginCommand) -> TokenPair:
        # SEC-002: a tenant-scoped login names its tenant in the request body,
        # which the middleware never sees, so the session was bound to nothing
        # and RLS hid the very account being authenticated. Bind from the
        # request before the lookup. This grants no access on its own — the
        # password still has to verify, and an attacker naming a tenant they
        # do not belong to only narrows what they can see.
        from platform_core.core.rls import rebind_tenant

        if cmd.tenant_id is not None:
            await rebind_tenant(self._session, cmd.tenant_id)
            user = await self._identity.get_by_email(cmd.email, cmd.tenant_id)
            if (
                user is None
                or not user.is_active
                or not verify_password(cmd.password, user.password_hash)
            ):
                # Identical failure for unknown user vs wrong password (no oracle).
                raise InvalidCredentialsError()
        else:
            user = await self._resolve_without_a_named_tenant(cmd)
        if user.tenant_id is not None and not await self._membership.is_active_member(
            user.id, user.tenant_id
        ):
            raise InvalidCredentialsError()
        # DEMO-008 §9: recorded here, on the one path that proves the
        # credential was accepted. A refresh does not update it — a token
        # renewing itself is not the person coming back.
        user.last_login_at = utcnow()
        auth_session = AuthSession(
            user_id=user.id,
            tenant_id=user.tenant_id,
            # DEMO-012: the placeholder is UNIQUE PER ROW, and that is not
            # cosmetic. It used to be the literal string `"pending"`, written
            # into a column with a UNIQUE constraint and replaced a few lines
            # later by `_issue_pair`. So a row that ever reached the database
            # still holding it — one interrupted request is enough — made
            # EVERY subsequent login on the platform fail with a 500, for
            # every user, permanently, because the next insert collided with
            # it and nothing in the system ever cleans it up.
            #
            # Found by accident: a local API process was killed mid-login and
            # one such row survived, after which no account could sign in at
            # all until it was deleted by hand. A placeholder is a value the
            # code does not care about; a unique index cares about every
            # value, so the two must not meet.
            refresh_token_hash=_placeholder_hash(),
            expires_at=utcnow(),
        )
        self._session.add(auth_session)
        await self._session.flush()
        pair = await self._issue_pair(auth_session)
        await self._audit.record(
            action="auth.login.succeeded",
            resource_type="user",
            resource_id=user.id,
            actor_id=user.id,
            detail={"session_id": str(auth_session.id)},
        )
        return pair

    async def _resolve_without_a_named_tenant(self, cmd: LoginCommand):
        """Work out WHICH account is signing in, from the credentials alone.

        DEMO-010. Before this, omitting `tenant_id` looked only for an account
        with no tenant at all, so every ordinary member of an organization had
        to supply their organization's UUID — which is what the portal's login
        form asked for, in a text box, as the first thing anyone saw.

        The password is verified against each candidate, and the ANSWER is
        derived from how many verified:

        * none — `invalid_credentials`, byte for byte the same response an
          unknown address gets. Nothing is revealed by asking.
        * one — sign in as that account. This is every real case.
        * more than one — the same password really does open accounts in
          several organizations, and only then is the caller told so and asked
          to name one. They have already proven the password, so listing the
          organizations reveals nothing they could not have discovered by
          trying each in turn.

        The cost is at most `LOGIN_CANDIDATE_LIMIT` password verifications for
        an address that has several accounts, which is the point of the limit.
        """
        from platform_core.core.rls import rebind_tenant

        candidates = await self._identity.candidates_for_login(cmd.email)
        verified = [
            user
            for user in candidates
            if user.is_active and verify_password(cmd.password, user.password_hash)
        ]
        if not verified:
            raise InvalidCredentialsError()
        if len(verified) > 1:
            raise AmbiguousTenantError(
                [t for t in (u.tenant_id for u in verified) if t is not None]
            )
        user = verified[0]
        # The session was bound to nothing (no tenant was named), so bind it to
        # the tenant we have just established — for the same reason SEC-002
        # gives above, and before the membership check reads a tenant-owned row.
        await rebind_tenant(self._session, user.tenant_id)
        return user

    async def refresh(self, refresh_token: str) -> TokenPair:
        # WO-73 follow-up, found on the live handset twenty minutes after
        # WO-69 shipped: `auth_session` is TENANT-OWNED under RLS, and a
        # refresh request carries no tenant — no bearer, no body field, just
        # the opaque token. The login route rebinds the tenant it was told in
        # its body before looking the user up; this route had nothing to
        # rebind to, so on PostgreSQL a tenant-scoped session was invisible
        # to the query that renews it: the token was refused, the app signed
        # the operator out at fifteen minutes exactly as before, and every
        # test was green because SQLite has no policies. The token IS the
        # credential — 256 bits, matched by hash — so the lookup runs under
        # the audited platform bypass, and the request is then bound to the
        # tenant the session names for everything that follows.
        from platform_core.core.rls import bind_platform_context, rebind_tenant

        await bind_platform_context(
            self._session, reason="token refresh: the tenant is unknown until the session is found"
        )
        token_hash = _hash_secret(refresh_token)
        auth_session = await self._session.scalar(
            select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
        )
        if auth_session is not None:
            await rebind_tenant(self._session, auth_session.tenant_id)
        if auth_session is None:
            # Reuse of an already-rotated token = theft signal: kill that session.
            stolen = await self._session.scalar(
                select(AuthSession).where(AuthSession.previous_token_hash == token_hash)
            )
            if stolen is not None:
                await self._revoke(stolen, reason="refresh-reuse")
                await self._audit.record(
                    action="auth.session.reuse_detected",
                    resource_type="auth_session",
                    resource_id=stolen.id,
                    actor_id=stolen.user_id,
                )
                # The 401 below rolls the request transaction back — the
                # revocation is a security response and MUST survive it.
                await self._session.commit()
            raise InvalidCredentialsError()
        if auth_session.revoked_at is not None or as_utc(auth_session.expires_at) < utcnow():
            raise InvalidCredentialsError()
        user = await self._identity.get_user(auth_session.user_id)
        if not user.is_active:
            raise InvalidCredentialsError()
        return await self._issue_pair(auth_session)

    async def logout(self, session_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        auth_session = await self._session.get(AuthSession, session_id)
        if auth_session is not None and auth_session.revoked_at is None:
            await self._revoke(auth_session, reason="logout")
            await self._audit.record(
                action="auth.logout",
                resource_type="auth_session",
                resource_id=session_id,
                actor_id=actor_id,
            )

    async def _revoke(self, auth_session: AuthSession, *, reason: str) -> None:
        auth_session.revoked_at = utcnow()
        auth_session.revoke_reason = reason

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, reason: str) -> None:
        await self._session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utcnow(), revoke_reason=reason)
        )

    async def set_user_active(
        self,
        user_id: uuid.UUID,
        *,
        active: bool,
        actor_id: uuid.UUID,
        tenant_id: uuid.UUID | None,
    ):
        """Deactivate or reactivate a user AND settle their sessions.

        SEC-003 / F-02. Identity owns the flag; this module owns sessions, and
        an offboarding that leaves a live refresh token behind is not an
        offboarding. `get_current_principal` already re-reads `is_active` on
        every request, so the access token dies at its next use whatever
        happens here — this closes the refresh path too, which would otherwise
        keep minting access tokens from a session nobody re-checked.

        Reactivation does NOT restore sessions. They were revoked; the user
        logs in again. Resurrecting a revoked session would make the revoke
        reason a lie and would hand back a refresh token that may have been
        captured in the meantime.
        """
        user = await self._identity.set_active(
            user_id, active=active, actor_id=actor_id, tenant_id=tenant_id
        )
        if not active:
            await self.revoke_all_for_user(user_id, reason="user-deactivated")
        return user

    # --- password reset (foundation) --------------------------------------

    async def request_password_reset(self, email: str, tenant_id: uuid.UUID | None) -> str | None:
        """Always succeeds outwardly (no account oracle). Returns the raw token
        to the CALLER (service layer) only — the API never exposes it.

        The code reaches the person the same way an invitation's does: sent
        from here, directly, with the secret outside the event (see
        `_send_reset_code`). The event is still published, because it is the
        audit fact that a reset was asked for — it simply is not the delivery.

        WITHOUT a tenant it resolves the way LOGIN does (LACTEVA-BACKEND-005).
        Both clients omit `tenant_id`, and they are right to: a locked-out
        person does not know their organization's UUID, which is exactly the
        problem DEMO-010 solved for the login form. `get_by_email(email, None)`
        matches `tenant_id IS NULL`, so every real tenant user's reset request
        found nothing, returned early, and disappeared behind the 202 that
        exists to reveal nothing. The flow was reachable only by someone who
        could supply a UUID they had no way to know.

        So the lookup is now login's: the same bounded cross-organization
        candidate read. An address that owns accounts in several organizations
        gets a code for EACH — the inbox is the identity, and the owner of the
        inbox is entitled to recover every account it holds — and each message
        names its organization so the reader knows which account its code
        opens. A caller who names a tenant explicitly keeps the exact-match
        path, unchanged.

        Nothing about the outward contract moves: still 202 whatever happens,
        still nothing sent for an address the platform does not know.
        """
        from platform_core.core.rls import rebind_tenant

        if tenant_id is not None:
            found = await self._identity.get_by_email(email, tenant_id)
            users = [found] if found is not None and found.is_active else []
        else:
            # Already filtered to active accounts and bounded by
            # LOGIN_CANDIDATE_LIMIT — the same bound, for the same reason.
            users = await self._identity.candidates_for_login(email)

        raw_last: str | None = None
        for user in users:
            # Bound to each account's own tenant before its message is built,
            # exactly as login rebinds once it knows whose account it is
            # (SEC-002). Not tidiness: `dispatch` reads tenant-owned settings,
            # so an unbound send would render one organization's message
            # against another's configuration.
            await rebind_tenant(self._session, user.tenant_id)
            raw = secrets.token_urlsafe(32)
            token = PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_secret(raw),
                expires_at=utcnow() + RESET_TOKEN_TTL,
            )
            self._session.add(token)
            # Flushed for its id, exactly as the invitation is: the id is what
            # keys the notification's idempotency, and `IdMixin` fills it at
            # INSERT.
            await self._session.flush()
            await self._send_reset_code(token, user, raw)
            await self._bus.publish(
                EventEnvelope.new(
                    "identity.password-reset-requested.v1",
                    {
                        "user_id": str(user.id),
                        "email": user.email,
                        "locale": user.locale,
                        "expires_hours": int(RESET_TOKEN_TTL.total_seconds() // 3600),
                    },
                    actor_id=user.id,
                )
            )
            raw_last = raw
        return raw_last

    async def _organization_name(self, tenant_id: uuid.UUID | None) -> str:
        """Which account this code opens (LACTEVA-BACKEND-005).

        One address can hold accounts in several organizations, and each now
        gets its own code. Two identical emails arriving together, both saying
        only "your account", would be a puzzle rather than a recovery — so the
        message says whose account it is.

        A platform account belongs to no organization, and "Lacteva" is what
        the invitation template already calls that case.
        """
        if tenant_id is None:
            return "Lacteva"
        from platform_core.modules.organization.models import Organization

        organization = await self._session.get(Organization, tenant_id)
        return organization.name if organization is not None else "Lacteva"

    async def _send_reset_code(self, token: PasswordResetToken, user, raw_token: str):
        """The second place a business module sends a notification itself, and
        for the same reason as the first (SEC-003 / F-04).

        Everywhere else the module publishes and the notification consumer
        sends — NOT-001/BR-0016, and it stands. It cannot stand here: the
        consumer reads the durable outbox log, so anything it needs must be
        written into `event_outbox.payload`, which is never pruned and is in
        every backup. A live reset code there trades one exposure for a worse
        one, which is exactly why the event has never carried it.

        What it carried instead, until now, was nothing usable: the message
        said a reset had been requested and that "the link expires in 2 hours",
        with no link and no code. The code was minted, hashed, stored and
        returned to a caller that dropped it, so `confirm_password_reset` could
        not be reached by any real person and both clients advertised a flow
        nobody could finish (LACTEVA-BACKEND-004, found by the E2E harness).

        Everything else is the invitation's arrangement, unchanged: same
        service, same provider, same delivery record, same retry budget, and
        idempotency keyed on THIS token — so a second request sends the second
        code rather than suppressing it or re-sending a stale one.
        """
        from platform_core.modules.notification.service import (
            NotificationRequest,
            NotificationService,
        )

        return await NotificationService(self._session).dispatch(
            NotificationRequest(
                event_id=token.id,
                event_name="identity.password-reset-requested.v1",
                tenant_id=user.tenant_id,
                template_key="password_reset",
                channel="email",
                recipient=user.email,
                recipient_ref=user.id,
                language=user.locale,
                variables={
                    "expires_hours": int(RESET_TOKEN_TTL.total_seconds() // 3600),
                    "organization": await self._organization_name(user.tenant_id),
                },
                secret_variables={"reset_token": raw_token},
            )
        )

    async def confirm_password_reset(self, token: str, new_password: str) -> None:
        """Spend a reset token (LACTEVA-BACKEND-006).

        The caller is ANONYMOUS by definition — somebody locked out of their
        account — so the request carries no tenant and the session is unbound.
        `password_reset_token` is not tenant-owned and reads fine, but the
        ACCOUNT it names is: `user_account` is tenant-owned, so an unbound
        session cannot see it and `get_user` raised NotFound. The endpoint
        answered 404 for every tenant user, which reads as "bad token" — the
        one thing this flow must never say wrongly, because the person
        retrying is already locked out.

        Found by running the E2E journeys as `lacteva_app` with RLS forced;
        the harness had been connecting as a superuser, which bypasses every
        policy, so twenty-eight journeys passed over it.

        The remedy is the shape `accept_invitation` already uses, and the
        narrowest one available: bypass for the two indexed reads that
        discover WHICH tenant this is, then bind to that tenant before
        anything is written. The token hash is a high-entropy secret, so
        resolving it across tenants reveals nothing to a caller who does not
        already hold it.
        """
        from platform_core.core.rls import bind_platform_context, rebind_tenant

        await bind_platform_context(
            self._session, reason="password reset: resolve the account from the token"
        )
        record = await self._session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_secret(token))
        )
        if record is None or record.used_at is not None or as_utc(record.expires_at) < utcnow():
            raise InvalidTokenError()
        user = await self._identity.get_user(record.user_id)
        # Bypass ends here. Everything below writes tenant-owned rows — the
        # account, the revoked sessions, the audit entry — and must be
        # constrained to the tenant the token turned out to belong to.
        await rebind_tenant(self._session, user.tenant_id)
        user.password_hash = hash_password(new_password)
        record.used_at = utcnow()
        await self.revoke_all_for_user(user.id, reason="password-reset")
        await self._audit.record(
            action="auth.password.reset",
            resource_type="user",
            resource_id=user.id,
            actor_id=user.id,
        )

    # TODO(M2): login throttling (Redis counters), MFA hook, session listing
    # endpoint. TODO(M2): OIDC federation for enterprise tenants (platform ADR).
