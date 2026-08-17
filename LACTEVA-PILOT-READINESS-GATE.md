---
id: LACTEVA-PILOT-READINESS-GATE
title: Pilot Readiness Gate — What Actually Prevents a 7-Day Pilot
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-PILOT-MASTER-ROADMAP, LACTEVA-PRODUCT-AUDIT, LACTEVA-COLLECTION-HARDWARE-AUDIT, LACTEVA-RATE-CHART-QUESTIONNAIRE, LACTEVA-HARDWARE-INTEGRATION-SPEC]
baseline: ARCH-BASELINE-V1
---

# Pilot Readiness Gate (P0-PILOT-001)

**The question:** if a real Indian dairy agrees to pilot Lacteva tomorrow,
what exactly prevents us from operating their business for 7 days?

**The answer, up front:** almost nothing in engineering. The genuine gate is
**four business artifacts** (rate chart, farmer list, outlet list, settlement
rules), **one operational installation** (a scheduled backup on the host —
the scripts are proven, the cron does not exist), **one legal minimum**
(a DPDPA notice and consent line — zero code exists today), and **one
validation debt** (no screen of either mobile experience has ever been seen
on a physical handset). Messaging vendors, hardware, AI, and SAP block
nothing. Audit only; nothing was modified by this milestone.

---

## 1. Real pilot personas

| Persona | Logs in? | Needs a phone? | Software | Receipt |
|---|---|---|---|---|
| **A. Dairy owner/manager** | Yes | No | **Browser portal** (desktop) — dashboard, rate cards, settlements, payments, receivables, reports | — |
| **B. Collection-centre operator** | Yes | Yes (any Android with Chrome, or the Flutter app) | **Mobile app** capture wizard (offline-capable) or portal capture | issues the parchi |
| **C. Delivery driver** | Yes | Yes | **Mobile app** driver experience only (`logistics.run.execute`; portal actively refuses them and says so) | — |
| **D. Customer / B2B outlet** | **No** | No | **None for the pilot.** Deliveries are recorded by the driver; invoices/receivables live in the portal; statements can be printed/shared. (A customer mobile experience exists but is not a pilot dependency) | printed/shared invoice |
| **E. Farmer / supplier** | **No** | No | **None, ever, for the pilot.** | **Parchi** — printed from the portal or shared as bilingual text (P0-BIZ-003) |

Two logins per centre (operator) plus one per driver plus one or two office
logins is the entire identity footprint. Nobody without a login is blocked
from anything they need.

## 2. End-to-end real day, step by step

### Procurement (farmer → settlement)

| Step | Status | Evidence / gap |
|---|---|---|
| Supplier onboarding (list load) | **YELLOW** | `POST /v1/suppliers/import` exists; needs the dairy's farmer list |
| Milk arrives, session open (shift) | **GREEN** | Sessions with morning/evening labels; readiness checks live |
| Supplier identification | **GREEN** | QR / code / phone / manual |
| Cow vs buffalo | **GREEN** | Captured, and priced as separate products — proven end-to-end |
| Quantity (weight) | **GREEN**\* | Manual capture, kg, validated. \***kg-only is enforced** — if the dairy trades in litres, this is a real (bounded) engineering increment |
| FAT/SNF (quality) | **GREEN** | Manual capture with plausibility bounds; SNF/CLR stored |
| Rate calculation | **YELLOW** | Engine proven (FAT bands per product, INR-ready) — but **no real chart is configured**; if the dairy's chart is FAT×SNF, one engineering increment precedes configuration |
| Accept / reject | **GREEN** | State machine, reasons, immutability |
| Parchi | **GREEN** | Numbered, printable, shareable, bilingual — verified live on DEV |
| Settlement | **YELLOW** | STL- series, periods, finalization, payments all proven — needs the dairy's cycle rules (period length, start day) |

### Sales (dairy → outlet)

| Step | Status | Evidence / gap |
|---|---|---|
| Customer/outlet onboarding | **YELLOW** | Create via portal/API (no bulk import — acceptable at pilot scale of tens); needs the outlet list and agreed prices |
| Standing orders / plans | **GREEN** | Delivery plans with rates, calendar suppression |
| Route planning | **GREEN** | Routes, stops, vehicles, drivers (DEMO-034) |
| Driver assignment | **GREEN** | Run generation route-aware, scheduler proven under concurrency |
| B2B delivery + confirmation | **GREEN** | Driver phone: own-run scoping, delivered/skipped/returned, offline queue, idempotent replay — verified live over HTTPS |
| Billing / receivable | **GREEN** | INV- invoices, customer payments, receivables report, "who owes money" |
| NOT REQUIRED for pilot | — | Customer app/login, ad-hoc customer self-ordering, GPS tracking, farmer app |

