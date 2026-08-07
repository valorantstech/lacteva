---
id: PITR-001-REPORT
title: Point-in-Time Recovery Report (PITR-001)
type: report
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-08
last-updated: 2026-08-08
related: [PITR, DISASTER_RECOVERY, BACKUP, RESTORE, DR-001-REPORT, VER-001-REPORT]
baseline: ARCH-BASELINE-V1
---

# Point-in-Time Recovery Report (PITR-001)

**Result: point-in-time recovery is proven.** Ten steps against a real PostgreSQL 16.2 cluster, ending with the primary **destroyed** and four separate recoveries driven from the WAL archive alone — to an exact timestamp, a transaction boundary, a named restore point, and latest.

This closes divergence #26, open since BAK-001 across four work orders, and it was the last major guarantee on this platform that had never been executed.

## 1. The finding that made the rest necessary

**Production had `wal_level = replica` and no `archive_mode`.**

That combination looks like it is configured for point-in-time recovery and is not. `wal_level=replica` makes WAL *sufficient* to replay; `archive_mode=on` is what makes it *leave the server*. Without the second, WAL is recycled in place and the only recoverable point is the base backup itself.

So the platform's documented **5-minute RPO was fiction**. The real RPO was the age of the last logical backup — up to 24 hours. `INFRASTRUCTURE.md` said so in one line, which is better than lying, but a documented gap is still a gap: three separate documents described PITR procedures that could not have worked.

## 2. Problems discovered

### P-1 — No WAL archiving in production (the headline)

Described above. Fixed in `docker-compose.production.yml`: `archive_mode=on`, an `archive_command` that refuses to overwrite, `archive_timeout=60`, and a **separate `wal_archive` volume** — an archive that dies with the data directory recovers nothing, which is the exact failure PITR exists to survive.

### P-2 — The restore test migrated the database it was recovering

`pg-restore-test.sh` ran `alembic upgrade head` immediately after starting the recovered instance.

A physical restore is byte-identical to the source at the recovery target. Running migrations against it **mutates the recovered data**, applying a migration that point in time never had — during an incident, which is the worst possible moment to alter the evidence. It now *asserts* the revision instead; migrating a recovered database is a separate, deliberate decision.

### P-3 — Both scripts read the database before recovery had finished

`pg_ctl -w start` returns when the server **accepts connections**, and during recovery that happens at *"ready to accept read-only connections"* — before the target is reached and before promotion.

Everything the old script did next was therefore talking to a read-only, still-replaying database. This was found by executing: the proof's first run failed on exactly this, and the PostgreSQL log showed recovery completing correctly *after* the check had already read the wrong answer. Both scripts now poll `pg_is_in_recovery()`.

### P-4 — The retention prune could delete every base backup

```bash
find "${BACKUP_ROOT}/base" -maxdepth 1 -type d -mtime +35 -exec rm -rf {} +
```

`find DIR -maxdepth 1 -type d` matches **DIR itself**. Demonstrated:

```
$ find /tmp/prune-demo/base -maxdepth 1 -type d -mtime +35
/tmp/prune-demo/base                          <-- the whole backup root
/tmp/prune-demo/base/20260101T000000Z
```

With `rm -rf`, that removes every base backup including the newest. It is **latent rather than active**: creating a backup updates the parent's mtime, so it only fires once `base/` is itself older than the window — which happens precisely when backups have stopped, the moment the old ones matter most. Fixed with `-mindepth 1`.

### P-5 — WAL retention was not tied to base-backup retention

There was no archive pruning at all. Added — and deliberately **not** date-based: a base backup without its WAL is a snapshot, not point-in-time recovery, so the archive is pruned against the *oldest retained base backup* using `pg_archivecleanup`. If the `.backup` label cannot be found the script **refuses to prune and says why**, because deleting a segment a base backup needs turns that backup into an unrestorable directory, silently.

## 3. The timeline trap

Not a defect found, but a trap avoided, and the most likely way a future recovery goes wrong.

A recovered cluster **promotes onto a new timeline**. If it also archives, its timeline lands in the same archive — and because `recovery_target_timeline` defaults to **`latest`**, the *next* recovery from the same base backup can follow the recovered timeline instead of the original, **overshooting its target with no error**.

Both scripts now set `archive_mode = off` and `recovery_target_timeline = 'current'` on recovered clusters. Verified after four recoveries: the archive still contains only timeline 1 and no `.history` file.

## 4. Fixes applied

| # | Fix | File |
| --- | --- | --- |
| 1 | `archive_mode=on`, non-overwriting `archive_command`, `archive_timeout`, separate `wal_archive` volume | `docker-compose.production.yml` |
| 2 | `alembic upgrade head` replaced by a revision assertion | `infra/backup/pg-restore-test.sh` |
| 3 | Poll `pg_is_in_recovery()` until promotion completes | `pg-restore-test.sh`, `pitr-proof.sh` |
| 4 | Timeline pinning: `archive_mode=off`, `recovery_target_timeline='current'` | both scripts |
| 5 | `-mindepth 1` on the retention prune | `infra/backup/pg-backup.sh` |
| 6 | WAL pruning via `pg_archivecleanup`, tied to the oldest retained base | `pg-backup.sh` |
| 7 | `pg_verifybackup` before depending on a base backup | `pg-backup.sh`, `pg-restore-test.sh` |
| 8 | Refuse more than one recovery target | `pg-restore-test.sh` |
| 9 | Support for named and xid targets, not only timestamps | `pg-restore-test.sh` |

## 5. Tests added

Six, in `tests/test_production_readiness.py`. **All six were verified to fail against the pre-PITR-001 state**, by removing the settings and re-running:

