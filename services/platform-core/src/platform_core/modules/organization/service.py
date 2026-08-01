"""Organization module — application service."""

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.infrastructure.events import EventBus, EventEnvelope
from platform_core.modules.audit.service import AuditService
from platform_core.modules.organization.models import Organization


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

    # TODO(M1): membership management (add user to org with role — currently
    # done via authz role assignment directly), suspension, offboarding
    # (data retention rules per DBD lifecycle standards).
