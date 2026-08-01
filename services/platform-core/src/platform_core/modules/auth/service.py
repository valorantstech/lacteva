"""Authentication module — login and token issuance."""

import uuid

from pydantic import BaseModel, EmailStr

from platform_core.core.errors import InvalidCredentialsError
from platform_core.core.security import create_token, decode_token, verify_password
from platform_core.modules.audit.service import AuditService
from platform_core.modules.identity.service import IdentityService


class LoginCommand(BaseModel):
    email: EmailStr
    password: str
    tenant_id: uuid.UUID | None = None  # omit for platform-level login


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret


class AuthService:
    def __init__(self, identity: IdentityService, audit: AuditService):
        self._identity = identity
        self._audit = audit

    async def login(self, cmd: LoginCommand) -> TokenPair:
        user = await self._identity.get_by_email(cmd.email, cmd.tenant_id)
        if (
            user is None
            or not user.is_active
            or not verify_password(cmd.password, user.password_hash)
        ):
            # Identical failure for unknown user vs wrong password (no oracle).
            raise InvalidCredentialsError()
        await self._audit.record(
            action="auth.login.succeeded",
            resource_type="user",
            resource_id=user.id,
            actor_id=user.id,
        )
        return TokenPair(
            access_token=create_token(
                subject=user.id, token_type="access", tenant_id=user.tenant_id
            ),
            refresh_token=create_token(
                subject=user.id, token_type="refresh", tenant_id=user.tenant_id
            ),
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except Exception as exc:
            raise InvalidCredentialsError() from exc
        user = await self._identity.get_user(uuid.UUID(payload["sub"]))
        if not user.is_active:
            raise InvalidCredentialsError()
        # TODO(M1): rotation — invalidate the presented refresh token (jti
        # denylist in Redis) and audit refresh usage anomalies.
        return TokenPair(
            access_token=create_token(
                subject=user.id, token_type="access", tenant_id=user.tenant_id
            ),
            refresh_token=create_token(
                subject=user.id, token_type="refresh", tenant_id=user.tenant_id
            ),
        )

    # TODO(M1): brute-force lockout (Redis counters), MFA hook, device/session
    # listing. TODO(M2): OIDC federation for enterprise tenants (platform ADR).
