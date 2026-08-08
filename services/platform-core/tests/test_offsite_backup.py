"""Off-site backup replication: the failure modes (BKP-003).

The happy path is proven by execution against a real MinIO and a real
PostgreSQL — `infra/ci/offsite-proof.sh`, which destroys the database volume
and the local backup directory and recovers from the object store alone. What
lives here is everything that must NOT happen, because a backup subsystem is
judged by its refusals: the dangerous outcome is not "the backup failed", it is
"the backup reported success and cannot be restored".

Every test below is a way the platform could have lied about having a backup.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from platform_core.core.backup.offsite import (
    PREFIX,
    OffsiteBackupService,
    OffsiteError,
    OffsiteManifest,
    pack,
    sha256_of,
    unpack,
)
from platform_core.infrastructure.storage import InMemoryObjectStorage


def _write_backup(tmp_path: Path, backup_id: str, *, rows: int = 3) -> Path:
    """A backup directory shaped exactly like the engine writes one."""
    directory = tmp_path / backup_id
    (directory / "tables").mkdir(parents=True)
    (directory / "tables" / "supplier.jsonl").write_text(
        "\n".join(json.dumps({"id": n}) for n in range(rows))
    )
    manifest = {
        "backup_id": backup_id,
        "format_version": 1,
        "created_at": f"2026-08-0{(hash(backup_id) % 8) + 1}T00:00:00+00:00",
        "database_url_scheme": "postgresql+asyncpg",
        "platform_version": "0.1.0",
        "schema_revision": "5d12928a9564",
        "postgres_version": "16.2",
        "database_identity": "lacteva@7000000000000000000",
        "include_rebuildable": False,
        "tables": [
            {"table": "supplier", "classification": "critical", "rows": rows, "checksum": "abc"}
        ],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


async def _replicate(service, directory: Path):
    return await service.replicate(
        directory, database_identity="lacteva@7000000000000000000", postgres_version="16.2"
    )


@pytest.fixture
def storage():
    return InMemoryObjectStorage()


@pytest.fixture
def service(storage):
    return OffsiteBackupService(storage)


# --- the archive ------------------------------------------------------------


def test_the_archive_is_deterministic(tmp_path):
    """A checksum that changes when the data does not is not evidence.

    The tar normalises mtime, mode and ownership precisely so that two backups
    of identical data hash identically — which is what makes a checksum
    mismatch mean "corrupted" rather than "packed at a different second".
    """
    directory = _write_backup(tmp_path, "det-1")
    assert pack(directory) == pack(directory)
    assert sha256_of(pack(directory)) == sha256_of(pack(directory))


def test_packing_an_empty_directory_is_refused(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(OffsiteError, match="nothing to pack"):
        pack(empty)


def test_unpacking_rejects_a_member_that_escapes_the_destination(tmp_path):
    """A tar from a trusted backup never contains `../`. One that does is
    corrupt or hostile, and extracting it writes outside the destination."""
    import io
    import tarfile

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        info = tarfile.TarInfo(name="../escaped.txt")
        info.size = 4
        tar.addfile(info, io.BytesIO(b"evil"))
    with pytest.raises(OffsiteError, match="escapes the destination"):
        unpack(buffer.getvalue(), tmp_path / "out")


def test_unpacking_something_that_is_not_a_backup_is_refused(tmp_path):
    import io
    import tarfile

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        info = tarfile.TarInfo(name="notes.txt")
        info.size = 5
        tar.addfile(info, io.BytesIO(b"hello"))
    with pytest.raises(OffsiteError, match="not a platform backup"):
        unpack(buffer.getvalue(), tmp_path / "out")


# --- upload failures --------------------------------------------------------


async def test_an_upload_failure_leaves_no_visible_backup(tmp_path, storage, service):
    """The failure that matters: a backup that reports success and is not there."""
    directory = _write_backup(tmp_path, "fail-1")
    storage.fail_next_put = RuntimeError("network went away")

    with pytest.raises(RuntimeError):
        await _replicate(service, directory)

    assert await service.list_backups() == [], "a failed upload was listed as a backup"


async def test_an_interrupted_upload_is_not_a_backup(tmp_path, storage, service):
    """The archive lands but the process dies before the sidecar.

    This is the shape of a real interruption, and it is why the sidecar is
    written LAST: the orphan archive must be invisible, because a listed
    backup whose manifest is missing would be counted by retention as one of
    the copies worth keeping.
    """
    directory = _write_backup(tmp_path, "partial-1")
    manifest = json.loads((directory / "manifest.json").read_text())
    await storage.put_object(
        f"{PREFIX}{manifest['backup_id']}.tar", b"partial", "application/x-tar"
    )

    assert await service.list_backups() == [], "an orphan archive was treated as a backup"


async def test_a_corrupted_upload_is_detected_and_removed(tmp_path, storage, service):
    """The read-back check. An object store that accepts a PUT and stores
    something else must not produce a backup anyone trusts."""
    directory = _write_backup(tmp_path, "corrupt-upload")

    original_get = storage.get_object

    async def corrupting_get(key: str) -> bytes:
        data = await original_get(key)
        return data + b"corruption" if key.endswith(".tar") else data

    storage.get_object = corrupting_get
    with pytest.raises(OffsiteError, match="does not match its checksum"):
        await _replicate(service, directory)

    storage.get_object = original_get
    assert await service.list_backups() == []
    assert not [k for k in storage.objects if k.endswith(".tar")], (
        "the partial archive was left behind"
    )


async def test_a_duplicate_backup_id_never_overwrites(tmp_path, storage, service):
    """Overwriting a copy that has already been verified is never the safe move."""
    directory = _write_backup(tmp_path, "dup-1")
    await _replicate(service, directory)
    before = dict(storage.objects)

    with pytest.raises(OffsiteError, match="already exists off-site"):
        await _replicate(service, directory)
    assert storage.objects == before, "the existing off-site copy was modified"


async def test_a_backup_that_does_not_verify_locally_is_never_shipped(tmp_path, storage):
    """Shipping a backup that is already wrong just puts a wrong backup
    somewhere safer."""

    class RefusingEngine:
        def verify_files(self, directory):
            return ["tables/supplier.jsonl: checksum mismatch"]

    service = OffsiteBackupService(storage, RefusingEngine())
    with pytest.raises(OffsiteError, match="does not verify locally"):
        await _replicate(service, _write_backup(tmp_path, "bad-local"))
    assert storage.objects == {}


# --- download failures ------------------------------------------------------


async def test_a_missing_backup_is_a_clear_error(service, tmp_path):
    with pytest.raises(OffsiteError, match="could not be read"):
        await service.fetch("nobody-has-this-id", tmp_path / "out")


async def test_a_corrupted_archive_is_caught_by_its_checksum(tmp_path, storage, service):
    """Corruption at rest. The store's own metadata still says the object is
    whatever it was written as, so the checksum has to be recomputed."""
    directory = _write_backup(tmp_path, "rot-1")
    manifest = await _replicate(service, directory)

    storage.objects[manifest.archive_key] = b"rotted bytes that are not a tar"
    with pytest.raises(OffsiteError, match="is CORRUPT"):
        await service.fetch(manifest.backup_id, tmp_path / "out")


async def test_a_truncated_archive_is_caught_by_its_size(tmp_path, storage, service):
    directory = _write_backup(tmp_path, "trunc-1")
    manifest = await _replicate(service, directory)

    # Truncate AND fix the checksum, so only the length check can catch it.
    truncated = storage.objects[manifest.archive_key][:-64]
    storage.objects[manifest.archive_key] = truncated
    sidecar = OffsiteManifest.from_json(
        storage.objects[f"{PREFIX}{manifest.backup_id}.manifest.json"]
    )
    patched = replace(sidecar, archive_sha256=sha256_of(truncated))
    storage.objects[f"{PREFIX}{manifest.backup_id}.manifest.json"] = patched.to_json().encode()

    with pytest.raises(OffsiteError, match="truncated"):
        await service.fetch(manifest.backup_id, tmp_path / "out")


async def test_a_swapped_archive_is_caught_by_the_inner_manifest(tmp_path, storage, service):
    """Sidecar says one backup, archive contains another.

    The manifest is stored twice for this reason: if only the sidecar were
    trusted, an archive swapped underneath it would restore the wrong data
    while every checksum agreed.
    """
    first = await _replicate(service, _write_backup(tmp_path, "swap-a"))
    second = await _replicate(service, _write_backup(tmp_path, "swap-b"))

    # Give the first backup's sidecar the second's archive bytes, and make the
    # checksum agree so only the inner manifest can reveal the swap.
    other = storage.objects[second.archive_key]
    storage.objects[first.archive_key] = other
    sidecar = OffsiteManifest.from_json(storage.objects[f"{PREFIX}{first.backup_id}.manifest.json"])
    patched = replace(sidecar, archive_sha256=sha256_of(other), archive_bytes=len(other))
    storage.objects[f"{PREFIX}{first.backup_id}.manifest.json"] = patched.to_json().encode()

    with pytest.raises(OffsiteError, match="sidecar claims"):
        await service.fetch(first.backup_id, tmp_path / "out")


async def test_an_unreadable_sidecar_is_not_counted_as_a_backup(tmp_path, storage, service):
    await _replicate(service, _write_backup(tmp_path, "ok-1"))
    storage.objects[f"{PREFIX}garbage.manifest.json"] = b"{ not json"

    listed = await service.list_backups()
    assert len(listed) == 1, "an unparseable sidecar was counted as a backup"


async def test_a_round_trip_returns_exactly_what_was_uploaded(tmp_path, storage, service):
    """Off-site object exists, local backup is gone — the DR case, in miniature."""
    directory = _write_backup(tmp_path, "roundtrip-1", rows=5)
    original = (directory / "tables" / "supplier.jsonl").read_text()
    manifest = await _replicate(service, directory)

    import shutil

    shutil.rmtree(directory)  # the local copy no longer exists
    assert not directory.exists()

    recovered, sidecar = await service.fetch(manifest.backup_id, tmp_path / "recovered")
    assert (recovered / "tables" / "supplier.jsonl").read_text() == original
    assert sidecar.schema_revision == "5d12928a9564"
    assert sidecar.postgres_version == "16.2"
    assert sidecar.total_rows == 5


# --- retention: the dangerous boundaries ------------------------------------


async def test_retention_never_deletes_the_only_backup(tmp_path, service):
    """The one that matters most. There is no `keep` for which deleting the
    only copy is the right answer."""
    await _replicate(service, _write_backup(tmp_path, "solo-1"))

    for keep in (1, 2, 30):
        assert await service.prune(keep=keep, dry_run=False) == []
    assert len(await service.list_backups()) == 1


async def test_retention_refuses_a_keep_below_one(tmp_path, service):
    """ "Keep zero backups" is never an instruction anybody means."""
    await _replicate(service, _write_backup(tmp_path, "zero-1"))
    for keep in (0, -1, -100):
        with pytest.raises(OffsiteError, match="at least 1"):
            await service.prune(keep=keep, dry_run=False)
    assert len(await service.list_backups()) == 1


async def test_retention_with_fewer_backups_than_the_threshold_deletes_nothing(tmp_path, service):
    for n in range(3):
        await _replicate(service, _write_backup(tmp_path, f"few-{n}"))
    assert await service.prune(keep=10, dry_run=False) == []
    assert len(await service.list_backups()) == 3


async def test_retention_keeps_the_newest_and_deletes_the_oldest(tmp_path, service):
    for n in range(5):
        await _replicate(service, _write_backup(tmp_path, f"many-{n}"))
    before = await service.list_backups()
    newest = before[0].backup_id

    deleted = await service.prune(keep=2, dry_run=False)
    after = await service.list_backups()

    assert len(after) == 2
    assert newest not in deleted, "the newest backup was selected for deletion"
    assert after[0].backup_id == newest, "the newest backup did not survive"
    assert len(deleted) == 3


async def test_retention_dry_run_is_the_default_and_deletes_nothing(tmp_path, service):
    """A retention routine that deletes by default is one that will eventually
    be run by somebody who was just looking."""
    for n in range(4):
        await _replicate(service, _write_backup(tmp_path, f"dry-{n}"))

    selected = await service.prune(keep=1)  # no dry_run argument at all
    assert len(selected) == 3, "dry run did not report what it would delete"
    assert len(await service.list_backups()) == 4, "dry run deleted something"


async def test_retention_only_ever_touches_its_own_prefix(tmp_path, storage, service):
    """The DR-001 finding, generalised: a retention routine that can be pointed
    at the wrong place will eventually be pointed at the wrong place. This one
    lists a fixed prefix and cannot be aimed anywhere."""
    storage.objects["not-a-backup/important.txt"] = b"keep me"
    storage.objects["documents/supplier-id-card.png"] = b"keep me too"
    for n in range(3):
        await _replicate(service, _write_backup(tmp_path, f"prefix-{n}"))

    await service.prune(keep=1, dry_run=False)

    assert storage.objects["not-a-backup/important.txt"] == b"keep me"
    assert storage.objects["documents/supplier-id-card.png"] == b"keep me too"
    assert len(await service.list_backups()) == 1


async def test_retention_removes_the_sidecar_before_the_archive(tmp_path, storage, service):
    """Order matters for an interrupted prune: without a sidecar the backup is
    invisible, which is safe. An archive deleted first would leave a LISTED
    backup that cannot be fetched — a backup that lies."""
    for n in range(3):
        await _replicate(service, _write_backup(tmp_path, f"order-{n}"))

    deleted_order: list[str] = []
    original_delete = storage.delete_object

    async def recording_delete(key: str) -> None:
        deleted_order.append(key)
        await original_delete(key)

    storage.delete_object = recording_delete
    await service.prune(keep=1, dry_run=False)

    assert deleted_order, "nothing was deleted"
    for sidecar, archive in zip(deleted_order[::2], deleted_order[1::2], strict=True):
        assert sidecar.endswith(".manifest.json"), f"{sidecar} was deleted before its sidecar"
        assert archive.endswith(".tar")
