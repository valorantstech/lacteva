"""Audit module — write path (used by every other module) and query path."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import structlog
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import as_utc
from platform_core.core.tenancy import get_current_tenant
from platform_core.modules.audit.models import AuditRecord


def _start_of(day: date) -> datetime:
    """Midnight UTC. The platform's clock is UTC everywhere; a local midnight
    here would silently shift the window by the operator's offset."""
    return datetime.combine(day, time.min, tzinfo=UTC)


class AuditEntryView(BaseModel):
    id: uuid.UUID
    action: str
    resource_type: str
    resource_id: str
    actor_id: uuid.UUID | None
    request_id: str | None
    detail: dict[str, Any]
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditEntryView]
    total: int
    limit: int
    offset: int


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
        """Tenant-scoped listing, newest first — the original unfiltered read.

        Kept because callers exist; `search` below is the one the API uses.
        """
        stmt = (
            select(AuditRecord)
            .where(AuditRecord.tenant_id == get_current_tenant())
            .order_by(AuditRecord.created_at.desc())
            .limit(min(limit, 500))
        )
        return list((await self._session.scalars(stmt)).all())

    async def search(
        self,
        *,
        q: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        actor_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditPage:
        """Filtered, paged audit history — the TODO(M2) this module carried.

        DEMO-007: the audit screen could only ever say "the newest 100 things
        that happened", which is not an answer to "what did this operator do
        to that settlement". Filtering in the browser was the alternative, and
        it would have been a lie the moment the 101st record existed.

        The OpenSearch projection in the original TODO is still the right home
        for full-text search; this is the exact-match half, which is what an
        operations screen actually asks for.
        """
        conditions = [AuditRecord.tenant_id == get_current_tenant()]
        if action:
            conditions.append(AuditRecord.action.ilike(f"%{action}%"))
        if resource_type:
            conditions.append(AuditRecord.resource_type == resource_type)
        if actor_id is not None:
            conditions.append(AuditRecord.actor_id == actor_id)
        if date_from is not None:
            conditions.append(AuditRecord.created_at >= _start_of(date_from))
        if date_to is not None:
            conditions.append(AuditRecord.created_at < _start_of(date_to) + timedelta(days=1))
        if q:
            like = f"%{q}%"
            conditions.append(
                or_(
                    AuditRecord.action.ilike(like),
                    AuditRecord.resource_type.ilike(like),
                    AuditRecord.resource_id.ilike(like),
                )
            )

        total = await self._session.scalar(
            select(func.count()).select_from(AuditRecord).where(*conditions)
        )
        rows = (
            await self._session.scalars(
                select(AuditRecord)
                .where(*conditions)
                .order_by(AuditRecord.created_at.desc(), AuditRecord.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return AuditPage(
            items=[
                AuditEntryView(
                    id=r.id,
                    action=r.action,
                    resource_type=r.resource_type,
                    resource_id=r.resource_id,
                    actor_id=r.actor_id,
                    request_id=r.request_id,
                    detail=r.detail or {},
                    created_at=as_utc(r.created_at),
                )
                for r in rows
            ],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    async def actions(self) -> list[str]:
        """The action vocabulary actually present in this tenant's history.

        The filter dropdown is built from what happened, not from a hard-coded
        list that would drift the moment a module records something new.
        """
        rows = await self._session.scalars(
            select(AuditRecord.action)
            .where(AuditRecord.tenant_id == get_current_tenant())
            .group_by(AuditRecord.action)
            .order_by(AuditRecord.action)
        )
        return list(rows.all())
