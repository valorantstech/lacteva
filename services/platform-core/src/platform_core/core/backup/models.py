"""Backup run history (BAK-001).

The platform records its own backup and restore runs so an operator can
answer "when did this last succeed?" without reading a cron log on a host
they may no longer have access to — which is precisely the situation a
disaster puts them in.

This table is deliberately NOT tenant-scoped: a backup is a platform
operation covering every tenant at once, and scoping it would imply a
per-tenant recovery story the platform does not offer.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

BACKUP_KINDS = ("backup", "restore", "verify")
BACKUP_STATUSES = ("running", "succeeded", "failed")


class BackupRun(Base, IdMixin):
    __tablename__ = "backup_run"

    kind: Mapped[str] = mapped_column(String(12), index=True)
    status: Mapped[str] = mapped_column(String(12), default="running", index=True)
    backup_id: Mapped[uuid.UUID | None] = mapped_column(default=None, nullable=True)
    location: Mapped[str] = mapped_column(String(500), default="")
    tables: Mapped[int] = mapped_column(Integer, default=0)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    bytes_written: Mapped[int] = mapped_column(Integer, default=0)
    # Verification outcome, so history answers "was it good?" not just "did it run?"
    verified: Mapped[bool] = mapped_column(default=False)
    integrity: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        from platform_core.core.db import as_utc

        return round((as_utc(self.finished_at) - as_utc(self.started_at)).total_seconds(), 2)
