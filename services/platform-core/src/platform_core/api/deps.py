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
from platform_core.core.tenancy import get_current_tenant, set_current_tenant
from platform_core.infrastructure.events import EventBus, get_event_bus
from platform_core.infrastructure.notifications import get_notifier
from platform_core.infrastructure.storage import get_object_storage
from platform_core.modules.audit.service import AuditService
from platform_core.modules.auth.models import AuthSession
from platform_core.modules.auth.service import AuthService
from platform_core.modules.authz.service import AuthzService, PermissionEngine
from platform_core.modules.collection_center.service import CollectionCenterService
from platform_core.modules.configuration.service import ConfigurationService
from platform_core.modules.identity.models import User
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.milk_collection.service import MilkCollectionService
from platform_core.modules.operational_readiness.service import OperationalReadinessService
from platform_core.modules.organization.service import (
    InvitationService,
    MembershipService,
    OrganizationService,
    StructureService,
)
from platform_core.modules.supplier.service import SupplierService

Session = Annotated[AsyncSession, Depends(get_session)]
Bus = Annotated[EventBus, Depends(get_event_bus)]

_bearer = HTTPBearer(auto_error=False)


def get_audit_service(session: Session) -> AuditService:
    return AuditService(session)


Audit = Annotated[AuditService, Depends(get_audit_service)]


def get_identity_service(session: Session, bus: Bus, audit: Audit) -> IdentityService:
    return IdentityService(session, bus, audit)


Identity = Annotated[IdentityService, Depends(get_identity_service)]


def get_membership_service(session: Session) -> MembershipService:
    return MembershipService(session)


def get_auth_service(session: Session, identity: Identity, audit: Audit, bus: Bus) -> AuthService:
    return AuthService(session, identity, MembershipService(session), audit, bus, get_notifier())


def get_structure_service(session: Session, bus: Bus, audit: Audit) -> StructureService:
    return StructureService(session, bus, audit)


def get_invitation_service(session: Session, bus: Bus, audit: Audit) -> InvitationService:
    return InvitationService(session, bus, audit, get_notifier())


def get_organization_service(session: Session, bus: Bus, audit: Audit) -> OrganizationService:
    return OrganizationService(session, bus, audit)


def get_authz_service(session: Session) -> AuthzService:
    return AuthzService(session)


def get_permission_engine(session: Session) -> PermissionEngine:
    return PermissionEngine(session)


def get_configuration_service(session: Session, audit: Audit) -> ConfigurationService:
    return ConfigurationService(session, audit)


def get_collection_center_service(
    session: Session, bus: Bus, audit: Audit
) -> CollectionCenterService:
    return CollectionCenterService(session, bus, audit)


def get_readiness_service(session: Session, bus: Bus, audit: Audit) -> OperationalReadinessService:
    return OperationalReadinessService(session, bus, audit)


def get_supplier_service(session: Session, bus: Bus, audit: Audit) -> SupplierService:
    return SupplierService(session, bus, audit, get_object_storage())


def get_milk_collection_service(session: Session, bus: Bus, audit: Audit) -> MilkCollectionService:
    return MilkCollectionService(
        session, bus, audit, OperationalReadinessService(session, bus, audit)
    )


@dataclass(frozen=True)
class Principal:
    user: User
    tenant_id: uuid.UUID | None
    session_id: uuid.UUID

    @property
    def id(self) -> uuid.UUID:
        return self.user.id


async def get_current_principal(
    session: Session,
    identity: Identity,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise UnauthorizedError()
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        session_id = uuid.UUID(payload["sid"])
    except (pyjwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise UnauthorizedError() from exc
    # Access tokens die with their session: logout/reset revokes immediately.
    # TODO(M2): cache active-session lookups in Redis (one DB hit per request now).
    auth_session = await session.get(AuthSession, session_id)
    from platform_core.core.db import as_utc, utcnow

    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or as_utc(auth_session.expires_at) < utcnow()
    ):
        raise UnauthorizedError()
    user = await identity.get_user(uuid.UUID(payload["sub"]))
    if not user.is_active:
        raise UnauthorizedError()
    tenant_id = uuid.UUID(payload["tenant_id"]) if payload.get("tenant_id") else None
    if tenant_id is not None:
        # Tenant-scoped tokens are authoritative — the header cannot override.
        set_current_tenant(tenant_id)
        principal_tenant = tenant_id
    else:
        # Platform-level principals may act inside a tenant via X-Tenant-ID
        # (bootstrap/administration path, permission-guarded per route).
        principal_tenant = get_current_tenant()
    return Principal(user=user, tenant_id=principal_tenant, session_id=session_id)


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
