---
id: LACTEVA-P1-E2E-HARNESS-001
title: Real Client↔Server E2E Harness
type: reference
status: Approved
version: "1.1"
owner: Engineering
created: 2026-08-19
last-updated: 2026-08-19
related: [LACTEVA-P0-PRODUCT-008-FULL-PRODUCT-READINESS-AUDIT, LACTEVA-P1-PORTAL-SCALE-001, LACTEVA-P1-MOBILE-COUNTER-001, LACTEVA-P1-LOCALE-I18N-001, LACTEVA-MASTER-PRODUCT-ROADMAP]
baseline: ARCH-BASELINE-V1
---

# Lacteva — Real Client↔Server E2E Harness (P1-E2E-HARNESS-001)

## 1. Executive summary

The deepest gap the readiness audit found is closed: **20 automated tests now
cross a real client↔server boundary** — the shipping Flutter and portal client
code, over real HTTP, to a real FastAPI server, against a **real PostgreSQL**
database, with a synthetic dairy seeded entirely through the platform's own
API. One command creates that world from nothing and destroys it afterwards.

The harness paid for itself while being built. It proved tenant isolation holds
under concurrent two-tenant load (0 leaks in 24 interleaved write/read cycles);
it caught the rate limiter defending itself; it forced the seeder to walk the
real onboarding runbook (a centre will not accept milk until it has hours, an
active scale and an operator; a supplier is a draft until assigned and
activated; a session refuses to close with work in flight); and it found a real
product defect that no unit suite could have seen, because no unit suite can:
**the platform answered every write before it committed it** (E2E-001, §19.1).
Server-side instrumentation established the cause, it is fixed, and the fix is
guarded by a test that was watched failing first.

**Verdict: PARTIAL — GREEN for the API boundary, with browser-level E2E
honestly deferred.** No browser driver is vendored in this repository and
adding one means downloading browsers, which the milestone forbids inventing.

## 2. Existing test architecture

Backend ~120 pytest files (deep, adversarial, PostgreSQL-gated suites for RLS /
exact aggregation / DR). Portal 29 vitest files (jsdom, network mocked). Mobile
15 flutter_test files (mocked HTTP). All valuable; all stopping at a mock.

## 3. The gap this milestone closes

Every client test mocked the network, so a backend serializer change, a
contract drift, a cookie/proxy regression or a readiness rule could ship with
all three suites green and break on the first real click. Nothing exercised
authentication, RLS, offline replay or the parchi across a real wire.

## 4. Client/server boundaries discovered

| Boundary | Reachable here? |
|---|---|
| Flutter `ApiClient`/`OfflineApiClient` → HTTP → FastAPI | **YES** — real, and now covered |
| Portal route handlers (`/api/auth/login`, `/api/proxy/[...path]`) → FastAPI | **YES** — real, and now covered |
| Browser DOM → portal page → proxy → FastAPI | **NO driver vendored** — deferred (§24) |
| Flutter widget tree on a device → HTTP | needs a device/emulator — deferred (§24) |

## 5. E2E architecture selected

`infra/e2e/run-e2e.sh` — one command, one process tree, no leftovers:

```
fresh PostgreSQL database (pgserver wheel — no Docker, no root)
   → alembic upgrade head
   → local SMTP sink (infra/e2e/mailsink.py)
   → REAL FastAPI app under uvicorn
   → synthetic dairy seeded through the platform's own HTTP API
   → client suites driven against that server
   → everything torn down
```

Modes: `all` · `mobile` · `portal` · `seed-only` · `probe` (ad-hoc
investigation against the live seeded platform).

Two deliberate choices, both recorded in the script itself:
- **PostgreSQL, not SQLite.** RLS is a PostgreSQL feature, so an RLS assertion
  on SQLite would be theatre; and a real server runs five background workers
  whose concurrent writes SQLite's single-writer lock cannot serve.
