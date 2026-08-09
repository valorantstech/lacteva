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
from platform_core.core.errors import InvalidCredentialsError, InvalidTokenError
from platform_core.core.security import create_token, hash_password, verify_password
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.auth.models import AuthSession, PasswordResetToken
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.organization.service import MembershipService

RESET_TOKEN_TTL = timedelta(hours=2)


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
        if user.tenant_id is not None and not await self._membership.is_active_member(
            user.id, user.tenant_id
        ):
            raise InvalidCredentialsError()
        auth_session = AuthSession(
            user_id=user.id,
            tenant_id=user.tenant_id,
            refresh_token_hash="pending",
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

    async def refresh(self, refresh_token: str) -> TokenPair:
        token_hash = _hash_secret(refresh_token)
        auth_session = await self._session.scalar(
            select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
        )
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

        Delivery is NOT this module's business (NOT-001/BR-0016): the event
        carries the address and the notification consumer renders and sends."""
        user = await self._identity.get_by_email(email, tenant_id)
        if user is None or not user.is_active:
            return None
        raw = secrets.token_urlsafe(32)
        self._session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_secret(raw),
                expires_at=utcnow() + RESET_TOKEN_TTL,
            )
        )
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
        return raw

    async def confirm_password_reset(self, token: str, new_password: str) -> None:
        record = await self._session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_secret(token))
        )
        if record is None or record.used_at is not None or as_utc(record.expires_at) < utcnow():
            raise InvalidTokenError()
        user = await self._identity.get_user(record.user_id)
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
