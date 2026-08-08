"""Operator command line for backup and recovery (BAK-001).

    uv run python -m platform_core.core.backup.cli <command>

    status                     are we protected right now?
    history [--kind K]         every recorded backup, restore, verification
    classification             what is captured, what is rebuilt, and why
    backup PATH                take and verify a backup
    verify PATH                re-checksum a backup on disk
    integrity [--deep]         check the LIVE database against business rules
    restore PATH [--force]     DESTRUCTIVE: load a backup into the database
                               (checksums are verified first; --skip-verification
                               overrides, which you should almost never do)

**Restore lives here and nowhere else.** It is not an HTTP endpoint and never
will be: overwriting the database is the most destructive operation this
platform can perform, and an endpoint puts it one misrouted request away.
A CLI requires someone to be on the host, holding the credentials, having
typed the word.

Everything here is read-only except `restore`, which refuses a non-empty
database unless `--force` is given.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path


def _print(payload) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, default=str) + "\n")


def _offsite_storage():
    """The INDEPENDENT destination, from configuration only.

    Deliberately not `get_object_storage()`: that returns the application's own
    MinIO, which lives on the host whose loss the backup exists to survive.
    """
    from platform_core.core.backup.engine import BackupError
    from platform_core.core.config import get_settings
    from platform_core.infrastructure.storage import MinioObjectStorage

    settings = get_settings()
    if not settings.backup_offsite_endpoint:
        raise BackupError(
            "LACTEVA_BACKUP_OFFSITE_ENDPOINT is not configured — there is nowhere "
            "independent to put this backup"
        )
    return MinioObjectStorage(
        endpoint=settings.backup_offsite_endpoint,
        access_key=settings.backup_offsite_access_key,
        secret_key=settings.backup_offsite_secret_key,
        secure=settings.backup_offsite_secure,
        bucket=settings.backup_offsite_bucket,
    )


async def _offsite(args, service) -> int:
    """Replicate to, list, fetch from, and prune the independent store."""
    from platform_core.core.backup.engine import BackupEngine
    from platform_core.core.backup.offsite import OffsiteBackupService
    from platform_core.core.config import get_settings
    from platform_core.core.rls import platform_factory

    engine = BackupEngine(platform_factory("backup CLI: off-site replication"))
    offsite = OffsiteBackupService(_offsite_storage(), engine)

    if args.command == "replicate":
        manifest = BackupEngine.read_manifest(Path(args.path))
        result = await offsite.replicate(
            Path(args.path),
            database_identity=manifest.database_identity,
            postgres_version=manifest.postgres_version,
        )
        _print(
            {
                "backup_id": result.backup_id,
                "archive_key": result.archive_key,
                "archive_sha256": result.archive_sha256,
                "archive_bytes": result.archive_bytes,
                "rows": result.total_rows,
                "schema_revision": result.schema_revision,
            }
        )
        return 0

    if args.command == "offsite-list":
        _print(
            [
                {
                    "backup_id": m.backup_id,
                    "created_at": m.created_at,
                    "rows": m.total_rows,
                    "bytes": m.archive_bytes,
                    "schema_revision": m.schema_revision,
                }
                for m in await offsite.list_backups()
            ]
        )
        return 0

    if args.command == "offsite-fetch":
        path, manifest = await offsite.fetch(args.backup_id, Path(args.destination))
        _print(
            {
                "backup_id": manifest.backup_id,
                "restored_to": str(path),
                "verified_sha256": manifest.archive_sha256,
                "rows": manifest.total_rows,
            }
        )
        return 0

    # offsite-prune
    keep = args.keep if args.keep is not None else get_settings().backup_offsite_retain
    doomed = await offsite.prune(keep=keep, dry_run=not args.delete)
    _print({"keep": keep, "dry_run": not args.delete, "selected": doomed})
    return 0


async def _run(args: argparse.Namespace) -> int:
    from platform_core.core.backup.engine import BackupError
    from platform_core.core.backup.service import BackupService
    from platform_core.core.rls import platform_factory

    # A backup spans every tenant by definition; a restore writes rows back
    # into every tenant. Neither is meaningful through a tenant-scoped session.
    service = BackupService(platform_factory("backup CLI: whole-database operation"))

    if args.command == "status":
        status = await service.status()
        _print(status.model_dump())
        return 0 if status.healthy else 1

    if args.command == "history":
        _print([run.model_dump() for run in await service.history(kind=args.kind)])
        return 0

    if args.command == "classification":
        _print([entry.model_dump() for entry in service.classification()])
        return 0

    if args.command in ("replicate", "offsite-list", "offsite-fetch", "offsite-prune"):
        return await _offsite(args, service)

    if args.command == "backup":
        run = await service.run_backup(
            Path(args.path), include_rebuildable=args.include_rebuildable
        )
        _print(service._view(run).model_dump())
        return 0 if run.status == "succeeded" else 1

    if args.command == "verify":
        try:
            run = await service.verify_backup(Path(args.path))
        except BackupError as exc:
            _print({"status": "failed", "error": str(exc)})
            return 1
        _print(service._view(run).model_dump())
        return 0 if run.status == "succeeded" else 1

    if args.command == "integrity":
        run = await service.verify_integrity(deep=args.deep)
        _print(service._view(run).model_dump())
        return 0 if run.status == "succeeded" else 1

    if args.command == "restore":
        # The one destructive path. Say so, loudly, before doing it.
        sys.stderr.write(
            f"RESTORE: loading {args.path} into the configured database.\n"
            f"         This REPLACES existing data.{' (--force given)' if args.force else ''}\n"
        )
        try:
            manifest = await service.engine.restore(
                Path(args.path),
                allow_non_empty=args.force,
                verify_first=not args.skip_verification,
                allow_schema_mismatch=args.allow_schema_mismatch,
            )
        except BackupError as exc:
            sys.stderr.write(f"restore refused: {exc}\n")
            return 1
        report = await service.verifier.verify(deep=True)
        _print(
            {
                "restored_backup_id": manifest.backup_id,
                "tables": len(manifest.tables),
                "rows": manifest.total_rows,
                "integrity_healthy": report.healthy,
                "checks": [
                    {"name": c.name, "passed": c.passed, "detail": c.detail} for c in report.checks
                ],
            }
        )
        # A restore that loaded every row but left the business wrong is a
        # FAILED restore, and the exit code must say so.
        return 0 if report.healthy else 1

    raise SystemExit(f"unknown command {args.command!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="platform-backup", description="Lacteva backup and recovery operator tools"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="are we protected right now?")
    history = sub.add_parser("history", help="recorded backup/restore/verify runs")
    history.add_argument("--kind", choices=("backup", "restore", "verify"), default=None)
    sub.add_parser("classification", help="what is captured, what is rebuilt, and why")

    backup = sub.add_parser("backup", help="take and verify a backup")
    backup.add_argument("path")
    backup.add_argument(
        "--include-rebuildable",
        action="store_true",
        help="also capture projections (faster restore, larger backup)",
    )

    verify = sub.add_parser("verify", help="re-checksum a backup on disk")
    verify.add_argument("path")

    # --- off-site replication (BKP-003) ---
    replicate = sub.add_parser(
        "replicate", help="upload a verified local backup to the independent store"
    )
    replicate.add_argument("path")

    sub.add_parser("offsite-list", help="list complete off-site backups, newest first")

    fetch = sub.add_parser(
        "offsite-fetch", help="download and verify an off-site backup into a directory"
    )
    fetch.add_argument("backup_id")
    fetch.add_argument("destination")

    prune = sub.add_parser("offsite-prune", help="apply retention to the off-site store")
    prune.add_argument("--keep", type=int, default=None)
    # Deleting requires saying so. A retention command that deletes by default
    # is one that will eventually be run by somebody who was just looking.
    prune.add_argument("--delete", action="store_true", help="actually delete (default is dry-run)")

    integrity = sub.add_parser("integrity", help="check the live database against business rules")
    integrity.add_argument(
        "--deep", action="store_true", help="also rebuild projections from the event log"
    )

    restore = sub.add_parser("restore", help="DESTRUCTIVE: load a backup into the database")
    restore.add_argument("path")
    restore.add_argument(
        "--allow-schema-mismatch",
        action="store_true",
        help=(
            "restore even though the target's migration revision differs from "
            "the backup's. Data can be lost or silently nulled; migrate the "
            "target to the backup's revision instead"
        ),
    )
    restore.add_argument(
        "--skip-verification",
        action="store_true",
        help=(
            "DANGEROUS: load the backup without checking it against its own "
            "checksums. Only for a partial recovery from a backup already known "
            "to be damaged, where some data is better than none"
        ),
    )
    restore.add_argument(
        "--force", action="store_true", help="allow restoring over a non-empty database"
    )

    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
