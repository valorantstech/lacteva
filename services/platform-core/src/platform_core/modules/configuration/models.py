"""Configuration module — scoped configuration entries.

Resolution order (most specific wins): tenant → global. This is the platform
mechanism that market packs (ETE.LOC) and market-parameterized business rules
(e.g. Collect R05 variance tolerance) will use.
TODO(M2): market scope between global and tenant once market packs land.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow


class ConfigEntry(Base, IdMixin):
    __tablename__ = "config_entry"
    __table_args__ = (
        UniqueConstraint("scope", "tenant_id", "key", name="uq_config_scope_tenant_key"),
    )

    scope: Mapped[str] = mapped_column(String(10))  # "global" | "tenant"
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    key: Mapped[str] = mapped_column(String(160), index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON)  # {"value": <json>} envelope
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