- **`OUTBOX_MODE=background`, the production mode.** `inline` is the unit
  suite's mode, is refused in prod, and races the relay workers a real server
  starts.

## 6. Test environment

No Docker, no daemon, no root, no credentials, no external service, no
production data. PostgreSQL binaries come from the `pgserver` wheel already
used by the repository's verification proofs; the mail sink is 40 lines of
stdlib asyncio because `aiosmtpd` is not vendored and adding a dependency to
receive four test emails would be worse.

## 7. Synthetic data strategy

`infra/e2e/seed.py` builds, through the **real API**: two organizations (the
second exists so cross-tenant tests use a real foreign tenant, not a fabricated
id), workspace → branch → two centres, per-centre scale/analyzer/printer
devices registered → assigned → activated → health-reported, operating hours,
an operator assignment, centre activation, five users across five roles via
the **real invitation flow**, and three suppliers assigned and activated.

Everything is labelled `(TEST DATA)` on `.e2e.example` addresses. No real
dairy, farmer, outlet, price or rate appears anywhere. A fresh database per
run makes the data deterministic and the teardown total.

**The invitation path is real.** The platform deliberately does not return an
invitation's raw token (SEC-003/F-04 — whoever issued it could otherwise accept
it). The harness therefore reads the token the way an invitee does: out of a
message really delivered over real SMTP. The security design was respected, not
worked around — and the notification path got covered as a bonus.

## 8–16. Test matrices

| # | Area | Tests | Class |
|---|---|---|---|
| 8 | **Authentication** (mobile) | valid sign-in + platform-resolved identity/grants; wrong password refused; unauthenticated request refused; post-sign-out refusal | REAL ×4 |
| 9 | **Organization / centre / RLS** (mobile) | own centres listed; **another tenant's centre invisible** (404/403, and absent from the list); role without the grant refused by the backend | REAL ×3 |
| 10 | **Collection** (mobile) | full six-step capture: session → identify → milk → weight → quality → accept → complete, all through real endpoints | REAL ×1 |
| 11 | **Quality / rate / parchi** (mobile) | net weight computed by the platform; **slip number minted by the platform** (`SLP-…`) and its text carries it; impossible measurement (tare > gross) refused; fabricated device reading refused/bounded | REAL ×3 |
| 12 | **Offline / replay** (mobile) | full capture queued offline → replayed exactly once on reconnect → second sync sends nothing; **queue survives a process restart byte-for-byte** and replays once after re-authentication | REAL ×2 |
| 13 | **Transaction history** (mobile) | completed collection retrievable, centre-scoped, and its parchi matches the transaction | REAL ×1 |
| 14 | **Session close** (mobile) | close through the platform; the centre then reports no open session | REAL ×1 |
| 15 | **Portal** | sign-in returns 204 with the **token in an HttpOnly cookie and never in the body**; wrong password sets no session; authenticated proxied read returns the dairy's own centres; **unauthenticated proxy refused**; **another tenant's centre unreachable through the proxy**; a viewer's write refused 403 with the platform's own RFC-9457 problem document passed through | REAL ×6 |
| 16 | Mobile totals | 14 | REAL |

## 17. Real vs integration vs mocked

| Class | Count | What it means here |
|---|---|---|
| **REAL** | **20** | Shipping client code → real HTTP → real FastAPI → real PostgreSQL → real response parsed by real client code |
| INTEGRATION | 0 | — |
| MOCKED | 0 in this suite | The pre-existing 594 client tests remain mocked by design and are unchanged |

The only stand-in anywhere is `next/headers` in the portal suite — a cookie jar
is the Next runtime's job, not the boundary under test. Every request that
leaves these tests is real.

## 18. Security findings

- **Tenant isolation holds under concurrency — verified, not assumed.** A probe
  ran two tenants concurrently through 24 interleaved create/assign/read cycles
  and attempted cross-tenant reads throughout: **0 leaks, 0 misses**. RLS is
  real here because the database is real.
