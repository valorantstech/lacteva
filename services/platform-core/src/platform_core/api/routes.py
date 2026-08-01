"""API routers for all platform modules (OpenAPI-tagged, /v1 prefix)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from platform_core.api import deps
from platform_core.api.deps import CurrentPrincipal, Principal, require_permission
from platform_core.modules.auth.service import AuthService, LoginCommand, TokenPair
from platform_core.modules.authz.permissions import PERMISSIONS
from platform_core.modules.authz.service import AuthzService, PermissionEngine
from platform_core.modules.configuration.service import ConfigurationService
from platform_core.modules.identity.schemas import RegisterUserCommand, UserView
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.organization.service import (
    CreateOrganizationCommand,
    OrganizationService,
    OrganizationView,
)

router = APIRouter(prefix="/v1")

# --- Authentication -------------------------------------------------------
auth = APIRouter(prefix="/auth", tags=["auth"])


@auth.post("/register", response_model=UserView, status_code=201)
async def register(
    cmd: RegisterUserCommand,
    identity: Annotated[IdentityService, Depends(deps.get_identity_service)],
) -> Any:
    """Public self-registration (platform-level user, no tenant).

    TODO(M1): org-scoped users join via invitation flow; this endpoint then
    gains rate limiting + email verification before production exposure.
    """
    return await identity.register_user(cmd, tenant_id=None)


@auth.post("/token", response_model=TokenPair)
async def login(
    cmd: LoginCommand, service: Annotated[AuthService, Depends(deps.get_auth_service)]
) -> TokenPair:
    return await service.login(cmd)


class RefreshRequest(BaseModel):
    refresh_token: str


@auth.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest, service: Annotated[AuthService, Depends(deps.get_auth_service)]
) -> TokenPair:
    return await service.refresh(body.refresh_token)


class MeView(BaseModel):
    user: UserView
    tenant_id: uuid.UUID | None
    permissions: list[str]


@auth.get("/me", response_model=MeView)
async def me(
    principal: CurrentPrincipal,
    engine: Annotated[PermissionEngine, Depends(deps.get_permission_engine)],
) -> MeView:
    perms = await engine.effective_permissions(principal.id, principal.tenant_id)
    return MeView(
        user=UserView.model_validate(principal.user),
        tenant_id=principal.tenant_id,
        permissions=sorted(perms),
    )


# --- Identity -------------------------------------------------------------
identity_router = APIRouter(prefix="/identity", tags=["identity"])


@identity_router.get("/users/{user_id}", response_model=UserView)
async def get_user(
    user_id: uuid.UUID,
    identity: Annotated[IdentityService, Depends(deps.get_identity_service)],
    _: Annotated[Principal, Depends(require_permission("identity.user.read"))],
) -> Any:
    return await identity.get_user(user_id)


# --- Organizations --------------------------------------------------------
org_router = APIRouter(prefix="/organizations", tags=["organizations"])


@org_router.post("", response_model=OrganizationView, status_code=201)
async def create_organization(
    cmd: CreateOrganizationCommand,
    service: Annotated[OrganizationService, Depends(deps.get_organization_service)],
    principal: Annotated[Principal, Depends(require_permission("organization.manage"))],
) -> Any:
    return await service.create_organization(cmd, actor_id=principal.id)


@org_router.get("/{org_id}", response_model=OrganizationView)
async def get_organization(
    org_id: uuid.UUID,
    service: Annotated[OrganizationService, Depends(deps.get_organization_service)],
    _: Annotated[Principal, Depends(require_permission("organization.read"))],
) -> Any:
    return await service.get_organization(org_id)


# --- Authorization --------------------------------------------------------
authz_router = APIRouter(prefix="/authz", tags=["authz"])


@authz_router.get("/permissions")
async def list_permissions(_: CurrentPrincipal) -> dict[str, str]:
    return PERMISSIONS


class CreateRoleRequest(BaseModel):
    name: str
    permission_keys: list[str]


@authz_router.post("/roles", status_code=201)
async def create_role(
    body: CreateRoleRequest,
    service: Annotated[AuthzService, Depends(deps.get_authz_service)],
    principal: Annotated[Principal, Depends(require_permission("authz.role.manage"))],
) -> dict:
    role = await service.create_role(
        tenant_id=principal.tenant_id, name=body.name, permission_keys=body.permission_keys
    )
    return {"id": str(role.id), "name": role.name}


class AssignRoleRequest(BaseModel):
    user_id: uuid.UUID
    role_name: str


@authz_router.post("/assignments", status_code=201)
async def assign_role(
    body: AssignRoleRequest,
    service: Annotated[AuthzService, Depends(deps.get_authz_service)],
    principal: Annotated[Principal, Depends(require_permission("authz.role.manage"))],
) -> dict:
    assignment = await service.assign_role(
        user_id=body.user_id, role_name=body.role_name, tenant_id=principal.tenant_id
    )
    return {"id": str(assignment.id)}


# --- Configuration --------------------------------------------------------
config_router = APIRouter(prefix="/config", tags=["configuration"])


@config_router.get("/{key}")
async def get_config(
    key: str,
    service: Annotated[ConfigurationService, Depends(deps.get_configuration_service)],
    _: Annotated[Principal, Depends(require_permission("configuration.read"))],
) -> dict:
    return {"key": key, "value": await service.resolve(key)}


class SetConfigRequest(BaseModel):
    value: Any
    scope: str = "tenant"  # "tenant" | "global" (global requires platform admin in practice)


@config_router.put("/{key}")
async def set_config(
    key: str,
    body: SetConfigRequest,
    service: Annotated[ConfigurationService, Depends(deps.get_configuration_service)],
    principal: Annotated[Principal, Depends(require_permission("configuration.write"))],
) -> dict:
    await service.set_value(key, body.value, scope=body.scope, actor_id=principal.id)
    return {"key": key, "scope": body.scope, "status": "saved"}


# --- Audit ----------------------------------------------------------------
audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.get("")
async def list_audit(
    service: Annotated[deps.AuditService, Depends(deps.get_audit_service)],
    _: Annotated[Principal, Depends(require_permission("audit.read"))],
    limit: int = 100,
) -> list[dict]:
    records = await service.list_records(limit=limit)
    return [
        {
            "id": str(r.id),
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "actor_id": str(r.actor_id) if r.actor_id else None,
            "created_at": r.created_at.isoformat(),
            "detail": r.detail,
        }
        for r in records
    ]


for sub in (auth, identity_router, org_router, authz_router, config_router, audit_router):
    router.include_router(sub)