## 3. Genuine pilot blockers — and only those

**A. Engineering** — *none unconditional.* Two conditional ones, both
resolved the day the rate chart arrives: (1) litres-based buying (kg-only is
enforced today); (2) FAT×SNF grid pricing (engine is single-axis, MVP-001).
Either is a bounded increment, not a rebuild.

**B. Business data** — the real gate: actual rate chart; farmer list
(names/codes/phones/milk types); outlet list with agreed prices and standing
quantities; settlement cycle rules. Without these the platform is a correctly
engineered empty shell.

**C. Vendor/onboarding** — **none for the pilot.** The parchi is paper/shared
text; reports live in the portal. Email needs only an SMTP mailbox (hours,
config-only — `SmtpEmailProvider` is real code). SMS requires India DLT
registration (weeks — start only if the dairy wants it), WhatsApp requires a
BSP (weeks). Neither gates day 1.

**D. Legal/compliance** — one real item: farmer and customer names/phones are
personal data under the DPDPA and **the repository contains zero consent or
notice machinery**. The pilot minimum is small (§10) but it is not optional.

**E. Operational/process** — the sharpest finding of this audit: **the host
has no scheduled backup.** `/opt/lacteva/backups` holds only pre-deployment
dumps; no crontab entry exists. The logical-backup and restore scripts are
written and *proven* (VER-001/DR-001) — nobody ever installed the schedule.
Running a real dairy's money for 7 days on a single EC2 host without a
nightly off-host backup is the one operational fact that would be negligent
to ignore. Also: single-host DEV infrastructure double-booked as the pilot
environment (acceptable for a pilot, must be a conscious decision), disk at
71%, and no written onboarding/day-0 runbook.

**F. UX/device validation** — nothing *known broken*, one honest debt: no
physical handset has ever rendered either mobile experience (§9).

## 4. Rate chart — what is still required

Everything below is asked, precisely, in LACTEVA-RATE-CHART-QUESTIONNAIRE
(committed): milk types bought and whether mixed is accepted; FAT bands
(width, floor, ceiling); whether SNF affects price (grid vs deduction vs not
at all); CLR/density usage; morning/evening differentiation (engine records
shifts either way); effective dates and who approves changes; rejection
thresholds; deductions; bonuses; advances (BR-0011 currently pins adjustments
to zero-impact — advances are a settlement feature to schedule only if the
dairy uses them); rounding at rate/line/settlement level; **kg vs litre**;
settlement cycle.

**Can engineering proceed before the chart arrives? Yes — everything except
the rate card configuration itself and the two conditional increments in
§3-A.** Onboarding, imports, routes, plans, DPDPA kit, backups, handset
validation are all chart-independent. The chart gates configuration, not
construction.

## 5. Hardware

**READY WITHOUT HARDWARE (today):** the entire collection flow on PSP-0007's
Basic/Standard profile — operator-entered readings with source recorded
(`manual`), mocks refused in production, scale-presence as a readiness check,
parchi from the browser. The hardware audit's verdict stands: hardware is an
upgrade to trust and speed, not a launch dependency.

**REQUIRED FOR A HARDWARE PILOT (P0-HW-002, gated):** the discovery checklist
of LACTEVA-HARDWARE-INTEGRATION-SPEC §11 — analyzer make/model/interface with
**captured raw output**, scale make/model/interface (confirm a data port even
exists), printer make/model/command set, what computer lives at the centre,
and whether another software already owns the ports. Do not buy anything; do
not build until the checklist is answered.

## 6. AI

**Existing AI capability in the repository: none.** No model, no anomaly
code, no vendor SDK. What does exist is the *data*: every transaction stores
supplier, operator, centre, shift, milk type, FAT/SNF/CLR, quantity, price,
decision, and `TransactionMetrics` timing — a complete feature set for
statistical anomaly work with zero collection effort.