| Test | Proves |
| --- | --- |
| `test_production_postgres_archives_wal` | P-1 — `archive_mode=on` and an `archive_command` exist |
| `test_the_archive_command_refuses_to_overwrite` | The `test ! -f` guard is present |
| `test_the_archive_timeout_bounds_the_rpo` | The RPO is bounded during quiet periods |
| `test_the_wal_archive_is_not_on_the_data_volume` | The archive can survive the data directory |
| `test_the_restore_test_does_not_migrate_the_recovered_database` | P-2 and P-3 |
| `test_the_backup_pruner_cannot_delete_every_backup` | P-4 |

One of them failed on its own explanation first: the test searched the whole script for `alembic upgrade head`, which appears in the comment explaining why it must not be there. It now checks executable lines only — a small illustration of the same failure mode this platform keeps finding, where a check passes or fails for a reason unrelated to what it claims to measure.

## 6. Execution evidence

```
==> 1/10  archive_mode=on, archive_command set, archive_timeout=60s
==> 2/10  settlement STL-A6C138 / payment PAY-8320E6 / receipt RCP-1ED960, before the base
==> 3/10  base backup taken and verified against its own manifest
==> 4-5/10 batches A=5 B=7 C=3; named point 'before_batch_b'; xid 1076
==> 6/10  5 segments archived, 0 archiver failures, 0 pending
==> 7/10  primary DESTROYED — only the base backup and the archive remain
==> 8/10  recovery to a TIMESTAMP        A=5 B=0 C=0   timeline 2
==> 9a/10 recovery to a TRANSACTION      A=5 B=0 C=0   timeline 2
==> 9b/10 recovery to a NAMED POINT      A=5 B=0 C=0   timeline 2
==> 9c/10 recovery to LATEST             A=5 B=7 C=3   timeline 2
==> 10/10 7 business integrity checks passed on the recovered data
```

**The assertion that makes this point-in-time recovery rather than a restore is the zeroes.** Work committed after the target is *absent*. A restore test that only checks rows are present proves the backup works and says nothing about whether the target was honoured.

In every recovery: settlement `5647.50`, receipt `RCP-1ED960`, 52 RLS policies with 0 unforced, schema revision `ced805436869` unchanged.

## 7. Review findings that were already correct

| Checked | Result |
| --- | --- |
| `recovery.signal` handling | Correct — the modern mechanism, not the removed `recovery.conf` |
| Base backup format | Correct — `--wal-method=stream` makes the base self-consistent without waiting for the archive |
| Backup manifests | Present, and now verified with `pg_verifybackup` before use |
| PostgreSQL roles | Correct — recovery runs as the superuser owner; the *application* connects as the non-superuser `lacteva_app` (VER-001), and RLS is enforced on recovered data |
| RLS after recovery | **Enforced** — 52 policies, 0 unforced, in all four recoveries |
| Docker deployment | Correct once archiving was added; no permission or ownership problems surfaced (`chmod 700` on the restored data directory is required and is applied) |
| Archive gaps | None — 0 pending, 0 archiver failures, asserted rather than assumed |

## 8. Remaining limitations

1. **Streaming replication and replica promotion are still unexecuted.** Same WAL, different mechanism. This is now the largest untested guarantee.
2. **The WAL archive is a local volume.** PITR works; surviving *total host loss* needs the archive replicated off-host. Archiving to object storage changes the failure modes — partial uploads, credentials, eventual consistency — and is untested.
3. **No archive monitoring in the alerting stack.** The proof checks `pg_stat_archiver.failed_count`; production does not yet alert on it, so a production archive that started failing would be noticed by a human or during a recovery.
4. **Recovery time at scale is unknown.** The proof recovers a small dairy in seconds. An RTO is made of that number, and this does not measure it.
5. **One PostgreSQL version (16.2), one platform.** No cross-version recovery testing.
6. **Timestamp targets stop at commit boundaries**, so two transactions committed within the same clock tick cannot be separated by a time target. A limitation of PostgreSQL, documented rather than fixed; use an xid when it matters.

## 9. Production readiness

| Area | State |
| --- | --- |
| Runs on PostgreSQL | Proven (VER-001) |
| Tenant isolation enforced by the database | Proven (VER-001) |
| Logical backup and restore | Proven (DR-001) |
| **WAL archiving** | **Proven — did not exist** |
| **Recovery to a timestamp / transaction / named point / latest** | **Proven — never executed** |
| **Work after the recovery target excluded** | **Proven** |
| RLS and money intact after physical recovery | Proven |
| Replica promotion / streaming replication | **Not executed** |
| Off-host archive, recovery at scale | **Not executed** |

**Assessment: ready for production deployment on PostgreSQL 16 with both recovery paths proven** — logical restore for portability and verification, physical PITR for the incident an operator actually has. The RPO is now bounded by `archive_timeout` (60s) rather than by the age of a backup.

The pattern that has held for four work orders held again: **executing an already-written, already-reviewed guarantee found five defects, one of which meant the capability did not exist at all.** Nothing here was findable by reading the scripts, and the scripts were good.

## 10. Recommended next work order

**REP-001 — Execute streaming replication and replica promotion.** The last unexecuted piece of the physical path, and the one that turns a 4-hour RTO into minutes. Same WAL, same archive, different mechanism: a standby following the primary, then promoted, then verified with the fact-for-fact comparison DR-001 built.

After that, in order: **ARCH-OFFSITE-001** (replicate the WAL archive to object storage — PITR is proven but a local archive is not a disaster-recovery archive), and **SCALE-001** (recovery time and query behaviour at realistic cardinality, which is where the remaining silent defects at this layer would live).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-08 | Architecture Board | PITR-001: point-in-time recovery executed and proven against a real cluster; five defects found and fixed; divergence #26 closed after four work orders. |
