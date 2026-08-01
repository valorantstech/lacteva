"""Dependency injection wiring (FastAPI dependencies).

Composition root for request-scoped services: routers depend on these
providers, never construct services or touch the session directly.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import get_session
from platform_core.core.errors import ForbiddenError, UnauthorizedError
from platform_core.core.security import decode_token
from platform_core.core.tenancy import set_current_tenant
from platform_core.infrastructure.events import EventBus, get_event_bus
from platform_core.modules.audit.service import AuditService
from platform_core.modules.auth.service import AuthService
from platform_core.modules.authz.service import AuthzService, PermissionEngine
from platform_core.modules.configuration.service import ConfigurationService
from platform_core.modules.identity.models import User
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.organization.service import OrganizationService

Session = Annotated[AsyncSession, Depends(get_session)]
Bus = Annotated[EventBus, Depends(get_event_bus)]

_bearer = HTTPBearer(auto_error=False)


def get_audit_service(session: Session) -> AuditService:
    return AuditService(session)


Audit = Annotated[AuditService, Depends(get_audit_service)]


def get_identity_service(session: Session, bus: Bus, audit: Audit) -> IdentityService:
    return IdentityService(session, bus, audit)


Identity = Annotated[IdentityService, Depends(get_identity_service)]


def get_auth_service(identity: Identity, audit: Audit) -> AuthService:
    return AuthService(identity, audit)


def get_organization_service(session: Session, bus: Bus, audit: Audit) -> OrganizationService:
    return OrganizationService(session, bus, audit)


def get_authz_service(session: Session) -> AuthzService:
    return AuthzService(session)


def get_permission_engine(session: Session) -> PermissionEngine:
    return PermissionEngine(session)


def get_configuration_service(session: Session, audit: Audit) -> ConfigurationService:
    return ConfigurationService(session, audit)


@dataclass(frozen=True)
class Principal:
    user: User
    tenant_id: uuid.UUID | None

    @property
    def id(self) -> uuid.UUID:
        return self.user.id


async def get_current_principal(
    identity: Identity,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise UnauthorizedError()
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except pyjwt.InvalidTokenError as exc:
        raise UnauthorizedError() from exc
    user = await identity.get_user(uuid.UUID(payload["sub"]))
    if not user.is_active:
        raise UnauthorizedError()
    tenant_id = uuid.UUID(payload["tenant_id"]) if payload.get("tenant_id") else None
    set_current_tenant(tenant_id)  # token is authoritative over the header
    return Principal(user=user, tenant_id=tenant_id)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_permission(permission: str):
    """Route guard: Depends(require_permission('audit.read'))."""

    async def guard(
        principal: CurrentPrincipal,
        engine: Annotated[PermissionEngine, Depends(get_permission_engine)],
    ) -> Principal:
        if not await engine.check(principal.id, principal.tenant_id, permission):
            raise ForbiddenError(permission)
        return principal

    return guard
