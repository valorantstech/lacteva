---
id: VER-001-REPORT
title: PostgreSQL Verification Report (VER-001)
type: report
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-07
last-updated: 2026-08-07
related: [POSTGRES-PROOF, RLS-GUIDE, DEPLOYMENT, BACKUP, RESTORE, SECURITY]
baseline: ARCH-BASELINE-V1
---

# PostgreSQL Verification Report (VER-001)

**Result: the pipeline is green.** All nine proof steps execute, end to end, from a single command, against a real PostgreSQL 16.2. No step is skipped, no failure is tolerated, and no placeholder remains.

## 1. The finding behind the work order

The pipeline that verifies the platform's PostgreSQL guarantees **had never been run.** CI-001 wrote it carefully; no PostgreSQL was reachable in the development environment, and the standing guidance was "install one or use Docker", neither of which was available. So the verifier sat in exactly the condition of the things it verifies: asserted, reviewed, and never executed.

Running it found **five defects**, two of which were platform-fatal. Every one had passed code review, and every one was invisible to a suite that runs on SQLite.

The unifying cause is a single sentence: **a guarantee that only executes on PostgreSQL, tested only on SQLite, is not tested.** `is_postgres()` returns false, the function returns early, and the test goes green having exercised nothing.

## 2. Problems found

### P-1 — The platform could not serve a single request on PostgreSQL (fatal)

`bind_tenant` issued:

```sql
SET LOCAL lacteva.tenant_id = $1
```

`SET` is *utility syntax*, not a query: PostgreSQL accepts no bind parameter in it, and asyncpg sends every statement as a prepared statement. This is a **syntax error**. The binding runs in `get_session`, before any handler, so it would have been raised on **every request the platform ever received**. The same defect was in `bind_platform_context` and `_relax_statement_timeout`.

Written in SEC-001, carried through SEC-002, MT-001, API-001, IDM-001, MSG-001 and ARCH-001. First executed in VER-001.

### P-2 — Row-level security was inert in production (fatal, silent)

**A PostgreSQL superuser ignores every RLS policy.** `FORCE ROW LEVEL SECURITY` does not close this — `FORCE` covers the table *owner*, and says nothing about superusers.

`docker-compose.production.yml` connected the API as `${POSTGRES_USER}`, which the official `postgres` image creates as a superuser. So every policy built by SEC-001, SEC-002 and MT-001 was **enabled, forced, listed in `pg_policies`, and enforcing nothing.** Tenant isolation was application-level only — precisely the dependency RLS was introduced to remove.

This one is worth dwelling on: **nothing would ever have alerted.** `verify-deployment.sh` checked that the policies existed, and they did. The platform would have run for months looking correct. It would have been discovered by a cross-tenant data leak.

The proof pipeline had the same defect, so its RLS suite was passing vacuously too.

### P-3 — The RLS suite re-implemented the binding it existed to protect

All 54 binding sites in `test_rls_postgres.py` issued their own `SET LOCAL ...` instead of calling `bind_tenant`. A test that builds its own copy of the thing under test is testing the copy: P-1 could not have been caught by the suite whose entire purpose is that guarantee.

### P-4 — Consumers saw no events under real RLS

`seed_proof_data.py` built its `ConsumerRunner` on a plain session factory. A consumer drains the log for *all* tenants, so its session has no tenant to bind, and an unbound session sees nothing once policies are enforced. The runner processed zero events, produced no receipt, and **reported success.** (`main.py` was already correct; only the seeder was not.)

### P-5 — Three test defects that only PostgreSQL could expose

- `settlement_line` and `payment_line` rows were inserted against foreign keys that matched nothing. SQLite does not enforce foreign keys unless asked, and the suite never asked.
- Two catalog tests read whatever the database happened to contain, passing only if an earlier run had left rows behind.
- One test passed its bind parameters to a tuple instead of to `execute()`.

## 3. Fixes applied

| # | Fix | File |
| --- | --- | --- |
| 1 | `SELECT set_config(:name, :value, true)` replaces `SET LOCAL ... = :param` in all three binding functions | `core/rls.py` |
| 2 | `assert_rls_is_enforceable()` — the platform **refuses to start** in `prod`/`staging` when connected as a role that bypasses RLS | `core/rls.py`, `main.py` |
| 3 | A non-superuser application role, created at first start, separate from the schema owner | `infra/postgres/init/10-application-role.sh` |
| 4 | The API connects as that role; `migrate` keeps the owner, because DDL needs it | `docker-compose.production.yml`, `.env.production.example` |
| 5 | `verify-deployment.sh` asserts the API role is neither `rolsuper` nor `rolbypassrls`, and differs from the owner | `infra/deploy/verify-deployment.sh` |
| 6 | The proof creates and asserts its own unprivileged role, and runs every isolation test as it | `infra/ci/postgres-proof.sh` |
| 7 | The RLS suite calls the production binding functions | `tests/test_rls_postgres.py` |
| 8 | Consumers and the platform-admin grant use `platform_factory` | `infra/ci/seed_proof_data.py` |
| 9 | Parent rows created; catalog seeded via `ensure_system_roles()`; the bind-parameter bug fixed | `tests/test_rls_postgres.py` |
| 10 | The seeder writes its JSON summary to an explicit path — stdout also carries structured logs, so the report's "evidence" was a truncated log line | `infra/ci/seed_proof_data.py` |

