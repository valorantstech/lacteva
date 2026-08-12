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
        # SEC-002: `organization` is isolated by IDENTITY — a bound session
        # sees exactly its own row. Creating one is therefore necessarily a
        # cross-tenant act: the organization does not exist yet, so nobody can
        # be bound to it, and both the slug-uniqueness check (which must see
        # every tenant's slug) and the INSERT would be refused by the policy.
        # An audited bypass is the honest mechanism; a NULL hole in the policy
        # would have been a permanent one.
        from platform_core.core.rls import bind_platform_context

        await bind_platform_context(
            self._session, reason="organization creation: no tenant exists yet"
        )
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
        # SEC-002: under the identity policy a bound tenant sees exactly its
        # own organization, so a tenant asking for someone else's gets a 404
        # from the database rather than a row from a forgotten filter.
        #
        # A platform-level principal has no tenant bound and would therefore
        # see nothing at all. Reading another organization IS a cross-tenant
        # act, so it takes the audited bypass — and only after the route's
        # `organization.read` guard has already run. The test that matters
        # here is that a TENANT-scoped caller never reaches this branch: a
        # tenant token always binds a tenant, so `get_current_tenant()` is
        # None only for platform principals.
        from platform_core.core.rls import bind_platform_context
        from platform_core.core.tenancy import get_current_tenant

        if get_current_tenant() is None:
            await bind_platform_context(
                self._session, reason=f"platform principal reading organization {org_id}"
            )
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

    MEMBERSHIP_STATUSES = ("active", "suspended", "invited")

    async def set_status(
        self, user_id: uuid.UUID, status: str, *, actor_id: uuid.UUID | None = None
    ) -> Membership:
        """Suspend or reinstate a member of the current organization.

        DEMO-008: the status column existed from the beginning and nothing
        could write it — suspension was a database operation, which meant in
        practice that it never happened. It is an end state rather than a
        verb, so suspending twice is not an error.
        """
        if status not in self.MEMBERSHIP_STATUSES:
            raise ConflictError(f"status must be one of {', '.join(self.MEMBERSHIP_STATUSES)}")
        tenant_id = get_current_tenant()
        if tenant_id is None:
            raise ForbiddenError("tenant context required")
        membership = await self._session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id, Membership.user_id == user_id
            )
        )
        if membership is None:
            raise NotFoundError("membership not found")
        membership.status = status
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
        """Returns (invitation, raw_token). The raw token goes to the CALLER
        (service layer) only — the API never exposes it, exactly as
        `AuthService.request_password_reset` does.

        SEC-003 / F-04: it used to be returned in the API response "as a
        FOUNDATION-ONLY convenience until email delivery lands". Delivery has
        landed, and the convenience was a hole: the inviter could accept the
        invitation themselves and create an account bound to the invitee's
        email address, inside the invitee's future tenant, with the role the
        invitation named. Only the hash is stored, and the raw value travels
        to the invitee through the notification channel as a SECRET variable
        (see `Notification.secret_payload`) — never through this response,
        never through the outbox payload, never through a log line.
        """
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
                    "email": invitation.email,
                    "expires_days": INVITATION_TTL.days,
                    # NOTE the absence of the token. This payload lands in
                    # `event_outbox`, which is classified critical, is never
                    # pruned, and is in every backup — the last place a live
                    # one-time secret should be.
                },
                actor_id=actor_id,
            )
        )
        await self._send_invitation(invitation, raw, role_name)
        return invitation, raw

    async def _send_invitation(self, invitation: Invitation, raw_token: str, role_name: str):
        """The one place a business module sends a notification itself, and
        the reason is the secret (SEC-003 / F-04).

        Everywhere else the module publishes and the notification consumer
        sends — that separation is NOT-001/BR-0016 and it stands. It cannot
        stand here: the consumer reads the durable outbox log, so anything the
        consumer needs must be written into `event_outbox.payload`, which is
        never pruned and is captured by every backup. Putting a live
        invitation token there trades one exposure for a worse one.

        Everything else about the message is unchanged — same template, same
        provider, same delivery record, same retry budget, same idempotency
        (keyed on the invitation id, so re-issuing is not re-sending).
        """
        from platform_core.modules.notification.service import (
            NotificationRequest,
            NotificationService,
        )

        return await NotificationService(self._session).dispatch(
            NotificationRequest(
                event_id=invitation.id,
                event_name="organization.invitation-issued.v1",
                tenant_id=invitation.tenant_id,
                template_key="invitation",
                channel="email",
                recipient=invitation.email,
                variables={
                    "role": role_name,
                    "organization": "Lacteva",
                    "expires_days": INVITATION_TTL.days,
                },
                secret_variables={"invite_token": raw_token},
            )
        )

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
        # SEC-002: accepting an invitation is definitionally pre-tenant — the
        # caller is anonymous and the whole point of the lookup is to discover
        # which tenant they are joining. `invitation` is tenant-owned, so an
        # unbound session cannot see it. This is the narrowest possible
        # bypass: one indexed read by token hash, immediately followed by
        # binding to the tenant that read reveals.
        from platform_core.core.rls import bind_platform_context, rebind_tenant

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        await bind_platform_context(
            self._session, reason="invitation acceptance: resolve tenant from token"
        )
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
        # Bypass ends here. Everything below writes tenant-owned rows
        # (user_account, membership, user_role) and must be constrained by
        # the tenant the invitation named — `set_current_tenant` alone moved
        # the context variable but left the database binding behind, so
        # WITH CHECK rejected the writes.
        await rebind_tenant(self._session, invitation.tenant_id)
        user = await identity.register_user(
            RegisterUserCommand(email=invitation.email, password=password, full_name=full_name),
            tenant_id=invitation.tenant_id,
        )
        await membership.add_member(
            user_id=user.id, tenant_id=invitation.tenant_id, invited_by=invitation.invited_by
        )
        await authz.assign_role(
            user_id=user.id,
            role_name=invitation.role_name,
            tenant_id=invitation.tenant_id,
            # The new account grants itself the role the invitation named.
            # There is no other actor: the inviter is not present at
            # acceptance time, and attributing it to them would misreport who
            # was at the keyboard.
            actor_id=user.id,
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
