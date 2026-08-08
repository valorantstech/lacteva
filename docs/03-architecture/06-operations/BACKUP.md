---
id: BACKUP
title: Backup Strategy
type: reference
status: Approved
version: "1.2"
owner: Architecture Board
created: 2026-08-06
last-updated: 2026-08-08
related: [RESTORE, DISASTER_RECOVERY, RUNBOOK_BACKUP, RECOVERY_CHECKLIST, SECURITY]
baseline: ARCH-BASELINE-V1
---

# Backup Strategy

What is protected, how, and why. Established by BAK-001 (Phase B).

**A successful backup is not evidence. A successful restore is.** Every policy here is written so that the restore can be *demonstrated* — see [RESTORE.md](RESTORE.md), where it is.

## 1. Classification first

What you choose *not* to back up matters as much as what you do. Backing up a rebuildable read model costs restore time and buys nothing; backing up a rate-limit counter restores yesterday's abuse budget.

| Class | Meaning | On loss |
| --- | --- | --- |
| **critical** | Business truth; cannot be reconstructed | Money and trust are lost |
| **important** | Operational state; painful but survivable | Degraded service, no data loss |
| **rebuildable** | Derived from something else the platform holds | Rebuild it |
| **ephemeral** | Meaningful only right now | Let it go |

The classification is **derived from the mapped metadata**, not hand-maintained, and an unclassified table defaults to `critical` — the safe answer to "I don't know what this is" is "keep it". Inspect it live:

```bash
uv run python -m platform_core.core.backup.cli classification
```

### The two entries worth understanding

**Projections are `rebuildable`.** The platform guarantees every projection can be reconstructed from the event log (BR-0015), so a restore rebuilds them rather than carrying them. That guarantee is what makes the exclusion safe.

**Consumer ledgers are `important`, not rebuildable.** `consumer_cursor`, `consumer_execution`, and `sync_operation` are not business data — but restoring *without* them replays the whole event log into consumers, **sending every notification again and minting every receipt again**. They are the difference between a restore and a duplicate-effects incident. A test asserts this directly (`test_consumers_do_not_re_fire_after_a_restore`).

## 2. PostgreSQL

Two layers, answering different questions.

| | Physical (`pg_basebackup` + WAL) | Logical (platform CLI) |
| --- | --- | --- |
| Recovery point | **Any instant (PITR)** | The moment it ran |
| Speed at scale | Fast | Slower |
| Portable across versions | No | **Yes** |
| **Verifiable by the application** | No | **Yes** |

The last row is why both exist. A physical backup can only be checked by restoring a cluster; the logical one is a manifest the platform can read, checksum, and reason about — which is what makes automated restore verification possible.

| | Frequency | Retention | Compression | Encryption | Verification |
| --- | --- | --- | --- | --- | --- |
| Base backup | Daily 02:00 UTC | 35 days | gzip -6 | At rest, by the storage layer | Weekly restore test |
| WAL archive | Continuous | 35 days | gzip | At rest | Implicit in the restore test |
| Logical backup | Daily, post-base | 35 days | none (JSONL, compresses well upstream) | At rest | **Checksummed on every run** |

Scripts: [`infra/backup/pg-backup.sh`](../../../infra/backup/pg-backup.sh), [`infra/backup/pg-restore-test.sh`](../../../infra/backup/pg-restore-test.sh).

**Checksums.** `pg_basebackup` writes `backup_manifest` with per-file checksums; the script keeps a digest of the manifest so tampering with both file and manifest is detectable. The logical backup checksums every table over its serialized bytes, in primary-key order, so the same data always produces the same checksum — a checksum that changes when nothing did is one nobody trusts.

## 3. Object storage

Supplier documents today; printed receipts and PDFs when RCP-001's placeholder renderer is replaced.

| Concern | Policy |
| --- | --- |
| Versioning | **Enabled.** An overwrite must be recoverable, and MinIO/S3 versioning is cheaper than any application-level history |
| Retention | Non-current versions kept 90 days |
| Deletion | Soft-delete (delete marker) only; no lifecycle rule hard-deletes inside the retention window |
| Cross-region | Replicate to a second region; object storage is the one store where geo-redundancy is nearly free |
| Integrity | Server-side checksums; documents are content-addressed by the platform |
| Recovery | Restore an object version in place — no application involvement |

**Receipts are the exception worth stating**: they are *rendered on demand from immutable database records* (RCP-001), not stored. Losing object storage therefore loses no receipt. That is a deliberate architectural property, not luck.

## 4. Redis

**Nothing in Redis is backed up.** Every use is either ephemeral or rebuildable, and restoring stale state would be worse than starting clean:

| Data | Class | Why no backup |
| --- | --- | --- |
| Rate-limit counters | ephemeral | Restoring them restores yesterday's abuse budget. Losing them costs one window of protection |
| Cache entries | ephemeral | Repopulate on read |
| Distributed locks | ephemeral | A restored lock is a **deadlock** — it refers to a holder that no longer exists |
| Consumer state | *not in Redis* | It lives in PostgreSQL (`consumer_cursor`), precisely so it is durable and backed up |

Redis loss is a **degraded**, not critical, event: rate limits fail open by design (SECURITY.md), so collection continues.

## 5. Configuration and secrets

| | Where it lives | Backup |
| --- | --- | --- |
| Tenant/global configuration | PostgreSQL (`config_entry`) | Covered — classified `critical` |
| Secrets (JWT keys, storage credentials) | The secret store; **never** the database | **Backed up by the secret store, never by the platform** |

A platform backup that contained signing keys would turn every backup copy into a credential leak. The logical manifest is asserted free of connection strings and credentials by test. Key material is recovered by re-provisioning from the secret store — and if that is impossible, by emergency key rotation (JWT-ROTATION.md §3), which is *designed* to be survivable.

## 6. Event outbox and audit

Both `critical`, and both unusual:

- **`event_outbox` is the platform's memory of what happened.** Every projection and every consumer effect derives from it. It is the single most valuable table to restore correctly, and the reason projections need no backup.
- **`audit_record` is evidence.** It is required for dispute resolution, and a restore that returns payments without their audit trail has lost the ability to explain them. An integrity check fails exactly that case.

## 7. What runs when

```
02:00 UTC  pg-backup.sh                    base backup + WAL continues
02:30 UTC  cli backup /var/backups/logical verified logical backup
03:00 UTC  cli integrity --deep            business rules + projection rebuild
Sunday     pg-restore-test.sh              full restore into a throwaway instance
```

The daily integrity check matters more than it looks: **silent corruption that nobody checks for is corruption a farmer discovers.**

## 7b. `rebuildable` is a claim about code (DR-001)

Excluding a table from the backup is only safe if something actually reconstructs it. `transaction_metrics` was classified `rebuildable` — "derived counters over collection transactions" — and **nothing rebuilt it**: it is written once, by `MilkCollectionService.complete()`, and is not a registered projection. Every restore lost it permanently and silently.

The rule is now enforced rather than intended. `rebuildable_tables_without_a_rebuilder()` returns any table excluded from backup that no registered projection owns, and a test fails the build if it is ever non-empty. A table may only be excluded if a projection declares it in `models`.

## 8. Known limits

- **PITR is proven** (PITR-001) — see [PITR](PITR.md). Executing it found that production had `wal_level=replica` and **no `archive_mode`**, so no WAL ever left the server and the documented RPO was unachievable. Both lines of defence now execute: the logical path in `dr-proof.sh`, the physical path in `pitr-proof.sh`.
- **The logical backup takes a lock-free snapshot**, so it is consistent per table but not across tables at a single instant. For point-in-time consistency, use PITR.
- **No cross-region automation.** Documented as a procedure, not implemented.
- **`backup_run` is not comparable across a restore.** It records the act of backing up, so reading it changes it. The recovery comparison excludes it explicitly and says so; it is not silently skipped.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.2 | 2026-08-08 | Architecture Board | PITR-001: physical point-in-time recovery proven; WAL archiving enabled and its retention tied to base-backup retention. |
| 1.1 | 2026-08-08 | Architecture Board | DR-001: `time` columns are serializable (their absence aborted every backup on a real schema); the manifest records the schema revision; `rebuildable` now requires an actual rebuilder. |
| 1.0 | 2026-08-06 | Architecture Board | Established by BAK-001. |

## Off-site replication (BKP-003)

### The problem this closes

`infra/backup/run-logical-backup.sh` writes to `/backup/logical`, which on the
single-host deployment is **the same volume as the database**. Losing the volume
— the most likely single failure there is — destroyed the data and every means
of recovering it at the same instant. The DR and PITR proofs were real and they
restored from a copy that might not survive the incident requiring it.

### Architecture

The backup engine is unchanged. DR-001 proved it produces a verifiable
directory that restores, and replacing that would discard executed evidence to
gain nothing. Replication is a layer ON TOP:

```
BackupEngine  ->  local directory  ->  pack (deterministic tar)  ->  S3 object
                       verify              sha256                  read back + verify
                                                                        |
                                                                   sidecar manifest
                                                                   (written LAST)
```

* **One object, not many.** A backup split across objects has no moment at
  which it becomes valid — a restore could find nine tables of ten and no way
  to know. The tar means it exists whole or not at all.
* **Deterministic tar** (sorted members, no mtimes, normalised mode/ownership),
  so the checksum is a function of the DATA. A checksum that changes when the
  data does not cannot detect corruption.