- **Cross-tenant access is refused at every layer tested** — mobile client,
  portal proxy — and the foreign row is absent from lists, not merely
  forbidden.
- **Authorization is the backend's**: a viewer's write is refused 403 by the
  platform; no client can manufacture it.
- **The token never reaches page script**: the portal's sign-in returns 204 and
  the session lives in an HttpOnly cookie — proven, not asserted in prose.
- **The rate limiter defended itself** during harness development (login,
  10/minute/IP). It is disabled *in the harness only*, with the reason recorded
  in the script; its behaviour is proven by the backend suite.
- **A false alarm was caught before it was reported.** An early probe appeared
  to show 132 cross-tenant leaks; the probe was wiring each tenant's own ids
  into the list it then read. Corrected, the answer is 0. Recorded because the
  discipline matters more than the result.

## 19. Defects discovered

| # | Finding | Class | Status |
|---|---|---|---|
| 1 | `inline` outbox mode races the relay workers a real server starts (`StaleDataError` on `event_outbox`) | harness defect (B) | **Fixed** — harness runs the production `background` mode |
| 2 | SQLite cannot serve a real server's five concurrent workers (`StaleDataError` on `auth_session`, `consumer_cursor`) | environment limitation (C) | **Fixed** — harness uses real PostgreSQL, which also makes RLS genuine |
| 3 | **The platform answered before it committed (E2E-001)** — a row created moments earlier is reported missing by the very next request, across `supplier`, `device`, `branch`, `workspace` and `user_account` alike | **product defect — FIXED** | Root cause established by server-side instrumentation (§19.1): the response reached the client **0.3–1.1 ms before the commit**, every time. Fixed by committing inside the route handler; proven 107/150 → **0/150**. The seeder's retry was **removed**, not kept. |
| 4 | My own probe mis-wired its id lists and reported false leaks | test defect (B) | **Fixed** before any conclusion was drawn |
| 5 | **Authentication refused a session the platform had just issued** — `auth_failures_total{reason="session_revoked_or_expired"}` with **zero** `invalid_token`, and `POST /v1/auth/token` answering "Email or password is incorrect" for a user registered a moment earlier | **same defect as 3 — FIXED** | Not a second bug: `auth_session` and `user_account` are rows like any other, so an uncommitted write answers 401 exactly where another answers 404. It looked unrecoverable because each retry re-ran the same losing race. Gone with the fix (0/150 sign-ins refused, 14/14 seedings clean). |
| 6 | My own commit-lag measurement reported "40% of writes uncommitted, 124–313 ms" | test defect (B) | **Fixed** — the load ran as asyncio tasks in the same event loop as the measurement and starved it; re-measured with load in separate processes gives **0/60** |

### 19.1 E2E-001 — the platform answered before it committed

**Root cause, established and fixed.** Every request's transaction was
committed in FastAPI's dependency teardown (`get_session`). The middleware
stack is built on `BaseHTTPMiddleware`, whose `call_next` returns as soon as
the response *starts* — so the answer reached the client while that teardown
was still pending. The platform's own log, with the commit instrumented, says
it plainly and says it every single time:

```
53:28.755048  RESPONSE SENT     status=201 duration_ms=59.24
53:28.756153  ABOUT TO COMMIT   txid=40622
53:28.860199  RESPONSE SENT     status=201 duration_ms=52.05
53:28.860594  ABOUT TO COMMIT   txid=40637
```

The window is 0.3–1.1 ms. A client that acts on its own answer within it —
which a local client does constantly and a real one does sometimes — asks for a
row that has not been committed yet, and is correctly told it does not exist.

**The visible half was never the serious half.** Read-your-writes breaking is
annoying. The dangerous half is that a commit failing *after* the response has
gone cannot change it: the platform would have answered **201 for a write that
never happened**. For a transaction, a settlement or a receipt, that is the one
failure this codebase refuses to tolerate — and it was reachable.

