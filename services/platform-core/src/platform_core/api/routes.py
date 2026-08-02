"""API routers for all platform modules (OpenAPI-tagged, /v1 prefix)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from platform_core.api import deps
from platform_core.api.deps import CurrentPrincipal, Principal, require_permission
from platform_core.modules.auth.service import AuthService, LoginCommand, TokenPair
from platform_core.modules.authz.permissions import PERMISSIONS
from platform_core.modules.authz.service import AuthzService, PermissionEngine
from platform_core.modules.collection_center.service import (
    CalendarEntryInput,
    CalendarEntryView,
    CenterDetailView,
    CenterPage,
    CenterView,
    CollectionCenterService,
    CreateCenterCommand,
    OperatingWindowInput,
    OperatingWindowView,
    UpdateCenterCommand,
)
from platform_core.modules.configuration.service import ConfigurationService
from platform_core.modules.identity.schemas import RegisterUserCommand, UserView
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.organization.service import (
    BranchView,
    CreateOrganizationCommand,
    InvitationService,
    MembershipService,
    OrganizationService,
    OrganizationView,
    StructureService,
    WorkspaceView,
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


@auth.post("/logout", status_code=204)
async def logout(
    principal: CurrentPrincipal,
    service: Annotated[AuthService, Depends(deps.get_auth_service)],
) -> None:
    await service.logout(principal.session_id, actor_id=principal.id)


class PasswordResetRequest(BaseModel):
    email: str
    tenant_id: uuid.UUID | None = None


@auth.post("/password-reset/request", status_code=202)
async def request_password_reset(
    body: PasswordResetRequest,
    service: Annotated[AuthService, Depends(deps.get_auth_service)],
) -> dict:
    """Always 202 — never reveals whether the account exists. Delivery via
    the notification channel (logging adapter until M2)."""
    await service.request_password_reset(body.email, body.tenant_id)
    return {"status": "accepted"}


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=128)


@auth.post("/password-reset/confirm", status_code=204)
async def confirm_password_reset(
    body: PasswordResetConfirm,
    service: Annotated[AuthService, Depends(deps.get_auth_service)],
) -> None:
    await service.confirm_password_reset(body.token, body.new_password)


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


# --- Organization structure (workspaces, branches) ------------------------
structure_router = APIRouter(tags=["organization-structure"])


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")


@structure_router.post("/workspaces", response_model=WorkspaceView, status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest,
    service: Annotated[StructureService, Depends(deps.get_structure_service)],
    principal: Annotated[Principal, Depends(require_permission("organization.structure.manage"))],
) -> Any:
    return await service.create_workspace(name=body.name, slug=body.slug, actor_id=principal.id)


@structure_router.get("/workspaces", response_model=list[WorkspaceView])
async def list_workspaces(
    service: Annotated[StructureService, Depends(deps.get_structure_service)],
    _: Annotated[Principal, Depends(require_permission("organization.structure.read"))],
) -> Any:
    return await service.list_workspaces()


class CreateBranchRequest(BaseModel):
    workspace_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")


@structure_router.post("/branches", response_model=BranchView, status_code=201)
async def create_branch(
    body: CreateBranchRequest,
    service: Annotated[StructureService, Depends(deps.get_structure_service)],
    principal: Annotated[Principal, Depends(require_permission("organization.structure.manage"))],
) -> Any:
    return await service.create_branch(
        workspace_id=body.workspace_id, name=body.name, code=body.code, actor_id=principal.id
    )


@structure_router.get("/branches", response_model=list[BranchView])
async def list_branches(
    service: Annotated[StructureService, Depends(deps.get_structure_service)],
    _: Annotated[Principal, Depends(require_permission("organization.structure.read"))],
) -> Any:
    return await service.list_branches()


# --- Members & invitations -------------------------------------------------
member_router = APIRouter(tags=["members"])


@member_router.get("/members")
async def list_members(
    service: Annotated[MembershipService, Depends(deps.get_membership_service)],
    _: Annotated[Principal, Depends(require_permission("organization.member.read"))],
) -> list[dict]:
    return [
        {
            "user_id": str(m.user_id),
            "status": m.status,
            "joined_at": m.joined_at.isoformat(),
        }
        for m in await service.list_members()
    ]


class InviteRequest(BaseModel):
    email: str
    role_name: str = "tenant-viewer"


@member_router.post("/invitations", status_code=201)
async def create_invitation(
    body: InviteRequest,
    service: Annotated[InvitationService, Depends(deps.get_invitation_service)],
    principal: Annotated[Principal, Depends(require_permission("organization.member.manage"))],
) -> dict:
    invitation, raw_token = await service.invite(
        email=body.email, role_name=body.role_name, actor_id=principal.id
    )
    # FOUNDATION ONLY: token in the response until real delivery lands (M2).
    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "expires_at": invitation.expires_at.isoformat(),
        "invitation_token": raw_token,
    }


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)


@member_router.post("/invitations/accept", response_model=UserView, status_code=201)
async def accept_invitation(
    body: AcceptInvitationRequest,
    service: Annotated[InvitationService, Depends(deps.get_invitation_service)],
    identity: Annotated[IdentityService, Depends(deps.get_identity_service)],
    authz: Annotated[AuthzService, Depends(deps.get_authz_service)],
    membership: Annotated[MembershipService, Depends(deps.get_membership_service)],
) -> Any:
    """Public: how invited people join their organization."""
    return await service.accept(
        token=body.token,
        password=body.password,
        full_name=body.full_name,
        identity=identity,
        authz=authz,
        membership=membership,
    )


# --- Collection centers (facility management only) -------------------------
center_router = APIRouter(prefix="/collection-centers", tags=["collection-centers"])
CenterManage = Annotated[Principal, Depends(require_permission("collection.center.manage"))]
CenterRead = Annotated[Principal, Depends(require_permission("collection.center.read"))]
CenterSvc = Annotated[CollectionCenterService, Depends(deps.get_collection_center_service)]


@center_router.post("", response_model=CenterView, status_code=201)
async def create_center(cmd: CreateCenterCommand, service: CenterSvc, p: CenterManage) -> Any:
    return await service.create(cmd, actor_id=p.id)


@center_router.get("", response_model=CenterPage)
async def list_centers(
    service: CenterSvc,
    _: CenterRead,
    q: str | None = None,
    status: str | None = None,
    branch_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> CenterPage:
    return await service.list_page(
        q=q, status=status, branch_id=branch_id, limit=limit, offset=offset
    )


@center_router.get("/{center_id}", response_model=CenterDetailView)
async def get_center_detail(
    center_id: uuid.UUID, service: CenterSvc, _: CenterRead
) -> CenterDetailView:
    return await service.detail(center_id)


@center_router.put("/{center_id}", response_model=CenterView)
async def update_center(
    center_id: uuid.UUID, cmd: UpdateCenterCommand, service: CenterSvc, p: CenterManage
) -> Any:
    return await service.update(center_id, cmd, actor_id=p.id)


class SetStatusRequest(BaseModel):
    status: str


@center_router.post("/{center_id}/status", response_model=CenterView)
async def set_center_status(
    center_id: uuid.UUID, body: SetStatusRequest, service: CenterSvc, p: CenterManage
) -> Any:
    return await service.set_status(center_id, body.status, actor_id=p.id)


class SetConfigCenterRequest(BaseModel):
    settings: dict[str, Any]


@center_router.put("/{center_id}/config")
async def set_center_config(
    center_id: uuid.UUID, body: SetConfigCenterRequest, service: CenterSvc, p: CenterManage
) -> dict:
    settings = await service.set_config(center_id, body.settings, actor_id=p.id)
    return {"settings": settings}


class SetHoursRequest(BaseModel):
    windows: list[OperatingWindowInput]


@center_router.put("/{center_id}/operating-hours", response_model=list[OperatingWindowView])
async def set_center_hours(
    center_id: uuid.UUID, body: SetHoursRequest, service: CenterSvc, p: CenterManage
) -> Any:
    return await service.set_operating_hours(center_id, body.windows, actor_id=p.id)


@center_router.post("/{center_id}/calendar", response_model=CalendarEntryView, status_code=201)
async def add_center_calendar_entry(
    center_id: uuid.UUID, entry: CalendarEntryInput, service: CenterSvc, p: CenterManage
) -> Any:
    return await service.add_calendar_entry(center_id, entry, actor_id=p.id)


@center_router.delete("/{center_id}/calendar/{entry_id}", status_code=204)
async def remove_center_calendar_entry(
    center_id: uuid.UUID, entry_id: uuid.UUID, service: CenterSvc, p: CenterManage
) -> None:
    await service.remove_calendar_entry(center_id, entry_id, actor_id=p.id)


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


for sub in (
    auth,
    identity_router,
    org_router,
    structure_router,
    member_router,
    center_router,
    authz_router,
    config_router,
    audit_router,
):
    router.include_router(sub)
