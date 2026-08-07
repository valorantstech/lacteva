---
id: RECOVERY_CHECKLIST
title: Recovery Checklist
type: reference
status: Approved
version: "1.1"
owner: Architecture Board
created: 2026-08-06
last-updated: 2026-08-08
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
- [ ] The manifest's `schema_revision` matches the revision you will migrate the target to.
- [ ] For PITR: the WAL archive covers the window between base backup and target time.

The worst moment to discover a corrupt backup is halfway through a recovery. DR-001 made that structural rather than procedural: `cli restore` now verifies every checksum and compares the schema revision **before it writes anything**, and refuses on either. You should still run `verify` first — knowing early is better than knowing at the start of the restore — but forgetting no longer costs you the target.

## Restore

- [ ] Target database is empty (or you have consciously chosen `--force`).
- [ ] `alembic upgrade head` succeeds.
- [ ] `cli restore /path/to/backup` — exit 0.
- [ ] Restore included the **consumer ledgers** (`consumer_cursor`, `consumer_execution`, `sync_operation`). Without them, consumers replay the entire log and every farmer is notified again.

## The seven gates

- [ ] **0. The backup is intact** — checksums verified before the database is touched. Enforced by `cli restore`; `--skip-verification` overrides it and should be a decision you can justify out loud.
- [ ] **0b. The schema matches** — the manifest's revision equals the target's. Enforced; `--allow-schema-mismatch` overrides. Restoring across a schema change silently nulls columns added since the backup and drops constraints added since.
- [ ] **1. Database restores** — migrations at head.
- [ ] **2. Application starts** — lifespan completes, consumers and probes register.
- [ ] **3. Health is green** — `/health/ready` 200; `/v1/_ops/health` shows no `critical`.
- [ ] **4. Projections rebuild** — `POST /v1/_projections/rebuild-all`, then verify deep.
- [ ] **5. Business rules hold** — `cli integrity --deep`, exit 0.

**All seven, or the restore is not done.** Gate 5 is the one that catches a restore that loaded everything and still left the business wrong. Gates 0 and 0b are the ones that stop you overwriting your recovery target with data you cannot use — both were proven necessary by executing them: a corrupt backup restored a settlement worth 1.00 instead of 5647.50, and a backup restored into a database one migration older reported `integrity_healthy: true` while silently lacking the `amount > 0` constraint.

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
| 1.1 | 2026-08-08 | Architecture Board | DR-001: the restore verifies checksums and the schema revision before writing anything, so two checklist steps are now enforced by the tool rather than by the operator remembering. |
| 1.0 | 2026-08-06 | Architecture Board | Established by BAK-001. |
