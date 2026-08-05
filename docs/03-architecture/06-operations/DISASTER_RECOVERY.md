---
id: DISASTER_RECOVERY
title: Disaster Recovery
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-06
last-updated: 2026-08-06
related: [BACKUP, RESTORE, RECOVERY_CHECKLIST, SECURITY-CHECKLIST]
baseline: ARCH-BASELINE-V1
---

# Disaster Recovery

Named disasters, what each actually costs, and what to do. Established by BAK-001.

## 1. Objectives

**RPO** = how much data you can afford to lose. **RTO** = how long you can afford to be down.

| Environment | RPO | RTO | Basis |
| --- | --- | --- | --- |
| **Production** | **5 min** | **4 h** | Continuous WAL archiving bounds loss to the unarchived segment. RTO is base restore + WAL replay + rebuild + verification, with human decision time |
| Staging | 24 h | 8 h | Daily backup; rebuilt from production shape if lost entirely |
| Development | ∞ | ∞ | Disposable. Recreate with migrations and fixtures |

### The assumptions these rest on

State them, because an RPO whose assumptions are unexamined is a number, not a commitment:

1. WAL archiving is **actually running** and its target is reachable. If archiving silently stops, RPO degrades to the last base backup without any alarm — which is why `backups` is a health component.
2. Backups are stored **off the database host**. A backup on the failed disk is not a backup.
3. Someone is **available to decide**. RTO includes human decision time; a 4-hour RTO with a 3-hour page response is a 7-hour RTO.
4. The restore target has **comparable capacity**. Restoring production onto a small instance meets neither number.
5. **The restore procedure has been rehearsed.** An unrehearsed procedure has an unknown RTO, not the documented one.

## 2. The disasters

### Region failure

**Impact:** total. **RPO** 5 min, **RTO** 4 h — the worst case the objectives are set for.

1. Confirm it is the region, not a single component (cloud status page, independent probe).
2. Provision PostgreSQL in the secondary region.
3. Restore the most recent base backup + WAL from cross-region storage.
4. Re-provision secrets from the secret store **into the new region**.
5. Repoint DNS.
6. Run the five gates (RESTORE.md §1).

**Note:** cross-region replication is *documented, not automated*. Today this is a manual procedure and its RTO reflects that.

### Database corruption

**Impact:** critical. **RPO** depends on when corruption began — which is the hard part.

1. **Stop writes immediately.** Every further write may compound it.
2. Find the onset: `cli integrity --deep` against successive PITR targets narrows the window by bisection.
3. PITR to just before onset.
4. Reconcile anything legitimately written after that point — the audit trail and the event log are what make this possible.

**The trap:** restoring to "now minus one hour" without finding the onset can restore the corruption. The integrity checks exist precisely to answer "was the business correct at this instant?"

### Object storage loss

**Impact:** moderate — smaller than it looks. Supplier documents are lost and must be re-uploaded; **receipts are unaffected**, because they render on demand from immutable database records rather than being stored (RCP-001).

Recover: restore from versioning or the cross-region replica; if genuinely gone, re-collect documents. No application involvement.

### Redis loss

**Impact:** degraded only. Rate limits fail open by design; collection continues. Restart Redis, empty. **Never restore Redis from a backup** — a restored lock is a deadlock referring to a holder that no longer exists.

### Key compromise

**Impact:** critical, and *not* a data-recovery problem — see SECURITY-CHECKLIST.md. Emergency-rotate (JWT-ROTATION.md §3), rotate the secret-store credential that exposed the key, then audit for what the compromised key could have signed. Backups are irrelevant here; restoring would reinstate the compromised key.

### Operator error (accidental delete)

**Impact:** varies. **The most common real disaster**, and the one PITR exists for.

1. **Do not** "undo" with more writes. Stop and think.
2. Identify the exact time from the audit trail — every mutation is recorded with actor and timestamp.
3. PITR to just before it, into a **separate instance**.
4. Extract only the affected rows and re-insert them into production.

Restoring the whole cluster to fix one deletion discards every legitimate write since. That is usually a bigger disaster than the one being fixed.

### Failed deployment

**Impact:** varies. Roll the application back first — it is faster and reversible.

Only if a **migration** corrupted data: `alembic downgrade` if the migration has a real downgrade path, otherwise PITR to before the deploy. Note that the platform's migration chain is asserted linear by test, so there is always exactly one head to reach.

### Accidental `DROP TABLE`

**Impact:** critical, and the reason BAK-001 found a live latent bug: `migrations/env.py` had lost its model imports, so the next `alembic revision --autogenerate` would have produced a migration **dropping every table**. It is now guarded by `tests/test_migrations.py` and a lint exemption. If it ever happens anyway: PITR to before the migration ran.

## 3. Rollback

| Change | Rollback | Cost |
| --- | --- | --- |
| Application | Redeploy the previous image | Seconds; no data effect |
| Migration (with downgrade) | `alembic downgrade -1` | Minutes |
| Migration (destructive) | PITR to before the deploy | Full RTO |
| Restore itself | Take a backup **before** restoring; restore that | Doubles the window |

**Always back up before restoring.** A restore that goes wrong with no pre-restore backup leaves nothing to return to.

## 4. What is *not* covered

- **Cross-region automation** — documented, manual.
- **Physical PITR execution** — scripted and CI-wired, never run (no PostgreSQL during BAK-001).
- **Automated failover** — there is none. Recovery is a human decision, deliberately: an automatic failover on a false positive is its own outage.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-06 | Architecture Board | Established by BAK-001. |
