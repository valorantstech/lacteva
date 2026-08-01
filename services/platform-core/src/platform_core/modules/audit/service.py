"""Audit module — write path (used by every other module) and query path."""

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.tenancy import get_current_tenant
from platform_core.modules.audit.models import AuditRecord


class AuditService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | str,
        actor_id: uuid.UUID | None,
        detail: dict[str, Any] | None = None,
    ) -> AuditRecord:
        ctx = structlog.contextvars.get_contextvars()
        rec = AuditRecord(
            tenant_id=get_current_tenant(),
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            detail=detail or {},
            request_id=ctx.get("request_id"),
        )
        self._session.add(rec)
        return rec

    async def list_records(self, *, limit: int = 100) -> list[AuditRecord]:
        """Tenant-scoped listing, newest first. TODO(M2): filters + OpenSearch
        projection for full-text/faceted audit queries (search.index_name('audit'))."""
        stmt = (
            select(AuditRecord)
            .where(AuditRecord.tenant_id == get_current_tenant())
            .order_by(AuditRecord.created_at.desc())
            .limit(min(limit, 500))
        )
        return list((await self._session.scalars(stmt)).all())
