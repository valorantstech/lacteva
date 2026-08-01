"""Configuration module — application service."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.errors import NotFoundError
from platform_core.core.tenancy import get_current_tenant
from platform_core.modules.audit.service import AuditService
from platform_core.modules.configuration.models import ConfigEntry


class ConfigurationService:
    def __init__(self, session: AsyncSession, audit: AuditService):
        self._session = session
        self._audit = audit

    async def resolve(self, key: str) -> Any:
        """Tenant value if present, else global; NotFound if neither."""
        tenant_id = get_current_tenant()
        if tenant_id is not None:
            entry = await self._session.scalar(
                select(ConfigEntry).where(
                    ConfigEntry.scope == "tenant",
                    ConfigEntry.tenant_id == tenant_id,
                    ConfigEntry.key == key,
                )
            )
            if entry is not None:
                return entry.value["value"]
        entry = await self._session.scalar(
            select(ConfigEntry).where(ConfigEntry.scope == "global", ConfigEntry.key == key)
        )
        if entry is None:
            raise NotFoundError(f"config key not found: {key}")
        return entry.value["value"]

    async def set_value(
        self, key: str, value: Any, *, scope: str, actor_id: uuid.UUID | None
    ) -> None:
        tenant_id = get_current_tenant() if scope == "tenant" else None
        entry = await self._session.scalar(
            select(ConfigEntry).where(
                ConfigEntry.scope == scope,
                ConfigEntry.tenant_id == tenant_id,
                ConfigEntry.key == key,
            )
        )
        if entry is None:
            entry = ConfigEntry(scope=scope, tenant_id=tenant_id, key=key, value={"value": value})
            self._session.add(entry)
        else:
            entry.value = {"value": value}
        await self._audit.record(
            action="configuration.entry.set",
            resource_type="config_entry",
            resource_id=key,
            actor_id=actor_id,
            detail={"scope": scope},
        )

    # TODO(M1): typed config schemas with validation per key (a registry like
    # authz permissions), change notifications via config-changed events, and
    # read-side caching in Redis with invalidation.
