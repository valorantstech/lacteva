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
