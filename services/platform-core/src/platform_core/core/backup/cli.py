"""Operator command line for backup and recovery (BAK-001).

    uv run python -m platform_core.core.backup.cli <command>

    status                     are we protected right now?
    history [--kind K]         every recorded backup, restore, verification
    classification             what is captured, what is rebuilt, and why
    backup PATH                take and verify a backup
    verify PATH                re-checksum a backup on disk
    integrity [--deep]         check the LIVE database against business rules
    restore PATH [--force]     DESTRUCTIVE: load a backup into the database

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


async def _run(args: argparse.Namespace) -> int:
    from platform_core.core.backup.engine import BackupError
    from platform_core.core.backup.service import BackupService
    from platform_core.core.db import get_session_factory

    service = BackupService(get_session_factory())

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
            manifest = await service.engine.restore(Path(args.path), allow_non_empty=args.force)
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

    integrity = sub.add_parser("integrity", help="check the live database against business rules")
    integrity.add_argument(
        "--deep", action="store_true", help="also rebuild projections from the event log"
    )

    restore = sub.add_parser("restore", help="DESTRUCTIVE: load a backup into the database")
    restore.add_argument("path")
    restore.add_argument(
        "--force", action="store_true", help="allow restoring over a non-empty database"
    )

    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
