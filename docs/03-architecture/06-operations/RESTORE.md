---
id: RESTORE
title: Restore Procedures
type: reference
status: Approved
version: "1.1"
owner: Architecture Board
created: 2026-08-06
last-updated: 2026-08-08
related: [BACKUP, DISASTER_RECOVERY, RUNBOOK_BACKUP, RECOVERY_CHECKLIST]
baseline: ARCH-BASELINE-V1
---

# Restore Procedures

How to bring the platform back, and how to know you actually did. Established by BAK-001.

## 1. What "restored" means here

A restore is complete when **seven** things are true. Loading rows is only the first — and two of them must hold *before* anything is written, because the worst moment to learn a backup is unusable is halfway through a recovery.

| # | Gate | How it is checked |
| --- | --- | --- |
| 0 | The backup is intact | Checksums are verified **before** the database is touched (DR-001) |
| 0b | The schema matches | The manifest's Alembic revision equals the target's (DR-001) |
| 1 | The database restores | `alembic upgrade head` succeeds on it |
| 2 | The application starts | Lifespan completes; consumers and probes register |
| 3 | Health is green | `/health/ready` returns 200; `/v1/_ops/health` shows no `critical` |
| 4 | Projections rebuild | Rebuilt from the event log and verified (BR-0015) |
| 5 | **Business rules hold** | Settlements balance, payments reconcile, receipts match |

Gate 5 is the one most recovery procedures omit, and the only one that catches a restore that loaded everything and still left the business wrong.

## 2. This has been demonstrated, not just written

`tests/test_backup_restore.py::test_a_destroyed_platform_is_fully_recovered` builds a real dairy — collection → pricing → settlement → payment → receipt → notifications — takes a backup, **deletes every row in every table**, restores, and then asserts:

- every row count matches, table by table;
- the payment amount is identical **to the cent**, with its reference and status;
- the receipt is still listable and still *renders*, carrying its original number;
- the platform still **refuses** a second payment on a fully-paid settlement — proving the rules came back, not merely the rows;
- new business still succeeds afterwards;
- and every integrity check passes, including a deep projection rebuild.

A sibling test proves the subtlest failure is avoided: after a restore, running the consumers does **not** re-mint receipts or re-send notifications.

That suite is real evidence, and it was not sufficient. It runs on SQLite.

## 2b. What executing it on PostgreSQL then found (DR-001)

The suite above proved the *shape* of recovery. Running the same pipeline against two real PostgreSQL instances found four defects it structurally could not see:

| Defect | Why the SQLite suite missed it |
| --- | --- |
| **Every backup aborted on a `time` column.** `center_operating_window.opens/closes` are TIME, and the engine had no encoder for it — so any deployment with configured opening hours could not be backed up **at all** | the suite never seeded a center with operating hours, so the branch was never reached |
| **A corrupt backup restored silently.** `verify_files` existed and nothing called it before a restore. Editing one number in `settlement.jsonl` produced a restore reporting 350 rows loaded and a settlement worth 1.00 instead of 5647.50 | the suite never corrupts a backup |
| **A restore across a schema change succeeded and reported healthy.** Restoring into a database one migration older loaded every row and returned `integrity_healthy: true`; the recovered system silently lacked the `amount > 0` constraint | SQLite has no `alembic_version` — the schema revision did not exist to compare |
| **`transaction_metrics` was excluded from backup as "rebuildable" while nothing rebuilt it**, so every restore lost it permanently | the row counts compared only what the backup contained, so a table absent from both sides matched |

The last one is the most instructive. **"Derived" and "rebuildable" are different claims**: derived says the information exists elsewhere, rebuildable says there is *code* that reconstructs it. Only the second makes it safe to discard.

All four are fixed, each has a test that fails without the fix, and `./infra/ci/dr-proof.sh` executes the whole pipeline.

## 3. Restore is CLI-only, deliberately

There is no restore endpoint and there will not be one. Overwriting the database is the most destructive operation the platform can perform; an endpoint puts it one misrouted request away from catastrophe, and no permission check makes that trade worthwhile. A CLI requires someone to be on the host, holding the credentials, having typed the word.

A test asserts no route contains "restore".

## 4. Logical restore (verifiable)

```bash
# 1. Check the backup BEFORE depending on it. The worst moment to discover
#    corruption is halfway through a recovery.
uv run python -m platform_core.core.backup.cli verify /var/backups/logical/2026-08-06

# 2. Bring the schema to head on the (empty) target.
LACTEVA_DATABASE_URL=... uv run alembic upgrade head

# 3. Restore. Refuses a non-empty database unless --force.
uv run python -m platform_core.core.backup.cli restore /var/backups/logical/2026-08-06

# 4. Rebuild the read models the backup deliberately did not carry.
curl -XPOST -H "Authorization: Bearer $OPS" localhost:8000/v1/_projections/rebuild-all
```

Step 3 runs a **deep integrity check automatically** and exits non-zero if the business is wrong — a restore that loaded every row but broke an invariant reports failure, because it is one.

## 5. Physical restore with PITR (production first line)

Use when you need a specific instant — the usual case for operator error, where "restore to 09:14, just before the delete" is the requirement.

```bash
BASE_BACKUP=/var/backups/lacteva/base/20260806T020000Z \
RESTORE_PGDATA=/var/lib/postgresql/restore-test \
TARGET_TIME='2026-08-06 09:14:00+00' \
  infra/backup/pg-restore-test.sh
```

The script runs all five gates and fails loudly on any of them.

**Honest limit:** the physical path is scripted and CI-wired but has **not been executed** — no PostgreSQL was available during BAK-001. The logical path is demonstrated. See BACKUP.md §8.

## 6. Recovery sequence (order matters)

```
1. Database          restore, then `alembic upgrade head`
2. Outbox            arrives with the database — it IS a table
3. Consumer ledgers  arrive with the database (cursor + execution)
        ↑ these two together are why consumers do not re-fire
4. Application       start it; consumers resume from their cursors
5. Projections       rebuild from the event log, then verify
6. Integrity         `cli integrity --deep`
7. Smoke test        a real read through the API
```

**Do not skip step 3 by restoring only business tables.** Consumers would replay the entire log: every farmer notified again, every receipt minted again. This is the failure mode the classification exists to prevent.

## 7. Partial restores

| Situation | Approach |
| --- | --- |
| One tenant's data lost | Restore to a **separate** instance, extract that tenant, re-insert. Never restore a whole cluster to fix one tenant |
| One table corrupted | Same: side restore, then targeted repair, with an integrity check afterwards |
| Projections wrong only | **No restore needed.** Rebuild from the log (BR-0015) |
| Read models stale | Same — rebuild is always safe |

The last two are worth internalising: a large class of "we need a restore" incidents are actually rebuilds, which are faster, safer, and need no backup at all.

## 8. After any restore

- Run `cli integrity --deep` even if the tooling already did — it is cheap and it is the gate that matters.
- Check `/v1/_ops/health` for `critical` components.
- Confirm the consumer cursors are within the log (an integrity check does this).
- Take a **fresh backup**. The restored state is now the truth, and the pre-disaster backup is history.
- Record what happened in the incident log while it is fresh.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-08 | Architecture Board | DR-001: executed against two real PostgreSQL instances. Checksums and schema revision are now verified before a restore writes anything; four defects recorded in §2b. |
| 1.0 | 2026-08-06 | Architecture Board | Established by BAK-001. |
