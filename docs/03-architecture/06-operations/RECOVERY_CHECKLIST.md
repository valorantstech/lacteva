---
id: RECOVERY_CHECKLIST
title: Recovery Checklist
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-06
last-updated: 2026-08-06
related: [BACKUP, RESTORE, DISASTER_RECOVERY, RUNBOOK_BACKUP]
baseline: ARCH-BASELINE-V1
---

# Recovery Checklist

The page to open during a recovery. Written to be followed under pressure by someone who did not write it.

## Before you touch anything

- [ ] **Stop writes** if data may be corrupt. Every further write may compound the damage.
- [ ] **Take a backup of the current state**, however broken. A restore that goes wrong with nothing to return to is a second disaster.
- [ ] Write down the time you started and what you believe happened. You will not remember later.
- [ ] Decide the **target time** — "now" is rarely right for operator error.
- [ ] Confirm the restore target has comparable capacity.

## Verify the backup before depending on it

- [ ] `cli verify /path/to/backup` — exit 0.
- [ ] The backup's timestamp is **before** the incident.
- [ ] For PITR: the WAL archive covers the window between base backup and target time.

The worst moment to discover a corrupt backup is halfway through a recovery.

## Restore

- [ ] Target database is empty (or you have consciously chosen `--force`).
- [ ] `alembic upgrade head` succeeds.
- [ ] `cli restore /path/to/backup` — exit 0.
- [ ] Restore included the **consumer ledgers** (`consumer_cursor`, `consumer_execution`, `sync_operation`). Without them, consumers replay the entire log and every farmer is notified again.

## The five gates

- [ ] **1. Database restores** — migrations at head.
- [ ] **2. Application starts** — lifespan completes, consumers and probes register.
- [ ] **3. Health is green** — `/health/ready` 200; `/v1/_ops/health` shows no `critical`.
- [ ] **4. Projections rebuild** — `POST /v1/_projections/rebuild-all`, then verify deep.
- [ ] **5. Business rules hold** — `cli integrity --deep`, exit 0.

**All five, or the restore is not done.** Gate 5 is the one that catches a restore that loaded everything and still left the business wrong.

## Business smoke test

- [ ] A known settlement shows its **expected amount**.
- [ ] A known payment shows `completed` with its reference.
- [ ] Its receipt still **renders** and carries its original number.
- [ ] A report returns plausible totals.
- [ ] A **new** collection can be recorded — a read-only museum is a failed restore.

## After

- [ ] Take a **fresh backup**. The restored state is now the truth.
- [ ] Verify it.
- [ ] Confirm the backup schedule is running again.
- [ ] Check for duplicate side effects: any receipt minted twice, any notification re-sent.
- [ ] Record the actual RPO and RTO achieved — not the documented ones.
- [ ] Write the incident up while it is fresh.

## Then ask

- [ ] Did an alert fire? If not, add one — an incident nobody was told about is a gap.
- [ ] Was the runbook right? Fix what was wrong **now**, not "later".
- [ ] Did the achieved RTO match the objective? If not, either the objective or the procedure is wrong. Say which.
- [ ] Could this have been a **rebuild** instead of a restore? Projections and read models never need one.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-06 | Architecture Board | Established by BAK-001. |
