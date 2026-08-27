---
id: LACTEVA-P1-E2E-404-INVESTIGATION
title: The Read-After-Write 404 — Investigation and Resolution
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-19
last-updated: 2026-08-19
related: [LACTEVA-P1-E2E-HARNESS-001, LACTEVA-P0-PRODUCT-008-FULL-PRODUCT-READINESS-AUDIT, LACTEVA-MASTER-PRODUCT-ROADMAP]
baseline: ARCH-BASELINE-V1
---

# Lacteva — The Read-After-Write 404 (P1-E2E-404-001)

## 1. Executive summary

The open finding from P1-E2E-HARNESS-001 is **reproduced, root-caused, fixed
and guarded**. It was a genuine product defect, and a more serious one than its
symptom suggested.

**The platform answered every write before it committed it.** `get_session`
commits in FastAPI's dependency teardown; the middleware stack is built on
`BaseHTTPMiddleware`, whose `call_next` returns as soon as the response
*starts*. The answer therefore reached the client **0.3–1.1 ms before the
commit** — every time, not occasionally. A client acting on its own answer
inside that window asked for a row that was not committed yet and was correctly
told it did not exist.

The 404 was the harmless half. The dangerous half is that **a commit failing
after the response has gone cannot change it**: the platform could have
answered `201 Created` for a write that never happened. For a milk transaction,
a settlement or a receipt, that is the one failure this codebase refuses to
tolerate, and no amount of review had found it.

It was fixed by committing inside the route handler, where the response is
still the platform's to change. Proven against real PostgreSQL: **107/150 → 0**
and **14/14 seeding runs clean**. Guarded by five tests, one of which was
watched failing with the fix removed before it was kept.

**Verdict: GREEN.**

## 2. Original observation

P1-E2E-HARNESS-001 §19 reported, as OPEN:

> roughly one seeding run in four, `POST /v1/suppliers/{id}/centers` reports
> "supplier not found" for a row created moments earlier

with projection lag, a simple sequential race and cross-tenant bleed already
investigated. Per this work order those exclusions were treated as leads, not
as proof, and each was re-tested independently.

## 3. Reproduction methodology

Everything ran against the real harness: real Flutter/portal client code, real
FastAPI under uvicorn, real PostgreSQL from the `pgserver` wheel, a synthetic
dairy seeded through the platform's own API. Synthetic data only — every record
is `(TEST DATA)` on `.e2e.example` addresses, in a database created and
destroyed per run. No real dairy, farmer, supplier, outlet or price was used at
any point.

Five instruments were built, in increasing order of directness:

| Instrument | Question it answers |
|---|---|
| `probe_seedloop` | How often does a full seeding run fail, and with what? |
| `probe_404` / `probe_alternating` | Does create→act fail in isolation? Under alternating principals? |
| `probe_commit` / `probe_commit2` | Was the row committed when the response arrived? |
| `probe_concurrent_seed` | Is contention required? |
| `probe_register` / `probe_order` | The two-request minimum case, and the server's own ordering |

Each failure was put to PostgreSQL directly, as a superuser, and to the
platform's own metrics — because a client-side inference is not evidence.

## 4. Reproduction frequency

| Path | Rate |
|---|---|
| Full seeding run (~40 writes) failing outright | ~1 in 4–8 runs |
| `POST /v1/auth/register` answering 2xx with the row not yet present | **107 / 150 (71%)** |
| Sign-in refused for a user registered a moment earlier | **12 / 150 (8%)** |
| Commit landing after the response, measured in the server's own log | **every request** |

The last row is the honest one. The defect was not intermittent at all — the
*consequence* was, and only because it depended on how fast the next request
arrived.

## 5. Exact failing sequence

The minimum case needs two requests and no tenancy at all:

```
POST /v1/auth/register        → 201 {"id": "228e8ae6-…"}
SELECT 1 FROM user_account WHERE id = '228e8ae6-…'   → no rows
POST /v1/auth/token           → 401 "Email or password is incorrect."
```

The seeding failures are the same sentence in other tables — the entity
differed with whatever the harness happened to write next:

```
POST /v1/devices/{id}/assign          → 404 "device not found"
POST /v1/collection-centers           → 404 "branch not found"
POST /v1/branches                     → 404 "workspace not found"
POST /v1/suppliers/{id}/centers       → 404 "supplier not found"
```