* **The sidecar is the completion marker.** Uploaded after the archive has been
  read back and re-checksummed. A backup with no sidecar is invisible to
  `list_backups` and therefore to retention — which is what stops an
  interrupted upload from being counted as a copy worth keeping.
* **Manifest stored twice** — inside the archive and beside it. Compared on
  download, so an archive swapped under a sidecar is caught.

### Manifest contents

`backup_id`, `created_at`, `archive_key`, `archive_sha256`, `archive_bytes`,
`database_identity` (name + PostgreSQL system identifier, never a URL),
`postgres_version`, `schema_revision`, `platform_version`, `total_rows`,
`table_count`, and the engine's own manifest verbatim.

### Retention

`offsite prune` applies three independent rules, each of which alone prevents
the disaster:

1. `keep < 1` is refused outright.
2. The newest backup is excluded before anything is considered.
3. Fewer backups than `keep` deletes nothing at all.

It lists **only its own `backups/` prefix**, so it cannot be pointed at another
directory — the generalised form of the DR-001 finding. `dry_run` is the
DEFAULT; deleting requires `--delete`. The sidecar is removed before the
archive, so an interrupted prune leaves an invisible orphan rather than a
listed backup whose archive has gone.

### Commands

```bash
python -m platform_core.core.backup.cli backup      /backup/logical/<stamp>
python -m platform_core.core.backup.cli verify      /backup/logical/<stamp>
python -m platform_core.core.backup.cli replicate   /backup/logical/<stamp>
python -m platform_core.core.backup.cli offsite-list
python -m platform_core.core.backup.cli offsite-fetch <backup-id> /restore/here
python -m platform_core.core.backup.cli offsite-prune --keep 30 --delete
```

### Configuration

| Variable | Purpose |
| --- | --- |
| `LACTEVA_BACKUP_OFFSITE_ENDPOINT` | S3-compatible host. **Deliberately separate from `LACTEVA_MINIO_*`** — the application's object storage lives on the host whose loss the backup exists to survive. |
| `LACTEVA_BACKUP_OFFSITE_ACCESS_KEY` / `_SECRET_KEY` | Credentials, from the environment or a Docker secret. Never in source. |
| `LACTEVA_BACKUP_OFFSITE_BUCKET` | Default `lacteva-backups`. |
| `LACTEVA_BACKUP_OFFSITE_SECURE` | TLS in transit. Default true; **prod refuses false**. |
| `LACTEVA_BACKUP_OFFSITE_RETAIN` | Copies to keep. Never below 1. |

`prod` refuses to start with no off-site endpoint configured, for the same
reason it refuses a development database credential.

### Encryption

* **In transit** — TLS to the object store, enforced in prod.
* **At rest** — delegated to the bucket (SSE-S3 / SSE-KMS on AWS, server-side
  encryption on MinIO). **The platform does not encrypt the archive itself**,
  which is a deliberate limitation and is recorded as such: client-side
  encryption would put a key in the recovery path, and a backup you cannot
  decrypt during an incident is not a backup. Bucket-level encryption plus
  restricted credentials is the standard posture; revisit if a market requires
  the platform to hold the key.

### What is proven, and what is not

**PROVEN BY EXECUTION** (`./infra/ci/offsite-proof.sh`, 32 checks):
real PostgreSQL 16.2 seeded through the platform's own API to a known state
(STL-2026-000001 / PAY-2026-000001 / RCP-2026-000001, 5,647.50 KES); backup
taken and verified; replicated to a real MinIO running as a separate process
with its own credentials and its own directory; duplicate id refused; **the
local backup directory deleted**; a fresh database migrated from empty;
downloaded, checksum-verified and restored **from the object store alone**; row
counts, monetary totals, settlement/payment relationships, RLS (53 policies, 0
unforced), foreign keys, schema revision and the platform integrity check all
verified on the recovered database.

**PROVEN BY AUTOMATED TEST** (`tests/test_offsite_backup.py`, 22 tests):
upload failure, interrupted upload, corrupted upload detected by read-back,
corrupted archive at rest, truncated archive, swapped archive, unreadable
sidecar, missing object, duplicate id, local-verify refusal, tar path escape,
and every retention boundary including "only one backup" and "keep=0".

**NOT PROVEN — same machine.** The object store was a separate process with a
separate directory, so this proves independence from the database VOLUME, the
database PROCESS and the local backup PATH. It does **not** prove independence
from the host, the physical disk, the building or the region. A genuine
off-site posture needs a bucket in a different failure domain from the database
host; the code path is identical and unexercised against a remote endpoint.

**NOT PROVEN — scale.** One small dairy. No multi-gigabyte archive, no slow
link, no resumable upload.
