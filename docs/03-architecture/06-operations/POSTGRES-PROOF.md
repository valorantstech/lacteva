---
id: POSTGRES-PROOF
title: PostgreSQL Proof
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-06
last-updated: 2026-08-06
related: [BACKUP, RESTORE, RLS-GUIDE, SECURITY, RUNBOOK_BACKUP]
baseline: ARCH-BASELINE-V1
---

# PostgreSQL Proof

How the platform proves, on a real engine, the guarantees SQLite cannot exercise. Established by CI-001 (Phase B).

## 1. Why this exists

Three work orders in a row ended the same way: a P0 guarantee was **written, tested, and CI-wired — but never actually executed**, because the test stack is SQLite and the guarantee is PostgreSQL-specific.

That gap is not academic. Running these steps against a real engine for the first time immediately surfaced three defects that every existing test had passed over:

| Defect | Why no test caught it |
| --- | --- |
| RLS blocked every platform-global row — **registration itself failed** | SQLite has no row-level security, so the policy predicate was never evaluated |
| A backup captured **1 table and 3 rows** while reporting success | The CLI process had imported only its own models; the test suite imports the whole app |
| Restore crashed ordering a table it could not see | Same root cause, different symptom |

The first would have taken authentication down on the first production deploy with RLS enabled. All three are fixed, and each now has a test that fails without the fix.

## 2. What is proven

One script, nine steps, any failure fails the build:

| # | Step | Converts to proven |
| --- | --- | --- |
| 1 | `alembic upgrade head` on an **empty** database | Migrations work from nothing, not just incrementally |
| 2 | Every tenant table has RLS **enabled AND forced** | `relrowsecurity` alone lets the owner bypass its own policy |
| 3 | `test_rls_postgres.py` passes **and did not skip** | Isolation is enforced by the database |
| 4 | A real dairy is seeded through the platform's own API | The rest is measured against real business data |
| 5 | Logical backup + checksum verification | The backup is internally consistent |
| 6 | A **second, fresh** database is migrated | The restore target is genuinely new |
| 7 | Restore into it | Cross-database recovery, not in-place |
| 8 | `integrity --deep` on the restored data | Settlements balance, payments reconcile, projections rebuild |
| 9 | Source vs restored compared fact by fact | Nothing silently changed |

Step 3's skip-check matters more than it looks: **a silently skipped security proof is worse than none, because it is green.**

## 3. Running it

### In CI

Automatic on every push and pull request — the `platform-core (PostgreSQL proof)` job.

### Locally, with Docker

```bash
docker compose -f docker-compose.proof.yml run --rm proof
```

This runs **the identical script** CI runs. There is deliberately one code path: two pipelines agree right up until the day it matters.

The database is ephemeral — no volume, no published port. Every run starts empty, because "migrations apply from empty" is one of the things being proven.

### Locally, against your own PostgreSQL

```bash
createdb -U lacteva postgres 2>/dev/null || true
PGHOST=localhost PGUSER=lacteva PGPASSWORD=lacteva ./infra/ci/postgres-proof.sh
```

It creates and drops `lacteva_proof` and `lacteva_restore`, so point it at a throwaway server. Override with `SOURCE_DB` / `RESTORE_DB`.

## 4. Reading a failure

The script prints a numbered step before each phase, so the last line before the failure names the phase.

| Failure | Meaning |
| --- | --- |
| `only N tables after migration` | A migration did not run, or the model registry is incomplete |
| `N table(s) have RLS enabled but NOT forced` | A policy exists but the application's own role bypasses it |
| `RLS tests SKIPPED` | pytest could not reach PostgreSQL — a configuration failure, not a pass |
| `seeding failed at X` | The platform rejected a legitimate operation; the message carries the response |
| `the backup did not verify` | Checksum mismatch — corruption between write and read |
| `restore failed, or the restored data violated a business rule` | The CLI exits non-zero when the restored business is wrong |
| `the restored database differs from its source` | The comparison names the mismatching fact |

## 5. Why the seeder avoids the app lifespan

It calls `discover_consumers()` and `ensure_system_roles()` directly instead of starting the app's lifespan, because the lifespan also starts background loops (relay, consumers, health sampling). Their sessions interleave with the seeding requests; on SQLite's `StaticPool` that shares a single connection and **silently loses writes**, and on PostgreSQL it merely makes the seed nondeterministic. Consumers are driven explicitly so receipts and notifications exist at a known point.

## 6. The model registry

Both defects 2 and 3 above had one root cause: `Base.metadata` is only as complete as the imports a process has done. `core/model_registry.py` is the single answer, and `import_all_models()` is a **function call** rather than an import block — no linter autofix can remove a call, which is exactly how the previous incarnation was lost (BAK-001 found `migrations/env.py` stripped of its model imports, one autogenerate away from dropping every table).

Migrations and the backup engine both call it. A test asserts the registry sees every table.

## 7. Known limits

- **Physical PITR is still unproven.** This proves the *logical* backup/restore path on PostgreSQL. `pg_basebackup` + WAL replay is scripted (`infra/backup/`) and documented but not exercised here — it needs a server the CI job does not manage.
- **Single-node only.** No replication, failover, or connection-pooler behaviour is exercised.
- **The seeded dataset is small.** It proves correctness, not performance at scale.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-06 | Architecture Board | Established by CI-001. |
