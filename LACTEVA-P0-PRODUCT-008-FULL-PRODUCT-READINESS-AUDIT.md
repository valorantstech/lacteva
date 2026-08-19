---
id: LACTEVA-P0-PRODUCT-008-FULL-PRODUCT-READINESS-AUDIT
title: Full Product Readiness Audit
type: reference
status: Approved
version: "1.0"
owner: Product & Engineering
created: 2026-08-19
last-updated: 2026-08-19
related: [LACTEVA-PRODUCT-CAPABILITY-VISIBILITY-AUDIT, LACTEVA-MASTER-PRODUCT-ROADMAP, LACTEVA-P0-GO-LIVE-001-FIRST-DAIRY-EXECUTION-CONTROL-SHEET, LACTEVA-DAIRY-ECOSYSTEM-AND-OPERATING-MODEL, LACTEVA-GO-LIVE-READINESS]
baseline: ARCH-BASELINE-V1
---

# Lacteva — Full Product Readiness Audit (P0-PRODUCT-008)

**Audit only — nothing was implemented, no code/UI/schema/API changed, no
synthetic feature or demo data created.** Source of truth: the actual code and
tests, inspected fresh (four parallel read-only audit passes: portal — every
one of 40 shipped pages read in full; mobile — all 25 lib files ~10.5k lines
read in full; test surface — ~120 backend + 26 portal + 15 mobile test files
mapped to workflows; backend surface — 262 endpoints / 34 routers / 70
registered permissions), plus fresh executions of all three test suites.
Earlier milestone claims were **not** trusted; physical-device proof is held
strictly to the P0-PILOT-004 list.

## 1. Executive summary

The backend is deep, adversarial and green. The portal is **two portals**: the
~28 modern pages are genuinely strong (four-state discipline, server
pagination, `<Money>` everywhere, confirm-with-consequences on money actions),
while 7 legacy pages (rate-cards, matrices, resolve, receipts, reports, sync,
notifications) predate the pattern. The mobile app's field surfaces are proven
— but the audit found **three genuine mobile P0 defects that block internal
UAT** (operator screens hang forever on a transport error; a 401 mid-flow is
an unrecoverable dead end; offline replay permanently strands captured work on
an expired token). The deepest structural finding: **no automated test
anywhere crosses a real client↔server boundary** — every client test mocks the
network. And the most surprising inversion: mobile over-serves back-office
admin (full rate-card/matrix editing on the phone, never used at a centre)
while under-serving the counter — **the parchi, whose audience stands at the
phone, does not exist on mobile.**

**Verdicts:** Backend **GREEN** · Portal **GREEN for UAT / AMBER for a real
dairy** · Mobile **AMBER (3 P0 fixes first)** · Overall internal UAT
**AMBER — ready after the three mobile P0 fixes; real-dairy readiness
additionally requires the P1 register.**

## 2. Current product inventory (classification against code + tests)