**Why it hid for so long.** It cannot happen in the backend suite: an in-process
ASGI client waits for the whole application to finish, so the ordering is
invisible however wrong it is. It needed a real client, a real server and a
real database — the exact thing this milestone built — and even then it
presented as nine different symptoms across five tables and two status codes.

**The shape that misled the investigation.** A row written and answered 2xx;
the next request from the same principal cannot see it. It fails **closed**,
never with wrong data, and never with another tenant's row — which reads
exactly like a tenancy or row-level-security fault, and is why the first nine
hypotheses all looked plausible. It is **not specific to any entity**
(`supplier`, `device`, `branch`, `workspace`, `user_account`) and needs
**neither load nor concurrency**.

**Ruled out, each with the evidence:**

| Hypothesis | Evidence against |
|---|---|
| Read model / projection lag | The handlers read their own table directly, not a projection |
| Simple sequential race | **0 failures / 40** create→act cycles with background noise |
| Cross-tenant context bleed | **0 leaks, 0 own-row misses / 60** with two tenants under concurrent load |
| GUC scope leaking across requests | Every `set_config` in `core/rls.py` passes `is_local=true` (transaction-scoped) |
| Response returned before commit | **0/60 uncommitted at response, 0/60 follow-up 404s**, load in separate processes (the earlier contrary figure was finding 6 — my own starved event loop) |
| Stale snapshot (REPEATABLE READ) | The engine takes PostgreSQL's default **READ COMMITTED**; no isolation level is set |
| A mid-request commit dropping `SET LOCAL` | The three request-path commits (`api/deps.py`, `modules/auth/service.py`) each immediately precede a raise, so the request ends; `core/idempotency.py` reserves with `flush`, never `commit` |
| Idempotency replay returning a stale response | The seeder sends no `Idempotency-Key`, and `idempotency_guard` returns immediately when the header is absent |
| RLS hiding platform-owned rows from a bound session | The policy explicitly allows `tenant_id IS NULL` (`core/rls.py`) |
| Contention | **9 concurrent seedings, 0 failures** |

Every one of those was ruled out by measurement, and every one was wrong about
where to look. What finally answered it was **asking the server instead of
inferring from outside**: a diagnostic (`session_diagnostics`, off by default)
that logs the transaction's real tenant binding when a request refuses, and
logs the commit it is about to make. The first line it printed ended the
tenancy theory outright — `binding_matches_context=True`, the correct org
bound — and the database said the row was simply **absent**.

**The fix.** Commit inside the route handler, where the response is still ours
to change: `TransactionalRoute` (new) and `IdempotentRoute` (which 32 of the 37
routers already carry) both call `commit_request_session()` before returning.
The write is durable before the answer exists, and a failed commit now becomes
a 500 the caller can act on instead of a lie. `get_session` keeps its teardown
commit as a backstop for non-routed use.

**Proof it is fixed** — the same probes that found it:

| Measurement | Before | After |
|---|---|---|
| `register` answering 2xx with no row (real PostgreSQL) | **107/150** | **0/150** |
| Sign-in refused for a user registered a moment earlier | **12/150** | **0/150** |
| Full seeding runs completing (each ~40 writes) | 1 failure in ~4–8 runs | **14/14** |
| Refusals for the platform to diagnose at all | many | **zero** |

**Proof it stays fixed.** `tests/test_commit_before_response.py` asserts the
ordering on the ASGI `send` channel — a test client would show it as correct
however wrong it is — plus read-your-writes across two requests, plus a
structural guard that **every** mutating route carries a committing route
class, because forgetting one on a new router would reintroduce this silently.
The ordering test was **watched failing** with the fix removed before it was
kept.

**The retry is gone.** The seeder's narrow 404 retry existed to survive an
unexplained defect; with the defect fixed it would only hide the regression it
was written for.

