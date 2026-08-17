---
id: LACTEVA-PRODUCT-AUDIT
title: Lacteva Product Gap Audit & Master Roadmap
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-17
last-updated: 2026-08-17
related: [DEMO-037-FINAL, ARCHITECTURE-BASELINE-V1]
baseline: ARCH-BASELINE-V1
---

# Lacteva Product Gap Audit & Master Roadmap

Everything below was verified against the repository and the dev deployment on
2026-08-17 — not inferred from the existence of a model, interface or test.
Where a capability is an abstraction waiting for a vendor, it says so.

**The honest headline:** Lacteva has a genuinely strong operational backend and
admin portal (procurement, sales, settlement, billing, routes, reporting — all
real, proven on PostgreSQL, deployed). What it does **not** have is any way for
the three people who make a dairy real — **the farmer, the driver, the paying
customer** — to receive a message, move money, or (for two of the three) even
log in. Every external boundary — SMS, WhatsApp, email, payment gateway, GPS,
hardware — is architecture with no vendor behind it, by explicit prior
decision.

---

## Phase 1 — Inventory: what really exists

Legend: **A** production-ready · **B** implemented but incomplete ·
**C** backend exists, UI/workflow missing · **D** architecture exists, real
integration missing · **E** missing · **F** intentionally deferred.
REAL / TEST / MOCK / NOT-IMPL states what actually executes.