- **Backend:** 26 modules, 262 endpoints across 34 routers, 70 permissions —
  the full lifecycle **PROVEN** (per-domain test evidence in §8's map): milk
  collection + sessions + parchi, pricing (matrix/calculator/resolution,
  publish immutability), settlement (period guards, late-collection BR-0027),
  payments (PG-race-proven allocation), receipts (41 tests, real PDF for
  receipts), customers/sales (paisa-reconciled chains), delivery/logistics
  (scheduler under real 4-worker concurrency), calendar/business-date,
  offline-sync replay (28 tests), identity/auth (pen-test style), authz/audit,
  org/tenancy incl. **data export + offboarding (implemented and tested** —
  `TenantExport` route; delivery CSV export), subscription (entitlement;
  payment provider **disabled by design**), notifications ("never claims
  delivered"), relay/outbox/projections, reporting aggregates, RLS (36
  PG tests), DR/backup/PITR. **COMING SOON (seams only):** hardware adapters
  (mock-refused in prod), WhatsApp/SMS send (no provider), receipt-PDF-on-
  mobile, payment gateway. **ENTERPRISE/FUTURE:** per the roadmap — nothing
  found mislabelled.
- **Portal:** 40 shipped pages, all real and API-backed, zero stubs. 28 modern
  **PROVEN/consistent**; 7 legacy **PARTIAL** (pattern debt, §4); roadmap page
  inert by test.
- **Mobile:** 25 screens/workflows classified A–F in §5 — field surfaces
  (login, routing, capture wizard incl. offline, driver round) **A: proven on
  glass**; most office screens **B: test-only**; sync UI screens **D**;
  `PlatformStatusScreen` dead code; nothing fake.

## 3. End-to-end functionality matrix (synthetic lifecycle)

The synthetic lifecycle is executed by the suites that ran green in this
audit, not asserted from documents:

| Step | Proven by (synthetic data only) |
|---|---|
| Organization → branch → centre → staff (invite→accept→grant→login) | `test_dev_onboarding_rehearsal.py` (real API, real token capture) |
| Farmer records → collection → weight → quality → rate → **parchi** | rehearsal final leg + `test_procurement_e2e.py`, `test_collection_slip(+pg)` (parchi byte-identical to engine pricing) |
| Settlement → payment → receipt (one unbroken money chain) | `test_settlement_late_collection.py::test_money_is_exact_from_collection_through_to_the_receipt` |
| Outlet → order → route → driver → delivery → billing → reconciliation | `test_sales_workflow`, `test_dairy_reconciliation` (to the paisa), `test_driver_execution`, scheduler suites |
| Reporting → audit | `test_sales_reporting`, reporting aggregation, audit search/tenancy tests |
| Permissions / invalid ops / inactive centre / wrong org / cross-tenant | rehearsal access matrix; `test_multitenancy` (three isolation layers); RLS PG suite (36 tests, CI-gated); authz tests |
| Multi-role / multi-centre user | rehearsal grants |
| Offline / queue / sync / replay / idempotency | `test_offline_sync` (28 tests: out-of-order, conflicts, resumed batches, authz never bypassed) + mobile offline trio |
| Stale session / API errors / validation | backend auth suites (rotation, forged/expired tokens) + portal 401→login test; **mobile stale-session = defect D-2** |

## 4. Portal UI/UX audit (40 pages read; concrete, evidenced)

**No P0 — the portal is UAT-usable as-is.** Highlights of the register
(full file:line detail preserved in §10):

- **P1 scale defects:** the capture wizard's supplier `<select>` caps at 100
  (`transactions/new/page.tsx:188`) — a 500-farmer dairy cannot record milk
  for farmer #101 from the portal; the same 100-cap poisons filter dropdowns
  and **name maps** on transactions/settlements/billing/deliveries/payments
  (UUID fragments shown to clerks); suppliers list shows false "none"
  activity beyond the top-100; **reports silently truncate to 50 rows** and
  sort money via `Number()`.
- **P1 money-contract violation:** `matrices/page.tsx:431-433,465-467` send
  `unit_price: Number(price)` — floats at the one surface that sets the milk
  price, against the platform's Decimal-string rule every other page obeys.
- **P1 irreversibles without confirm:** rate-card **Publish/Archive**, matrix
  **Delete**, band **Delete** are one-click — in contrast to the exemplary
  confirm flows on invoices/settlements/payments.
- **P1 Indian-locale gap:** catalogs exist (355 keys × en/hi/ar) but **27
  pages never import i18n**; shared chrome (DataTable pagination, "Loading…",
  sign-in/out, CsvImport) is hardcoded English — a Hindi operator gets a Hindi
  sidebar and English screens.
- **P2:** legacy-page pattern debt (no PageHeader/LoadingState, errors without
  `role="alert"`, unlabeled filters), raw timestamp `slice(0,19)` bypassing
  `datetime.tsx`, **UTC 30-day windows** on suppliers/centers (the DEMO-019
  bug pattern re-introduced), Kenya-centric placeholders on an India-bound
  product, RTL-unsafe physical alignment on three tables, `<Money>` missing on
  the subscription page, terminology drift (Transactions/Collections,
  bill/invoice, supplier/farmer, Centre/center).
- **Held as the bar:** the four-state `Load<T>` discipline, money-spelled
  confirm dialogs, URL-seeded filters, honest empty states.

## 5. Mobile audit (all 25 lib files read; physical proof held to P0-PILOT-004)

Classification (A on-glass / B test-only / C implemented-unverified / D
partial / E missing / F future) — full table in the audit working papers;
essentials:

- **A (on glass):** login (both personas), persona routing, centres browse,
  capture wizard all 6 steps **incl. full offline capture + durable queue +
  409 convergence**, driver home/start/record-delivered (with real phone-call
  interruptions).
- **B (tests only):** center form/readiness/today, supplier detail+QR, rate
  cards, matrices, resolution, settlements, payments, receipts, notifications,
  delivery round, customer home/bill, driver skipped/returned via UI.
- **C (no test, not on glass):** suppliers list/form, center detail actions,
  centres search/pagination/FAB.
- **D (partial):** sync screen/OfflineBanner/conflict detail (engine tested,
  widgets untested); receipt download (clipboard placeholder by design);
  driver sheet lacks "cancelled".
- **E (missing for pilot scope):** **the parchi** (wizard completion never
  calls the slip endpoint — no slip number, no share); transaction
  history/detail for dispute resolution; sign-out on a shared handset;
  session-close UI (**missing on both clients** — platform endpoint has no
  caller anywhere); operator-persona Hindi strings.
- **F (honestly labelled):** QR scanning, real hardware, push vendor, PDF.
- **Dead code:** `PlatformStatusScreen`; `assignRateCard*` client methods
  (catalog-without-callers pattern).
- **The inversion worth naming:** back-office admin is over-served on mobile
  (full pricing lifecycle editing, B-tested, never needed at a centre) while
  the counter interaction — parchi in the farmer's hand — is under-served.

## 6. Backend/API audit

Full suite executed fresh on this machine (SQLite in-memory stack):
**exit code 0 — true green, captured as `PYTEST-RC=0`, not a piped tail** —
2,260 tests collected across 117 files (run twice, both exit 0; the
PostgreSQL-gated subset skips locally by design and is CI-enforced).
262 endpoints / 34 routers; permissions are
`Annotated[Principal, Depends(require_permission("…"))]` aliases (70 registry
entries; the spot-checked pattern holds, incl. `TenantExport` for
`organization.data.export` — a permission **with** a real implementation).
Errors are RFC-9457; money is Decimal end-to-end (the one client-side float
violation is portal matrices, §4); idempotency is a route class; outbox +
consumer cursors are test-proven under real concurrency. **Honestly stated:**
~24 PostgreSQL-gated files (RLS 36 tests, exact aggregation, DR/PITR, payment
and subscription races) **skip on this machine** — correct locally, enforced
in CI by `LACTEVA_REQUIRE_POSTGRES=1` + `postgres.yml` (a missing URL is a
collection **error**, so a silent skip cannot go green). No unguarded route,
no dead endpoint group, and no backend defect was found in this audit.

## 7. E2E lifecycle audit

In-process E2E against the real API exists and is strong (rehearsal +
procurement + reconciliation + one-test money chain). **What does not exist:
any automated test crossing a real client↔server boundary.** No browser E2E
(no Playwright/Cypress anywhere); no Flutter `integration_test/`; every portal
and mobile test mocks fetch/HTTP. A backend serializer drift ships with all
three suites green and breaks the first real click — exactly where UAT lives.
P0-PILOT-004 was one manual session, not a repeatable harness.

## 8. Test coverage audit

~120 backend files (deep, adversarial: pen-test auth, PG races, DR-as-
evidence) · 26 portal files (mocked jsdom; **8 pages with no test at all:**
matrices, rate-cards(+id), receipts, reports, resolve, sync, admin/
configuration, admin/operations) · 15 mobile files (every screen at least
smoke-covered; wizard-beyond-step-1 thin). Ranked gaps: **P0** — no browser
E2E; no mobile-against-real-backend test; mobile 401 mid-flow untested (and
unhandled). **P1** — large imports (`MAX_IMPORT_ROWS = 500`, portal does no
chunking — a real 2,000-farmer CSV fails outright); no two-operator collection
race test; no pause/resume/process-death test (no `WidgetsBindingObserver` in
the app); portal `/sync` + `/reports` untested. **P2** — remaining untested
admin pages; rendered-Hindi/RTL page tests; client-side multi-centre
switching; deep pagination walks.

## 9. Defect register (genuine, evidenced — none fixed in this milestone)

| ID | Defect | Where | Severity |
|---|---|---|---|
| D-1 | Operator screens catch only `ApiException`; a `SocketException` leaves an eternal spinner, refresh silently rethrows | `centers.dart:145-160` + 8 sibling screens (driver/deliveries got the generic catch; the offline-first persona didn't) | **P0** |
| D-2 | No 401/session-expiry handling anywhere on mobile: token memory-only, no re-login route, no sign-out (`revokePush` has zero callers); raw problem-detail shown | `api.dart:25-26`, `push.dart:96` | **P0** |
| D-3 | Offline replay treats every 4xx except 409 as terminal conflict — an expired-token 401 permanently strands a morning's captured deliveries | `offline/offline_client.dart:384-391,426-434` | **P0** |
| D-4 | Matrices POST money as JS floats (`Number(price)`) against the Decimal-string contract | `matrices/page.tsx:431-433,465-467` | P1 |
| D-5 | 100-row caps: wizard supplier select, filter dropdowns, name maps (UUIDs shown), suppliers false "none" activity | `transactions/new/page.tsx:188` et al (§4) | P1 |
| D-6 | Reports truncate to 50 rows silently; money sorted via `Number()` | `reports/page.tsx:94-100,46-59` | P1 |
| D-7 | Rejection reason hardcoded `'Rejected at review'` — printed on the farmer's official parchi | `collection_wizard.dart:129-131` | P1 |
| D-8 | Offline wizard has no input bounds (gross>tare>0, plausible FAT/SNF) — garbage queues silently, surfaces hours later | `collection_wizard.dart:98-121` | P1 |
| D-9 | App restart while offline locks the operator out (token/session never persisted; session.dart:69's cache claim is untrue) | `home.dart:65-91` | P1 |
| D-10 | UTC 30-day windows on suppliers/centers (IST off by 05:30 — the fixed DEMO-019 pattern re-introduced) | `suppliers/page.tsx:49-57`, `centers/page.tsx:50-58` | P1 |
| D-11 | One-click irreversibles: rate-card Publish/Archive, matrix/band Delete | `rate-cards/page.tsx:289-298`, `matrices/page.tsx:184-191,439-441` | P1 |
| D-12 | Session-close endpoint has no UI caller on any client — end-of-shift discipline impossible | `routes.py:1775` vs both clients | P1 |
| D-13 | Sticky "believed offline": one transport failure queues everything until a manual sync tap | `offline_client.dart:42-44,450-452` | P1 |
| D-14 | Dead code/surface: `PlatformStatusScreen`; `assignRateCard*` methods; unused customer-catalog keys (catalog-without-callers again) | `main.dart:82`, `api.dart:369-383`, `customer_portal.dart:516-556` | P2 |

## 10. UI/UX gap register (portal) — P1: 100-caps + name maps; reports
truncation; i18n thinness (27 pages + shared chrome); pricing-page confirms;
matrices floats. P2: legacy-page states/labels/`role="alert"`; timestamp and
UTC-window drift; Kenya placeholders; RTL physical alignment (3 tables);
subscription `<Money>`; capped sublists on customer detail; terminology
glossary (Transactions/Collections · bill/invoice · supplier/farmer ·
Centre/center); copy nits. (Full file:line register held in §4 sources.)

## 11. Mobile completion register — P0: D-1, D-2, D-3. P1: parchi on the
completion step (call the existing slip endpoint + share); transaction
history/detail; offline input bounds (D-8); rejection reasons (D-7); operator
Hindi strings (l10n covers driver/customer only) + wire the existing unused
customer keys; restart-while-offline (D-9); sync-on-resume/connectivity
listener (D-13); driver quantity/notes on outcomes; permission-aware toolbar
(hide what `session.can()` refuses); sign-out. P2: distinct toolbar icons;
`decimal: true` keyboards; overflow protection beyond the driver card; wizard
back/cancel path; live queue counts; pull-to-refresh on details; driver
"cancelled" outcome. FUTURE (labelled): QR scan, hardware, push vendor, PDF.

## 12. Priorities

- **P0 (blocks internal UAT):** D-1, D-2, D-3 — all mobile, all small, all in
  the transport/auth layer.
- **P1 (before a real dairy):** portal scale caps + reports truncation +
  matrices floats + pricing confirms + i18n; mobile parchi + history + input
  bounds + rejection reasons + restart/auto-sync + Hindi; large-import
  chunking (500-row cap vs real files); one real-boundary E2E harness
  (browser + Flutter integration smoke); concurrent-capture race test.
- **P2 (polish):** the registers' remainder.

## 13. Implementation roadmap (sequence for the NEXT milestones — nothing implemented here)

1. **P0 mobile transport/auth fix-pack** (D-1 generic catch + retry UI; D-2
   401 → re-auth flow + sign-out; D-3 auth-retryable replay classification) +
   regression tests.
2. **P1 portal scale pack** (searchable supplier picker replacing capped
   selects; name-map strategy; reports pagination; matrices Decimal strings;
   publish/delete confirms).
3. **P1 mobile counter pack** (parchi on completion + share; transaction
   list/detail; offline bounds; rejection reasons; restart persistence;
   sync-on-resume).
4. **P1 locale pack** (portal shared chrome + top operator pages onto the
   catalogs; mobile operator-persona keys; wire unused keys).
5. **P1 E2E harness** (one Playwright smoke over login→capture→parchi against
   a real backend; one Flutter integration_test driving capture against a real
   backend; import-chunking + race tests).
6. **P2 polish** per registers.

## 14. Future roadmap preservation (verified this audit)

All 24 named future capabilities re-verified as preserved and correctly
labelled — AI (deviation flag only), SAP/ERP, GPS, payment gateway (provider
`disabled`), hardware automation/connector (discovery-gated), scale/analyzer,
QR scanning, PDF, messaging/WhatsApp/SMS (adapter, no provider), GST/FSSAI
fields, anomaly/forecasting, chilling/BMC, plant, procurement transport,
farmer app, outlet web portal, enterprise SSO, global identity, federation,
org-to-org, advanced analytics, advances/loans. The `/roadmap` page remains
inert (pinned by tests); the claims guards passed in this audit's fresh runs
(portal 27 guard tests inside 345; mobile 24 inside 170); no fake screen,
API, reading, or data exists anywhere the audit looked.

## 15. Internal UAT readiness verdict

| Surface | Verdict | Basis |
|---|---|---|
| A. Backend | **GREEN** | Fresh full suite green (true exit code); adversarial depth; PG suites CI-enforced |
| B. Portal | **GREEN for internal UAT · AMBER for real dairy** | No P0; P1 scale/i18n/confirm register stands |
| C. Mobile | **AMBER** | Three P0 defects (D-1..D-3) must be fixed first; field core proven on glass |
| D. Overall internal UAT | **AMBER** | Ready once the mobile P0 fix-pack lands; real-dairy readiness additionally needs the P1 registers. **Not claimed real-dairy ready.** |

## 16. Exact next milestone

**P0-PRODUCT-009 — Mobile P0 fix-pack (D-1, D-2, D-3) with regression tests**,
then the P1 sequence of §13. No go-live activity, no future capability, no
real dairy until the P0s are closed and internal UAT has actually run.

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-19 | Product & Engineering | Full current-product readiness audit: four parallel read-only inspection passes (40 portal pages, 25 mobile lib files, ~160 test files, 262-endpoint backend surface) + fresh suite executions; inventory, E2E matrix, portal and mobile registers, 14-item defect register (3 mobile P0s), coverage gaps (no real client↔server boundary automation), priorities and implementation sequence, roadmap preservation re-verified, verdicts GREEN/GREEN-AMBER/AMBER/AMBER. Audit only — no code, UI, schema, API, or data changed (P0-PRODUCT-008). |
