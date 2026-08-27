---
id: LACTEVA-PILOT-MASTER-ROADMAP
title: Lacteva Pilot Master Roadmap — First Indian Dairy Pilot
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-17
last-updated: 2026-08-17
related: [LACTEVA-PRODUCT-AUDIT, DEMO-037-FINAL]
baseline: ARCH-BASELINE-V1
---

# Lacteva Pilot Master Roadmap — First Indian Dairy Pilot

The definitive execution plan, reconciling DEMO-025…037, `LACTEVA-PRODUCT-AUDIT.md`
and the CTO challenge (session deliverable, 2026-08-17; its findings are folded in
here). Every state below was verified against the repository and the dev
deployment — never inferred from a model, interface or test.

**Objective: the first real Indian dairy pilot, live, without a false or fragile
MVP.** Not the most complete system.

---

## 1. The truth table (pilot-relevant capabilities)

States: COMPLETE / PARTIAL / NOT IMPLEMENTED / BLOCKED-EXTERNAL / DEFERRED.
Evidence tags: **REAL** (executes in the product) / **TEST** (proven only in suite/sandbox) / **NOT PROVEN**.

| ID | Capability | State | Evidence | Pilot? | Remaining work | Depends | Pri |
|---|---|---|---|---|---|---|---|
| T-01 | Tenancy, RLS, auth, roles, audit | COMPLETE | REAL — forced RLS on ~74 tables, 258-test PG proof, live checks each deploy | Yes | — | — | — |
| T-02 | Farmer records (profile, docs, bank, placements, QR, **CSV import**) | COMPLETE | REAL — `POST /v1/suppliers/import` exists | Yes | — | — | — |
| T-03 | Collection (sessions, weights, offline wizard, idempotent replay) | COMPLETE | REAL — incl. `milk_type` cow/buffalo/custom on transactions | Yes | — | — | — |
| T-04 | Quality entry (tenant-editable dimensions: FAT, SNF, CLR…) | COMPLETE (manual entry) | REAL — analyzer capture is MOCK, refused in prod | Yes | none for pilot (operator types values) | — | — |
| T-05 | Rate cards + pricing matrices + resolution | PARTIAL | REAL — but `resolution.py` resolves along **one dimension per query**; single-axis bands only | Yes | **Verify target dairy's chart; add two-axis fat×SNF / per-kg-fat only if their chart needs it** | the dairy's chart | **P0** |
| T-06 | Collection slip (farmer parchi) | NOT IMPLEMENTED | no farmer-facing artifact exists; receipts are payment-receipts | Yes | shareable/printable per-collection slip; channel copy when live | — | **P0** |
| T-07 | Settlements (periods, immutability, carry-forward, statements) | COMPLETE | REAL — 10-day Indian cycles fit the flexible periods | Yes | — | — | — |
| T-08 | Supplier payment records + receipts | COMPLETE (recording) | REAL ledger; **no money moves in-product** — by design for pilot | Yes | optional bank CSV export (P1) | — | P1 |
| T-09 | Customer records + standing orders (schedule, pause, per-weekday qty, per-slot) | COMPLETE | REAL — staff-managed | Yes | customer CSV import for onboarding | — | **P0** |
| T-10 | One-date quantity override ("+1L tomorrow") | NOT IMPLEMENTED | per-weekday overrides exist; per-date does not | Important | small addition on plans/generation | — | P1 |
| T-11 | Delivery generation (scheduled, holiday-aware, idempotent, route-aware) | COMPLETE | REAL — route branch executed on dev (DEMO-037); production loop on own clock NOT PROVEN | Yes | observe live once a routed tenant's morning arrives | routes on live tenant | P1 (free) |
| T-12 | Routes / stops / vehicles / drivers / runs (backend + portal) | COMPLETE | REAL — BR-0028, CAS, RLS proven | Yes | — | — | — |
| T-13 | Driver identity & mobile execution | NOT IMPLEMENTED | mobile has customer / delivery-operator / collection-operator experiences only; `driver.user_id` nullable exists; `list_runs(driver_id=…)` exists server-side | Yes | DRIVER role, user↔driver link, own-runs scoping, driver experience on phone | — | **P0** |
| T-14 | Delivery outcome recording, offline | COMPLETE | REAL — offline queue + idempotency keys; **run start/complete is not offline-queued** (runs read-only on mobile) | Yes | fold outcomes into driver experience; start/complete online-first is acceptable | T-13 | **P0** |
| T-15 | Billing → invoice → receivables → payment records → customer receipts | COMPLETE | REAL — no tax fields, which is *correct* for GST-nil fresh milk | Yes | — | — | — |
| T-16 | UPI payment | NOT IMPLEMENTED | none | Important | static-VPA UPI QR / deep link on invoice — **no PSP needed**; operator records payment (exists) | — | P1 |
| T-17 | Reports (day/customer/**route**), dashboard, CSV exports | COMPLETE | REAL | Yes | — | — | — |
| T-18 | WhatsApp | BLOCKED-EXTERNAL | 24 fixed-parameter template variants in 4 langs, approval lifecycle, adapters — **TEST/sandbox only; no BSP, zero real messages** | Yes (channel #1 for India) | BSP account + Meta verification, submit templates, flip mode | **vendor** | **P0 (paperwork) / P1 (landing)** |
| T-19 | SMS (India) | BLOCKED-EXTERNAL | real adapter, TEST-gated; **DLT registration not started** (researched DEMO-032) | Yes (fallback channel) | DLT PE + header + template registration, vendor account | **vendor/regulator** | P0 (paperwork) / P1 (landing) |
| T-20 | Email | PARTIAL | complete SMTP adapter; **needs only a host + mailbox** — configuration, not code | Owner digest, invites | configure + flip mode for email | mailbox | P1 |
| T-21 | Broadcast/announcements ("rate change Monday") | NOT IMPLEMENTED | notification engine is event-driven only | No (phone/WhatsApp-manual for pilot) | compose-and-send to farmer/customer sets | T-18/19 live | P2 |
| T-22 | DPDP consent capture | NOT IMPLEMENTED | tenant-level export/offboard exists; no per-person consent flag/notice | Yes | consent flag + timestamp + notice at supplier/customer creation | — | **P0** |
| T-23 | SaaS charging of tenant #1 | COMPLETE (manual path) | REAL — trial/entitlement + operator activation (DEMO-026/27); Test provider only for self-serve | Yes | none — invoice manually, activate via operator | — | — |
| T-24 | Onboarding a real dairy (runbook + data-in) | PARTIAL | supplier import REAL; customer import missing; no runbook | Yes | customer CSV import + written onboarding runbook | — | **P0** |
| T-25 | Portal UX verified in a browser | NOT PROVEN | no milestone since DEMO-028 visually verified; tests + API only | Yes | browser pass over the 6 critical journeys, fix fallout | — | **P0** |
| T-26 | GPS / vehicle tracking / maps | NOT IMPLEMENTED | zero coordinates in the tree | **No** | — (see §7) | — | P2/P3 |
| T-27 | AI | NOT IMPLEMENTED | no ML dependency, no model anywhere | No | — (see §6) | — | P1-stretch |
| T-28 | Monitoring, backups, DR, PITR, CI/CD | COMPLETE | REAL and running; single host | Yes | alert rules; restore drill for pilot SLA | — | P1 |
| T-29 | Hindi localization (portal + mobile) | COMPLETE | REAL — en/hi (+ar/sw) catalogs both clients | Yes | — | — | — |
| T-30 | Weighing scale / analyzer integration | NOT IMPLEMENTED | mock adapters, refused in production | No | — (V1 first device) | device | P2 |

## 2. The pilot business cycle — what works today

`ONBOARDING → COLLECTION → QUALITY → RATE → SLIP → ORDER → ROUTE → DRIVER →
DELIVERY → CONFIRMATION → BILLING → PAYMENT RECORD → SETTLEMENT/REPORTING`

**Working end-to-end today (REAL):** onboarding (farmer import; customers by hand),
collection with quality and cow/buffalo type (offline-capable), rate resolution
(single-axis), settlement, customer standing orders, route/run planning,
delivery generation (incl. route-aware), outcome recording (offline-capable, by
an *operator*), billing → receivables → payment records → receipts, reports
incl. by-route, Hindi UI, monitoring/DR underneath.

**Genuinely missing for the cycle:** the **slip** (T-06), the **driver as a
person** (T-13/14), **any live message** (T-18/19/20), **rate-chart fit
confirmation** (T-05), **customer import + runbook** (T-24), **consent**
(T-22), **browser verification** (T-25). That is the whole gap. Nothing else in
the cycle is missing.

## 3. Critical path

**A — must exist before pilot:** T-05 (verify; build only if needed), T-06 slip,
T-13/14 driver, T-22 consent, T-24 onboarding kit, T-25 UX pass, pilot tenant
configuration, **and at least one live channel** (WhatsApp preferred — see B).
**B — parallel from day 1:** Meta/WhatsApp BSP verification, DLT registration,
SMTP mailbox — *external clocks; start immediately*. Engineering tracks A/B/C/H
(§10) run concurrently.
**C — during/after pilot start:** T-10 one-date override, T-16 UPI-QR, owner
digest w/ anomaly flags, route detail page, alerting, Playwright, GPS-at-
confirmation, milk balance, bank CSV, restore drill, observe scheduler live.
**D — V1:** farmer app, customer self-serve + pay-in-app, UPI PSP/gateway,
self-serve SaaS billing, product catalog, cash reconciliation, broadcast, Tally,
scale integration, DSR/retention, trends, design pass, stop timestamps.
**E — V2/Future:** live GPS + maps, analyzer, forecasting, HA, assistant,
SAP/ERP/banking/partner API.

Verification of the suspected list: all confirmed as critical **except**
"UPI/payment recording" (recording already COMPLETE; UPI-QR is P1 not P0) and
GPS/browser-device caveats per §5/§7. Nothing on the suspected list was missing
from the repository analysis.

## 4. Minimum pilot UI/UX scope

**Exists & pilot-ready after a verification pass (no redesign):** login,
dashboard, suppliers(+import), transactions + capture wizard, rate cards/
matrices/resolve, settlements, customers, deliveries+report, routes/runs page,
payments/receipts/receivables, admin (users/roles/audit/settings), mobile
collection wizard + operator round + customer portal + offline sync.

**Must be built:** driver mobile experience (T-13/14) · collection slip render
(portal + share) · customer CSV import screen or CLI (T-24) · consent line on
supplier/customer forms (T-22).

**Functional but needs the P0 pass (fix, don't redesign):** the six journeys —
collect→settle, customer→bill, route→run→report — verified in a real browser
(never done since DEMO-028), route detail split (P1), empty states/nav (P1).

**Explicitly NOT pilot scope:** visual design system, farmer app, customer
self-serve, analytics screens, integrations screens, broadcast UI.

## 5. Driver / vehicle / logistics

Remaining for the driver (everything else listed in the brief already exists):
1. **DRIVER named role** + `driver.user_id` linkage + own-runs scoping
   (`list_runs(driver_id=…)` already exists server-side).
2. **Driver experience** in the mobile Experience router: today's assigned run →
   ordered stops with customer info (RunView already carries all of it) →
   record outcomes (reuses the existing offline queue and idempotency keys) →
   start/complete run. *Honest note:* run status change is currently **not**
   offline-queued (runs are read-only on mobile); pilot ships start/complete
   as online-first, outcomes fully offline — acceptable for one driver, queued
   transitions are a P1 follow-up.
3. Failure/skip **reasons** — P1, folded into the same screen.
4. Delivery **proof** — the recorded outcome + timestamp is the pilot's proof;
   GPS-at-confirmation is the P1 stretch; photo proof is V1 if the dairy asks.

**ARE WE CURRENTLY TRACKING VEHICLES? — No.** What exists: a vehicle *registry*
(registration, label, active, centre) and run *association* (which van took
which round, enforced by BR-0028). No location of any kind exists.
**GPS is not required for the first pilot** (one known driver, one van, ~50
stops); the pilot operates on association + outcomes. V1 architecture: phone-GPS
samples captured at delivery events, batched through the existing offline
queue into a tenant-owned `location_sample`-style store — ingestion API, no
live map. V2: continuous tracking, dedicated trackers, geofencing, maps.

## 6. AI

Data that exists today: per-farmer collection history (quantity, fat/SNF/CLR
readings, milk type, per-session), delivery/skip patterns per customer,
settlement/payment ledgers. Quality: exact-Decimal, timestamped, tenant-clean —
good. Volume at pilot scale: small (20 farmers).

| Candidate | Data | Model needed? | Rule-based works? | Pilot value | Effort |
|---|---|---|---|---|---|
| Collection anomaly (volume jump, fat/SNF drop → dilution) | YES | no — baselines/z-scores | **yes** | High (adulteration is the domain's chronic loss) | S/M |
| Customer churn/pause prediction | yes | statistical | yes | Low at 50 households (owner sees it) | M |
| Route/delivery anomaly | yes | — | yes | Low at 1 route | S |
| Payment/collection anomaly | yes | — | yes | Modest | S |
| Demand forecast | needs milk-balance first | yes | partly | Low at pilot scale | L |

**Recommendation: rule-based collection anomaly flags inside the owner's daily
digest** (P1, with the digest). No ML, no vendor, no new data. Sold as
"adulteration indicators", graduating to statistical baselines in V1 when real
pilot data accumulates. Everything else defers.

## 7. Hardware / GPS strategy

**PILOT: no hardware.** Phone-only; even phone-GPS is a stretch item.
**V1: phone sensor only** — GPS-at-confirmation (proof-of-presence), then the
**first real device: the weighing scale** (typing weights is the trust gap at
the collection centre; one device model, one protocol).
**V2: optional/dedicated** — continuous phone tracking → dedicated vehicle
trackers, geofencing, milk analyzer, cold-chain IoT.
Location design when it comes: event-driven samples (not continuous), through
the existing offline queue, tenant-owned table, ingestion API only — no map
dependency until V2.

## 8. Integrations

| Integration | Exists? | Pilot? | Form | External dep | Phase |
|---|---|---|---|---|---|
| WhatsApp (BSP) | adapters+templates TEST | **Yes — channel #1** | API via BSP | Meta verification + BSP | **Pilot** (paperwork P0) |
| SMS (India DLT) | adapter TEST | fallback | vendor API | DLT registration | Pilot-landing/V1 |
| Email (SMTP) | adapter REAL, unconfigured | owner digest | config only | a mailbox | Pilot |
| UPI (QR, no PSP) | — | important | render QR/deep-link | none | Pilot (P1) |
| UPI PSP / gateway | provider port, Test only | no | API | vendor acct | V1 |
| Tally / accounting | — | no | **file export sufficient** | none | V1 |
| Weighing machine | mock | no | device protocol | device | V1/V2 |
| Milk analyzer | mock | no | device protocol | device | V2 |
| GPS hardware / maps | — | no | API/vendor key | vendor | V2 |
| SAP / ERP / banking / partner API | — | no | — | — | Enterprise/Future |

No generic integration framework is to be built; the existing ports (providers,
outbox, webhook security) are sufficient seams.

## 9. India-specific gaps

| Item | Classification | Note |
|---|---|---|
| Cow/buffalo milk type | **already supported** | `milk_type` on transactions |
| FAT/SNF quality entry | **already supported** | tenant-editable dimensions |
| Two-axis fat×SNF / per-kg-fat chart | **PILOT BLOCKER *if* the dairy's chart needs it** | verified single-axis today; ask for their chart first |
| Collection slip / parchi | **PILOT BLOCKER** | the farmer trust artifact |
| Tax fields | not needed | fresh milk GST-nil; revisit with product catalog |
| Rate-change communication | PILOT IMPORTANT → V1 broadcast | manual for pilot |
| One-day quantity override | PILOT IMPORTANT | commonest doorstep request |
| Onboarding/import | **PILOT BLOCKER** | customer import + runbook |
| Cash reconciliation (driver) | V1 | monthly office billing suffices for pilot |
| Customer activation (SaaS, manual) | already works | operator activation |
| DPDP consent at onboarding | **PILOT BLOCKER** (cheap) | flag + notice |
| WhatsApp templates | ready, blocked external | submit on BSP day |
| DLT | PILOT paperwork, V1 landing | start now |

## 10. Parallel tracks

| Track | Tasks (IDs §13) | Start now? | Depends | Effort |
|---|---|---|---|---|
| **A Mobile/Driver** | P0-MOB-001/002 (+P1-MOB-003) | **yes** | nothing | 3–6 d |
| **B Business/Pricing** | P0-BIZ-001→(002), P0-BIZ-003, P1-BIZ-004/005 | **yes** (001 is a conversation) | dairy's chart for 002 | 2–7 d |
| **C UI/UX** | P0-UX-001, P1-UX-002 | **yes** | nothing | 2–4 d |
| **D Messaging/Vendor** | P0-INT-001 paperwork; P1-INT-002/003/004 landings | **yes (paperwork)** | vendor clocks | 1–3 d eng when cleared |
| **E Integrations** | P1-BIZ-005 UPI-QR, V1 items | after invoice render known | — | small |
| **F AI** | P1-REP-001 digest+flags | after INT email | INT-004 | 1–2 d |
| **G HW/GPS** | P1-HW-001 stretch | after MOB-002 | MOB-002 | 1–2 d |
| **H Sec/Ops** | P0-SEC-001, P0-OPS-001/CFG, P1-OPS-002/003/005 | **yes** | nothing | 2–4 d |

A, B, C, D-paperwork and H have **zero mutual dependencies** and run as
parallel sessions (the marketing-site session already proves the model).

## 11. Execution strategy — replacing per-feature DEMOs

**PHASE 0 (done):** audit + this roadmap; scope frozen to §13.
**PHASE 1 — pilot blockers** (tracks A/B/C/H in parallel): batch related changes
per track; full gates (suite, PG proof, mutation checks) per *merge*, not per
feature; CHANGELOG entries instead of FINAL reports.
**PHASE 2 — pilot operational flow:** seeded end-to-end dairy day on dev.
**PHASE 3 — UX/device verification:** browser + a real handset.
**PHASE 4 — external landings:** WhatsApp/SMS/email live as vendors clear.
**PHASE 5 — production hardening + onboarding:** restore drill, alerting,
runbook executed against the real tenant.

**DEMO-style checkpoints only where reality is proven — four of them:**
1. *Driver's day* — a driver runs a route end-to-end on a phone (dev).
2. *Dairy's day* — full business cycle demo, browser-verified.
3. *First real message* — WhatsApp/SMS live in production, one real recipient.
4. *Go-live readiness* — backup/restore drill, consent, onboarding executed.

## 12. Time estimates

Unit: engineering day ≈ 2–4 focused agent sessions. Vendor clocks dominate.

| Scenario | Engineering | Calendar to pilot-ready | Assumes |
|---|---|---|---|
| **FASTEST REALISTIC** | 8–10 d | **~3 weeks** | chart fits single-axis (BIZ-002 skipped); WhatsApp verification clears in ~2 wks; 3 parallel tracks; SMS lands post-go-live |
| **REALISTIC** | 12–15 d | **4–6 weeks** | BIZ-002 needed; normal vendor pace; browser pass finds fixable fallout |
| **CONSERVATIVE** | 18–20 d | **~8 weeks** | pricing rework + DLT drag + rework from device testing |

Parallelism is what compresses calendar: serially the same work is 2–3× longer.
The critical path is **Meta/DLT paperwork and the dairy's rate chart — not code.**

## 13. Final master backlog

| ID | Track | Feature | Why | Current | Remaining | Depends | Effort | Phase |
|---|---|---|---|---|---|---|---|---|
| **P0-MOB-001** | A | Driver identity: DRIVER role, user↔driver link, own-runs scoping | no driver can log in | role/link fields exist; no experience | role, linkage, scoping, session | — | 1–2 d | 1 |
| **P0-MOB-002** | A | "My Route Today": assigned run, ordered stops, outcomes (offline), start/complete | the pilot's one big build | server APIs exist; outcomes offline-ready | new mobile experience | MOB-001 | 2–4 d | 1 |
| **P0-BIZ-001** | B | Rate-chart fit check with the target dairy | discover mismatch before the sale, not during | engine is single-axis (verified) | a conversation + decision | dairy | 0 d | 1 |
| **P0-BIZ-002** | B | Two-axis fat×SNF / per-kg-fat pricing (conditional) | Indian charts often need it | not supported | matrix/resolution extension | BIZ-001 says yes | 2–4 d | 1 |
| **P0-BIZ-003** | B | Collection slip (parchi): render + share/print; channel copy later | the farmer trust artifact | nothing farmer-facing | slip artifact from existing transaction data | — | 1–2 d | 1 |
| **P0-UX-001** | C | Browser-verified pass over 6 critical journeys + fixes | never visually verified since DEMO-028 | tests/API only | run journeys in a browser; fix fallout | — | 2–3 d | 1/3 |
| **P0-OPS-001** | H | Pilot onboarding kit: customer CSV import + runbook | 50 households won't be typed | supplier import exists | customer import + written runbook | — | 1–2 d | 1 |
| **P0-SEC-001** | H | DPDP consent flag + notice at supplier/customer creation | store phones lawfully | absent | flag, timestamp, notice text | — | 0.5–1 d | 1 |
| **P0-CFG-001** | H | Pilot tenant configuration (org, centre, rates, SMTP, messaging plan) | the actual dairy | seeder exists as pattern | runbook execution | OPS-001 | 0.5 d | 5 |
| **P0-INT-001** | D | **Vendor paperwork**: Meta/WhatsApp BSP verification + DLT PE registration + mailbox | the calendar's critical path | not started | forms, not code | external | ~0 eng | 1 (day 1) |
| P1-INT-002 | D | WhatsApp live: BSP wired, 24 templates submitted, approvals recorded, mode flipped | channel #1 India | everything but vendor | adapter config + submissions | INT-001 clears | 1–2 d | 4 |
| P1-INT-003 | D | DLT SMS live | fallback channel | adapter ready | vendor wiring | DLT clears | 1 d | 4 |
| P1-INT-004 | D | Email live (SMTP config) → owner digest channel | cheap day-one win | adapter complete | configuration | mailbox | 0.5 d | 4 |
| P1-BIZ-004 | B | One-date quantity override ("+1L tomorrow") | commonest doorstep request | per-weekday only | per-date override in plans/generation | — | 1 d | 2 |
| P1-BIZ-005 | E | UPI QR (static VPA + amount) on invoice/statement | payment without a PSP | none | QR render; recording exists | — | 0.5–1 d | 2 |
| P1-MOB-003 | A | Failure/skip reasons on outcomes | doorstep reality | statuses only | reason field through queue | MOB-002 | 0.5–1 d | 2 |
| P1-REP-001 | F | Owner daily digest + rule-based collection anomaly flags | the AI pilot story, vendor-free | data exists | digest job + rules | INT-004 | 1–2 d | 2/4 |
| P1-UX-002 | C | Route detail page; split drivers/vehicles/runs | operator ergonomics | one combined page | portal page | — | 1 d | 3 |
| P1-OPS-002 | H | Alert rules (scheduler silence, outbox depth, disk) | pilot on-call | dashboards only | Prometheus rules | — | 0.5 d | 5 |
| P1-OPS-003 | H | Playwright E2E smoke in CI | closes the visual gap permanently | none | browser suite | UX-001 | 1–2 d | 3 |
| P1-OPS-004 | B | Observe production scheduler take the route branch unaided | last NOT-PROVEN of DEMO-036/37 | forced-date only | watch one morning | routed tenant | 0 d | 5 |
| P1-OPS-005 | H | Restore drill + pilot SLA runbook | single host today | DR proofs exist | execute drill, write runbook | — | 1 d | 5 |
| P1-HW-001 | G | Phone-GPS capture at delivery confirmation | proof-of-presence, stretch | no coordinates anywhere | capture + store via queue | MOB-002 | 1–2 d | 2 |
| P1-CORE-001 | B | Milk balance: collected vs committed | "can I cover the round?" | none | derived figure + tile | — | 1–2 d | 2 |
| P1-CORE-002 | B | Supplier payout bank CSV export | money moves without integration | ledger exists | export format | — | 0.5 d | 2 |
| P2-MOB-004 | A | Farmer app (supplier scope + experience) | farmer engagement | customer-scope as template | scope + screens | — | 3–5 d | V1 |
| P2-MOB-005 | A | Customer self-serve pause/quantity | reduce phone calls | staff-only APIs exist | scoped mutations + UI | — | 2–3 d | V1 |
| P2-MOB-006 | A | Customer pay-in-app | collections | read-only bill exists | needs PSP | INT-005 | 2–3 d | V1 |
| P2-INT-005 | E | UPI PSP / gateway | automated reconciliation | Test provider only | provider impl | vendor | 3–5 d | V1 |
| P2-INT-006 | G(SaaS) | Self-serve SaaS billing + signup | scale beyond customer #1 | manual path works | gateway + flows | INT-005 | 2–4 d | V1 |
| P2-BIZ-006 | B | Product catalog (milk types, value-added) | beyond single product | string constant | entity + wiring | — | 2–4 d | V1 |
| P2-BIZ-007 | B | Cash collection & driver-day reconciliation | doorstep cash reality | none | handover ledger | MOB-002 | 2–3 d | V1 |
| P2-BIZ-008 | D | Operator broadcast/announcements | weekly dairy reality | event-driven only | compose+send | channel live | 1–2 d | V1 |
| P2-INT-007 | E | Tally-importable export | the accountant's question | CSV exports exist | Tally format | — | 1–2 d | V1 |
| P2-HW-002 | G | Weighing-scale integration (one model) | the trust gap at the centre | mock refused in prod | device protocol | device | 3–5 d | V1 |
| P2-SEC-002 | H | Per-person DSR (export/erase) + retention | DPDP maturity | tenant-level only | person-level flows | — | 2–3 d | V1 |
| P2-REP-002 | F | Trend reports (period-over-period) | owner insight | window reports only | queries + UI | — | 2 d | V1 |
| P2-UX-003 | C | Design-system pass | commercial polish | shadcn defaults | tokens, hierarchy | — | 3–5 d | V1 |
| P2-CORE-003 | B | Stop timestamps → on-time KPI | MCL.RTE.01 | none | capture + report | MOB-002 | 1 d | V1 |
| P3-HW-003 | G | Live GPS tracking + map view | fleet visibility | none | continuous ingest + map vendor | HW-001 | L | V2 |
| P3-HW-004 | G | Milk analyzer integration | auto quality | mock | device protocol | HW-002 | L | V2 |
| P3-AI-002 | F | Demand forecasting | planning | needs CORE-001 history | model | CORE-001 | L | V2 |
| P3-OPS-006 | H | Multi-host HA | enterprise SLA | single host | infra | — | L | V2 |
| P4-AI-003 | F | NL assistant over reports | convenience | none | LLM vendor | — | L | Future |
| P4-INT-008 | E | SAP / ERP / banking / partner API | enterprise | none | per-partner | — | XL | Future |

Deferred without loss (traceable to audit IDs): orders engine (behind
P1-BIZ-004), maps display, Arabic-market work, marketplace, cold-chain IoT.

## 14. What we do next

**The next 5 implementation actions — nothing else:**
1. **P0-INT-001 (today, non-engineering):** start Meta/WhatsApp business
   verification + BSP shortlist, file DLT Principal-Entity registration,
   provision an SMTP mailbox.
2. **P0-BIZ-001 (today, a conversation):** obtain the target dairy's actual
   rate chart; decide whether P0-BIZ-002 exists.
3. **P0-MOB-001 + P0-MOB-002 (Track A):** driver identity and "My Route Today".
4. **P0-UX-001 (Track C, parallel):** the browser-verified pass over the six
   critical journeys.
5. **P0-BIZ-003 + P0-OPS-001 + P0-SEC-001 (Tracks B/H, parallel small items):**
   slip, onboarding kit, consent.

**Stop building:** messaging depth, template features, SaaS checkout machinery,
logistics polish — frozen until their vendors exist.
**Do not touch yet:** payment gateways, farmer app, GPS tracking/maps, product
catalog, broadcast, analytics, anything ERP/SAP, new hardware.
**Build in parallel:** Tracks A, B, C, H immediately; D is paperwork now,
engineering when vendors clear.
**External work starting now, outside engineering:** Meta verification, BSP
account, DLT registration, SMTP mailbox, the dairy's rate chart + farmer/customer
data sheets, and the dairy's own UPI VPA for QR billing.
**Earliest realistic pilot date (cooperating customer):** **~3 weeks** from
start in the fastest scenario; **4–6 weeks** is the honest planning number —
gated by WhatsApp verification and the rate-chart answer, not by code.

---

## Change Log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-17 | Definitive pilot execution plan; reconciles DEMO-025…037, the product audit and the CTO challenge; supersedes both as the planning source. |