## 6. Client trace

Not the client. The portal proxy, the Flutter `ApiClient` and the raw probes
all reproduce it identically, and the smallest reproduction uses no client code
at all — two `httpx` calls. No client caching, stale id, or scope error is
involved: the id in the failing request is the id the platform had just
returned. Nothing was changed in any client to conceal a backend defect.

## 7. API trace

`POST` → `IdempotentRoute` → `idempotency_guard` (returns immediately, no key
sent) → authentication → `require_permission` → service → `flush` → response
model → **response released** → commit. The last two are in the wrong order,
which is the whole defect.

## 8. Backend trace

`get_session` (`core/db.py`) yields the session, and commits **after** the
handler returns, in FastAPI's dependency teardown. `RequestContextMiddleware`,
`TenantContextMiddleware` and `SecurityHeadersMiddleware` are all
`BaseHTTPMiddleware` subclasses; Starlette's `call_next` returns as soon as the
inner app sends `http.response.start`, so the response travels back up the
middleware stack and out to the client while the teardown is still pending.

Instrumentation added for this investigation (`session_diagnostics`, off by
default) logs the commit immediately before it happens. The server's own log,
unedited:

```
53:28.755048  RESPONSE SENT     status=201 duration_ms=59.24
53:28.756153  ABOUT TO COMMIT   txid=40622
53:28.860199  RESPONSE SENT     status=201 duration_ms=52.05
53:28.860594  ABOUT TO COMMIT   txid=40637
53:28.964964  RESPONSE SENT     status=201 duration_ms=52.74
53:28.965633  ABOUT TO COMMIT   txid=40658
```

## 9. Database trace

At the moment of a real seeding failure, asked directly of PostgreSQL as a
superuser (which bypasses even FORCED row-level security):

```
device ea982233-3961-40e1-93ac-2485e0d024d9: ROW ABSENT — the write never became durable
```

Isolation level is PostgreSQL's default **READ COMMITTED** — the engine sets
none — so a stale snapshot cannot explain it and does not need to. The row was
absent because it had not been committed, not because the reader could not see
it. Category **A** of the work order's list, reached by elimination *and* by
direct observation.

## 10. RLS / security analysis

Row-level security was innocent, and this was established rather than assumed.
The binding diagnostic prints, at the moment of the refusal, what the failing
transaction actually had bound:

```
session_diagnostic  error=NotFoundError  detail='device not found'
                    bound_tenant=b1ec3471-…  context_tenant=b1ec3471-…
                    binding_matches_context=True  bypass=off
```

The correct organization was bound, no bypass was in force, and the row was
still absent. Additional negative evidence: `rls_denials_total` was **zero**
across every run; the policy explicitly allows `tenant_id IS NULL` so
platform-owned rows are not hidden from a bound session; every `set_config` in
`core/rls.py` is transaction-scoped (`is_local=true`); and 60 alternating
rounds across three principals on one connection produced **0 own-row misses
and 0 cross-tenant leaks**.

**No RLS policy, tenant filter, permission or query scope was changed by the
fix.** The commit moved; visibility did not.

## 11. Concurrency analysis

Concurrency is **not** causal — the opposite of the initial expectation.

| Experiment | Result |
|---|---|
| A — create → immediate read, sequential | Reproduces (107/150 on the register path) |
| B — create → small delay → read | Does not reproduce; the window is sub-millisecond |
| C — create → concurrent read | Reproduces no more often than A |
| D — multiple independent workers | 9 concurrent seedings, **0 failures** |
| E — same tenant | Reproduces |
| F — different tenants | 60 alternating rounds, 0 misses, 0 leaks |
| G — same entity, different scopes | No scope dependence; five different tables produced it |

It reproduces on a **pristine database, on the very first seeding, with no load
and no concurrency**. What governs the failure rate is only how quickly the
next request arrives.

## 12. Root cause

**The HTTP response was released before the request's transaction was
committed** (E2E-001). `get_session` commits in FastAPI's dependency teardown,
and the `BaseHTTPMiddleware` stack releases the response as soon as it starts,
so the commit is not on the request's critical path from the client's point of
view.

