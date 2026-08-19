---
id: LACTEVA-P1-E2E-HARNESS-001
title: Real Client↔Server E2E Harness
type: reference
status: Approved
version: "1.0"
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
activated; a session refuses to close with work in flight); and it surfaced one
**unresolved intermittent defect** (§19) that no unit suite could have seen.

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
| 3 | **Intermittent 404 on a just-created supplier** — roughly one seeding run in four, `POST /v1/suppliers/{id}/centers` reports "supplier not found" for a row created moments earlier | **OPEN — cause not established** | Ruled out: projection lag (the handler reads the table directly), simple sequential race (**0/20** in isolation), cross-tenant context bleed (**0 leaks / 0 misses** under concurrent load). The seeder retries once and prints `E2E-WARNING`; the retry keeps the harness usable and **must not be read as the cause being understood**. Recommended as the first item of a follow-up investigation. |
| 4 | My own probe mis-wired its id lists and reported false leaks | test defect (B) | **Fixed** before any conclusion was drawn |

Business rules the harness surfaced (all correct platform behaviour, now
covered): centre readiness requires operating hours plus an **active,
health-reported** scale and an assigned operator; a supplier is a draft until
assigned to a centre and activated; a session refuses to close while
transactions are in flight; `container_identifier` is required on the milk
step; portal sign-in answers 204.

## 20. Defects fixed

Harness defects 1, 2 and 4 above. **No product code was changed in this
milestone** — the platform behaved correctly in every case the harness
examined, and the one open finding (§19.3) is reported rather than patched.

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
- §19.3 remains open.

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

- The open finding (§19.3) is masked by a visible retry; if it also occurs in
  production traffic it would surface as a spurious "not found" to a real
  operator. It should be investigated before the pilot handles concurrent load.
- The harness's value decays if it is not run: unwired from CI, it is a command
  someone must remember (§23).
- E2E suites are slower than unit suites (~40s end to end here) and will grow;
  the small, high-value set should stay small and high-value.

## 30. Recommended next milestone

**Investigate §19.3** (short, focused — the harness now reproduces it), then
either **P1-SCALE-RACE-001** (concurrency and large-import hardening, which is
the same neighbourhood) or **P1-LOCALE-I18N-002**. Design System V1 remains
after the functional track, as agreed.

## 31. Verdict

**PARTIAL.** GREEN for the real API boundary — 20 cross-boundary tests, all
passing, deterministic across repeated runs, on real PostgreSQL with RLS
genuinely enforced. Browser-level and on-device E2E are honestly deferred for
missing infrastructure rather than claimed. One open defect is reported, not
hidden.

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-19 | Engineering | Real client↔server E2E harness: one-command environment (real PostgreSQL via the pgserver wheel, real FastAPI under uvicorn, local SMTP sink so the real invitation path delivers a real token), synthetic two-dairy dataset seeded entirely through the platform's own API along the documented onboarding runbook, 14 real mobile tests (auth, RLS/tenancy, full capture, parchi, offline replay, restart, history, session close) and 6 real portal tests (cookie auth, proxy, unauthenticated refusal, cross-tenant refusal, backend-authoritative 403). Tenant isolation verified under concurrent two-tenant load (0 leaks); three harness/environment defects fixed; one intermittent product finding reported open with the investigation trail; no product code changed; browser and on-device E2E deferred as missing infrastructure (P1-E2E-HARNESS-001). |