| Candidate | Data exists? | Effort | Business value | Pilot value | Needs vendor? |
|---|---|---|---|---|---|
| **Supplier FAT/SNF deviation** (sample far from this supplier's own recent baseline) | Yes | Days (statistics, not ML) | High — adulteration/misreading is *the* dairy trust problem | **High — visible on day 2** | **No** |
| Unusual quantity per supplier | Yes | Days | Medium | Medium | No |
| Operator anomaly (systematic reading bias) | Yes | ~1–2 weeks | High long-term | Low in week 1 (needs weeks of baseline) | No |
| Suspicious collection patterns (timing/volume rings) | Yes | Weeks | Medium | Low | No |
| Rejection anomaly | Yes (sparse) | Days | Low at pilot volume | Low | No |
| Payment anomaly | Yes | Weeks | Medium | Low (settlement runs weekly) | No |

**Recommendation — one AI MVP only:** *supplier FAT/SNF deviation flag* — a
z-score against the supplier's own trailing window, surfaced as a warning on
the accept screen and a line in the daily report. No external vendor, no
model hosting, honest about being statistics. Everything else waits for
post-pilot data volume. **Not built in this milestone.**

## 7. SAP / ERP

**Verdict: FUTURE — not a pilot blocker, not V1** unless a signed enterprise
customer makes it one. A pilot dairy of this size does not run SAP. Before
any integration is *chosen* (not built), obtain from the enterprise: system
and version (ECC vs S/4HANA, cloud vs on-prem), available interfaces
(OData/BAPI/IDoc/PI-PO/BTP middleware), authentication model, master-data
ownership (customer/vendor/material IDs — who is the system of record),
which documents integrate (sales orders, deliveries, invoices, payments,
settlements) and in which direction, and their middleware/basis team contact.
Nothing in Lacteva's UUID-boundary architecture needs to change to add this
later.

## 8. Messaging

| Channel | Technical readiness | Vendor approval | Production credentials | Templates | DLT |
|---|---|---|---|---|---|
| Email | **Real** (`SmtpEmailProvider`, config-only) | n/a | A mailbox — hours | Registry exists | n/a |
| SMS | **Real adapter** (`HttpSmsProvider`, gateway-agnostic) | Pick an Indian gateway | Account — days | Registry exists | **Required — weeks; the true SMS lead time** |
| WhatsApp | **Real adapter** (`HttpWhatsAppProvider`) + template variants & approval lifecycle (DEMO-033) | **BSP required — weeks** | After BSP | Built, awaiting real approval | via BSP |

**Minimum messaging for the pilot: none.** The parchi travels on paper or by
the operator sharing its text from their own phone; settlements print from
the portal. Email is the one channel worth switching on (config-only) for
finalized settlement statements. Start DLT/BSP paperwork in parallel *only
if* the dairy wants automated farmer messaging — it must not gate day 1.

## 9. UI/UX — proven vs not proven (from P0-UX-001, honestly)

| Surface | Status |
|---|---|
| Desktop browser portal | **Proven live** (Chrome walkthrough of every critical journey; 3 defects found and fixed; slip verified live in P0-BIZ-003) |
| Mobile browser portal | **NOT PROVEN** — viewport resize froze the tooling; never claimed |
| Driver app on a physical handset | **NOT PROVEN** — proven only as real widgets at 320×568 in tests (overflow = failure) and live over HTTPS from tests, never on glass |
| Collection operator wizard on a physical handset | **NOT PROVEN** on device; flow proven by tests and offline replay proofs |
| Hindi | Proven in widget tests and message catalogs (portal + mobile); slip bilingual proven by test; **not walked through visually end-to-end** |
| Arabic (RTL) | Catalogs exist; **never visually verified** — and **not pilot-relevant for India** |
| Offline operation | Proven at unit/integration level (queue, replay-once, 4xx parking); **never exercised in a real dead-zone field test** |

Nothing above is *known broken*. The pilot-relevant debt is one day with two
real Android handsets: driver day + operator capture + Hindi + airplane-mode
drill. Fix only what that day genuinely finds.

## 10. DPDPA / security — pilot minimum only

Exists and proven: tenant isolation (RLS FORCED, cross-tenant 404), RBAC
registry, audit trail, immutable financial records, idempotency, TLS,
HttpOnly session cookies, per-persona access separation. **Exists for
consent/notice: nothing.**

Pilot minimum (small, not a compliance program): a one-page privacy notice
(what is collected — farmer/customer/driver names and phones; purpose —
running collection, delivery and settlement; retention; contact); a consent
acknowledgment recorded at supplier/customer onboarding (a checkbox + stored
fact — the one tiny code change in this list); a written register of the two
processors involved (AWS Mumbai hosting; any future SMS/WhatsApp gateway);
manual fulfilment of access/correction/deletion via existing admin surfaces
(supplier/customer records are editable; deletion of financial history is —
correctly — refused and must be explained as legal retention); scheduled
backups (§3-E) as part of data-protection duty.

## 11. 7-day pilot simulation

| Day | What happens | Blockers surfaced |
|---|---|---|
| **1 — Onboarding** | Create org (IN defaults: INR, Asia/Kolkata, en-IN/hi-IN — proven), branches, centres, devices-as-declared, roles, operator+driver logins; import farmers; enter outlets and plans; configure rate card | Farmer list, outlet list, **rate chart** (B); no written runbook (E); consent line (D) |
| **2 — Collection** | Two shifts of real capture, parchi to farmers | Handset validation debt (F); rate card must be published day 1 |
| **3 — Collection + delivery** | Routes, runs, driver day, outcomes, invoices | None new — this chain is the best-proven in the platform |
| **4 — Settlement** | Close period per dairy rules, finalize, print statements | Settlement cycle rules (B); email nice-to-have |
| **5 — Reporting** | Owner review: daily collection, by-supplier, by-centre, receivables, payments | None — reporting surface is broad and live |
| **6 — Failure drill** | Airplane-mode capture + replay; operator retry; host restart; **restore last night's backup to a scratch instance** | **The backup being restored must exist — §3-E is the day-6 blocker**; offline field test is this day's validation |
| **7 — Management review** | Metrics, honesty review, decision on hardware/messaging next steps | None |

## 12. Final verdict

**A. READY TODAY** — the full collection chain (identify → cow/buffalo →
weigh → quality → price → accept/reject → parchi → settle) on
operator-entered readings; the full sales chain (plans → routes → driver →
outcomes → invoices → receivables); persona separation with calm refusals;
offline capture/replay; reporting; IN localization; backup/restore *scripts*;
deployment with auto-rollback.

**B. REQUIRED BEFORE FIRST PILOT** — (1) the four business artifacts (chart,
farmers, outlets, settlement rules); (2) **install the nightly off-host
backup schedule** and restore-test it once; (3) DPDPA minimum kit (notice +
consent fact + register); (4) one physical-handset validation day (Hindi +
offline included); (5) day-0 onboarding runbook, executed once against a
clean org; (6) conditional: litres and/or FAT×SNF increment *only if the
chart demands it*.

**C. REQUIRED DURING PILOT** — SMTP mailbox for statements (config); the
supplier FAT/SNF deviation flag (the one AI MVP, if capacity allows); daily
disk/health check (disk-guard exists); support channel with a human on it.

**D. V1 AFTER PILOT** — SMS with DLT; WhatsApp BSP + approved templates;
hardware connector P0-HW-002 (gated on discovery checklist); customer bulk
import; operator anomaly analytics; multi-dimension pricing if the pilot
proves the need beyond the pilot dairy's own chart shape.

**E. FUTURE / DO NOT BUILD NOW** — SAP/ERP integration; GPS/vehicle
tracking; farmer-facing app; customer self-service ordering; payment-gateway
integration; multi-pilot SaaS onboarding automation; Arabic visual pass.

### The shortest path to the first real dairy (≤10 engineering actions)

1. Install and verify the scheduled off-host backup on the host; restore it
   once to a scratch instance (scripts exist — this is wiring, then proof).
2. Write and execute the day-0 onboarding runbook against a clean org
   (org → centres → roles → logins → import → plans → rate card).
3. Add the consent-acknowledgment fact to supplier/customer onboarding and
   publish the one-page privacy notice.
4. Run the physical-handset day (driver + operator + Hindi + airplane-mode);
   fix only genuine defects found.
5. Run the mobile-browser portal pass (owner on a phone); fix only genuine
   defects found.
6. Configure the real rate card + matrices the day the chart arrives; verify
   one priced collection against the dairy's own arithmetic to the paisa.
7. *Conditional:* implement litres support if the dairy trades litres.
8. *Conditional:* implement the FAT×SNF increment if the chart is a grid.
9. Configure SMTP for settlement statements.
10. Build the supplier FAT/SNF deviation flag (the single AI MVP) — last,
    and only if 1–8 are done.

Everything else on this list is business legwork (chart, lists, rules,
paperwork), not engineering.

### Things we should stop building

- **New feature milestones of any kind** until B-list items close — the
  platform's breadth already exceeds what a 7-day pilot can exercise.
- More portal reports and dashboard refinements (the surface is already
  wider than the pilot needs).
- WhatsApp machinery beyond what exists — templates and adapters are done;
  the gap is a vendor signature, not code.
- Hardware adapters ahead of the discovery checklist (P0-HW-001 already
  drew this line — hold it).
- Multi-dimension pricing ahead of the actual chart.
- Marketing-site iterations, additional locales, and anything on the E-list
  above.

The honest summary: **Lacteva stopped being the bottleneck several
milestones ago.** The remaining path runs through a dairy's filing cabinet,
a cron entry, one page of legal text, and an afternoon with two Android
phones.

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Initial pilot readiness gate: personas, end-to-end classification, genuine blockers (backup schedule finding), rate-chart/hardware/AI/SAP/messaging/UX/DPDPA verdicts, 7-day simulation, final verdict with shortest path (P0-PILOT-001). |