## 13. Evidence supporting the root cause

1. The server's own log shows `RESPONSE SENT` before `ABOUT TO COMMIT`, in
   every sampled request, by 0.3–1.1 ms.
2. A direct superuser query at the instant of failure reports the row **absent**.
3. The binding diagnostic shows the **correct** tenant bound and no bypass.
4. The failure crosses five unrelated tables and two status codes — the common
   factor is "written by the previous request", not any module.
5. Removing the fix makes the ordering test fail; restoring it makes it pass.
6. After the fix, every rate collapses to zero (§19).

## 14. Alternative causes ruled out

Each by measurement, not by argument:

| Cause | Evidence against |
|---|---|
| B — committed but unreadable | Superuser read shows the row absent, not hidden |
| C — wrong tenant id | `binding_matches_context=True`, correct org bound |
| D — wrong centre scope | Reproduces on `register`, which has no centre or tenant |
| E — RLS hides it | `rls_denials_total` = 0; policy allows `tenant_id IS NULL`; 0 leaks/60 |
| F — wrong identifier | The id used is the id the platform returned; by-email lookup finds the same id moments later |
| G — stale cache | No read cache exists on these paths; handlers read their tables directly |
| H — async projection | The failing handlers do not read projections |
| I — background worker race | 5 workers idle-clean; reproduces with workers doing nothing |
| J — fixture collision | Ids are server-generated UUIDs, unique per run, fresh database per run |
| K — isolation level | Engine uses READ COMMITTED (nothing set); no snapshot involved |
| L — application filtering | Same code path succeeds milliseconds later, unchanged |
| N — harness defect | The minimum case is two `httpx` calls and no harness code |
| O — environment-specific | Ordering is a property of the middleware/dependency design, not the machine |

