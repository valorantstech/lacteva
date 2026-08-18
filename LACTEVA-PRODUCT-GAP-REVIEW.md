---
id: LACTEVA-PRODUCT-GAP-REVIEW
title: Product Gap Review — the Shortest Credible Path to a Live Dairy
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-PILOT-MASTER-ROADMAP, LACTEVA-PILOT-READINESS-GATE, LACTEVA-REGULATORY-APPLICABILITY-AUDIT, LACTEVA-HARDWARE-INTEGRATION-SPEC, LACTEVA-PILOT-ONBOARDING-PACK]
baseline: ARCH-BASELINE-V1
---

# Product Gap Review (post-P0-PILOT-003)

Audit only. Every claim verified against the repository and the live DEV
deployment (`main-1da4e81`) on 2026-08-18 — not recited from old roadmaps.
Optimized for the shortest credible path to *"one real Indian dairy operates
Lacteva for 7 consecutive days"*, not for generating engineering work.

**Executive verdict, up front: the software is done enough. Every remaining
item on the pilot's critical path is a piece of paper, a phone, or a
person — not code.** The engineering backlog that remains is real but
belongs *during* or *after* the pilot, and most of it is gated on facts only
a live dairy can supply.

---

## 1. Core dairy operations — verified line by line

| Capability | Status | Evidence (this session) |
|---|---|---|
| Farmer/supplier onboarding | **DONE** | `/suppliers/import` API + portal CSV UI, per-row validation, QR/code/phone identity |
| Collection centre | **DONE** | Centres, operating hours, readiness checks (scale = blocking), operators |
| Cow/buffalo | **DONE** | Separate products on one rate card; differentiated pricing proven end-to-end |
| Morning/evening shifts | **DONE** | Session labels; on the parchi; per-shift capture proven |
| Quantity | **DONE** (kg) | Gross/tare/net, validated, source-attributed. **Litres = DATA-DEPENDENT** conditional increment |
| FAT / SNF | **DONE** (captured); SNF **not priced** (MVP-001, deliberate) | Grid/deduction pricing = DATA-DEPENDENT on the actual chart |
| Rate calculation | **DONE** (engine) / **DATA-DEPENDENT** (configuration) | FAT bands per product, effective windows, centre scoping, INR |
| Collection transaction | **DONE** | State machine, event log, snapshot, immutability, idempotency, offline replay |
| Parchi/slip | **DONE** | Numbered (SLP-), printable, shareable, bilingual; verified live; lazy mint proven on PG |
| Settlement | **DONE** | STL- series, free cycle dates, finalization, immutability |
| Customer/outlet | **DONE** | CRUD + CSV import with duplicate guard + inline standing orders |
| Standing orders | **DONE** | Plans with rates, calendar suppression, pause/resume |
| Route / delivery | **DONE** | Routes/stops/vehicles/drivers/runs; route-aware generation proven under concurrency |
| Billing / payments | **DONE** | INV-/CPY-/CRC- series, receivables, "who owes money" |
| Reports | **DONE** (12 report endpoints) | daily/by-centre/by-supplier/trend/by-rate/settlements/sales/receivables/payments/chain/operational-status/dashboard |
| Reconciliation | **DONE** (procedure) | Onboarding pack §5: parchi→settlement→payment and plan→delivery→invoice, on paper, byte-traceable |

## 2. Collection hardware

Per LACTEVA-HARDWARE-INTEGRATION-SPEC (P0-HW-001), verified in code:

- **Exists in software**: `weight_source`/`quality_source` on every reading;
  `WeightCaptured`/`QualityCaptured` events carry the source; device registry
  (`scale`/`milk_analyzer`/`printer`/… with lifecycle + health) wired into
  readiness; mock adapters production-refused twice, their dataclasses the
  adapter contract.
- **Remains to integrate**: the Centre Connector (read-assist) + one real
  scale/analyzer adapter each + optional ESC/POS printing — **all gated on
  the §11 discovery checklist** (device photos, interfaces, captured raw
  output). ~2–3 weeks *with devices in hand*.
