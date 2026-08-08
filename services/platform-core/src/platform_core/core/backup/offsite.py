"""Off-site backup replication (BKP-003).

QR-0007 rated this a CRITICAL blocker and the reason is one sentence:
`infra/backup/` writes to `/backup/logical` on the **same volume as the
database**, so the single most likely failure for a single-host deployment —
losing the volume — destroys the data and every means of recovering it at the
same instant. The DR and PITR proofs are real and they restore from a copy that
may not survive the incident that requires it.

This module moves a verified local backup to independent storage and, more
importantly, brings it back.

## What it deliberately does NOT do

It does not re-implement the backup. `BackupEngine` already produces a
verifiable directory (`manifest.json` + `tables/*.jsonl`) with per-table
checksums, type-tagged encoding and a schema revision, and DR-001 proved it
restores. Replacing that would throw away executed evidence to gain nothing.
This layer packages what the engine wrote, ships it, and unpacks it.

## The archive

The directory becomes ONE object, because a backup split across many objects
has no moment at which it becomes valid — a restore could find nine of ten
tables and no way to know. A single tar means the object either exists whole or
does not exist.

The tar is written deterministically (sorted members, normalised metadata,
no mtimes) so the archive checksum is a function of the DATA, not of when the
backup ran. Two backups of an unchanged database produce the same bytes, which
is what makes the checksum evidence rather than decoration.

## Why the manifest is uploaded twice

Once inside the archive, once beside it as `<id>.manifest.json`. The sidecar is
what makes retention and inspection possible without downloading gigabytes to
read six fields, and the copy inside the archive is what makes the archive
self-describing if the sidecar is ever lost. They are compared on download.

## The completion marker

An upload that dies halfway leaves a partial object, and S3 will happily serve
it. So the archive is uploaded first, verified by reading it back, and only
then is the sidecar manifest written. **A backup with no sidecar is not a
backup**, and `list_backups` will not return it. The marker is written last on
purpose: the failure mode it removes is "looks complete, restores to nothing".
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import structlog

from platform_core.core.backup.engine import MANIFEST, BackupEngine, BackupError, BackupManifest
from platform_core.core.db import utcnow

log = structlog.get_logger("backup.offsite")

#: Everything this module writes lives under one prefix, so a bucket shared
#: with anything else can never be confused for a backup namespace — and so
#: retention can never list, let alone delete, an object it does not own.
PREFIX = "backups/"

ARCHIVE_SUFFIX = ".tar"
SIDECAR_SUFFIX = ".manifest.json"


class OffsiteError(BackupError):
    """The off-site copy could not be created, verified, or retrieved."""


@dataclass
class OffsiteManifest:
    """The sidecar. Everything an operator needs before downloading anything.

    Extends the engine's manifest rather than replacing it: `backup` carries
    the original verbatim, so nothing the DR proof depends on is reinterpreted
    here.
    """

    backup_id: str
    created_at: str
    archive_key: str
    #: sha256 of the WHOLE archive. The engine checksums each table; this is
    #: the one number that says the shipped object is the object that was
    #: written, and it is what `restore` re-computes after download.
    archive_sha256: str
    archive_bytes: int
    #: Identity of the source database, so a restore cannot quietly load one
    #: deployment's data into another. Never a URL — a manifest must not carry
    #: credentials.
    database_identity: str
    postgres_version: str
    schema_revision: str
    platform_version: str
    total_rows: int
    table_count: int
    backup: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str | bytes) -> OffsiteManifest:
        return cls(**json.loads(raw))

    @property
    def engine_manifest(self) -> BackupManifest:
        return BackupManifest.from_json(json.dumps(self.backup))


def _archive_key(backup_id: str) -> str:
    return f"{PREFIX}{backup_id}{ARCHIVE_SUFFIX}"


def _sidecar_key(backup_id: str) -> str:
    return f"{PREFIX}{backup_id}{SIDECAR_SUFFIX}"


def pack(directory: Path) -> bytes:
    """A backup directory as one deterministic tar.

    Determinism is not tidiness. If the archive embedded mtimes or uid/gid, two
    backups of identical data would have different checksums, and a checksum
    that changes when the data does not cannot be used to detect corruption.
    """
    directory = Path(directory)
    members = sorted(p for p in directory.rglob("*") if p.is_file())
    if not members:
        raise OffsiteError(f"nothing to pack: {directory} contains no files")

    buffer = io.BytesIO()
    # `format=GNU_FORMAT` and an explicit mtime keep the bytes stable across
    # Python versions; `gettarinfo` would otherwise carry the filesystem's.
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for path in members:
            info = tarfile.TarInfo(name=str(path.relative_to(directory)))
            data = path.read_bytes()
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def unpack(archive: bytes, destination: Path) -> Path:
    """Restore the directory from a tar, refusing anything that escapes it."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as tar:
        for member in tar.getmembers():
            # A tar from a trusted backup should never contain these; a tar
            # that does is either corrupt or hostile, and unpacking it would
            # write outside the destination.
            target = (destination / member.name).resolve()
            if not str(target).startswith(str(destination.resolve())):
                raise OffsiteError(f"archive member escapes the destination: {member.name}")
            if member.issym() or member.islnk():
                raise OffsiteError(f"archive contains a link: {member.name}")
        tar.extractall(destination)  # noqa: S202 - every member checked above
    if not (destination / MANIFEST).exists():
        raise OffsiteError("archive does not contain a manifest — it is not a platform backup")
    return destination


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class OffsiteBackupService:
    """Ship a verified local backup to independent storage, and bring it back."""

    def __init__(self, storage, engine: BackupEngine | None = None) -> None:
        self._storage = storage
        self._engine = engine

    # --- replicate ----------------------------------------------------------

    async def replicate(
        self, directory: Path, *, database_identity: str, postgres_version: str = ""
    ) -> OffsiteManifest:
        """Upload a LOCAL backup directory, then prove the upload is readable.

        Order matters and is the whole design:

          1. verify locally    — never ship a backup that is already wrong
          2. pack + checksum
          3. upload archive
          4. READ IT BACK and re-checksum — an upload that reports success and
             stored something else is the failure this step exists to catch
          5. only now write the sidecar, which is what makes the backup VISIBLE

        A crash at any point before 5 leaves an orphan archive that
        `list_backups` ignores and retention will not count as a backup.
        """
        directory = Path(directory)
        if self._engine is not None:
            problems = self._engine.verify_files(directory)
            if problems:
                raise OffsiteError(
                    "refusing to replicate a backup that does not verify locally: "
                    + "; ".join(problems[:5])
                )

        manifest = BackupEngine.read_manifest(directory)
        backup_id = manifest.backup_id

        if await self._storage.stat_object(_sidecar_key(backup_id)) is not None:
            # Backup ids are uuid4, so this is either a genuine re-run of the
            # same backup or a caller reusing an id. Either way, overwriting a
            # copy that has already been verified is never the safe move.
            raise OffsiteError(
                f"backup {backup_id} already exists off-site — refusing to overwrite it"
            )

        log.info("offsite_backup_started", backup_id=backup_id, tables=len(manifest.tables))
        archive = pack(directory)
        digest = sha256_of(archive)

        await self._storage.put_object(_archive_key(backup_id), archive, "application/x-tar")

        # Read back. `stat` alone would prove a NAME exists, not that the bytes
        # are the ones we sent.
        stored = await self._storage.get_object(_archive_key(backup_id))
        if sha256_of(stored) != digest:
            await self._storage.delete_object(_archive_key(backup_id))
            raise OffsiteError(
                f"uploaded archive for {backup_id} does not match its checksum — "
                "the partial object has been removed"
            )
        log.info("offsite_checksum_verified", backup_id=backup_id, sha256=digest[:16])

        sidecar = OffsiteManifest(
            backup_id=backup_id,
            created_at=manifest.created_at or utcnow().isoformat(),
            archive_key=_archive_key(backup_id),
            archive_sha256=digest,
            archive_bytes=len(archive),
            database_identity=database_identity,
            postgres_version=postgres_version,
            schema_revision=manifest.schema_revision,
            platform_version=manifest.platform_version,
            total_rows=manifest.total_rows,
            table_count=len(manifest.tables),
            backup=json.loads(manifest.to_json()),
        )
        await self._storage.put_object(
            _sidecar_key(backup_id), sidecar.to_json().encode(), "application/json"
        )
        log.info(
            "offsite_upload_completed",
            backup_id=backup_id,
            bytes=len(archive),
            rows=sidecar.total_rows,
            schema_revision=sidecar.schema_revision,
        )
        return sidecar

    # --- read side ----------------------------------------------------------

    async def list_backups(self) -> list[OffsiteManifest]:
        """Every COMPLETE off-site backup, newest first.

        Driven by sidecars, so a half-uploaded archive is invisible here — and
        therefore invisible to retention, which is what stops a partial upload
        from being counted as one of the copies worth keeping.
        """
        found: list[OffsiteManifest] = []
        for info in await self._storage.list_objects(PREFIX):
            if not info.key.endswith(SIDECAR_SUFFIX):
                continue
            try:
                found.append(OffsiteManifest.from_json(await self._storage.get_object(info.key)))
            except Exception as exc:  # a sidecar we cannot parse is not a backup
                log.warning("offsite_manifest_unreadable", key=info.key, error=str(exc)[:120])
        return sorted(found, key=lambda m: m.created_at, reverse=True)

    async def fetch(self, backup_id: str, destination: Path) -> tuple[Path, OffsiteManifest]:
        """Download, verify, and unpack — in that order.

        The checksum is re-computed from the downloaded bytes rather than
        trusted from the store's metadata: an object that was corrupted at rest
        still has whatever ETag it was written with.
        """
        sidecar_raw = await self._read(_sidecar_key(backup_id), what="manifest")
        sidecar = OffsiteManifest.from_json(sidecar_raw)

        archive = await self._read(sidecar.archive_key, what="archive")
        digest = sha256_of(archive)
        if digest != sidecar.archive_sha256:
            raise OffsiteError(
                f"off-site archive for {backup_id} is CORRUPT: manifest says "
                f"{sidecar.archive_sha256[:16]}, downloaded bytes hash to {digest[:16]}"
            )
        if len(archive) != sidecar.archive_bytes:
            raise OffsiteError(
                f"off-site archive for {backup_id} is truncated: expected "
                f"{sidecar.archive_bytes} bytes, got {len(archive)}"
            )

        path = unpack(archive, Path(destination))
        # The manifest inside the archive must agree with the sidecar; if they
        # disagree, one of them has been tampered with or swapped.
        inner = BackupEngine.read_manifest(path)
        if inner.backup_id != sidecar.backup_id:
            raise OffsiteError(
                f"archive contains backup {inner.backup_id}, sidecar claims {sidecar.backup_id}"
            )
        log.info(
            "offsite_download_verified",
            backup_id=backup_id,
            bytes=len(archive),
            destination=str(path),
        )
        return path, sidecar

    async def _read(self, key: str, *, what: str) -> bytes:
        try:
            return await self._storage.get_object(key)
        except Exception as exc:
            raise OffsiteError(
                f"off-site {what} {key} could not be read: {type(exc).__name__}"
            ) from exc

    # --- retention ----------------------------------------------------------

    async def prune(self, *, keep: int, dry_run: bool = True) -> list[str]:
        """Delete old off-site backups, and refuse every way of deleting them all.

        INF-001's shell retention had the shape of the DR-001 finding: it
        deleted by `find -mtime` against a directory from an environment
        variable, so an unset variable pointed it somewhere else entirely. This
        one cannot be pointed anywhere: it lists only its own prefix, decides
        from the MANIFEST's `created_at` rather than the store's clock, and
        applies three rules that each independently prevent the disaster:

          * `keep` below 1 is refused outright — "keep zero backups" is never
            an instruction anyone means
          * the newest backup is excluded before anything is considered
          * if fewer backups exist than `keep`, nothing is deleted at all

        `dry_run` defaults to TRUE. A retention routine that deletes by default
        when someone is exploring is a retention routine that will one day be
        run by someone exploring.
        """
        if keep < 1:
            raise OffsiteError(f"keep must be at least 1 — refusing to prune to {keep} backups")

        backups = await self.list_backups()
        if len(backups) <= keep:
            log.info("offsite_retention_noop", have=len(backups), keep=keep)
            return []

        # `list_backups` is newest-first, so everything from index `keep` on is
        # a candidate — and index 0, the newest, can never be among them.
        doomed = backups[keep:]
        newest = backups[0].backup_id
        if any(m.backup_id == newest for m in doomed):  # pragma: no cover - impossible by slicing
            raise OffsiteError("retention selected the newest backup — refusing")

        keys = [m.backup_id for m in doomed]
        log.info(
            "offsite_retention_plan",
            keep=keep,
            have=len(backups),
            deleting=len(keys),
            newest_retained=newest,
            dry_run=dry_run,
            backup_ids=keys,
        )
        if dry_run:
            return keys

        for manifest in doomed:
            # Sidecar FIRST: it is what makes a backup visible, so removing it
            # first means an interrupted prune leaves an invisible orphan
            # rather than a listed backup whose archive has gone.
            await self._storage.delete_object(_sidecar_key(manifest.backup_id))
            await self._storage.delete_object(manifest.archive_key)
            log.info("offsite_retention_deleted", backup_id=manifest.backup_id)

        remaining = await self.list_backups()
        if not remaining:
            raise OffsiteError("retention removed every backup — this should be impossible")
        return keys
