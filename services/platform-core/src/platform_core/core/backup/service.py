"""Backup operations service (BAK-001).

Wraps the engine and the verifier so every run is *recorded*, and so the
question an operator asks in a disaster — "when did this last succeed, and
was it any good?" — is answerable from the platform itself rather than from
a cron log on a host that may no longer exist.

**Restore is not exposed here as a callable API surface.** It is available to
the CLI only. An HTTP endpoint that overwrites the database would be the most
destructive button in the platform, one misrouted request away from
catastrophe, and no amount of permission checking makes that a good trade.
"""

import uuid
from dataclasses import asdict
from pathlib import Path

import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_core.core.backup.classification import classify_all
from platform_core.core.backup.engine import BackupEngine, BackupError
from platform_core.core.backup.integrity import IntegrityVerifier
from platform_core.core.backup.models import BackupRun
from platform_core.core.db import utcnow

log = structlog.get_logger("backup.service")


def _directory_size(path: Path) -> int:
    """Total bytes on disk. Kept out of the async functions deliberately —
    filesystem walks are blocking, and the linter is right to say so."""
    return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())


class BackupRunView(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    backup_id: uuid.UUID | None
    location: str
    tables: int
    rows: int
    bytes_written: int
    verified: bool
    integrity: dict
    error: str | None
    started_at: object
    finished_at: object | None
    duration_seconds: float | None

    model_config = {"from_attributes": True, "arbitrary_types_allowed": True}


class BackupStatusView(BaseModel):
    """The answer to 'are we protected right now?'"""

    last_successful_backup: BackupRunView | None
    last_backup_attempt: BackupRunView | None
    last_verification: BackupRunView | None
    age_hours: float | None
    healthy: bool
    detail: str


class ClassificationView(BaseModel):
    table: str
    classification: str
    reason: str


#: WO-92. The retention the go-live control sheet requires (G8), and the
#: tenants that do not count as anybody's money. Both are checked by
#: `retention_gate`, run by the nightly backup and the watchdog.
RETENTION_FLOOR_DAYS = 30
DEMO_TENANT_SLUGS = frozenset({"lacteva-demo", "lacteva-india-demo", "lacteva-isolation-demo"})


class BackupService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._sf = session_factory
        self.engine = BackupEngine(session_factory)
        self.verifier = IntegrityVerifier(session_factory)

    # --- operations ---------------------------------------------------------

    async def run_backup(
        self, destination: Path, *, include_rebuildable: bool = False, verify: bool = True
    ) -> BackupRun:
        """Take a backup and record it. Verification is on by default: an
        unverified backup is a guess."""
        run = await self._start("backup", str(destination))
        try:
            manifest = await self.engine.backup(
                destination, include_rebuildable=include_rebuildable
            )
            problems = self.engine.verify_files(destination) if verify else []
            size = _directory_size(destination)
            await self._finish(
                run,
                status="succeeded" if not problems else "failed",
                backup_id=uuid.UUID(manifest.backup_id),
                tables=len(manifest.tables),
                rows=manifest.total_rows,
                bytes_written=size,
                verified=verify and not problems,
                error="; ".join(problems) if problems else None,
            )
        except Exception as exc:
            await self._finish(run, status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        return run

    async def verify_backup(self, source: Path) -> BackupRun:
        """Check a backup ON DISK without touching the database — the check
        that catches corruption before a recovery depends on it."""
        run = await self._start("verify", str(source))
        try:
            problems = self.engine.verify_files(source)
            manifest = self.engine.read_manifest(source)
            await self._finish(
                run,
                status="succeeded" if not problems else "failed",
                backup_id=uuid.UUID(manifest.backup_id),
                tables=len(manifest.tables),
                rows=manifest.total_rows,
                verified=not problems,
                error="; ".join(problems) if problems else None,
            )
        except BackupError as exc:
            await self._finish(run, status="failed", error=str(exc))
            raise
        return run

    async def verify_integrity(self, *, deep: bool = False) -> BackupRun:
        """Verify the LIVE database against the platform's own business rules.

        Useful after a restore, and useful on a schedule: silent corruption
        that nobody checks for is corruption discovered by a farmer.
        """
        run = await self._start("verify", "live-database")
        report = await self.verifier.verify(deep=deep)
        await self._finish(
            run,
            status="succeeded" if report.healthy else "failed",
            verified=report.healthy,
            integrity={"checks": [asdict(c) for c in report.checks]},
            error=(
                None
                if report.healthy
                else "; ".join(f"{c.name}: {c.detail}" for c in report.failures)
            ),
        )
        return run

    # --- history ------------------------------------------------------------

    async def history(self, *, kind: str | None = None, limit: int = 20) -> list[BackupRunView]:
        async with self._sf() as session:
            stmt = select(BackupRun).order_by(BackupRun.started_at.desc()).limit(min(limit, 200))
            if kind:
                stmt = stmt.where(BackupRun.kind == kind)
            runs = list((await session.scalars(stmt)).all())
        return [self._view(run) for run in runs]

    async def retention_gate(self, days: int) -> dict:
        """Is a retention of `days` acceptable for what this deployment holds?

        WO-92. The go-live control sheet said `BACKUP_RETAIN_DAYS=30` and the
        live host said 2, for weeks, because a number in a document is not
        checked by anything. This is: below the floor is refused the moment
        an organisation exists that is not one of the demo tenants. Demo
        tenants are named by slug — they are the only organisations a
        deployment may legitimately run with a short retention, because
        nothing in them is anybody's money.
        """
        from platform_core.modules.organization.models import Organization

        async with self._sf() as session:
            slugs = list(await session.scalars(select(Organization.slug)))
        real = sorted(s for s in slugs if s not in DEMO_TENANT_SLUGS)
        ok = days >= RETENTION_FLOOR_DAYS or not real
        return {
            "ok": ok,
            "days": days,
            "floor_days": RETENTION_FLOOR_DAYS,
            "organisations": len(slugs),
            "real_tenants": len(real),
            "detail": (
                "retention is at or above the floor"
                if days >= RETENTION_FLOOR_DAYS
                else (
                    "below the floor, but only demo tenants exist"
                    if ok
                    else f"BACKUP_RETAIN_DAYS={days} is below {RETENTION_FLOOR_DAYS} with "
                    f"{len(real)} real tenant(s): {', '.join(real[:5])}"
                )
            ),
        }

    async def status(self, *, stale_after_hours: float = 26.0) -> BackupStatusView:
        """Daily backups with a two-hour grace: 26 hours means a missed run is
        noticed the next day, not three days later."""
        async with self._sf() as session:
            last_success = await session.scalar(
                select(BackupRun)
                .where(BackupRun.kind == "backup", BackupRun.status == "succeeded")
                .order_by(BackupRun.started_at.desc())
                .limit(1)
            )
            last_attempt = await session.scalar(
                select(BackupRun)
                .where(BackupRun.kind == "backup")
                .order_by(BackupRun.started_at.desc())
                .limit(1)
            )
            last_verify = await session.scalar(
                select(BackupRun)
                .where(BackupRun.kind == "verify")
                .order_by(BackupRun.started_at.desc())
                .limit(1)
            )

        age = None
        if last_success is not None:
            from platform_core.core.db import as_utc

            age = round((utcnow() - as_utc(last_success.started_at)).total_seconds() / 3600, 2)

        if last_success is None:
            healthy, detail = False, "no successful backup has ever been recorded"
        elif age is not None and age > stale_after_hours:
            healthy, detail = False, f"the last successful backup is {age} hours old"
        elif not last_success.verified:
            healthy, detail = False, "the last backup completed but was never verified"
        else:
            healthy, detail = True, f"verified backup {age} hours old"

        return BackupStatusView(
            last_successful_backup=self._view(last_success) if last_success else None,
            last_backup_attempt=self._view(last_attempt) if last_attempt else None,
            last_verification=self._view(last_verify) if last_verify else None,
            age_hours=age,
            healthy=healthy,
            detail=detail,
        )

    @staticmethod
    def classification() -> list[ClassificationView]:
        return [ClassificationView(**vars(entry)) for entry in classify_all()]

    # --- helpers ------------------------------------------------------------

    async def _start(self, kind: str, location: str) -> BackupRun:
        async with self._sf() as session:
            run = BackupRun(kind=kind, status="running", location=location)
            session.add(run)
            await session.commit()
            await session.refresh(run)
        log.info("backup_run_started", kind=kind, location=location, run_id=str(run.id))
        return run

    async def _finish(self, run: BackupRun, **fields) -> None:
        async with self._sf() as session:
            stored = await session.get(BackupRun, run.id)
            if stored is None:  # pragma: no cover - the row was just written
                return
            for key, value in fields.items():
                setattr(stored, key, value)
            stored.finished_at = utcnow()
            await session.commit()
            await session.refresh(stored)
            for key, value in fields.items():
                setattr(run, key, value)
            run.finished_at = stored.finished_at
        level = log.info if fields.get("status") == "succeeded" else log.error
        level("backup_run_finished", kind=run.kind, status=fields.get("status"), run_id=str(run.id))

    @staticmethod
    def _view(run: BackupRun) -> BackupRunView:
        return BackupRunView(
            id=run.id,
            kind=run.kind,
            status=run.status,
            backup_id=run.backup_id,
            location=run.location,
            tables=run.tables,
            rows=run.rows,
            bytes_written=run.bytes_written,
            verified=run.verified,
            integrity=run.integrity or {},
            error=run.error,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_seconds=run.duration_seconds,
        )