| # | Area | Class | Reality |
|---|------|-------|---------|
| 1 | Multi-tenancy | **A** | REAL. `Organization.id` everywhere, contextvar + PostgreSQL RLS `FORCED` on every tenant table; proven in the 258-test PG proof and live checks every deploy. |
| 2 | Authentication | **A** | REAL. JWT RS256, invitations with one-time tokens via notification channel, customer logins. No tenant self-signup (platform admin creates orgs) — deliberate. |
| 3 | Users / roles / permissions | **A** | REAL. Permission registry (`<module>.<entity>.<action>`), system + named roles, wildcard platform-admin; portal pages `admin/users`, `admin/roles`. |
| 4 | RLS / security | **A** | REAL. ~74 policies with USING **and** WITH CHECK, forced; metadata-derived coverage test; cross-tenant is 404 never 403; webhook HMAC via one shared `core/webhook_security.py`. |
| 5 | Audit | **A** | REAL. One `AuditService`, every operational change recorded; portal `admin/audit`. |
| 6 | Farmers / suppliers | **A** backend / **E** farmer-facing | REAL records: profile, documents, bank accounts, centre placements, QR, contact repair, reachability. **A farmer cannot log in** — no supplier-scoped principal exists (only customer scope does). |
| 7 | Milk collection | **A** | REAL. Sessions, transaction state machine with event log, mobile collection wizard, offline capture with idempotent replay. |
| 8 | Milk quality | **A** (capture is manual) | REAL. Quality-dimension registry, readings on transactions, band-based pricing. Values are typed by an operator; analyzer integration is MOCK (see 44). |
| 9 | Milk rates | **A** | REAL. Rate cards (draft→approve→publish, immutable), pricing matrices by centre/quality band, resolution engine; portal + mobile read views. |
| 10 | Settlements | **A** | REAL. draft→calculated→finalized (immutable), BR-0008…12, late-collection carry-forward (BR-0027), exact Decimal, statements. |
| 11 | Supplier payments | **B/D** | Ledger REAL (allocations, attempts, retry, cancel, outstanding, receipts). **No money moves** — payment methods are metadata; no bank/UPI/M-Pesa rail. |
| 12 | Customers | **A** | REAL. Registration with mandatory plan, statements with brought-forward balance, receivables, portal + read-only customer mobile. |
| 13 | Products | **E** | `product` is a string (`"RAW-COW-MILK"`) on plans/deliveries. No catalog, no second product ever exercised. |
| 14 | Subscriptions (customer standing order) | **A** backend / **C** self-serve | The `DeliveryPlan` IS a subscription: schedule mask, pause window, per-weekday quantities, supersede-per-slot. Managed by staff only; a customer cannot pause/change from their app. |
| 15 | Orders (ad-hoc) | **E** | No one-off order concept. Everything flows from standing orders. |
| 16 | Invoicing | **A** | REAL. Bills built from deliveries, issue→immutable, double-billing impossible, statements, month-end drafting on the scheduler. |
| 17 | Notifications (engine) | **A** | REAL. Event-driven dispatch, recipient directory projection, retry budgets, delivery receipts w/ webhook security, reachability. |
| 18 | SMS | **D** | Real HTTP adapter with retry classification + idempotency keys — TEST-gated (`LACTEVA_MESSAGING_MODE=test`), **no vendor, no credential, zero real messages ever sent**. |
| 19 | Email | **D** (nearest to real) | Real SMTP adapter (STARTTLS, credential redaction, loop-prevention header). Needs only an SMTP host + mailbox — configuration, not code. |
| 20 | WhatsApp | **D** | 57 templates incl. 24 fixed-parameter variants in 4 languages, approval lifecycle, provider mapping. **No BSP, nothing submitted, `ready=0` honestly.** |
| 21 | Messaging templates | **A** | REAL registry + variants + approval audit + portal panel. |
| 22 | Payment providers (SaaS) | **D** | Provider port with `Disabled` + `Test` implementations; hosted-checkout state machine + webhooks proven against the test provider only. |
| 23 | Delivery | **A** | REAL. Record/amend/cancel, scheduled→delivered/skipped/returned/cancelled, billable = delivered only. |
| 24–25 | Routes / stops | **A** | REAL (DEMO-034/35). Ordered stops, PUT-the-order, 404 isolation. |
| 26 | Vehicles | **B** | Registration + label + active only — capacity/maintenance deliberately out (F). |
| 27 | Drivers | **B** | Code/name/phone, nullable `user_id`. A record, not a user experience. |
| 28 | Delivery runs | **A** backend+portal / **C** mobile | planned→in_progress→completed, BR-0028 guard, CAS transitions. Mobile shows the run read-only. |
| 29 | Scheduled generation | **A** | REAL, running in production hourly-poll loop; per-tenant clock, holidays, idempotent, 4-worker safe. |
| 30 | Route-aware generation | **A** (dev-proven) | REAL code path; executed on dev with real data (DEMO-037). Production loop reaching it on its own clock: not yet observed. |
| 31 | Delivery execution | **B** | Operator records outcomes on the round screen (incl. offline). **Driver-as-driver execution is E** — see 35. |
| 32 | Offline mobile | **A** | REAL. Durable queue, idempotency keys honoured server-side, sync engine, conflict surfaces, portal monitor. |
| 33 | GPS / vehicle tracking | **E** | No latitude/longitude anywhere in the tree. |
| 34 | Maps / navigation | **E** | None. |
| 35 | Driver mobile workflow | **E** | Mobile has exactly three experiences: customer, delivery-**operator**, collection-operator. No driver identity, no "my route today", no start/complete from the phone. |
| 36 | Farmer mobile workflow | **E** | No supplier-scoped login. Farmers are subjects of the system, not users of it. |
| 37 | Customer mobile workflow | **B** | REAL but read-only: deliveries, bill with opening balance, receipts. No self-serve pause, quantity change, or payment. |
| 38 | Admin portal | **A/B** | 37 real pages incl. admin/users, roles, audit, settings, configuration, organizations, operations, calendar, subscription. Functional-first; no design system pass beyond shadcn defaults. |
| 39 | Dashboard | **A** | REAL, aggregates from platform figures, failure states honest. |
| 40 | Reports | **A** | REAL. Delivery report (by day/customer/**route**), collection reporting, CSV exports, capped exports that say so. |
| 41 | Analytics (trends/BI) | **E** | Window reports only; no trends, cohorts, or cross-period analysis. |
| 42 | AI | **E** | Nothing. No ML dependency, no model, no assistant. Grep hits are English words in comments. |
| 43 | Hardware / IoT | **D** | Device registry + reported health (API-reported, not device-reported); readiness engine. |
| 44 | Collection machine / analyzer | **E** (mock) | `MockScaleAdapter` / `MockAnalyzerAdapter`, refused in production by guard. No real device protocol. |
| 45 | GPS hardware | **E** | None. |
| 46 | Payment gateway | **E** (abstraction **D**) | No Razorpay/Stripe/Flutterwave/anything. |
| 47–49 | SAP / ERP / Accounting | **E** | Nothing. Not even stubs — correctly. |
| 50 | Bank integrations | **E** | Supplier bank accounts stored as data; no transfer capability. |
| 51 | Third-party API framework | **B** | The seams exist and are proven: provider registries, outbox→consumers, webhook security, per-tenant channel config. No partner-facing API/webhooks product. |
| 52 | DPDPA / privacy | **B** | Tenant data export + offboarding plan + irreversible delete (permission-gated), secret redaction in notifications, audit trail. No consent management, no per-person DSR workflow, no retention policies. |
| 53 | Country configuration | **A** | Currency/timezone/languages per organization; no country branches anywhere (tested). |
| 54 | India support | **A** platform / **D** regulatory | INR, Asia/Kolkata, Hindi throughout. TRAI DLT researched and documented (DEMO-032), not registered. |
| 55 | Kenya support | **A** platform | KES, Nairobi, Swahili throughout. M-Pesa: not integrated. |
| 56 | SaaS subscription / billing | **B** | Trial→entitlement→plan→hosted-checkout state machine REAL; the only providers are Disabled/Test, so no tenant can actually pay. |
| 57 | Monitoring / observability | **A** | REAL and running: Prometheus, Grafana, Loki, Promtail, 9 health probes, structured logs, request ids. |
| 58 | Backup / recovery | **A** | REAL: nightly + pre-deploy logical backups, DR proof, PITR proof (4 targets), offsite round-trip tests, disk-guard timer. |
| 59 | Deployment / CI/CD | **A** | REAL: GH Actions → ECR → `deploy.sh` (migrate→verify→smoke→auto-rollback), PG proof in CI. Single-host; no HA. |
| 60 | Documentation | **A** | 207 governed markdown files, validated + cross-referenced in CI, honest divergence register. |

## Phase 2 — UI/UX audit

### Admin portal (37 pages verified on disk)

| Requested screen | State | Where / gap |
|---|---|---|
| Login, Dashboard | **EXISTS · FUNCTIONAL** | `/login`, `/` |
| Farmers + profile | **EXISTS** | `/suppliers`, `/suppliers/[id]` |
| Collection (+ new) | **EXISTS** | `/transactions`, `/transactions/new` (guided capture wizard) |
| Collection centre | **EXISTS** | `/centers`, `/centers/[id]` |
| Milk quality / Rates | **EXISTS** | `/matrices`, `/rate-cards`, `/resolve` |
| Settlements, Payments | **EXISTS** | list + detail each |
| Customers + profile | **EXISTS** | `/customers`, `/customers/[id]` |
| Deliveries, Reports | **EXISTS** | incl. by-route breakdown (DEMO-037) |
| Routes / Drivers / Vehicles / Runs | **PARTIAL** | One combined `/routes` page. Works, but no route detail page, no per-driver or per-vehicle view. |
| Notifications + Templates | **EXISTS** | one page incl. template registry + approval |
| Users / Roles / Audit / Settings | **EXISTS** | under `/admin/*` |
| Billing (SaaS) | **EXISTS** | `/admin/subscription` |
| **Products** | **MISSING** | no product concept |
| **Customer subscriptions (admin view of plans across customers)** | **PARTIAL** | plans live inside each customer's profile only |
| **Orders** | **MISSING** | no concept |
| **Analytics** | **MISSING** | |
| **Integrations** | **MISSING** | (honest: there is nothing to configure yet) |
| Whole portal | **NEEDS UX PASS** | Functional shadcn/Base-UI; never had a design pass, information architecture grew one DEMO at a time. Never verified in a browser during any milestone since DEMO-028. |

### Mobile — the decisive finding

The app routes by capability into **three experiences: customer, delivery-operator, collection-operator.** Two of the three personas in the phase-2 checklist do not exist at all.

| Persona | State |
|---|---|
| **FARMER** | **MISSING ENTIRELY.** No supplier-scoped login. Every listed farmer screen (collection today, quality, rate, earnings, settlement, payment, history) is E. The *data* for all of it exists server-side. |
| **DRIVER** | **MISSING AS A PERSONA.** The delivery-operator round screen covers: today's list in route order (EXISTS), record quantity/delivered/skipped (EXISTS, offline-capable), sync (EXISTS). Missing: driver login/identity, route list, stop detail, failure reasons, run start/complete from phone, GPS, driver profile. |
| **CUSTOMER** | **PARTIAL, read-only.** Login, dashboard, deliveries, invoice w/ opening balance, receipts: EXISTS · FUNCTIONAL. Missing: pause/resume, quantity change, payment, products, support. |
| Operator (not in the checklist, but real) | Collection wizard, suppliers, centres, settlements, payments, receipts, rates, matrices, offline sync — EXISTS · FUNCTIONAL. |

No mobile screen is mock/static — what exists is wired to the real API.

## Phase 3 — workflow audit: first point a real user is stuck

**A. Farmer:** onboarding → collection → quality → rate → settlement → payment-record all work end-to-end through portal + mobile (proven repeatedly, incl. seeded 30-day histories). **First stop: the farmer themself.** They cannot log in, and the settlement notice that says "your money is ready" cannot actually send (no SMS/WhatsApp vendor). The payment is a ledger entry; no money moves. *A cash-paying dairy with an office notice-board could run this today — but the farmer experiences Lacteva only as a QR code.*

**B. Customer:** onboarding → plan → generation → route → assignment → delivery-record → invoice → payment-record all work. **First stop: the driver's hands.** The person driving the van has no app identity; an operator records outcomes on their behalf. Second stop: the invoice cannot be sent, and payment is recorded, not collected (no UPI/M-Pesa/gateway).

**C. Daily operation:** collection → *(gap)* → delivery planning → routes → delivery → billing → reporting. **First stop: "available milk vs customer demand" does not exist.** There is no inventory/stock concept linking litres collected to litres promised. Planning is standing-orders-only, which is fine for a pilot but the question "can I cover today's round?" is unanswerable in-product.

## Phase 4 — REAL vs DEMO (the external boundary)

| Capability | Real | Test-only | Mock | External dependency | Blocker |
|---|---|---|---|---|---|
| SMS | adapter, retry, idempotency | mode-gate proofs | sandbox provider | **vendor + India DLT registration** | account + credentials |
| WhatsApp | templates, variants, approval lifecycle | full workflow | sandbox | **BSP account + template approval** | vendor selection |
| Email | SMTP adapter complete | full workflow | capture provider | **an SMTP host** | *configuration only* |
| Payments (SaaS + customer) | ledgers, checkout state machine, webhook security | end-to-end vs Test provider | Test/Disabled providers | **gateway (Razorpay/UPI…), M-Pesa** | vendor + account |
| GPS / Maps | — | — | — | phone GPS (free), map vendor | build it |
| Hardware (scale/analyzer) | device registry, reported health | readiness engine | Mock adapters (refused in prod) | real device protocols | device + protocol work |
| AI | — | — | — | model provider (or none) | build it |
| SAP / ERP / Tally / Bank | — | — | — | everything | out of scope for pilot |
| Driver / Farmer as users | — | — | — | none — internal work | build it |
| Customer self-serve | read-only real | — | — | payment rail for pay-in-app | build + vendor |

**Demonstrable today with zero vendors:** the entire operator-side dairy: procurement→settlement, sales→billing, routes→generation→reporting, offline capture, multi-country, on live infra with monitoring and DR. **Requires a vendor/account before it is real:** every message, every rupee/shilling that moves, every map pin.

## Phase 5 — the pilot MVP

Smallest commercially credible pilot = **a cash-or-recorded-payment dairy** (payments recorded by staff, as most cooperatives already operate) + **one real messaging channel** + **a driver who can work from a phone**. Of the 16 required flows, **13 exist today.** Missing:

1. **Driver mobile execution** (MOB-001..004): driver identity → today's run → start/complete → outcomes with failure reasons, on the existing offline queue.
2. **One real messaging channel live** (INT-001/002): SMTP first (config-only), one SMS vendor second. Farmers get settlement notices; customers get bills.
3. **Operator UX hardening pass** (UX-001..003): route detail page, browser-verified critical journeys, navigation IA cleanup — the portal has never been visually verified since DEMO-028.

Explicitly *not* required for pilot: payment gateway (record payments), products/orders, GPS, AI, hardware, analytics.

## Phase 6 — AI

All eight listed capabilities (assistant, NL queries, anomaly detection, demand forecasting, churn, farmer anomaly, route intelligence, OCR): **NOT IMPLEMENTED**. The capability register names them as opportunities; zero code exists.

**Recommendation — one capability: farmer collection anomaly detection** (AI-001). Per-farmer baselines over quantity and quality readings, flagging deviations (sudden volume jumps, fat/SNF drops suggesting dilution). Why this one: the data already exists and is trustworthy (real pipelines, 30-day seeded histories, exact Decimal); it needs **no external vendor** (statistical baselines first, no LLM); it addresses the domain's chronic loss (CAP-0004 names adulteration detection); and it lands where the money is — procurement. An LLM assistant would demo better and help a dairy less.

## Phase 7 — Hardware / GPS

All eleven listed capabilities: **NOT IMPLEMENTED** (device registry + reported-health is the only real piece; adapters are mocks that production refuses).

**Recommendation — phone-GPS delivery confirmation** (HW-001): capture the driver phone's coordinates at the moment a delivery outcome is recorded, stored on the existing offline queue. No device to buy, no tracking infrastructure, no battery-draining background location — and it turns "delivered" into "delivered *here*", which is the dispute that actually reaches a dairy owner. Live tracking, geofencing and analyzer integration come after, in that order.

## Phase 8 — Integrations by tier

| Tier | Integrations | Note |
|---|---|---|
| **CORE MVP** | SMTP email (config-only); one SMS vendor (KE first — no DLT hurdle) | India SMS requires DLT registration — start paperwork early |
| **PILOT** | WhatsApp BSP (templates already approval-ready); UPI (IN) / M-Pesa (KE) for customer payments | |
| **COMMERCIAL V1** | Card gateway; Google Maps/Mapbox; India DLT SMS | |
| **ENTERPRISE / FUTURE** | Tally, SAP, banking rails, ERP, partner API/webhooks | correctly untouched today |

## Phase 9 — Master backlog

Priority: P0 pilot-blocking · P1 pilot-strengthening · P2 V1 · P3 later.
Complexity: S ≤ 1 milestone-day equivalent · M ≈ one DEMO-sized increment · L = several.

| ID | Area | Description | Current state | Pri | Depends | Cx | Phase |
|---|---|---|---|---|---|---|---|
| MOB-001 | Driver | Driver identity: link `driver.user_id` to a real login + `DRIVER` named role (run.read/manage scoped to own runs) | driver record exists, no experience | **P0** | — | M | **MVP** |
| MOB-002 | Driver | "My route today" experience: run banner → own runs, stop detail, start/complete from phone via offline queue | run read-only on mobile | **P0** | MOB-001 | M | **MVP** |
| MOB-003 | Driver | Failure/skip reasons on delivery outcomes (customer away, spoiled, refused) surfaced to the run + report | statuses exist, no reasons | P1 | MOB-002 | S | MVP |
| MOB-004 | Driver | Run completion summary + handover (litres out vs delivered) | — | P1 | MOB-002 | S | MVP |
| MOB-010 | Farmer | Supplier-scoped principal (mirror of DEMO-012 customer scope) + farmer login issuance | customer scope exists as template | P1 | — | M | MVP-stretch |
| MOB-011 | Farmer | Farmer experience: today's collection, quality, rate, running earnings, settlement + receipt | all data server-side | P1 | MOB-010 | M | MVP-stretch |
| MOB-020 | Customer | Self-serve pause/resume + quantity change (plan APIs exist; add customer-scoped mutation w/ guardrails) | staff-only today | P2 | — | M | V1 |
| MOB-021 | Customer | Pay-in-app | read-only bill exists | P2 | INT-010 | M | V1 |
| UX-001 | Portal | Browser-verified pass over the 6 critical journeys (collect→settle, customer→bill, route→run); fix what falls out | never visually verified since DEMO-028 | **P0** | — | M | **MVP** |
| UX-002 | Portal | Route detail page; split drivers/vehicles/runs out of the single `/routes` page | one combined page | P1 | — | S | MVP |
| UX-003 | Portal | Navigation/IA cleanup + empty-state and onboarding hints (grew one DEMO at a time) | functional, unpolished | P1 | — | M | MVP |
| UX-004 | Portal | Design-system pass (tokens, spacing, dashboard hierarchy) | shadcn defaults | P2 | UX-003 | L | V1 |
| UX-005 | Portal | Cross-customer subscriptions/plans admin view | per-customer only | P2 | — | S | V1 |
| CORE-001 | Sales | Product catalog entity (name, unit, price basis) replacing the string constant | string | P2 | — | M | V1 |
| CORE-002 | Sales | Ad-hoc orders alongside standing orders | — | P2 | CORE-001 | L | V1 |
| CORE-003 | Ops | Milk balance: collected vs committed litres per day (first inventory concept) | — | P1 | — | M | MVP-stretch |
| CORE-004 | Logistics | Stop-level timestamps → on-time % (MCL.RTE.01 KPI) | — | P2 | MOB-002 | S | V1 |
| CORE-005 | Sched | Observe the production scheduler taking the route branch on its own clock; close DEMO-036/37 NOT-PROVEN | forced-date only | **P0** | routes on a live tenant | S | **MVP** |
| CORE-006 | Fin | Supplier payment export (bank-file/CSV for cooperative's bank upload) — money moves without an integration | — | P1 | — | S | MVP-stretch |
| INT-001 | Email | Configure real SMTP on dev/prod; flip mode to sandbox→production for email | adapter complete | **P0** | mailbox | S | **MVP** |
| INT-002 | SMS | Select + wire one SMS vendor (KE), sandbox first; real settlement/bill notices | adapter complete, vendor-less | **P0** | vendor acct | M | **MVP** |
| INT-003 | SMS-IN | India DLT registration + template filing (long lead time — start now) | researched (DEMO-032) | P1 | legal entity | M | V1 |
| INT-004 | WhatsApp | BSP selection; submit the 24 variants; record outcomes via existing approval API | everything ready but vendor | P1 | vendor acct | M | V1 |
| INT-010 | Pay | UPI (IN) or M-Pesa (KE) for customer receipts via existing provider port | Test provider only | P2 | vendor acct | L | V1 |
| INT-011 | Pay | Card gateway for SaaS tenant billing | checkout machine ready | P2 | vendor acct | M | V1 |
| INT-020 | Maps | Map view of a route (display only) | — | P3 | vendor key | M | V2 |
| INT-030 | ERP | Tally export (IN accountants) | — | P3 | — | M | V2 |
| INT-031 | ERP | SAP/banking/partner-API | — | P3 | — | L | Future |
| AI-001 | AI | Farmer collection anomaly detection (statistical baselines; flags on portal + digest) | nothing | P1 | — | M | MVP-stretch |
| AI-002 | AI | Demand forecasting for route planning | — | P3 | CORE-003 | L | V2 |
| AI-003 | AI | NL business-query assistant over reports | — | P3 | — | L | Future |
| HW-001 | GPS | Phone-GPS capture on delivery confirmation (proof-of-presence) | no location anywhere | P1 | MOB-002 | M | MVP-stretch |
| HW-002 | GPS | Live driver tracking + map | — | P3 | HW-001, INT-020 | L | V2 |
| HW-003 | IoT | Real weighing-scale protocol (replace mock) for one device model | mock refused in prod | P2 | device | L | V1/V2 |
| HW-004 | IoT | Milk analyzer integration | mock | P3 | HW-003 | L | V2 |
| SEC-001 | Privacy | DPDPA consent + per-person DSR (farmer/customer data export & erasure) on top of tenant-level lifecycle | tenant-level only | P2 | — | M | V1 |
| SEC-002 | Privacy | Retention policies for messages/PII | — | P2 | — | S | V1 |
| REP-001 | Analytics | Trend reports (period-over-period for collections, sales, per-route) | window reports only | P2 | — | M | V1 |
| REP-002 | Analytics | Owner's daily digest (email — depends INT-001) | — | P1 | INT-001 | S | MVP-stretch |
| SaaS-001 | Billing | Real gateway on the existing checkout machine → tenants can pay | Test provider only | P2 | INT-011 | S | V1 |
| SaaS-002 | Growth | Tenant self-signup + guided onboarding | admin-created only | P2 | SaaS-001 | M | V1 |
| OPS-001 | Infra | Second host / restore-drill runbook for pilot SLA (single host today) | single host + DR proofs | P1 | — | M | MVP-stretch |
| OPS-002 | Infra | Alerting rules on the existing Prometheus (scheduler silence, outbox depth, disk) | dashboards only | P1 | — | S | MVP |
| OPS-003 | Infra | Browser-based E2E smoke (Playwright) in CI — closes the "never visually verified" gap permanently | API smoke only | P1 | UX-001 | M | MVP-stretch |

## Phase 10 — execution plan

### Parallel tracks (independence verified against module boundaries)

| Track | Items | Independent because |
|---|---|---|
| **A UI/UX** | UX-001..003 | portal only; API frozen |
| **B Backend/core** | CORE-005, CORE-003, CORE-006 | scheduler/reporting seams already exist |
| **C Mobile** | MOB-001..004 (then 010/011) | new role + screens; server APIs mostly exist |
| **D Integrations** | INT-001 → INT-002 → INT-004 | config + adapters behind existing ports; **vendor lead times are the critical path — start accounts/DLT paperwork on day one** |
| **E AI** | AI-001 | read-only over existing data |
| **F GPS/HW** | HW-001 | rides on MOB-002's queue |
| **G Security** | SEC-001/002 | additive |
| **H Ops** | OPS-001..003 | infra only |

Tracks A, B, D, H can start simultaneously today. C is the long pole of the pilot; E and F slot in behind C without blocking it.

### Releases

**PILOT MVP** — *a real dairy runs a real day; staff record payments*
MOB-001/002 (driver on a phone) · INT-001 (email live) · INT-002 (one SMS vendor) · UX-001/002 · CORE-005 · OPS-002.
Everything else in the pilot column already exists. This is weeks of work, not months — the operator platform is done; the gap is one persona and one vendor.

**PILOT-STRENGTHEN** (during pilot): MOB-003/004/010/011, CORE-003/006, AI-001, HW-001, REP-002, OPS-001/003.

**COMMERCIAL V1** — *money moves, WhatsApp talks, tenants pay*
INT-004 (WhatsApp) · INT-010 (UPI/M-Pesa) · INT-011+SaaS-001/002 · INT-003 (India DLT) · MOB-020/021 · CORE-001/004 · UX-004/005 · SEC-001/002 · REP-001 · HW-003.

**ENTERPRISE V2**: INT-020, HW-002/004, AI-002, INT-030, multi-host HA.

**FUTURE**: AI-003, INT-031 (SAP/banking/partner API), marketplace.

### The one-sentence answer

**Lacteva's operator platform is pilot-ready today; the pilot is unlocked by exactly three things — a driver who can log in, one messaging channel with a real vendor behind it, and a browser-verified UX pass — and the vendor paperwork, not the code, is the critical path.**

---

## Change Log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-17 | Initial audit after DEMO-037; supersedes sequential DEMO planning as the roadmap source. |
