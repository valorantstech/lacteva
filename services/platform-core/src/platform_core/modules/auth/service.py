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
from platform_core.infrastructure.notifications import Notification, Notifier
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
        notifier: Notifier,
    ):
        self._session = session
        self._identity = identity
        self._membership = membership
        self._audit = audit
        self._bus = bus
        self._notifier = notifier

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

    # --- password reset (foundation) --------------------------------------

    async def request_password_reset(self, email: str, tenant_id: uuid.UUID | None) -> str | None:
        """Always succeeds outwardly (no account oracle). Returns the raw token
        to the CALLER (service layer) only — the API never exposes it; delivery
        goes through the notifier. Real email/SMS channels land in M2."""
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
        await self._notifier.send(
            Notification(
                channel="email",
                recipient=user.email,
                template_key="notification.password_reset",
                locale=user.locale,
                payload={"expires_hours": 2},
            )
        )
        await self._bus.publish(
            EventEnvelope.new(
                "identity.password-reset-requested.v1",
                {"user_id": str(user.id)},
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
