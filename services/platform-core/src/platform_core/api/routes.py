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
from platform_core.modules.event_relay.service import (
    DeadLetterView,
    OutboxEventView,
    RelayService,
    RelayStats,
)
from platform_core.modules.identity.schemas import RegisterUserCommand, UserView
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.milk_collection.service import (
    IdentifySupplierCommand,
    MilkCollectionService,
    MilkInfoCommand,
    QualityCommand,
    RejectCommand,
    SessionView,
    TransactionEventView,
    TransactionPage,
    TransactionView,
    WeightCommand,
)
from platform_core.modules.operational_readiness.models import DEVICE_CATEGORIES
from platform_core.modules.operational_readiness.service import (
    READINESS_RULES,
    DeviceDetailView,
    DevicePage,
    DeviceView,
    OperationalReadinessService,
    OperatorView,
    ReadinessResult,
    RegisterDeviceCommand,
)
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
from platform_core.modules.supplier.service import (
    AddBankAccountCommand,
    BankAccountView,
    CreateSupplierCommand,
    DocumentView,
    ImportRowResult,
    SupplierDetailView,
    SupplierPage,
    SupplierProfileInput,
    SupplierService,
    SupplierView,
    UploadDocumentCommand,
    qr_payload_for,
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


# --- Operational readiness (devices, operators, readiness engine) ----------
ops_router = APIRouter(tags=["operational-readiness"])
DeviceManage = Annotated[Principal, Depends(require_permission("operations.device.manage"))]
DeviceRead = Annotated[Principal, Depends(require_permission("operations.device.read"))]
ReadinessRead = Annotated[Principal, Depends(require_permission("operations.readiness.read"))]
OpsSvc = Annotated[OperationalReadinessService, Depends(deps.get_readiness_service)]


@ops_router.get("/device-categories")
async def list_device_categories(_: DeviceRead) -> dict[str, dict]:
    return DEVICE_CATEGORIES


@ops_router.post("/devices", response_model=DeviceView, status_code=201)
async def register_device(cmd: RegisterDeviceCommand, service: OpsSvc, p: DeviceManage) -> Any:
    return await service.register_device(cmd, actor_id=p.id)


@ops_router.get("/devices", response_model=DevicePage)
async def list_devices(
    service: OpsSvc,
    _: DeviceRead,
    center_id: uuid.UUID | None = None,
    category: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> DevicePage:
    return await service.list_devices(
        center_id=center_id, category=category, status=status, limit=limit, offset=offset
    )


@ops_router.get("/devices/{device_id}", response_model=DeviceDetailView)
async def get_device_detail(
    device_id: uuid.UUID, service: OpsSvc, _: DeviceRead
) -> DeviceDetailView:
    return await service.device_detail(device_id)


class AssignDeviceRequest(BaseModel):
    center_id: uuid.UUID


@ops_router.post("/devices/{device_id}/assign", response_model=DeviceView)
async def assign_device(
    device_id: uuid.UUID, body: AssignDeviceRequest, service: OpsSvc, p: DeviceManage
) -> Any:
    return await service.assign_device(device_id, body.center_id, actor_id=p.id)


class DeviceStatusRequest(BaseModel):
    status: str


@ops_router.post("/devices/{device_id}/status", response_model=DeviceView)
async def set_device_status(
    device_id: uuid.UUID, body: DeviceStatusRequest, service: OpsSvc, p: DeviceManage
) -> Any:
    return await service.set_device_status(device_id, body.status, actor_id=p.id)


class HealthReportRequest(BaseModel):
    state: str
    note: str = ""


@ops_router.post("/devices/{device_id}/health", status_code=201)
async def report_device_health(
    device_id: uuid.UUID, body: HealthReportRequest, service: OpsSvc, p: DeviceManage
) -> dict:
    report = await service.report_health(device_id, body.state, body.note, actor_id=p.id)
    return {"id": str(report.id), "state": report.state}


class AssignOperatorRequest(BaseModel):
    user_id: uuid.UUID
    role_label: str = "operator"


@ops_router.post("/collection-centers/{center_id}/operators", status_code=201)
async def assign_operator(
    center_id: uuid.UUID, body: AssignOperatorRequest, service: OpsSvc, p: DeviceManage
) -> dict:
    a = await service.assign_operator(center_id, body.user_id, body.role_label, actor_id=p.id)
    return {"user_id": str(a.user_id), "role_label": a.role_label}


@ops_router.get("/collection-centers/{center_id}/operators", response_model=list[OperatorView])
async def list_operators(center_id: uuid.UUID, service: OpsSvc, _: DeviceRead) -> Any:
    return await service.list_operators(center_id)


@ops_router.delete("/collection-centers/{center_id}/operators/{user_id}", status_code=204)
async def remove_operator(
    center_id: uuid.UUID, user_id: uuid.UUID, service: OpsSvc, p: DeviceManage
) -> None:
    await service.remove_operator(center_id, user_id, actor_id=p.id)


@ops_router.get("/readiness/rules")
async def list_readiness_rules(_: ReadinessRead) -> dict[str, dict]:
    return READINESS_RULES


@ops_router.get("/collection-centers/{center_id}/readiness", response_model=ReadinessResult)
async def evaluate_center_readiness(
    center_id: uuid.UUID, service: OpsSvc, _: ReadinessRead
) -> ReadinessResult:
    """The Operational Status API: evaluates the center now, on demand."""
    return await service.evaluate_readiness(center_id)


# --- Suppliers -------------------------------------------------------------
supplier_router = APIRouter(prefix="/suppliers", tags=["suppliers"])
SupplierManage = Annotated[Principal, Depends(require_permission("supplier.manage"))]
SupplierRead = Annotated[Principal, Depends(require_permission("supplier.read"))]
SupplierSvc = Annotated[SupplierService, Depends(deps.get_supplier_service)]


@supplier_router.post("", response_model=SupplierView, status_code=201)
async def create_supplier(
    cmd: CreateSupplierCommand, service: SupplierSvc, p: SupplierManage
) -> Any:
    supplier = await service.create(cmd, actor_id=p.id)
    return (await service.detail(supplier.id)).supplier


@supplier_router.get("", response_model=SupplierPage)
async def search_suppliers(
    service: SupplierSvc,
    _: SupplierRead,
    q: str | None = None,
    status: str | None = None,
    center_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> SupplierPage:
    return await service.search(
        q=q, status=status, center_id=center_id, branch_id=branch_id, limit=limit, offset=offset
    )


@supplier_router.get("/{supplier_id}", response_model=SupplierDetailView)
async def get_supplier_detail(
    supplier_id: uuid.UUID, service: SupplierSvc, _: SupplierRead
) -> SupplierDetailView:
    return await service.detail(supplier_id)


@supplier_router.put("/{supplier_id}", response_model=SupplierProfileInput)
async def update_supplier_profile(
    supplier_id: uuid.UUID, cmd: SupplierProfileInput, service: SupplierSvc, p: SupplierManage
) -> Any:
    profile = await service.update_profile(supplier_id, cmd, actor_id=p.id)
    return SupplierProfileInput(
        full_name=profile.full_name,
        phone=profile.phone,
        national_id=profile.national_id,
        village=profile.village,
        locale=profile.locale,
        extra=profile.extra,
    )


class SupplierStatusRequest(BaseModel):
    status: str


@supplier_router.post("/{supplier_id}/status", response_model=SupplierView)
async def set_supplier_status(
    supplier_id: uuid.UUID, body: SupplierStatusRequest, service: SupplierSvc, p: SupplierManage
) -> Any:
    await service.set_status(supplier_id, body.status, actor_id=p.id)
    return (await service.detail(supplier_id)).supplier


class AssignSupplierCenterRequest(BaseModel):
    center_id: uuid.UUID


@supplier_router.post("/{supplier_id}/centers", status_code=201)
async def assign_supplier_center(
    supplier_id: uuid.UUID,
    body: AssignSupplierCenterRequest,
    service: SupplierSvc,
    p: SupplierManage,
) -> dict:
    a = await service.assign_center(supplier_id, body.center_id, actor_id=p.id)
    return {"supplier_id": str(a.supplier_id), "center_id": str(a.center_id)}


@supplier_router.delete("/{supplier_id}/centers/{center_id}", status_code=204)
async def unassign_supplier_center(
    supplier_id: uuid.UUID, center_id: uuid.UUID, service: SupplierSvc, p: SupplierManage
) -> None:
    await service.unassign_center(supplier_id, center_id, actor_id=p.id)


class AssignSupplierBranchRequest(BaseModel):
    branch_id: uuid.UUID


@supplier_router.post("/{supplier_id}/branch", response_model=SupplierView)
async def assign_supplier_branch(
    supplier_id: uuid.UUID,
    body: AssignSupplierBranchRequest,
    service: SupplierSvc,
    p: SupplierManage,
) -> Any:
    await service.set_branch(supplier_id, body.branch_id, actor_id=p.id)
    return (await service.detail(supplier_id)).supplier


@supplier_router.post(
    "/{supplier_id}/bank-accounts", response_model=BankAccountView, status_code=201
)
async def add_supplier_bank_account(
    supplier_id: uuid.UUID, cmd: AddBankAccountCommand, service: SupplierSvc, p: SupplierManage
) -> Any:
    account = await service.add_bank_account(supplier_id, cmd, actor_id=p.id)
    accounts = await service.list_bank_accounts(supplier_id)
    return next(a for a in accounts if a.id == account.id)


@supplier_router.get("/{supplier_id}/bank-accounts", response_model=list[BankAccountView])
async def list_supplier_bank_accounts(
    supplier_id: uuid.UUID, service: SupplierSvc, _: SupplierRead
) -> Any:
    return await service.list_bank_accounts(supplier_id)


@supplier_router.post("/{supplier_id}/documents", response_model=DocumentView, status_code=201)
async def add_supplier_document(
    supplier_id: uuid.UUID, cmd: UploadDocumentCommand, service: SupplierSvc, p: SupplierManage
) -> Any:
    return await service.add_document(supplier_id, cmd, actor_id=p.id)


@supplier_router.get("/{supplier_id}/documents", response_model=list[DocumentView])
async def list_supplier_documents(
    supplier_id: uuid.UUID, service: SupplierSvc, _: SupplierRead
) -> Any:
    return await service.list_documents(supplier_id)


@supplier_router.get("/{supplier_id}/documents/{document_id}/url")
async def get_supplier_document_url(
    supplier_id: uuid.UUID, document_id: uuid.UUID, service: SupplierSvc, _: SupplierRead
) -> dict:
    return {"url": await service.document_url(supplier_id, document_id)}


@supplier_router.get("/{supplier_id}/qr")
async def get_supplier_qr(supplier_id: uuid.UUID, service: SupplierSvc, _: SupplierRead) -> dict:
    supplier = await service.get(supplier_id)
    return {"payload": qr_payload_for(supplier.id), "code": supplier.code}


class ResolveQrRequest(BaseModel):
    payload: str


@supplier_router.post("/qr/resolve", response_model=SupplierView)
async def resolve_supplier_qr(body: ResolveQrRequest, service: SupplierSvc, _: SupplierRead) -> Any:
    supplier = await service.resolve_qr(body.payload)
    return (await service.detail(supplier.id)).supplier


class ImportRequest(BaseModel):
    # Loose dicts by design: each row is validated individually in the service
    # so a single malformed row yields a per-row error, not a 422 batch failure.
    rows: list[dict[str, Any]]


@supplier_router.post("/import", response_model=list[ImportRowResult])
async def import_suppliers(body: ImportRequest, service: SupplierSvc, p: SupplierManage) -> Any:
    return await service.import_rows(body.rows, actor_id=p.id)


# --- Milk collection (sessions + transaction engine) ------------------------
milk_router = APIRouter(tags=["milk-collection"])
SessionManage = Annotated[Principal, Depends(require_permission("collection.session.manage"))]
TxRecord = Annotated[Principal, Depends(require_permission("collection.transaction.record"))]
TxRead = Annotated[Principal, Depends(require_permission("collection.transaction.read"))]
MilkSvc = Annotated[MilkCollectionService, Depends(deps.get_milk_collection_service)]


class OpenSessionRequest(BaseModel):
    center_id: uuid.UUID
    label: str = ""


@milk_router.post("/collection-sessions", response_model=SessionView, status_code=201)
async def open_collection_session(
    body: OpenSessionRequest, service: MilkSvc, p: SessionManage
) -> Any:
    return await service.open_session(body.center_id, body.label, actor_id=p.id)


@milk_router.post("/collection-sessions/{session_id}/close", response_model=SessionView)
async def close_collection_session(
    session_id: uuid.UUID, service: MilkSvc, p: SessionManage
) -> Any:
    return await service.close_session(session_id, actor_id=p.id)


@milk_router.get("/collection-sessions", response_model=list[SessionView])
async def list_collection_sessions(
    service: MilkSvc,
    _: TxRead,
    center_id: uuid.UUID | None = None,
    status: str | None = None,
) -> Any:
    return await service.list_sessions(center_id=center_id, status=status)


class CreateTransactionRequest(BaseModel):
    session_id: uuid.UUID


@milk_router.post("/milk-transactions", response_model=TransactionView, status_code=201)
async def create_milk_transaction(
    body: CreateTransactionRequest, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.create_transaction(body.session_id, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/identify", response_model=TransactionView)
async def identify_transaction_supplier(
    tx_id: uuid.UUID, cmd: IdentifySupplierCommand, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.identify_supplier(tx_id, cmd, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/milk", response_model=TransactionView)
async def receive_transaction_milk(
    tx_id: uuid.UUID, cmd: MilkInfoCommand, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.receive_milk(tx_id, cmd, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/weight", response_model=TransactionView)
async def capture_transaction_weight(
    tx_id: uuid.UUID, cmd: WeightCommand, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.capture_weight(tx_id, cmd, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/quality", response_model=TransactionView)
async def capture_transaction_quality(
    tx_id: uuid.UUID, cmd: QualityCommand, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.capture_quality(tx_id, cmd, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/accept", response_model=TransactionView)
async def accept_transaction(tx_id: uuid.UUID, service: MilkSvc, p: TxRecord) -> Any:
    return await service.accept(tx_id, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/reject", response_model=TransactionView)
async def reject_transaction(
    tx_id: uuid.UUID, cmd: RejectCommand, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.reject(tx_id, cmd, actor_id=p.id)


@milk_router.post("/milk-transactions/{tx_id}/complete", response_model=TransactionView)
async def complete_transaction(tx_id: uuid.UUID, service: MilkSvc, p: TxRecord) -> Any:
    return await service.complete(tx_id, actor_id=p.id)


class CancelTransactionRequest(BaseModel):
    reason: str = ""


@milk_router.post("/milk-transactions/{tx_id}/cancel", response_model=TransactionView)
async def cancel_transaction(
    tx_id: uuid.UUID, body: CancelTransactionRequest, service: MilkSvc, p: TxRecord
) -> Any:
    return await service.cancel(tx_id, body.reason, actor_id=p.id)


@milk_router.get("/milk-transactions", response_model=TransactionPage)
async def list_milk_transactions(
    service: MilkSvc,
    _: TxRead,
    session_id: uuid.UUID | None = None,
    center_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    state: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> TransactionPage:
    return await service.list_transactions(
        session_id=session_id,
        center_id=center_id,
        supplier_id=supplier_id,
        state=state,
        limit=limit,
        offset=offset,
    )


@milk_router.get("/milk-transactions/{tx_id}", response_model=TransactionView)
async def get_milk_transaction(tx_id: uuid.UUID, service: MilkSvc, _: TxRead) -> Any:
    return await service.get_tx_view(tx_id)


@milk_router.get("/milk-transactions/{tx_id}/events", response_model=list[TransactionEventView])
async def get_milk_transaction_events(tx_id: uuid.UUID, service: MilkSvc, _: TxRead) -> Any:
    return await service.list_events(tx_id)


# --- Event relay (internal platform operations) -----------------------------
relay_router = APIRouter(prefix="/_relay", tags=["event-relay"])
RelayOps = Annotated[Principal, Depends(require_permission("platform.relay.manage"))]
RelaySvc = Annotated[RelayService, Depends(deps.get_relay_service)]


@relay_router.get("/status", response_model=RelayStats)
async def relay_status(service: RelaySvc, _: RelayOps) -> RelayStats:
    return await service.stats()


@relay_router.get("/events", response_model=list[OutboxEventView])
async def relay_events(
    service: RelaySvc, _: RelayOps, status: str | None = None, limit: int = 50
) -> Any:
    return await service.list_events(status=status, limit=limit)


@relay_router.get("/dead-letters", response_model=list[DeadLetterView])
async def relay_dead_letters(service: RelaySvc, _: RelayOps, limit: int = 50) -> Any:
    return await service.list_dead_letters(limit=limit)


@relay_router.post("/dead-letters/{dead_letter_id}/replay", response_model=OutboxEventView)
async def relay_replay_dead_letter(
    dead_letter_id: uuid.UUID, service: RelaySvc, _: RelayOps
) -> Any:
    return await service.replay_dead_letter(dead_letter_id)


@relay_router.post("/events/{event_id}/retry", response_model=OutboxEventView)
async def relay_retry_event(event_id: uuid.UUID, service: RelaySvc, _: RelayOps) -> Any:
    return await service.retry_event(event_id)


@relay_router.post("/events/{event_id}/replay", response_model=OutboxEventView)
async def relay_replay_event(event_id: uuid.UUID, service: RelaySvc, _: RelayOps) -> Any:
    return await service.replay_delivered(event_id)


@relay_router.post("/dispatch")
async def relay_dispatch_now(service: RelaySvc, _: RelayOps) -> dict:
    delivered = await service.dispatch_pending()
    return {"delivered": delivered}


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
    ops_router,
    supplier_router,
    milk_router,
    relay_router,
    authz_router,
    config_router,
    audit_router,
):
    router.include_router(sub)