- **Manual for the pilot**: everything — PSP-0007 Basic/Standard profile is
  a first-class equipment class, not a degraded mode.
- **V1**: connector MVP (P0-HW-002) after discovery; auto-capture later.

## 3. Delivery / driver model — correct as built

Verified: the driver persona holds only `logistics.run.execute`; the portal
actively refuses drivers and points them to the app; runs are own-scoped
(another driver's run is a 404); outcomes go through the run-scoped endpoint
into the same delivery engine; deliveries are dairy→outlet B2B movements
generated from standing orders and routes. **No door-to-door farmer
collection is modeled anywhere. No GPS exists anywhere, and nothing depends
on it.** The model matches the business.

## 4. UI/UX

- **Visually verified (P0-UX-001, real Chrome on DEV)**: login, dashboard,
  suppliers, capture wizard, transactions (+ slip, verified live in
  P0-BIZ-003), customers, deliveries, settlements, reports, role refusals.
- **Unverified**: mobile-browser portal (tooling froze; never claimed);
  physical Android anything; Hindi end-to-end visually; Arabic RTL (not
  pilot-relevant).
- Operator/driver/customer workflows: usable per tests and (desktop) per
  browser walkthrough; **usability on the actual operator's device is
  exactly what the handset day proves** — nothing known broken.

## 5. Mobile

Exists and tested (widget tests at 320×568 where overflow fails, offline
queue replay-once proofs, live HTTPS driver day from tests): operator capture
wizard, driver run experience, delivery operator, customer experience (not a
pilot dependency). **Not tested on physical glass — the pilot's one
validation debt.** APK built against DEV; script in the onboarding pack §6.
V1/future: slip sharing from the operator app; auto-capture UI.

## 6. AI

- **Implemented (P0-PILOT-003)**: supplier FAT/SNF deviation flag — the one
  MVP. Statistics against the supplier's own last-20 same-milk-type
  baseline; event-only; never blocks; never on the parchi.
- **Documented only**: operator anomaly, collection-pattern rings, payment
  anomaly, forecasting — all wait for real pilot data volume, correctly.
- **Data availability**: complete (supplier/operator/centre/shift/quality/
  quantity/price/decision + timing metrics per transaction).
- **Verdict**: nothing further until the pilot generates real baselines.
  No vendor needed for anything on this list.

## 7. Hardware readiness matrix

| Capability | Existing software | Manual fallback | Integration required | Vendor/device dep. | Pilot req.? | V1? |
|---|---|---|---|---|---|---|
| Weighing scale | Source attribution, registry, blocking readiness check | **Yes — first-class** | Connector + adapter | Yes (device + raw output) | **No** | Yes |
| FAT/SNF analyzer | Same + plausibility bounds + deviation flag | **Yes** | Connector + adapter | Yes | **No** | Yes |
| Receipt printer | Browser slip-print + shareable text | **Yes** (paper/shared) | ESC/POS via connector | Yes | **No** | Yes |
| Future centre devices (QR/RFID/camera) | Registry categories exist | n/a | Undefined | Yes | **No** | Later |
| Phone-based operations | Full (operator + driver, offline) | n/a | None | Handset for validation | **Yes — validation only** | — |

## 8. Third-party integrations

| Integration | Boundary exists | Implementation | Vendor dep. | Pilot? | Verdict |
|---|---|---|---|---|---|
| Email (SMTP) | Yes | **Real** (`SmtpEmailProvider`) | Mailbox only | Optional | Config during pilot |
| SMS | Yes (`HttpSmsProvider`, gateway-agnostic) | Adapter real, no vendor | **DLT weeks** | No | V1; start paperwork if dairy wants it |
| WhatsApp | Yes (`HttpWhatsAppProvider` + template registry/approval lifecycle) | Adapter real, no BSP | **BSP weeks** | No | V1 |
| Payment gateway | Sandbox provider + webhook ledger (subscriptions) | No real PSP | Yes | No | V1/commercial |
| SAP/ERP | UUID-boundary architecture ready; nothing built | None | Enterprise-dep. | No | FUTURE (unless an enterprise signs) |
| GPS/maps | **Nothing, deliberately** | n/a | n/a | **No** | Optional future |
| Hardware | §2/§7 | Mocks only (prod-refused) | Yes | No | P0-HW-002 |

## 9. Regulatory (per P0-REG-001, re-affirmed)

- **A. Relevant before pilot**: dairy's FSSAI license *existing* + scale's
  Legal Metrology certificate — **file copies at onboarding, zero code**;
  processor clause + privacy notice + consent line (paperwork, in the pack);
  Maharashtra floor price — human rate-card review step.
- **B. Operational practice**: hygiene, cold chain, record-keeping (Lacteva
  *is* the record system already).
- **C. Optional**: supplier FSSAI-reg note; LM metadata on device registry.
- **D. Not Lacteva's**: licensing itself, stamping itself, GST registration,
  farmer registration, everything animal/environmental/labour.
- V1 code items: FSSAI number + GSTIN/HSN/bill-of-supply on customer
  documents. **No compliance module, ever, per standing decision.**

## 10. Commercial lifecycle

DAIRY→FARMER→COLLECTION→QUALITY→RATE→SETTLEMENT→CUSTOMER→ORDER→ROUTE→
DELIVERY→BILLING→PAYMENT→REPORTING: **every stage exists and is tested.**
Genuinely missing commercial capabilities (all V1+, none pilot-blocking):
farmer **advances/loans** against settlements (BR-0011 revision — the most
commercially significant gap for Indian dairies), ad-hoc/variable customer
ordering beyond standing orders + driver-recorded actuals, multi-dairy SaaS
self-onboarding, subscription billing to *dairies* (exists in code — needs a
payment vendor), processing/inventory (milk in vs product out) — a genuine
V2 domain.

## 11. Analytics

Exists: 12 report endpoints incl. trend and rate-band distribution, plus the
live dashboard. Pilot-sufficient. V1: supplier trend view (data exists —
surface it), deviation-flag summary report, route efficiency, outlet
profitability. FUTURE: forecasting, ML anomaly dashboards.

## 12. Security / operations

Proven: RBAC registry + persona separation, RLS FORCED (cross-tenant 404,
PG-proven per table), audit log + event trails + immutable snapshots,
idempotency (incl. the RLS rebind fix), TLS + HttpOnly sessions, nightly
backup + off-site S3 + watchdog + restore drill (all live-verified;
DEV retention deliberately trimmed to 2 days, production keeps 30),
deploy with pre-backup/verify/smoke/auto-rollback, disk guard.
**Gaps, honestly**: single-host DEV doubles as pilot environment (accepted
consciously for the pilot; V1 needs a separated production host); monitoring
is health-probe + journal + markers, no external pager (acceptable at pilot
scale, V1 item); DR runbook exists and restore is drilled, but a full
host-loss rebuild has never been rehearsed end-to-end (V1).

## 13. Market readiness — the non-theoretical answer

**Today, a dairy that signs can use**: farmer/outlet onboarding by CSV in
the portal; every collection captured with cow/buffalo, shift, weight,
FAT/SNF, priced by their own chart once configured; a numbered bilingual
parchi printed or shared per farmer; settlements on their own cycle with
statements; standing orders, routes, a driver phone that works offline;
invoices, payments, receivables; 12 reports and a live dashboard; nightly
verified off-site backups.

**They must provide**: the rate chart (photographed), farmer list, outlet
list with prices, settlement rules, FSSAI license copy, scale's LM
certificate, signatures on the pilot agreement.

**We must configure**: the org (one command sets India defaults), centres,
logins, imports, the rate card (with the floor check), SMTP if wanted.

**Must be physically tested**: one day, two Android handsets — driver run +
operator capture + Hindi + airplane-mode. Nothing is known broken; nothing
mobile is proven on glass.

**Cannot yet be done**: litres-based buying (if their chart demands it —
bounded increment); FAT×SNF grid pricing (same); automated farmer
SMS/WhatsApp (vendor paperwork); instrument-connected capture (discovery
first); advances/loans in settlements.

## 14. Master gap table

| ID | Area | Capability | Status | Phase | Blocker type | Dependency | Size | Order |
|---|---|---|---|---|---|---|---|---|
| G-01 | Business data | Four dairy artifacts loaded & rate card configured | DATA-DEPENDENT | PILOT | Business | Dairy | Config (hours) | 1 |
| G-02 | Mobile | Physical-handset validation day | PHYSICAL-VALIDATION | PILOT | Device | Any Android | 1 day | 2 |
| G-03 | Legal | Signed agreement + notice/consent in use | MISSING (paperwork) | PILOT | Legal | Dairy + Phoenix | Days | 1 |
| G-04 | Pricing | Litres support | DATA-DEPENDENT | PILOT-conditional | Engineering | Chart says litres | ~3–5 d | 3 |
| G-05 | Pricing | FAT×SNF grid / SNF deduction | DATA-DEPENDENT | PILOT-conditional | Engineering | Chart shape | ~1 wk | 3 |
| G-06 | Messaging | SMTP mailbox for statements | MISSING (config) | P1 | Config | Mailbox | Hours | 4 |
| G-07 | Hardware | Discovery checklist answered | HARDWARE-DEPENDENT | P1 | Discovery | Dairy's devices | 1 visit | 4 |
| G-08 | Hardware | Centre Connector MVP (P0-HW-002) | MISSING | V1 | Engineering | G-07 | 2–3 wk | 6 |
| G-09 | Messaging | SMS via DLT | VENDOR-DEPENDENT | V1 | Vendor | DLT reg. | Weeks lead | 5 |
| G-10 | Messaging | WhatsApp via BSP | VENDOR-DEPENDENT | V1 | Vendor | BSP | Weeks lead | 5 |
| G-11 | Regulatory | FSSAI no. + GST fields on documents | MISSING | V1 | Engineering | None | ~2–3 d | 6 |
| G-12 | Commercial | Advances/loans vs settlements | MISSING | V1 | Engineering + BR-0011 | Dairy practice (§E q.15) | ~2 wk | 7 |
| G-13 | Analytics | Supplier trends + deviation summary | PARTIAL (data exists) | V1 | Engineering | Pilot data | ~1 wk | 7 |
| G-14 | Ops | Separate production host + external alerting | PARTIAL | V1 | Ops | Budget | ~1 wk | 6 |
| G-15 | Mobile | Slip share from operator app | MISSING | V1 | Engineering | None | ~2–3 d | 7 |
| G-16 | AI | Post-pilot anomaly analytics | FUTURE | P2 | Data volume | Pilot | — | 8 |
| G-17 | Integrations | Payment gateway, SAP/ERP | FUTURE | P2/P3 | Vendor/enterprise | Customer demand | — | 9 |
| G-18 | Product | Processing/inventory domain | FUTURE | P3 | Product | Market | — | 10 |

## 15. Prioritization

- **P0 (before the first dairy)**: G-01, G-02, G-03; G-04/G-05 only if the
  chart demands them. **Nothing else.**
- **P1 (during/immediately after)**: G-06, G-07, G-13 (deviation summary at
  least), start G-09/G-10 paperwork if the dairy wants farmer messaging.
- **P2 (V1 commercial)**: G-08, G-11, G-12, G-14, G-15, G-16.
- **P3 (future)**: G-17, G-18, GPS-optional, Arabic pass, multi-pilot SaaS
  automation.

### Recommended next 3 milestones

1. **P0-PILOT-004 — Go live**: execute the onboarding pack against the real
   dairy's artifacts + the handset day + first reconciled settlement.
   Engineering only if G-04/G-05 trigger. *Gated on the dairy, not on us.*
2. **P0-HW-002 — Centre Connector MVP** *(only after the discovery visit
   returns raw output)*: read-assist connector + the one scale and one
   analyzer the pilot actually owns + printer if confirmed.
3. **V1-COM-001 — Commercial hardening**: advances/loans (BR-0011 revision),
   FSSAI/GST document fields, SMTP + first messaging vendor, supplier trend
   analytics, separated production host.

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Consolidated post-P0-PILOT-003 gap review: 13 area audits, master gap table, prioritization, next 3 milestones. |