Business rules the harness surfaced (all correct platform behaviour, now
covered): centre readiness requires operating hours plus an **active,
health-reported** scale and an assigned operator; a supplier is a draft until
assigned to a centre and activated; a session refuses to close while
transactions are in flight; `container_identifier` is required on the milk
step; portal sign-in answers 204.

## 20. Defects fixed

Harness defects 1, 2, 4 and 6 above, plus a fifth found in the follow-up: the
mail reader took the newest message and demanded a token be in it, so a
"Welcome to Lacteva" arriving in the same moment failed a seeding the platform
had served correctly. It now scans new messages for one that actually carries a
token.

**Product code was changed once, after the cause was established**: findings 3
and 5 are one defect (E2E-001, §19.1) and it is fixed. The platform was
answering before it committed. Everything else the harness examined, the
platform got right — including every case where the harness was wrong first.

## 21. Tests added

`apps/mobile/test_e2e/operator_journey_e2e_test.dart` (14) and
`apps/admin-portal/e2e/portal-boundary.e2e.test.ts` (6), plus the harness
itself (`run-e2e.sh`, `seed.py`, `mailsink.py`) and
`apps/admin-portal/vitest.e2e.config.ts`.

## 22. Exact test counts

| Suite | Passed | Failed | Skipped | Exit |
|---|---|---|---|---|
| **E2E mobile** (real) | **14** | 0 | 0 | **0** |
| **E2E portal** (real) | **6** | 0 | 0 | **0** |
| **E2E combined** (`run-e2e.sh all`) | **20** | 0 | 0 | **0** |
| Backend pytest (full) | **1,998** passed / **265** skipped (PostgreSQL-gated by design) / **0** failed of 2,263 | **0** |
| Portal vitest (unit, unchanged) | **367** | 0 | 0 | **0** |
| Portal eslint `--max-warnings 0` | clean | — | — | **0** |
| Mobile `flutter test` (unit, unchanged) | **212** | 0 | 0 | **0** |
| Mobile `flutter analyze` | no issues | — | — | **0** |
| Docs validation + xref | pass | — | — | **0** |

Determinism: the mobile E2E suite was run **three consecutive times green**
after the last change, and the portal suite twice; the combined run green.
Earlier non-determinism was chased to its cause (§19) rather than re-run away.

## 23. CI execution results

The harness needs only what this repository already vendors (the `pgserver`
wheel and the checked-in venv), so it is CI-ready as a single command:
`./infra/e2e/run-e2e.sh all`. It is **not wired into a CI workflow in this
milestone** — choosing where it runs, and its time budget, is a pipeline
decision (**TO CONFIRM**), and inventing a workflow file would be inventing
infrastructure.

## 24. Remaining gaps

- **Browser-level E2E** (real DOM, real navigation, real clicks): no driver is
  vendored; adding Playwright means downloading browsers. **TO CONFIRM /
  FUTURE**, with a recommendation to adopt it once someone owns the CI cost.
- **On-device Flutter integration_test**: needs a device or emulator; the
  physical-handset track was deferred by the owner earlier and is unchanged.
- Portal E2E covers the **server** boundary (auth + proxy); page rendering
  against a real server is part of the browser gap above.
- Settlement → payment → receipt and the sales side are covered by the backend
  suite in-process, not yet across a client boundary.
- Nothing from §19 remains open: findings 3 and 5 were one defect, and it is
  fixed and guarded (§19.1).

## 25. Roadmap preservation

Confirmed untouched and unimplemented: AI beyond the existing statistical
deviation flag, anomaly detection, forecasting, advanced analytics, SAP/ERP and
system-of-record integration, enterprise SSO, global identity, federation,
org-to-org relationships, GPS, WhatsApp/SMS providers, automated
scale/analyzer capture, QR scanning, PDF generation, GST/FSSAI fields,
chilling centre, BMC, plant/processing, procurement transport, farmer app,
customer/outlet web portal, advances/loans, payment gateway, enterprise
integrations. No Coming-Soon or Enterprise label was removed or downgraded; no
fake screen, API, reading or integration was created. The claims guards passed
in this milestone's own runs.