Two earlier scares were **my own measurement bugs**, caught before they became
findings and recorded rather than deleted: a false "132 cross-tenant leaks" (a
probe appending each tenant's own ids to the list it then read) and a false
"40% of writes uncommitted, 124–313 ms" (load generated as asyncio tasks in the
same event loop that did the timing, starving the measurer).

## 15. Product defect vs harness defect

**Product defect: YES** — E2E-001, fixed here.

**Harness defect: YES, separately** — one, unrelated to the 404: the mail
reader took the newest delivered message and demanded a token be in it, so a
"Welcome to Lacteva" arriving in the same moment failed a seeding the platform
had served correctly. It now scans new messages for one that actually carries a
token. Fixed in the harness, not in the product.

## 16. Fix applied

The smallest correct layer is the route, because that is the last place the
response is still the platform's to change.

- `api/transactional_route.py` (new) — `TransactionalRoute` commits the
  request's transaction after the endpoint returns and before the response is
  handed back.
- `api/idempotent_route.py` — the same call, placed **after** the idempotency
  record is written, so the record and the business change still commit
  together. 32 of the 37 routers already carry this class.
- `api/routes.py` — the five routers that had no route class now carry
  `TransactionalRoute`.
- `core/db.py` — `commit_request_session()`, and `get_session` keeps its
  teardown commit as a backstop for non-routed use.
- `core/config.py` — `session_diagnostics` (default **False**): the
  instrumentation that solved this, kept because the next question of this kind
  will need it and it costs nothing when off.

No sleep, no blind retry, no widened query, no weakened policy, no API contract
change. The seeder's existing masking retry was **removed** — a retry that
outlives its defect becomes a blindfold.

A second, quieter improvement falls out of it: a commit that fails now happens
while the response can still become a 500, instead of after the client has been
told 201.

## 17. Regression test

Five assertions across two levels, because neither level alone is sufficient.

`services/platform-core/tests/test_commit_before_response.py`:
1. **Ordering**, observed on the ASGI `send` channel — a test client waits for
   the application to finish and would show this as correct however wrong it
   is, so the assertion is on the server's own sequence.
2. **Read-your-writes** across two real requests (register → sign in).
3. **Structural guard**: every mutating route (`POST/PUT/PATCH/DELETE`) in the
   built application must carry a committing route class. Forgetting one on a
   future router would reintroduce this silently, since the write usually still
   lands in time.

`apps/admin-portal/e2e/portal-boundary.e2e.test.ts` (real server, real
PostgreSQL, real portal route handlers):
4. **25 consecutive create→immediate-read cycles**, all of which must return
   200. Repeated because the window was sub-millisecond; before the fix this
   failed within the first handful.
5. **Tenant isolation of the newly created rows** — the other dairy still
   cannot read them.

Test 1 was **watched failing** with the fix removed, then restored. Nothing is
mocked in tests 4 and 5.

## 18. Security verification

- Binding, bypass and denial evidence as in §10 — unchanged by the fix.
- Cross-tenant read of a *newly created* row refused (new E2E test 5).
- Existing cross-tenant and authorization tests in both the backend and portal
  E2E suites re-run and green (§19).
- The PostgreSQL RLS proof re-run (§19).

No policy, filter, permission, scope or role was touched.

## 19. Full test results

| Suite | Passed | Failed | Skipped | Exit |
|---|---|---|---|---|
| Backend pytest (full) | see §Results | 0 | PostgreSQL-gated by design | **0** |
| E2E combined (`run-e2e.sh all`) | 22 (14 mobile + 8 portal) | 0 | 0 | **0** |
| PostgreSQL proof (`verify-postgres.sh`) | migrations, RLS, backup, restore | 0 | — | **0** |
| Portal vitest (unit) | unchanged | 0 | 0 | **0** |
| Portal eslint `--max-warnings 0` | clean | — | — | **0** |
| Mobile `flutter test` / `analyze` | unchanged | 0 | 0 | **0** |
| Docs validation + xref | pass | — | — | **0** |

Exact counts are recorded in the final report and the CHANGELOG entry.

## 20. Remaining uncertainty

- **No evidence of an actual lost write exists.** A commit failing inside that
  window would have needed a coinciding database fault. The *guarantee* was
  missing; a realised loss is not claimed, and anything already committed in a
  deployed database is unaffected.
- **Write latency is now honest for the first time** — the commit is on the
  request's critical path where it belongs. The harness saw no regression, but
  a real load profile has never been measured (**TO CONFIRM**, and a natural
  item for the scale milestone).
- Whether any *other* framework-ordering assumption hides elsewhere in the
  stack has not been swept; this investigation was scoped to one defect.

## 21. Roadmap preservation

Confirmed untouched and unimplemented: AI beyond the existing statistical
deviation flag, anomaly detection, forecasting, advanced analytics, SAP/ERP,
enterprise SSO, global identity, federation, org-to-org relationships, GPS,
hardware scale/analyzer connectors, QR, PDF, messaging providers, chilling
centre, BMC, plant/processing, procurement transport, farmer app,
customer/outlet portal, advances/loans, payment gateway. No UI, design system,
colour, typography, navigation or animation was touched. No demo data, fake
endpoint or placeholder integration was created.

## 22. Final verdict

**GREEN.** Reproduced, root-caused with direct evidence from inside the server,
fixed at the smallest correct layer, guarded by tests including one proven able
to fail, with security boundaries verified unchanged.

The finding that matters beyond this defect: it was invisible to ~2,000 backend
tests **by construction**, because an in-process client cannot observe the
ordering. That is an argument for the E2E harness existing, and for asking the
server rather than inferring from outside.

## 23. Recommended next milestone

**P1-SCALE-RACE-001** (concurrency and large-import hardening) — the same
neighbourhood, and the natural home for the write-latency profile §20 leaves
open. **P1-LOCALE-I18N-002** is the alternative. Design System V1 remains after
the functional track, as agreed. **Not started here.**

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-19 | Engineering | Investigation and resolution of the open read-after-write 404 from P1-E2E-HARNESS-001. Reproduced (107/150 on the minimum two-request case); root cause established by server-side instrumentation as the response being released before the commit (0.3–1.1 ms, every request), caused by `get_session` committing in FastAPI dependency teardown behind a `BaseHTTPMiddleware` stack; thirteen alternative causes ruled out by measurement; fixed with `TransactionalRoute` plus the same commit in `IdempotentRoute`; five regression tests added across in-process and real-database levels, one watched failing first; RLS/tenant isolation re-verified unchanged; harness mail-reader defect fixed and the masking retry removed (P1-E2E-404-001). |
