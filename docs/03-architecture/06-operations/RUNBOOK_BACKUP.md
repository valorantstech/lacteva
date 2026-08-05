---
id: RUNBOOK_BACKUP
title: Backup Operations Runbook
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-06
last-updated: 2026-08-06
related: [BACKUP, RESTORE, DISASTER_RECOVERY, RECOVERY_CHECKLIST, RUNBOOK]
baseline: ARCH-BASELINE-V1
---

# Backup Operations Runbook

Day-to-day backup operations, and what to do when they go wrong. Established by BAK-001.

## 0. Start here

```bash
uv run python -m platform_core.core.backup.cli status
```

Exit 0 means protected; exit 1 means not. It also surfaces in the platform health model, so `GET /v1/_ops/health` shows a `backups` component alongside everything else — an operator should not need a second dashboard to learn that backups have been failing for a week.

## 1. Commands

| Command | Purpose | Destructive |
| --- | --- | --- |
| `cli status` | Are we protected right now? | no |
| `cli history [--kind K]` | Every recorded run | no |
| `cli classification` | What is captured, what is rebuilt, why | no |
| `cli backup PATH` | Take and verify a backup | no |
| `cli verify PATH` | Re-checksum a backup on disk | no |
| `cli integrity [--deep]` | Check the live database against business rules | no |
| `cli restore PATH [--force]` | **Load a backup into the database** | **YES** |

API equivalents (read-only, platform staff): `/v1/_ops/backups/status`, `/v1/_ops/backups`, `/v1/_ops/backups/classification`, `POST /v1/_ops/backups/verify-integrity`.

There is no restore endpoint, deliberately (RESTORE.md §3).

## 2. Daily checks

- `cli status` is healthy — a backup within 26 hours **and verified**.
- The nightly `cli integrity --deep` passed.
- The `backups` health component is not warning.

**26 hours, not 24**: a two-hour grace means a slightly late run does not page anyone, while a genuinely missed run is caught the next day rather than three days later.

## 3. When something is wrong

### `status` says "no successful backup has ever been recorded"

The schedule has never run. Check the cron/job definition and the credentials it uses. Until this is fixed **there is no recovery path at all** — treat as urgent.

### `status` says the last backup is N hours old

The schedule stopped. Check the job runner first, then disk space at the destination, then database reachability. Take a manual backup immediately:

```bash
uv run python -m platform_core.core.backup.cli backup /var/backups/logical/manual-$(date -u +%Y%m%dT%H%M%SZ)
```

### `status` says "completed but was never verified"

Someone ran with `verify=False`, or verification failed. **An unverified backup is a guess.** Verify it now:

```bash
uv run python -m platform_core.core.backup.cli verify /path/to/backup
```

### `verify` reports a checksum mismatch

The backup file changed after it was written — corruption, or tampering. **Do not restore from it.** Take a fresh backup, verify that, and investigate why the file changed (storage integrity, or someone with write access who should not have it).

### `integrity` fails

The **live** database violates a business rule. This is not a backup problem; it is a data problem that a backup would faithfully preserve.

Read which check failed:

| Check | Meaning | First move |
| --- | --- | --- |
| `settlement_totals_match_lines` | A settlement's stored total disagrees with its lines | Recalculate the settlement; check for a partial write |
| `payments_never_exceed_the_payable` | A settlement is over-allocated | Find the extra payment; it should have been refused |
| `one_receipt_per_completed_payment` | Evidence duplicated or dangling | Check whether a restore re-ran consumers |
| `no_orphaned_child_rows` | Referential damage | Almost always a partial restore |
| `consumer_cursors_within_the_log` | A cursor is ahead of the restored log | Events will be **skipped** — reset the cursor and replay |
| `audit_trail_restored` | Payments with no audit history | An incomplete restore; the evidence is missing |
| `projections_rebuild_from_the_event_log` | Read models disagree with the log | Rebuild them; the log wins |

### A backup is taking too long / affecting traffic

It should not — the backup runs in read-only transactions and takes no locks on business tables. If traffic is affected, check for a long-running transaction holding a snapshot, and consider moving the backup to a read replica.

## 4. Weekly

Run the restore test. **A backup nobody has restored is not evidence.**

```bash
BASE_BACKUP=/var/backups/lacteva/base/$(ls -1 /var/backups/lacteva/base | tail -1) \
RESTORE_PGDATA=/var/lib/postgresql/restore-test \
  infra/backup/pg-restore-test.sh
```

It runs all five gates (RESTORE.md §1) and fails loudly on any. A restore test that only runs after a disaster is not a test.

## 5. Quarterly

- **Rehearse a full recovery**, timed, by someone who did not write the procedure. That is the only way the documented RTO becomes a real one.
- Review retention against actual storage cost and any regulatory requirement.
- Re-read DISASTER_RECOVERY.md §1 and check the assumptions still hold.

## 6. Before any risky change

```bash
uv run python -m platform_core.core.backup.cli backup /var/backups/logical/pre-change-$(date -u +%Y%m%dT%H%M%SZ)
uv run python -m platform_core.core.backup.cli verify  /var/backups/logical/pre-change-...
```

Verify it. An unverified pre-change backup is exactly the one you will need.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-06 | Architecture Board | Established by BAK-001. |