## 4. Tests added

| Test | Proves |
| --- | --- |
| `test_the_tenant_binding_is_valid_sql_and_takes_effect` | The binding executes on PostgreSQL and sets the value — fails against P-1 |
| `test_the_binding_does_not_survive_the_transaction` | Transaction scope, which is what makes a pooled connection safe |
| `test_a_role_that_bypasses_rls_is_refused` | The pipeline's own role cannot bypass RLS — without it every other test here is vacuous |
| `test_production_refuses_a_role_that_ignores_rls[SUPERUSER]` | Startup refusal, superuser |
| `test_production_refuses_a_role_that_ignores_rls[BYPASSRLS]` | Startup refusal, `BYPASSRLS` |
| `test_a_normal_role_starts_cleanly` | The refusal does not fire on a correct deployment |

Plus the structural change that matters more than any single case: **all 54 binding sites in the RLS suite now exercise production code**, so a regression in `bind_tenant` fails the suite that exists to protect it.

## 5. Execution evidence

```
==> 1/9  migrations apply to an EMPTY database        58 tables created
==> 2/9  RLS enabled AND forced, and covering         52 forced, 52 policies, 0 uncovered
         application role lacteva_app                 NOSUPERUSER, NOBYPASSRLS
==> 3/9  PostgreSQL-only suites                       41 tests, 0 skipped
==> 4/9  a real dairy seeds through the platform API  30 endpoints, 201/200 throughout
==> 5/9  logical backup + checksum verification       verified
==> 6/9  a second, fresh database migrates            lacteva_restore
==> 7/9  restore into it                              restored
==> 8/9  deep business integrity on restored data     settlements, payments, receipts, projections
==> 9/9  source vs restored, fact by fact             identical
```

`POSTGRESQL PROOF PASSED` — PostgreSQL 16.2, one command, no Docker.

## 6. Making it runnable — the actual deliverable

The defects above are worth less than the reason they survived. `./infra/ci/verify-postgres.sh` runs the entire pipeline and finds an engine three ways: an existing `PGHOST`; Docker (`docker-compose.proof.yml`); or a real PostgreSQL initialised from the **`pgserver` PyPI wheel** — genuine server and client binaries, a unix socket in a temporary directory, no daemon, no port, no root.

That third path is the fix for the root cause. There is now no environment in which the verification pipeline cannot be executed. All three paths run `infra/ci/postgres-proof.sh`; there is one proof.

## 7. Remaining infrastructure limitations

Stated plainly, because an unstated limitation reads as a covered case.

1. **One PostgreSQL version has actually executed here: 16.2.** The CI matrix covers 16 and 17; the 17 leg has not run in this environment. PostgreSQL 18 remains deliberately unproven and unsupported.
2. **Physical recovery is not proven.** The pipeline proves *logical* backup and restore. PITR, WAL archiving and replica promotion are documented in `DISASTER-RECOVERY.md` and have never been executed.
3. **No concurrency at production scale.** The payment race is proven with staged transactions on a real engine, not under load. No load test exists.
4. **The full production compose has not been stood up here** — no Docker. The role split is asserted by `verify-deployment.sh` and by the startup refusal, both of which run against a real database; the compose file itself is verified only by `config` resolution.
5. **`pgserver` is a development and verification tool, not a deployment target.** No durability tuning, no supervision, no backup schedule.
6. **The proof seeds one dairy.** Cardinality-dependent behaviour — index selection, plan changes, vacuum pressure at scale — is untested.

## 8. Production readiness

**Before VER-001, on the engine the platform actually deploys to, it was 0%.** The application could not answer a request (P-1), and had it been patched past that, it would have served every tenant's data to every other tenant (P-2). The prior estimate of "≈92–95%" was measuring a SQLite build.

That is the finding, not the score. **A guarantee that has not been executed is an intention.** Six of the last eight work orders produced at least one defect of exactly this shape, and each was found in the first minute of running the code rather than in any amount of review.

| Area | State |
| --- | --- |
| Runs on PostgreSQL at all | **Proven** — was broken |
| Tenant isolation enforced by the database | **Proven** — was inert |
| Migrations from empty | Proven |
| Backup, restore, deep integrity, fact-by-fact | Proven |
| Exact numeric aggregation | Proven |
| Idempotency and payment concurrency | Proven on a real engine |
| Physical DR (PITR, replicas) | **Not executed** |
| Behaviour under load and at scale | **Not executed** |

**Assessment: production-ready for a controlled first deployment, on PostgreSQL 16, with logical backup as the recovery path.** Not yet ready for an uncontrolled one: items 2 and 3 in §7 are the gap, and both need infrastructure rather than code.

The number matters less than the direction of the error. The right next work order is the one that executes disaster recovery, for the same reason this one mattered.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-07 | Architecture Board | VER-001: the PostgreSQL verification pipeline executed for the first time; five defects found and fixed; the pipeline is green. |
