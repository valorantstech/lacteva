---
id: PITR
title: Point-in-Time Recovery
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-08
last-updated: 2026-08-08
related: [DISASTER_RECOVERY, BACKUP, RESTORE, RECOVERY_CHECKLIST, RUNBOOK_BACKUP, POSTGRES-PROOF]
baseline: ARCH-BASELINE-V1
---

# Point-in-Time Recovery

How the platform recovers to *a moment* rather than to *a backup*. Established by PITR-001, and — unlike its four predecessors — **executed**.

## 1. Why this is the first line

The logical backup ([BACKUP](BACKUP.md)) recovers to the instant the backup ran. The most common real disaster is not a lost disk; it is **a bad deploy or a wrong `UPDATE` at 14:32 on a Tuesday**, and recovering to last night loses every collection since.

PITR recovers to 14:31. That is the difference between losing a day of milk records and losing a minute.

## 2. What it requires

Three settings, and the second is the one that was missing:

| Setting | Why |
| --- | --- |
| `wal_level = replica` | WAL must contain enough to replay. **Necessary and not sufficient** |
| `archive_mode = on` + `archive_command` | WAL must *leave the server*. Without this there is no recovery beyond the base backup |
| `archive_timeout` | A segment is archived when it **fills**, not when it is written. This is what actually bounds the RPO on a quiet night |

Until PITR-001, production had exactly the first one. The documented 5-minute RPO was fiction: the real RPO was the age of the last logical backup.

### The archive command refuses to overwrite

```
archive_command = 'test ! -f /wal-archive/%f && cp %p /wal-archive/%f'
```

The `test ! -f` is not defensive habit. Silently replacing an already-archived segment **destroys the recovery window from that segment forward**, and nothing reports it — the archive keeps looking healthy and the gap surfaces during a recovery. An archive that fails loudly is recoverable; one that overwrites quietly is not.

### The archive lives on separate storage

`wal_archive` is its own volume, deliberately not `pgdata`. An archive that dies with the data directory recovers nothing, which is the exact failure PITR exists to survive. In a real deployment it is replicated off-host.

## 3. The four recovery targets

All four are executed by `./infra/ci/pitr-proof.sh`.

| Target | Config | Use when |
| --- | --- | --- |
| **Timestamp** | `recovery_target_time` | You know roughly when it went wrong |
| **Named point** | `recovery_target_name` | You created a marker before a risky operation |
| **Transaction** | `recovery_target_xid` | You have identified the exact offending transaction |
| **Latest** | *(no target)* | Hardware loss — recover everything |

**Create a named restore point before anything risky.** It costs nothing and turns a guessed timestamp into a name:

```sql
SELECT pg_create_restore_point('before_migration_ced805436869');
```

A timestamp target also has a real limitation worth knowing before an incident: it stops at a **commit boundary**, so two transactions committed inside the same clock tick cannot be separated by a time target. Use an xid when that precision matters.

## 4. Running a recovery

```bash
BASE_BACKUP=/var/backups/lacteva/base/20260808T031500Z \
RESTORE_PGDATA=/var/lib/postgresql/restore \
WAL_ARCHIVE=/var/backups/lacteva/wal \
TARGET_TIME='2026-08-08 14:31:00+00' \
  ./infra/backup/pg-restore-test.sh
```

Set **at most one** target. PostgreSQL applies one; specifying several is a silent coin flip, so the script now refuses rather than choosing.

**Always recover into a separate instance**, never over the live one. The recovered database is a place to look at the data and decide, not a fait accompli.

## 5. The timeline trap

The subtlest thing here, and worth reading before an incident rather than during one.

A recovered cluster **promotes onto a new timeline** (1 → 2). If that cluster also archives, its timeline lands in the same archive. Because `recovery_target_timeline` defaults to **`latest`**, the *next* recovery from the same base backup can follow the recovered timeline instead of the original — **overshooting its target with no error at all.**

Two settings close it, and both are set by the scripts here:

```
archive_mode = off                      # a recovery must not pollute the archive
recovery_target_timeline = 'current'    # explicit, not the 'latest' default
```

Verified: after four recoveries in the proof, the archive still contains only timeline 1 and no `.history` file.

## 6. What the proof asserts

```bash
./infra/ci/pitr-proof.sh
```

Ten steps against a real cluster, ending with the primary **destroyed** so recovery depends on the archive alone. The assertion that makes it point-in-time rather than merely a restore:

> **Work committed after the target must be ABSENT.**

A restore test that only checks rows are present proves the backup works. It says nothing about whether the recovery target was honoured. The proof commits three labelled batches after the base backup and asserts, for each target:

| Recovery | Batch A | Batch B | Batch C |
| --- | --- | --- | --- |
| Timestamp after A | 5 | **0** | **0** |
| Xid after A | 5 | **0** | **0** |
| Named point after A | 5 | **0** | **0** |
| Latest | 5 | 7 | 3 |

And in every one of them: the settlement, payment and receipt committed *before* the base backup are identical, 52 RLS policies are present and forced, the schema revision is unchanged, and the platform's own deep integrity checks pass.

## 7. A recovery is restored, not upgraded

`pg-restore-test.sh` used to run `alembic upgrade head` on the recovered instance. That is wrong and potentially destructive: a physical restore is byte-identical to the source at the recovery target, and migrating it **mutates the recovered data** by applying a migration that point in time never had — during an incident.

It now *asserts* the revision instead. Migrating a recovered database is a separate, deliberate decision made after looking at it.

## 8. Waiting for promotion

`pg_ctl -w start` returns when the server **accepts connections**, and during recovery that happens at *"ready to accept read-only connections"* — before the target is reached and before promotion. Anything that proceeds at that point is talking to a read-only, still-replaying database.

Both scripts now poll `pg_is_in_recovery()` until it returns false. If it never does, the target is unreachable or the archive is missing a segment — and that is a finding, not a timeout to raise.

## 9. Retention: WAL and base backups are one unit

A base backup without its WAL is a snapshot, not point-in-time recovery. WAL without a base backup is unusable.

So the archive is pruned **against the oldest retained base backup**, never against a date. `pg-backup.sh` uses `pg_archivecleanup` with the `.backup` label naming the first segment that backup needs; if it cannot find the label it **refuses to prune and says so**, because deleting a segment a base backup needs turns that backup into an unrestorable directory, silently.

## 10. What is still not proven

- **Streaming replication and replica promotion.** Different mechanism, same WAL. Unexecuted.
- **Recovery at production scale.** The proof recovers a small dairy in seconds. Nothing here says how long a real recovery takes, which is the number an RTO is made of.
- **Archive to object storage.** The proof archives to a local directory. S3 changes the failure modes (partial uploads, eventual consistency, credentials) and is untested.
- **Automated archive monitoring.** `pg_stat_archiver.failed_count` is checked by the proof, not yet by the alerting stack — so a production archive that starts failing would be noticed by a human, or during a recovery.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-08 | Architecture Board | Established by PITR-001: WAL archiving enabled in production, four recovery targets executed against a real cluster, timeline trap documented, and the restore test corrected (it migrated the recovered database and did not wait for promotion). |
