"""Organization module — application services (org, structure, membership, invitations)."""

import hashlib
import secrets
import uuid
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import (
    ConflictError,
    ForbiddenError,
    InvalidTokenError,
    NotFoundError,
)
from platform_core.core.tenancy import (
    get_current_tenant,
    require_current_tenant,
    set_current_tenant,
)
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.authz.service import AuthzService
from platform_core.modules.identity.models import User
from platform_core.modules.identity.schemas import RegisterUserCommand
from platform_core.modules.identity.service import IdentityService
from platform_core.modules.organization.models import (
    Branch,
    Invitation,
    Membership,
    Organization,
    Workspace,
)


class CreateOrganizationCommand(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
    country_code: str = Field(min_length=2, max_length=2)
    org_type: str = "cooperative"
    default_locale: str = "en"


class OrganizationView(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    country_code: str
    org_type: str
    status: str
    default_locale: str

    model_config = {"from_attributes": True}


class OrganizationService:
    def __init__(self, session: AsyncSession, bus: EventBus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit

    async def create_organization(
        self, cmd: CreateOrganizationCommand, *, actor_id: uuid.UUID | None
    ) -> Organization:
        existing = await self._session.scalar(
            select(Organization).where(Organization.slug == cmd.slug)
        )
        if existing is not None:
            raise ConflictError("slug already taken")
        org = Organization(
            name=cmd.name,
            slug=cmd.slug,
            country_code=cmd.country_code.upper(),
            org_type=cmd.org_type,
            default_locale=cmd.default_locale,
        )
        self._session.add(org)
        await self._session.flush()
        await self._audit.record(
            action="organization.created",
            resource_type="organization",
            resource_id=org.id,
            actor_id=actor_id,
        )
        await self._bus.publish(
            EventEnvelope.new(
                "organization.organization-created.v1",
                {"organization_id": str(org.id), "slug": org.slug, "country": org.country_code},
                actor_id=actor_id,
            )
        )
        return org

    async def get_organization(self, org_id: uuid.UUID) -> Organization:
        org = await self._session.get(Organization, org_id)
        if org is None:
            raise NotFoundError("organization not found")
        return org

    # TODO(M1): suspension, offboarding (data retention rules per DBD
    # lifecycle standards), verification workflow (ETE.ONB.01).


class WorkspaceView(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class BranchView(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    code: str
    status: str

    model_config = {"from_attributes": True}


class StructureService:
    """Workspaces and branches — the tenant's internal structure."""

    def __init__(self, session: AsyncSession, bus: EventBus, audit: AuditService):
        self._session = session
        self._bus = bus
        self._audit = audit

    async def create_workspace(self, *, name: str, slug: str, actor_id: uuid.UUID) -> Workspace:
        tenant_id = require_current_tenant()
        existing = await self._session.scalar(
            select(Workspace).where(Workspace.tenant_id == tenant_id, Workspace.slug == slug)
        )
        if existing is not None:
            raise ConflictError("workspace slug already exists")
        workspace = Workspace(tenant_id=tenant_id, name=name, slug=slug)
        self._session.add(workspace)
        await self._session.flush()
        await self._audit.record(
            action="organization.workspace.created",
            resource_type="workspace",
            resource_id=workspace.id,
            actor_id=actor_id,
        )
        await self._bus.publish(
            EventEnvelope.new(
                "organization.workspace-created.v1",
                {"workspace_id": str(workspace.id), "slug": slug},
                actor_id=actor_id,
            )
        )
        return workspace

    async def list_workspaces(self) -> list[Workspace]:
        tenant_id = require_current_tenant()
        stmt = select(Workspace).where(Workspace.tenant_id == tenant_id).order_by(Workspace.name)
        return list((await self._session.scalars(stmt)).all())

    async def create_branch(
        self, *, workspace_id: uuid.UUID, name: str, code: str, actor_id: uuid.UUID
    ) -> Branch:
        tenant_id = require_current_tenant()
        workspace = await self._session.get(Workspace, workspace_id)
        if workspace is None or workspace.tenant_id != tenant_id:
            raise NotFoundError("workspace not found")
        existing = await self._session.scalar(
            select(Branch).where(Branch.tenant_id == tenant_id, Branch.code == code)
        )
        if existing is not None:
            raise ConflictError("branch code already exists")
        branch = Branch(tenant_id=tenant_id, workspace_id=workspace_id, name=name, code=code)
        self._session.add(branch)
        await self._session.flush()
        await self._audit.record(
            action="organization.branch.created",
            resource_type="branch",
            resource_id=branch.id,
            actor_id=actor_id,
        )
        await self._bus.publish(
            EventEnvelope.new(
                "organization.branch-created.v1",
                {"branch_id": str(branch.id), "workspace_id": str(workspace_id), "code": code},
                actor_id=actor_id,
            )
        )
        return branch

    async def list_branches(self) -> list[Branch]:
        tenant_id = require_current_tenant()
        stmt = select(Branch).where(Branch.tenant_id == tenant_id).order_by(Branch.code)
        return list((await self._session.scalars(stmt)).all())


class MembershipService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def is_active_member(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        """Missing membership row counts as active for now (pre-invitation
        users). TODO(M2): backfill memberships and make the row mandatory."""
        m = await self._session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id, Membership.user_id == user_id
            )
        )
        return m is None or m.status == "active"

    async def add_member(
        self, *, user_id: uuid.UUID, tenant_id: uuid.UUID, invited_by: uuid.UUID | None
    ) -> Membership:
        existing = await self._session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id, Membership.user_id == user_id
            )
        )
        if existing is not None:
            return existing
        membership = Membership(tenant_id=tenant_id, user_id=user_id, invited_by=invited_by)
        self._session.add(membership)
        return membership

    async def list_members(self) -> list[Membership]:
        tenant_id = get_current_tenant()
        if tenant_id is None:
            raise ForbiddenError("tenant context required")
        stmt = (
            select(Membership)
            .where(Membership.tenant_id == tenant_id)
            .order_by(Membership.joined_at)
        )
        return list((await self._session.scalars(stmt)).all())


INVITATION_TTL = timedelta(days=7)


class InvitationService:
    def __init__(
        self,
        session: AsyncSession,
        bus: EventBus,
        audit: AuditService,
    ):
        self._session = session
        self._bus = bus
        self._audit = audit

    async def invite(
        self, *, email: str, role_name: str, actor_id: uuid.UUID
    ) -> tuple[Invitation, str]:
        """Returns (invitation, raw_token). The raw token is exposed in the
        API response as a FOUNDATION-ONLY convenience until email/SMS delivery
        lands (M2) — remove from the response when the notifier goes real."""
        tenant_id = get_current_tenant()
        if tenant_id is None:
            raise ForbiddenError("tenant context required")
        raw = secrets.token_urlsafe(32)
        invitation = Invitation(
            tenant_id=tenant_id,
            email=email.lower(),
            role_name=role_name,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            invited_by=actor_id,
            expires_at=utcnow() + INVITATION_TTL,
        )
        self._session.add(invitation)
        await self._session.flush()
        await self._audit.record(
            action="organization.invitation.issued",
            resource_type="invitation",
            resource_id=invitation.id,
            actor_id=actor_id,
            detail={"email": invitation.email, "role": role_name},
        )
        await self._bus.publish(
            EventEnvelope.new(
                "organization.invitation-issued.v1",
                {
                    "invitation_id": str(invitation.id),
                    "role": role_name,
                    # Delivery data for the notification consumer (NOT-001):
                    # this module no longer sends anything itself.
                    "email": invitation.email,
                    "expires_days": INVITATION_TTL.days,
                },
                actor_id=actor_id,
            )
        )
        return invitation, raw

    async def accept(
        self,
        *,
        token: str,
        password: str,
        full_name: str,
        identity: "IdentityService",
        authz: "AuthzService",
        membership: MembershipService,
    ) -> User:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        invitation = await self._session.scalar(
            select(Invitation).where(Invitation.token_hash == token_hash)
        )
        if (
            invitation is None
            or invitation.accepted_at is not None
            or invitation.revoked_at is not None
            or as_utc(invitation.expires_at) < utcnow()
        ):
            raise InvalidTokenError()
        set_current_tenant(invitation.tenant_id)
        user = await identity.register_user(
            RegisterUserCommand(email=invitation.email, password=password, full_name=full_name),
            tenant_id=invitation.tenant_id,
        )
        await membership.add_member(
            user_id=user.id, tenant_id=invitation.tenant_id, invited_by=invitation.invited_by
        )
        await authz.assign_role(
            user_id=user.id, role_name=invitation.role_name, tenant_id=invitation.tenant_id
        )
        invitation.accepted_at = utcnow()
        await self._audit.record(
            action="organization.invitation.accepted",
            resource_type="invitation",
            resource_id=invitation.id,
            actor_id=user.id,
        )
        await self._bus.publish(
            EventEnvelope.new(
                "organization.member-added.v1",
                {
                    "user_id": str(user.id),
                    "role": invitation.role_name,
                    "email": user.email,
                    "locale": user.locale,
                },
                actor_id=user.id,
            )
        )
        return user
