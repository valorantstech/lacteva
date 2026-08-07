---
id: DR-001-REPORT
title: Disaster Recovery Pipeline Report (DR-001)
type: report
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-08
last-updated: 2026-08-08
related: [DISASTER_RECOVERY, BACKUP, RESTORE, RECOVERY_CHECKLIST, POSTGRES-PROOF, VER-001-REPORT]
baseline: ARCH-BASELINE-V1
---

# Disaster Recovery Pipeline Report (DR-001)

**Result: the recovery pipeline is green.** Ten steps, executed end to end from a single command, against **two separate PostgreSQL 16.2 instances**. The restored system holds the same facts as its source — 15 named entity classes and all 52 backed-up tables, compared by content checksum.

## 1. Method

DR-001 followed VER-001: execute every documented guarantee rather than review it.

Two *instances*, not two databases on one. Recovery means the original machine is gone; proving it in place quietly assumes the thing that failed still works.

The business activity is real. The seed now drives collections through the platform's own endpoints — a collection session, two transactions taken from identification through weight, quality, decision and completion, one accepted and one rejected — because a table with no rows compares equal trivially, and "the restore matched" means nothing if the source was empty.

## 2. Problems discovered

### D-1 — Every backup aborted on a `time` column (fatal)

`center_operating_window.opens` and `.closes` are `TIME`. `_encode` handled `date`, `datetime`, `Decimal`, `UUID`, `bytes` and JSON — and not `time`, so it raised `BackupError: cannot serialize column value of type time`.

This does not degrade a backup, it **aborts** it. A center cannot be activated without operating hours, so **any deployment with a single working collection center could not be backed up at all.** The test suite never seeded operating hours, so the branch was never reached.

### D-2 — A corrupt backup restored silently (fatal, silent)

`verify_files` existed, and nothing called it before a restore — despite its own docstring: *"This is the check that catches a corrupt or truncated backup BEFORE a restore begins — the worst moment to discover it is halfway through a recovery."*

Executed: changing one number in `settlement.jsonl` produced a restore that reported **350 rows loaded** and left a settlement worth **1.00 instead of 5647.50**. The only signal was the integrity check that runs *afterwards* — by which point the recovery target is overwritten and the operator starts again, mid-outage.

### D-3 — Restoring across a schema change succeeded and reported healthy

The manifest recorded `platform_version` but **not the Alembic revision**, so no check was possible.

Executed: a backup taken at `ced805436869` restored into a database one migration older loaded every row and returned `integrity_healthy: true`. The recovered system silently lacked the ARCH-001 `amount > 0` constraint. The quieter variants are worse — a column added since the backup restores as `NULL` for every row.

### D-4 — A table was excluded from backup on a promise nothing kept

`transaction_metrics` was classified `rebuildable`, which excludes it from every backup. Nothing rebuilds it: it is written once, by `MilkCollectionService.complete()`, and is not a registered projection. **Every restore lost it permanently and silently.** The comparison caught it as `reports: 2 rows in source, 0 restored`.

**"Derived" and "rebuildable" are different claims.** Derived says the information exists elsewhere; rebuildable says there is *code* that reconstructs it. Only the second makes it safe to discard.

### D-5 — The comparison tool could not fail (found in DR-001's own work)

The first version returned a failed query as an error *string*. Two identically-broken queries compared equal, so four checks reported **match** while querying columns that do not exist. It is the same failure this work order exists to eliminate, and it appeared in the tool written to eliminate it. An invalid comparison query is now a hard error.

## 3. Fixes applied

| # | Fix | File |
| --- | --- | --- |
| 1 | `time` encoded and decoded | `core/backup/engine.py` |
| 2 | `restore()` verifies every checksum **before writing**, with an explicit `--skip-verification` escape hatch | `core/backup/engine.py`, `cli.py` |
| 3 | The manifest records `schema_revision`; a mismatch is refused, an unknown revision warns | `core/backup/engine.py`, `cli.py` |
| 4 | `transaction_metrics` reclassified so it is backed up | `core/backup/classification.py` |
| 5 | `rebuildable_tables_without_a_rebuilder()` — a table may only be excluded if a registered projection declares it | `core/backup/classification.py` |
| 6 | An invalid comparison query raises instead of comparing equal | `infra/ci/dr_compare.py` |
| 7 | The seed produces real collection activity through the API | `infra/ci/seed_proof_data.py` |

Backwards compatibility: `schema_revision` defaults to `""`, so backups taken before DR-001 still restore — an unknown revision warns rather than refusing, because making every existing backup unrestorable is a worse failure than the one being guarded against.

## 4. Tests added

`tests/test_disaster_recovery_postgres.py`, ten tests, each failing without its fix:

| Test | Proves |
| --- | --- |
| `test_a_time_column_survives_a_backup` | D-1 |
| `test_every_column_type_in_the_schema_can_be_serialized` | The general form: a future model with an unencodable type fails here, not during a recovery |
| `test_no_table_is_excluded_from_backup_without_a_rebuilder` | D-4, enforced structurally |
| `test_the_manifest_records_the_schema_it_came_from` | D-3 |
| `test_a_corrupt_backup_is_refused_before_the_database_is_touched` | D-2 |
| `test_a_damaged_backup_can_still_be_forced_when_that_is_the_better_option` | The escape hatch works and is explicit |
| `test_restoring_into_a_different_schema_revision_is_refused` | D-3 |
| `test_an_unknown_revision_warns_rather_than_blocking_a_recovery` | Old backups stay restorable |
| `test_the_restored_database_still_enforces_tenant_isolation` | Isolation intact, asserted as a non-superuser |
| `test_indexes_and_constraints_survive_a_restore` | 271 indexes intact |

