---
id: POSTGRES-PROOF
title: PostgreSQL Proof
type: reference
status: Approved
version: "1.2"
owner: Architecture Board
created: 2026-08-06
last-updated: 2026-08-07
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

### VER-001 — and then the proof itself had never run

CI-001 wrote the pipeline below. It was never **executed**: no PostgreSQL was reachable in the development environment, and the guidance was "install one or use Docker". So the proof was a well-written script in the same condition as the guarantees it checks — asserted, not demonstrated.

Running it surfaced four more defects, every one of them invisible on SQLite:

| Defect | Consequence | Why no test caught it |
| --- | --- | --- |
| `SET LOCAL lacteva.tenant_id = $1` | **The platform could not serve a single request on PostgreSQL.** `SET` is utility syntax and takes no bind parameter; asyncpg sends prepared statements, so this raised a syntax error in `get_session`, before any handler | `is_postgres()` is false on SQLite, so `bind_tenant` returned early and the statement never executed |
| The application connected as a **superuser** | Every RLS policy on the platform was **inert** — enabled, forced, and enforcing nothing | Nothing asserted anything about the connected role |
| The RLS suite **re-implemented** the binding it was testing | A syntax error in the production binding could not fail the tests that exist to protect it | The tests issued their own SQL and never called `bind_tenant` |
| The proof's seeder used a plain session factory for consumers | Consumers saw zero events, produced no receipt, and reported success | Consumers only need `platform_factory` once RLS is actually enforced |

The pattern is one thing, not four: **a guarantee that only executes on PostgreSQL, in a suite that only runs on SQLite, is not tested.** The fix is not more review — it is this pipeline, actually running. `./infra/ci/verify-postgres.sh` now stands a real PostgreSQL up from a PyPI wheel, so there is no environment in which it cannot be run.

## 2. What is proven

One script, nine steps, any failure fails the build:

| # | Step | Converts to proven |
| --- | --- | --- |
| 1 | `alembic upgrade head` on an **empty** database | Migrations work from nothing, not just incrementally |
| 2 | Every tenant table has RLS **enabled AND forced** | `relrowsecurity` alone lets the owner bypass its own policy |
| 2b | The application role is **`NOSUPERUSER NOBYPASSRLS`** | A superuser ignores every policy; without this, step 3 passes vacuously |
| 3 | `test_rls_postgres.py` passes **and did not skip** | Isolation is enforced by the database |
| 4 | A real dairy is seeded through the platform's own API | The rest is measured against real business data |
| 5 | Logical backup + checksum verification | The backup is internally consistent |
| 6 | A **second, fresh** database is migrated | The restore target is genuinely new |
| 7 | Restore into it | Cross-database recovery, not in-place |
| 8 | `integrity --deep` on the restored data | Settlements balance, payments reconcile, projections rebuild |
| 9 | Source vs restored compared fact by fact | Nothing silently changed |

Step 3's skip-check matters more than it looks: **a silently skipped security proof is worse than none, because it is green.**

Step 2b matters for the same reason, one level deeper. Steps 2 and 3 were both passing while the role running them was a superuser — so the policies were verified to exist, and verified to be forced, and were being ignored. A proof needs to establish not only that the guard is present but that it is *capable of refusing*. The proof now creates an unprivileged `lacteva_app` role, asserts it holds neither `rolsuper` nor `rolbypassrls`, and runs every isolation test as it. The schema owner is used only for DDL, backup and restore.

## 3. Running it

### In CI

Its own workflow: **`.github/workflows/postgres.yml`**. It runs on every push and pull request, **nightly at 03:17 UTC**, and on demand (`workflow_dispatch`, with an option to leave the databases standing for inspection).

Nightly matters more than it looks: a dependency bump, a base-image change, or a new PostgreSQL point release can break a guarantee without anyone touching this repository. Verification that only runs on change only catches changes.

**A version matrix, not a version.**

| Leg | Role |
| --- | --- |
| `postgres:16` | The production baseline documented in DBD-0001 |
| `postgres:17` | The newest release the matrix covers |

Both must pass; `fail-fast: false`, because learning that 16 passed while 17 failed is the entire point. **PostgreSQL 18 is deliberately absent.** Adding a version to this matrix is how it becomes supported — the first green run is the evidence, not the intention — and an unproven version in a required matrix is a red build waiting for someone else's morning. Add it in its own change, so a failure is unambiguous.

A single `PostgreSQL verified` job depends on the matrix, so branch protection names one check rather than every leg — and adding a version later cannot silently stop gating merges.

### Why a skip cannot happen

CI-001 detected skips after the fact by grepping pytest's output for `N skipped`. OPS-001 makes them impossible instead, in two independent places:

1. **`LACTEVA_REQUIRE_POSTGRES=1`** (exported by the proof script) makes `tests/postgres_support.py` raise at *collection* when no database URL is set. A collection error fails the run before any test executes, so it cannot be mistaken for a passing suite.
2. **The JUnit counts** are then asserted from `pytest --junitxml` — structured output rather than prose, because pytest's summary line has changed format before and the XML attributes have not. Zero skipped, zero failures, zero errors, and more than zero collected.

Locally, with no `LACTEVA_TEST_POSTGRES_URL`, the suites still skip — which is the correct outcome on a laptop with no database. The two situations are genuinely different and are treated differently on purpose.

### Locally, with Docker

```bash
docker compose -f docker-compose.proof.yml run --rm proof

# a specific matrix leg
POSTGRES_VERSION=17 docker compose -f docker-compose.proof.yml run --rm proof

# keep the databases standing after a failure, to look at them
KEEP_DATABASES=1 docker compose -f docker-compose.proof.yml run --rm proof
```

This runs **the identical script** CI runs. There is deliberately one code path: two pipelines agree right up until the day it matters.

The database is ephemeral — no volume, no published port. Every run starts empty, because "migrations apply from empty" is one of the things being proven.

### Locally, with one command and no Docker

```bash
./infra/ci/verify-postgres.sh
```

The whole pipeline, all nine steps, against a real engine. It finds one in this order:

1. **`PGHOST`**, if you have set it — your own server.
2. **Docker**, via `docker-compose.proof.yml` — pins the server version, so a local run is a CI matrix leg.
3. **The `pgserver` wheel** — genuine PostgreSQL binaries from PyPI, initialised into a temporary directory and listening on a unix socket. No daemon, no port, no root.

Option 3 is why VER-001 exists. A verification pipeline that cannot be executed in the environment where the code is written is documentation, and four defects lived through four work orders because of it.

All three paths run `infra/ci/postgres-proof.sh`. There is one proof.

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
| `N PostgreSQL test(s) SKIPPED` | The suites ran without a reachable database — a configuration failure, never an expected outcome |
| `pytest produced no JUnit report` | The test step did not execute at all |
| `N table(s) carry tenant_id but have NO policy` | A tenant-owned table shipped without RLS (SEC-002) |

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
| 1.1 | 2026-08-06 | Architecture Board | OPS-001: dedicated workflow, version matrix, nightly schedule, skips made impossible rather than detected, published summary, teardown. |
| 1.0 | 2026-08-06 | Architecture Board | Established by CI-001. |
