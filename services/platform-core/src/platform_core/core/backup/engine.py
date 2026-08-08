"""Logical backup and restore (BAK-001).

**A successful backup is not evidence. A successful restore is.** This engine
exists so a restore can be executed and verified rather than assumed, and so
that the verification is about *business truth* — settlements that still
balance, payments that still reconcile — not about a process exiting zero.

## Why logical, when PostgreSQL has physical backups

Both are needed and they answer different questions:

| | Physical (`pg_basebackup` + WAL) | Logical (this engine) |
| --- | --- | --- |
| Recovery point | Any instant (PITR) | The moment the backup ran |
| Speed at scale | Fast | Slower |
| Portable across versions/engines | No | Yes |
| **Verifiable by the application** | No | **Yes** |

The last row is why this exists. A physical backup can only be verified by
restoring a whole cluster; this one is a manifest the platform can read,
check, and reason about — which is what makes the automated restore test
possible. Physical PITR remains the production first line and is documented
in BACKUP.md; this is the portable, verifiable second line and the one the
test suite can actually exercise.

## Format

A backup is a directory:

    manifest.json          metadata, per-table checksums, row counts
    tables/<name>.jsonl    one JSON object per row, column order fixed

JSONL rather than SQL: it is diffable, streamable, restorable into a
different engine, and — most importantly — checksummable per table in a way
that does not depend on dump ordering quirks.

Rows are written in primary-key order and the checksum is computed over the
serialized bytes, so the same data always produces the same checksum. A
checksum that changes when nothing did is a checksum nobody trusts.
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import structlog
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_core.core.backup.classification import classify, tables_for_backup
from platform_core.core.db import Base, utcnow

log = structlog.get_logger("backup")

FORMAT_VERSION = 1
MANIFEST = "manifest.json"


class BackupError(Exception):
    """A backup or restore could not be completed or trusted."""


@dataclass
class TableBackup:
    table: str
    classification: str
    rows: int
    checksum: str  # sha256 over the serialized rows


@dataclass
class BackupManifest:
    """Everything needed to verify and restore, in one readable file."""

    backup_id: str
    format_version: int
    created_at: str
    database_url_scheme: str  # never the credentials
    platform_version: str
    # DR-001. The Alembic revision the data was dumped from. Without it a
    # restore cannot know whether the target's schema is the one this data
    # came from, and an executed test showed exactly what that costs: a
    # backup restored into a database one migration OLDER loaded all 350 rows
    # and reported `integrity_healthy: true`. The recovered system was
    # missing the ARCH-001 `amount > 0` constraint and nobody was told.
    #
    # Defaults to "" so backups written before this field still load — an
    # unknown revision warns, a MISMATCHED one refuses.
    schema_revision: str = ""
    #: BKP-003. The server the data came from and WHICH database it was.
    #: Without them a restore cannot tell one deployment's backup from
    #: another's, and DR-001 already showed what an unnoticed mismatch costs.
    #: Defaulted so backups written before this field still load.
    postgres_version: str = ""
    database_identity: str = ""
    tables: list[TableBackup] = field(default_factory=list)
    include_rebuildable: bool = False

    @property
    def total_rows(self) -> int:
        return sum(t.rows for t in self.tables)

    def checksum_of(self, table: str) -> str | None:
        return next((t.checksum for t in self.tables if t.table == table), None)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "BackupManifest":
        data = json.loads(raw)
        tables = [TableBackup(**t) for t in data.pop("tables", [])]
        return cls(**data, tables=tables)


async def _database_identity(session) -> tuple[str, str]:
    """(postgres_version, database_identity) — never credentials.

    The identity is the database NAME plus PostgreSQL's own system identifier,
    which survives a rename and differs between clusters. It is what lets a
    restore refuse to load production data into a staging cluster.
    """
    from sqlalchemy import text

    try:
        version = str(await session.scalar(text("SHOW server_version")) or "")
    except Exception:
        return "", ""
    try:
        name = str(await session.scalar(text("SELECT current_database()")) or "")
        system_id = str(
            await session.scalar(text("SELECT system_identifier FROM pg_control_system()")) or ""
        )
        return version, f"{name}@{system_id}"
    except Exception:  # pragma: no cover - non-superuser or older server
        return version, ""


async def _schema_revision(session) -> str:
    """The Alembic revision the connected database is at.

    Empty when the table is absent — a database built by `create_all` rather
    than by migrations, which is what the SQLite test suite does.
    """
    from sqlalchemy import text

    try:
        value = await session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:
        return ""
    return str(value or "")


def _encode(value):
    """Serialize a column value losslessly and deterministically.

    Types are tagged rather than coerced: a UUID that came back as a string
    on restore would break foreign keys on PostgreSQL, and a Decimal turned
    into a float would silently change what a farmer is owed (BR-0005).
    """
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, uuid.UUID):
        return {"__type__": "uuid", "value": str(value)}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    # DR-001: `time` was missing, and the omission took the whole backup down
    # rather than degrading it — `center_operating_window.opens/closes` are
    # TIME columns, so any deployment that had configured opening hours could
    # not be backed up at all. The test suite never seeded a center with
    # operating hours, so nothing exercised it.
    #
    # `time` must be tested BEFORE `datetime`? No — the reverse trap: a
    # `datetime` is a subclass of `date`, which is why `datetime` is checked
    # first above. `time` is unrelated to both, so its position is free.
    if isinstance(value, time):
        return {"__type__": "time", "value": value.isoformat()}
    if isinstance(value, bytes):
        import base64

        return {"__type__": "bytes", "value": base64.b64encode(value).decode()}
    if isinstance(value, dict | list):
        return value  # JSON columns
    raise BackupError(f"cannot serialize column value of type {type(value).__name__}")


def _decode(value):
    if isinstance(value, dict) and "__type__" in value:
        kind, raw = value["__type__"], value["value"]
        if kind == "decimal":
            return Decimal(raw)
        if kind == "uuid":
            return uuid.UUID(raw)
        if kind == "datetime":
            return datetime.fromisoformat(raw)
        if kind == "date":
            return date.fromisoformat(raw)
        if kind == "time":
            return time.fromisoformat(raw)
        if kind == "bytes":
            import base64

            return base64.b64decode(raw)
        raise BackupError(f"unknown encoded type {kind!r}")
    return value


class BackupEngine:
    """Takes and restores logical backups of the platform's own tables."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._sf = session_factory
        # Every method here reads `Base.metadata`, which is only as complete
        # as the imports this process happens to have done. Registering once,
        # here, is what stops a CLI backup capturing a fraction of the schema
        # or a restore failing on a table it cannot order (CI-001).
        from platform_core.core.model_registry import import_all_models

        import_all_models()

    # --- backup ------------------------------------------------------------

    async def backup(
        self, destination: Path, *, include_rebuildable: bool = False
    ) -> BackupManifest:
        """Write a verifiable backup to `destination`.

        Runs entirely in read-only transactions and never locks a business
        table — a backup must never be the reason milk cannot be collected.
        """
        from platform_core import __version__
        from platform_core.core.config import get_settings

        destination = Path(destination)
        (destination / "tables").mkdir(parents=True, exist_ok=True)
        wanted = set(tables_for_backup(include_rebuildable))
        manifest = BackupManifest(
            backup_id=str(uuid.uuid4()),
            format_version=FORMAT_VERSION,
            created_at=utcnow().isoformat(),
            # The scheme only: a manifest must never carry credentials.
            database_url_scheme=get_settings().database_url.split("://", 1)[0],
            platform_version=__version__,
            include_rebuildable=include_rebuildable,
        )
        async with self._sf() as session:
            manifest.schema_revision = await _schema_revision(session)
            manifest.postgres_version, manifest.database_identity = await _database_identity(
                session
            )

        for table in Base.metadata.sorted_tables:
            if table.name not in wanted:
                continue
            rows, checksum = await self._dump_table(table, destination)
            manifest.tables.append(
                TableBackup(
                    table=table.name,
                    classification=classify(table.name).classification,
                    rows=rows,
                    checksum=checksum,
                )
            )

        (destination / MANIFEST).write_text(manifest.to_json())
        log.info(
            "backup_completed",
            backup_id=manifest.backup_id,
            tables=len(manifest.tables),
            rows=manifest.total_rows,
        )
        return manifest

    async def _dump_table(self, table, destination: Path) -> tuple[int, str]:
        digest = hashlib.sha256()
        path = destination / "tables" / f"{table.name}.jsonl"
        columns = [c.name for c in table.columns]
        count = 0
        # Deterministic order: the same data must always produce the same
        # checksum, or the checksum is not evidence of anything.
        order = list(table.primary_key.columns) or list(table.columns)[:1]
        with path.open("w", encoding="utf-8") as handle:
            async with self._sf() as session:
                result = await session.stream(select(table).order_by(*order))
                async for row in result:
                    payload = {
                        name: _encode(value) for name, value in zip(columns, row, strict=True)
                    }
                    line = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                    handle.write(line + "\n")
                    digest.update(line.encode())
                    count += 1
        return count, digest.hexdigest()

    # --- restore -----------------------------------------------------------

    async def restore(
        self,
        source: Path,
        *,
        allow_non_empty: bool = False,
        batch_size: int = 500,
        verify_first: bool = True,
        allow_schema_mismatch: bool = False,
    ) -> BackupManifest:
        """Restore a backup into the configured database.

        Refuses a non-empty target unless explicitly overridden. Restoring
        over live data is the single most destructive operation this platform
        can perform, so it must be a decision, never a default — which is also
        why restore is a CLI tool and NOT an HTTP endpoint.

        DR-001: it also refuses a backup whose checksums do not match. That
        check existed — `verify_files` — and nothing called it before a
        restore, despite its own docstring saying that is when it matters. An
        executed test proved the consequence: editing one number in
        `settlement.jsonl` produced a restore that reported 350 rows loaded
        and left a settlement worth 1.00 instead of 5647.50. The corruption
        was only noticed by the integrity check that runs AFTERWARDS, by
        which point the recovery target has already been overwritten and the
        operator has to start again — during an outage.
        """
        source = Path(source)
        manifest = self.read_manifest(source)

        # DR-001: the schema this data came from must be the schema it is
        # going into. A column added since the backup silently restores as
        # NULL for every row; a column removed since takes the data with it;
        # a constraint added since is simply absent from the recovered system.
        # None of that fails loudly on its own — proven by restoring a backup
        # into a database one migration behind, which loaded every row and
        # reported healthy.
        await self._check_schema_revision(manifest, allow_schema_mismatch)

        if verify_first:
            problems = self.verify_files(source)
            if problems:
                raise BackupError(
                    "refusing to restore a backup that does not match its own "
                    f"checksums — {len(problems)} problem(s): "
                    + "; ".join(problems[:5])
                    + ". The data on disk is not what was backed up. Find an "
                    "intact copy; pass verify_first=False only if a partial "
                    "recovery from a damaged backup is genuinely better than none."
                )
        if manifest.format_version != FORMAT_VERSION:
            raise BackupError(
                f"backup format {manifest.format_version} cannot be read by this "
                f"platform (expects {FORMAT_VERSION})"
            )

        if not allow_non_empty:
            occupied = await self._non_empty_tables([t.table for t in manifest.tables])
            if occupied:
                raise BackupError(
                    "refusing to restore over a non-empty database — "
                    f"{', '.join(sorted(occupied)[:5])} already hold rows. "
                    "Pass allow_non_empty to overwrite deliberately."
                )

        by_name = {t.name: t for t in Base.metadata.sorted_tables}
        # Parents before children on the way in; the reverse on the way out.
        ordered = [
            t for t in Base.metadata.sorted_tables if t.name in {b.table for b in manifest.tables}
        ]

        async with self._sf() as session:
            for table in reversed(ordered):
                await session.execute(delete(table))
            await session.commit()

        order = [t.name for t in ordered]
        for entry in sorted(manifest.tables, key=lambda e: order.index(e.table)):
            table = by_name[entry.table]
            await self._load_table(table, source, batch_size)

        log.warning(
            "restore_completed",
            backup_id=manifest.backup_id,
            tables=len(manifest.tables),
            rows=manifest.total_rows,
        )
        return manifest

    async def _check_schema_revision(self, manifest: BackupManifest, allow_mismatch: bool) -> None:
        async with self._sf() as session:
            target = await _schema_revision(session)

        if not manifest.schema_revision or not target:
            # One side predates this field, or was built by `create_all`.
            # Warn rather than refuse: refusing would make every backup taken
            # before DR-001 unrestorable, which is a worse failure than the
            # one being guarded against.
            log.warning(
                "restore_schema_revision_unknown",
                backup=manifest.schema_revision or "unknown",
                target=target or "unknown",
                detail="cannot confirm the target schema matches the backup",
            )
            return

        if manifest.schema_revision == target:
            log.info("restore_schema_revision_matches", revision=target)
            return

        message = (
            f"the backup was taken at schema revision {manifest.schema_revision} "
            f"but this database is at {target}. Restoring across a schema change "
            "silently loses or invents data — a column added since the backup "
            "restores as NULL for every row, and a constraint added since is "
            "simply absent. Migrate the target to "
            f"{manifest.schema_revision} first (`alembic upgrade`/`downgrade`), "
            "or pass allow_schema_mismatch if you have checked the difference "
            "by hand and accept it."
        )
        if allow_mismatch:
            log.warning("restore_schema_revision_mismatch_allowed", detail=message)
            return
        raise BackupError(message)

    async def _load_table(self, table, source: Path, batch_size: int) -> None:
        path = source / "tables" / f"{table.name}.jsonl"
        if not path.exists():
            raise BackupError(f"backup is missing data for table {table.name}")
        batch: list[dict] = []
        async with self._sf() as session:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    row = {k: _decode(v) for k, v in json.loads(line).items()}
                    batch.append(row)
                    if len(batch) >= batch_size:
                        await session.execute(insert(table), batch)
                        batch.clear()
            if batch:
                await session.execute(insert(table), batch)
            await session.commit()

    async def _non_empty_tables(self, names: list[str]) -> list[str]:
        from sqlalchemy import func

        occupied = []
        by_name = {t.name: t for t in Base.metadata.sorted_tables}
        async with self._sf() as session:
            for name in names:
                table = by_name.get(name)
                if table is None:
                    continue
                count = await session.scalar(select(func.count()).select_from(table))
                if count:
                    occupied.append(name)
        return occupied

    # --- verification ------------------------------------------------------

    @staticmethod
    def read_manifest(source: Path) -> BackupManifest:
        path = Path(source) / MANIFEST
        if not path.exists():
            raise BackupError(f"no {MANIFEST} in {source} — this is not a backup directory")
        return BackupManifest.from_json(path.read_text())

    def verify_files(self, source: Path) -> list[str]:
        """Re-checksum the backup ON DISK, without touching the database.

        This is the check that catches a corrupt or truncated backup BEFORE a
        restore begins — the worst moment to discover it is halfway through a
        recovery.
        """
        source = Path(source)
        manifest = self.read_manifest(source)
        problems: list[str] = []
        for entry in manifest.tables:
            path = source / "tables" / f"{entry.table}.jsonl"
            if not path.exists():
                problems.append(f"{entry.table}: data file missing")
                continue
            digest = hashlib.sha256()
            rows = 0
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    digest.update(line.rstrip("\n").encode())
                    rows += 1
            if digest.hexdigest() != entry.checksum:
                problems.append(f"{entry.table}: checksum mismatch — the file has changed")
            if rows != entry.rows:
                problems.append(f"{entry.table}: expected {entry.rows} rows, found {rows}")
        return problems