## 5. Execution evidence

```
==> 0/10  two separate PostgreSQL instances        16.2 and 16.2
==> 1/10  migrations apply to an EMPTY instance    source migrated
==> 2-3/10 realistic dairy + business activity     collections=2, STL-C42AF7, PAY-353680, RCP-4067BE
==> 4/10  logical backup                           52 tables, 350 rows, schema ced805436869
==> 5/10  verified against its own checksums       every table matches
==> 6/10  a SECOND, SEPARATE instance              migrated; lacteva_app NOSUPERUSER/NOBYPASSRLS
==> 7-8/10 restore + deep business integrity       350 rows, 9 integrity checks passed
==> 9/10  source vs restored, fact for fact        15/15 classes; 49 of 52 tables checksum-identical
==> 10/10 corruption, schema drift, isolation      10 recovery tests, 0 skipped
```

Three tables are excluded from the checksum comparison, **each with a printed reason** — never silently:

- `backup_run` records the act of backing up, so reading it changes it;
- `consumer_cursor` and `consumer_execution` are touched by the post-restore rebuild.

Their safety-relevant content is compared exactly instead: **cursor positions** (a rewound cursor re-notifies every farmer) and the **notification consumer's idempotency ledger** (resetting it turns a recovery into a duplicate-SMS incident). Both matched.

## 6. Review findings — the items that were already correct

Stated because a review that only reports defects gives no information about the rest.

| Checked | Result |
| --- | --- |
| Sequences / serial columns | **Not applicable** — every primary key is a UUID; the schema has no sequences at all, so there is no sequence to reset |
| UUID handling | Correct — tagged and decoded, proven by checksum equality across instances |
| Restore order / foreign keys | Correct — parents before children from `sorted_tables`, reverse on delete; 350 rows restore with FKs enforced |
| RLS after restore | **Enforced** — as `lacteva_app` (NOSUPERUSER/NOBYPASSRLS): unbound sees 0 settlements, the owning tenant sees 1, another tenant sees 0 |
| Permissions, ownership, grants | Correct — the application role restores and reads with no DDL rights |
| Indexes and constraints | Intact — 271 indexes, unchanged across restore |
| Superuser leakage | None — the recovery proof runs as a non-superuser, so its isolation assertions are not vacuous |
| Missing tables / metadata | None — 52 of 52 present, manifest complete |
| Checksum failure detection | Correct — `verify` reported the tampered table precisely |

## 7. Remaining limitations

1. **PITR has still never been executed.** WAL archiving, `recovery_target_time` and replica promotion remain scripted, CI-wired, and unrun. This is now the largest untested guarantee on the platform. Given that executing the logical path found four defects, the honest expectation is that executing this one will find some too.
2. **One PostgreSQL version, one direction.** 16.2 only, and the schema-drift test uses a manifest edit rather than a genuine multi-version matrix.
3. **Small data.** 350 rows. Nothing here says anything about a restore of a hundred million collections — batch sizing, memory, or how long an operator waits.
4. **No cross-region or cross-cloud recovery**, and no automated failover. Both remain documented procedures.
5. **Object storage and Redis are not part of this proof.** Supplier documents live in S3/MinIO; their recovery is documented and unexecuted.
6. **The restore's deep verification is not read-only** — it rebuilds projections, which rewrites projection-consumer bookkeeping. Correct, but operators should know that verifying mutates.

## 8. Production readiness

| Area | State |
| --- | --- |
| Runs on PostgreSQL | Proven (VER-001) |
| Tenant isolation enforced by the database | Proven (VER-001) |
| Logical backup | **Proven — was completely broken on any real deployment** |
| Backup corruption detection | **Proven — was absent at restore** |
| Schema-drift protection | **Proven — did not exist** |
| Restore into a separate instance | **Proven** |
| Deep business integrity after restore | Proven |
| Source vs restored, fact for fact | Proven |
| Isolation after restore | Proven |
| Physical DR (PITR, replicas) | **Not executed** |
| Recovery at scale | **Not executed** |
| Object storage / Redis recovery | **Not executed** |

**Assessment: ready for a controlled production deployment on PostgreSQL 16, with logical backup and restore as a *proven* recovery path.** That is a materially stronger claim than a week ago, when the backup would have failed on the first center with opening hours.

The prior estimate stands corrected in the same direction as VER-001: **before DR-001, the platform's recovery story was not partly working, it was not working.** A backup that aborts is not a backup, and every recovery guarantee downstream of it was resting on nothing.

## 9. Recommended next work order

**PITR-001 — Execute the physical recovery path.** WAL archiving on, a base backup, writes after it, then recovery to a target time on a separate instance, ending in the same fact-for-fact comparison used here. It is the last major guarantee on this platform that has never been run, and it is the one operators would reach for first in a real incident — the logical path documented in BACKUP.md is explicitly the *second* line.

Two candidates after that, in order: **SCALE-001** (recovery and query behaviour at realistic cardinality, which is the only remaining place a silent defect can hide at this layer) and **OBJ-001** (supplier documents in object storage, currently outside every recovery proof).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-08 | Architecture Board | DR-001: the recovery pipeline executed against two separate PostgreSQL instances; five defects found and fixed; the pipeline is green. |