## 26. P1-LOCALE-I18N-002 status

**Not started.** The back-office localization wave remains as scoped by
P1-LOCALE-I18N-001 §N.

## 27. Design System V1 status

**Not started.** No visual change of any kind was made in this milestone.

## 28. Future AI / SAP / Enterprise preservation

Unchanged and preserved per §25 and the master roadmap; nothing was
implemented, mocked, or converted into a present commitment.

## 29. Risks

- E2E-001 is fixed, but it is worth naming what it implies: **every write the
  platform has ever acknowledged was acknowledged before it was durable**. No
  evidence of an actual lost write exists — a commit failing in that window
  would have had to coincide with a database fault — but the guarantee was not
  there, and no amount of review had noticed. Anything already in a deployed
  database is unaffected; the exposure was forward-looking.
- The fix depends on every mutating route carrying a committing route class.
  That is now enforced by a test rather than by memory, which is the only
  reason it is a closed risk rather than an open one.
- The harness's value decays if it is not run: unwired from CI, it is a command
  someone must remember (§23).
- E2E suites are slower than unit suites (~40s end to end here) and will grow;
  the small, high-value set should stay small and high-value.

## 30. Recommended next milestone

**P1-SCALE-RACE-001** (concurrency and large-import hardening) or
**P1-LOCALE-I18N-002**. E2E-001 is closed, so the follow-up it would have
needed is not required. One thing it leaves behind is worth a deliberate look
in the scale milestone: the commit is now on the request's critical path, which
is correct but makes write latency honest for the first time — the harness saw
no regression, and a real load profile has never been measured (**TO
CONFIRM**). Design System V1 remains after the functional track, as agreed.

## 31. Verdict

**PARTIAL.** GREEN for the real API boundary — 20 cross-boundary tests, all
passing, deterministic across repeated runs, on real PostgreSQL with RLS
genuinely enforced. Browser-level and on-device E2E are honestly deferred for
missing infrastructure rather than claimed. The one defect it found is a real
product defect, and it is fixed at the root with an executable guard rather
than worked around: **the platform answered before it committed** (§19.1).

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.1 | 2026-08-19 | Engineering | Follow-up investigation closed the open finding. Server-side diagnostics (`session_diagnostics`, off by default) established the root cause: the response reached the client 0.3–1.1 ms BEFORE the commit, because `get_session` commits in FastAPI dependency teardown while the `BaseHTTPMiddleware` stack releases the response as soon as it starts. Both open findings (the intermittent "not found" and the 401 on a just-issued session) were this one defect. Fixed by committing inside the route handler (`TransactionalRoute`; `IdempotentRoute` likewise), proven 107/150 → 0/150 and 14/14 seedings, guarded by `tests/test_commit_before_response.py` (ASGI-level ordering, read-your-writes, and a structural check that every mutating route commits inside its handler), watched failing before being kept. The seeder's masking retry was removed and a fifth harness defect (mail reader took the newest message rather than one carrying a token) fixed (E2E-001). |
| 1.0 | 2026-08-19 | Engineering | Real client↔server E2E harness: one-command environment (real PostgreSQL via the pgserver wheel, real FastAPI under uvicorn, local SMTP sink so the real invitation path delivers a real token), synthetic two-dairy dataset seeded entirely through the platform's own API along the documented onboarding runbook, 14 real mobile tests (auth, RLS/tenancy, full capture, parchi, offline replay, restart, history, session close) and 6 real portal tests (cookie auth, proxy, unauthenticated refusal, cross-tenant refusal, backend-authoritative 403). Tenant isolation verified under concurrent two-tenant load (0 leaks); three harness/environment defects fixed; one intermittent product finding reported open with the investigation trail; no product code changed; browser and on-device E2E deferred as missing infrastructure (P1-E2E-HARNESS-001). |
