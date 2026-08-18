---
id: LACTEVA-P0-GO-LIVE-001-FIRST-DAIRY-EXECUTION-CONTROL-SHEET
title: First Dairy Execution Control Sheet
type: reference
status: Approved
version: "1.0"
owner: Pilot Lead
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-MASTER-PRODUCT-ROADMAP, LACTEVA-DAIRY-ECOSYSTEM-AND-OPERATING-MODEL, LACTEVA-P0-PILOT-008-REAL-DAIRY-ONBOARDING-READINESS, LACTEVA-DAIRY-ONBOARDING-INFORMATION-REQUEST-PACK, LACTEVA-FIRST-DAIRY-SALES-AND-PILOT-PACKAGE, LACTEVA-COMMERCIAL-MODEL-AND-PACKAGING, LACTEVA-PRODUCT-CAPABILITY-VISIBILITY-AUDIT, LACTEVA-IDENTITY-ENTERPRISE-ARCHITECTURE-AUDIT, LACTEVA-HARDWARE-CONNECTOR-DISCOVERY, LACTEVA-REGULATORY-APPLICABILITY-AUDIT]
baseline: ARCH-BASELINE-V1
---

# Lacteva — First Dairy Execution Control Sheet (P0-GO-LIVE-001)

**Operational control document.** It answers one question: *exactly what has to
happen, in what order, who supplies it, who verifies it, what Lacteva verifies
technically, what the dairy approves, and what allows the 7-day pilot to
start.* It consolidates — and defers to — the governing documents (front
matter); it invents **no** dairy data, price, threshold, legal fact, or
capability. Where a value is undecided it says **TO CONFIRM**. Where the
platform lacks a capability, that capability is **absent from this plan** and
preserved in §U/§V.

**The one-line state of the world (from the Go-Live Readiness verdict):**
*DATA-DEPENDENT — not GREEN. The platform is go-live ready and verified live;
the gate is the dairy's four artifacts, the legal signatures, and one
production backup-retention config line. The gate is the dairy, not
engineering.*

---

## A. Executive summary

Lacteva is technically ready: the full lifecycle (collection → quality → the
dairy's own rate → parchi → settlement → outlets → delivery → billing →
reporting) is deployed, verified live on DEV, and proven on a physical Android
handset. A synthetic end-to-end onboarding rehearsal passes as an integration
suite. What does not exist is any real dairy input: no real rate chart, farmer
list, outlet list, settlement rules, licence copies, or signed agreement. This
sheet turns the remaining work into a controlled sequence:
**PROSPECT → QUALIFIED → AGREEMENT → DATA RECEIVED → ORGANIZATION CONFIGURED →
USERS ONBOARDED → MASTERS IMPORTED → RATE CARD → SETTLEMENT → DAY-0
RECONCILIATION → PILOT DAY 1…7 → GO / STOP / EXTEND.**

## B. Current platform state (reconciled from the repository)

| Class | Items |
|---|---|
| **GREEN / READY** | The nine-stage lifecycle end to end; offline capture + sync (proven on a Motorola moto g57 power, Android 16); RBAC + org-scoped RLS (foreign resource = 404); audit; CSV imports with named duplicates; parchi (numbered, bilingual EN/HI, print/share); settlement with free cycles; subscription entitlement + 30-day trial; supplier FAT/SNF deviation flag (statistics, non-blocking); nightly backup + off-site S3 + restore drill (last verified backup: `verified: true`, 42,113 rows); DEV onboarding rehearsal green |
| **DATA REQUIRED** | The four artifacts: real rate chart, farmer list, outlet list (with agreed prices/quantities), settlement-cycle rules — none exist in the repository and none may be invented |
| **BUSINESS REQUIRED** | Qualified dairy + decision-maker; pilot scope choice (centres; sales side in/out); operating-model confirmation (M1 assumed); commercial terms; price per centre **TO CONFIRM** |
| **LEGAL REQUIRED** | Signed pilot agreement (incl. processor clause), FSSAI licence copy, Legal Metrology scale certificate copy (where a trade scale is used), privacy notice/consent wording adopted |
| **CONFIG REQUIRED (the one production line)** | Production `BACKUP_RETAIN_DAYS` restored to **30** before real financial operations (DEV was deliberately trimmed to 2). SMTP for statements: **PILOT-CONDITIONAL, config only, not a blocker** |
| **OPTIONAL / CONDITIONAL** | Litres (G-04) / FAT×SNF grid (G-05) — engineering **only if the real chart requires it**; pilot dairy's own handset run; second handset |
| **HARDWARE — DISCOVERY-GATED** | Centre Connector / automated scale-analyzer capture: nothing before the P0-HW-002 evidence gate; capture is manual-first |
| **ENTERPRISE / FUTURE** | SAP/ERP, enterprise SSO, global identity, federation, GPS, farmer app, web outlet portal, chilling/BMC, plant, procurement transport, payment gateway, advanced AI/analytics — **no V1/FUTURE item blocks the pilot** |
| **MUST NOT BE TOUCHED BEFORE PILOT** | The §16 do-not-build list (Master Roadmap + Ecosystem doc); RLS/RBAC/identity architecture; applied migrations; immutable records |

## C. First-dairy objective

One real Indian dairy, bounded scope (recommended: one organization · one
branch · one-or-few centres · their operators · their farmers · the real rate
chart · real collections · one real settlement; sales side only if the dairy
wants it — scope **TO CONFIRM with the dairy**), run for 7 controlled days on
the free 30-day trial, reconciled against the dairy's own arithmetic **to the
paisa**, ending in an explicit GO / STOP / EXTEND decision by the named owner.

## D. Roles & responsibilities (from the P0-PILOT-008 ownership matrix)

| Item | Dairy | Lacteva |
|---|---|---|
| Rate chart, farmer list, outlet list, settlement rules | **Provides (source of truth)** | Configures |
| FSSAI + Legal Metrology copies | **Holds/provides** | Files copy, verifies presence |
| Agreement + consent register | **Signs/keeps** | Provides templates |
| Org/centre/user setup | Approves | **Executes** |
| Imports, rate-card build, settlement config | Validates | **Executes** |
| Day-0 reconciliation | **Signs off** | Runs verification |
| Backup/restore, production config, security | — | **Owns** |
| Scale stamping, hygiene, cold chain, floor-price compliance | **Owns (regulated entity)** | Records/evidences |
| Subscription | **Buyer** | Invoices (when billing exists) |

Named individuals (fill at kickoff): Pilot lead (Lacteva) ______ · Dairy owner
______ · Dairy office contact ______ · Centre operator(s) ______.

**The standing principle:** *Lacteva proves the platform mechanics; the dairy
proves the business arithmetic and the expected outcome.*

## E. Onboarding sequence (exact, ordered, with owners)

| # | Stage | Action | Owner | Verifier | Gate |
|---|---|---|---|---|---|
| 1 | Sales qualification | Qualify per the sales-package checklist (decision-maker, FAT-banded kg chart or flag litres/grid, paper/Excel today, Android-willing staff, no day-one future dependency) | LACTEVA | Pilot lead | G1 |
| 2 | Commercial discussion / NDA | If the dairy requires an NDA, sign before data flows (**TO CONFIRM per dairy**); present trial + per-centre model, prices TO CONFIRM | JOINT | Both | G1 |
| 3 | Pilot agreement | Sign, incl. processor clause + privacy/consent wording | DAIRY (signs) / LACTEVA (template) | Owner | G2 |
| 4 | Information pack sent & returned | The Dairy Onboarding Information Request Pack, sections A–O, incl. the four artifacts + licence copies | DAIRY | Lacteva validates receipt | G2/G5 |
| 5 | Organization creation | Platform admin creates the Organization with `country_code: IN` (INR, Asia/Kolkata, en-IN + hi-IN arrive by default — proven) | LACTEVA | Pilot lead | G3 |
| 6 | Organization type confirmation | `org_type` from the code vocabulary (`cooperative\|processor\|collector\|farm\|other`) per what the dairy actually is | JOINT | Pilot lead | G3 |
| 7 | Hierarchy | Workspace(s) → Branch(es) → one Collection Centre per physical centre; hours; status active | LACTEVA (dairy approves) | Dairy office | G3 |
| 8 | Centre configuration | Operating windows, calendar, readiness; register the centre's **scale** device (a blocking readiness check); analyzer/printer as present | LACTEVA | Centre manager | G3 |
| 9 | Staff onboarding | Invite → accept (sets credential) → grant named role at scope; drivers: create profile → invite → **link** `/drivers/{id}/user` → assign vehicle/route | LACTEVA (dairy names people) | Each person logs in | G4 |
| 10 | Farmer import | CSV via `/suppliers/import` (portal preview; duplicates named; one bad row fails alone) | LACTEVA (dairy's file) | Counts match the file — DAIRY confirms | G5 |
| 11 | Outlet/customer import | CSV via `/customers/import`, inline standing orders (plans) | LACTEVA (dairy's file) | Counts + prices match — DAIRY confirms | G5 |
| 12 | Vehicles/routes (if sales side in scope) | Routes, stops, vehicles, driver assignment | LACTEVA (dairy's reality) | Sales officer / driver | G5 |
| 13 | Rate-chart submission | The ACTUAL chart — original Excel/PDF or clear photo; never recreated or simplified | DAIRY | Lacteva confirms legibility/completeness | G6 |
| 14 | Rate-card configuration | Create → matrices per product (cow/buffalo) → bands from the photographed chart → effective date. **ENG only if the chart needs litres/FAT×SNF (G-04/G-05) — STOP and schedule before proceeding** | LACTEVA | Four-eyes human review | G6 |
| 15 | Rate-card review & approval | Human review incl. the Maharashtra floor check (look up the current GR that day — a human check, not code); publish; **paisa reconciliation** of one known real collection | JOINT — DAIRY approves | Owner/accountant | G6 |
| 16 | Settlement rules | Period/cycle configured (free `period_from`/`period_to`); dry run reconciles | LACTEVA (dairy's rules) | Finance + dairy | G7 |
| 17 | Legal/document check | Agreement signed; FSSAI + LM copies on file; consent wording adopted | DAIRY provides / LACTEVA files | Pilot lead | G2 |
| 18 | Production config | `BACKUP_RETAIN_DAYS=30` on the production host; backup verified + off-site; SMTP if statements will be emailed (conditional) | LACTEVA | Pilot lead | G8 |
| 19 | User access verification | Spot-checks: operator refused office pages; driver routed to mobile experience; auditor read-only; centre visibility correct | LACTEVA | Pilot lead | G4/G8 |
| 20 | Technical verification | The full §N/Day-0 technical half below | LACTEVA | Pilot lead | G8 |
| 21 | Day-0 test transaction | One real collection end to end + one delivery run (if in scope) — §O | JOINT | Both | G9 |
| 22 | Dairy-side reconciliation | The dairy's own arithmetic, to the paisa — §O | DAIRY | Owner | G9 |
| 23 | Go-live approval | Named owner signs off; every §S box checked | DAIRY | Owner + pilot lead | G10 |
| 24 | Pilot Day 1 | §P begins | JOINT | Per §P | — |
| 25 | Daily monitoring | §P/§Q rhythm daily | JOINT | Pilot lead | — |
| 26 | Day-7 review → GO / STOP / EXTEND | Two paper reconciliations + owner review — §P Day 7 | JOINT — DAIRY decides | Owner | — |

## F. Required dairy information (exact checklist)

Authoritative instrument: **the Dairy Onboarding Information Request Pack**
(P0-PILOT-009) — this table controls execution; the pack is what the dairy
fills. No example values appear here beyond what the pack itself defines
(CSV column names), because **no real example may be fabricated**.

| Item | Required? | Owner | Format | Lacteva validation | Dairy approval? | Blocking? |
|---|---|---|---|---|---|---|
| A. Organization details (legal name, address, contact, centre count/locations) | REQUIRED | Owner/manager | Pack §A form | Completeness | — | **BLOCKING** |
| B. Collection-centre list (code, name, location, hours, manager, operators, existing scale make/model) | REQUIRED | Manager | Pack §B table | One row per physical centre | — | **BLOCKING** |
| C. Staff/users (name, mobile, role from the canonical list, centre(s), apps) | REQUIRED | Manager | Pack §C table | Roles exist; scopes valid | — | **BLOCKING** |
| D. Farmer list | REQUIRED | Manager/centre records | CSV — columns per the runbook: `code, full_name, phone, village, center_codes` | Import preview; duplicates named; counts match | Dairy confirms counts | **BLOCKING** |
| E. Outlet/customer list (with agreed prices/quantities) | REQUIRED if delivering | Sales/office | CSV — `name, customer_type, phone, address, plan_*` (product, quantity, unit, price) | Same import discipline | Dairy confirms | BLOCKING if sales in scope |
| F. **Actual rate chart** | REQUIRED | Owner/accountant | Original Excel/PDF or clear photo — never recreated | Digitize → four-eyes review → floor check → **paisa reconciliation** | **DAIRY APPROVES before publish** | **BLOCKING** |
| G. Settlement rules (frequency, period start/end, approver, deductions) | REQUIRED | Owner/accountant | Written / existing document | Dry-run reconciles | Dairy confirms | **BLOCKING** |
| H. Legal/regulatory: FSSAI copy; LM scale certificate; signed agreement; consent wording | REQUIRED (LM where a trade scale is used) | Owner/office | PDF/photo/signed copy | Presence on file | Owner signs | **BLOCKING** |
| I. Vehicles/routes | If delivering | Sales/office | Pack tables | Assignments resolve | — | Non-blocking unless sales in scope |
| J. Other configuration (holidays/calendar, shift labels, language preference) | OPTIONAL | Office | Written | Config applied | — | Non-blocking |

## G. User & identity setup (the architecture, used exactly)

Standing rules (Identity/Enterprise Audit — unchanged, no exceptions): **one
Lacteva identity per person · no per-application credentials, ever ·
application-specific authorization · role + scope on the grant
(`UserRole.center_id`) decide access · multi-role and multi-centre on one
identity · organization-safe RLS (foreign resource = 404) · farmers and
customer records are not login users by existence · devices are device
principals, never human users · enterprise SSO / global identity / federation
stay ENTERPRISE-future.**

First-dairy user matrix:

| Persona | Login? | Invited/created how | Organization | Scope | Role | Application | Can do | Cannot do |
|---|---|---|---|---|---|---|---|---|
| Owner / admin | YES | Platform admin invites → accept | The dairy | Org-wide | ORGANIZATION_ADMIN | Admin Portal | Everything in the tenant | Reach another tenant (404) |
| Manager | YES | Invite → accept → grant | The dairy | Org-wide | Manager | Admin Portal (+ Collection App if hands-on) | Operations + oversight | Platform administration |
| Centre manager | YES | Invite → grant at centre | The dairy | `center_id` | CENTRE_MANAGER | Portal + Collection App | Their centre | Other centres' operations |
| Collection operator | YES | Invite → grant at centre | The dairy | `center_id` | COLLECTION_OPERATOR | Collection App | Capture at their centre | Office pages (calm refusal), other centres |
| Finance | YES | Invite → grant | The dairy | Org-wide | Finance roles | Admin Portal | Settlements, payments, receivables | Capture |
| Sales officer | YES | Invite → grant | The dairy | Org-wide | SALES_OFFICER | Admin Portal | Customers, orders, routes | Finance approvals |
| Driver | YES | Create profile → invite → link `/drivers/{id}/user` → assign vehicle/route | The dairy | Own runs | DRIVER only | Driver experience (same binary) | Execute own runs, record outcomes | Portal work (refusal names the app), others' runs |
| Auditor | YES | Invite → grant | The dairy / external | Org read | AUDITOR | Admin Portal | Read everything | Change anything |
| Farmer | **NO** | CSV import / created at centre — a record | (record of the dairy) | — | — | — (receives a parchi) | — | — |
| Outlet/customer | **NO** | CSV import — a record (household mobile login exists as a shipped opt-in, DEMO-012 — **not part of this pilot's scope unless the dairy asks; TO CONFIRM**) | (record) | Own record if opted in | Customer persona | Customer mobile experience (if opted in) | See own deliveries/bills | Anything beyond own record |
| Scale/analyzer/printer | **NEVER** | Device registry (assets; scale is a blocking readiness check) | The dairy | One centre | — | — | Be recorded, report health | Log in |

## H. Application access matrix (first pilot)

| Persona | Admin Portal | Collection App | Driver experience | Customer mobile | Farmer App | Web Outlet Portal | Connector | Enterprise/SAP/SSO |
|---|---|---|---|---|---|---|---|---|
| Owner/manager/finance/sales/auditor | **USES** | optional (managers) | — | — | **FUTURE** | **FUTURE** | **GATED (P0-HW-002)** | **ENTERPRISE** |
| Centre manager | USES | USES | — | — | — | — | — | — |
| Operator | refusal | **USES** | — | — | — | — | — | — |
| Driver | refusal names the app | — | **USES** | — | — | — | — | — |
| Farmer | — | — | — | — | FUTURE | — | — | — |
| Household customer | — | — | — | shipped opt-in (scope TO CONFIRM) | — | FUTURE | — | — |

One identity per person; the same login authorizes whichever of these apps the
person's roles justify. **No separate usernames/passwords per application.**

## I. Organization / centre setup (control points)

- [ ] Organization created (`country_code: IN`; INR / Asia-Kolkata / en-IN+hi-IN arrive by default — proven)
- [ ] `org_type` confirmed with the dairy (code vocabulary)
- [ ] Workspace/Branch per the dairy's actual structure (small dairy: one of each)
- [ ] One Collection Centre per physical centre; hours; active
- [ ] Scale device registered per centre (**blocking readiness check**); analyzer/printer as present
- [ ] Centre timezone left NULL unless the centre genuinely differs from the organization

## J. Farmer / outlet master data (control points)

- [ ] Files received in the pack's format; **no value altered or invented by Lacteva**
- [ ] Portal CSV preview shows missing-required-column callout BEFORE send
- [ ] Import verdicts rendered verbatim; duplicates NAMED (never silently skipped or merged); one bad row fails alone
- [ ] Counts match the dairy's file — **dairy confirms the counts**
- [ ] Outlets carry inline standing orders (product, quantity, unit, agreed price — the dairy's own)
- [ ] Re-import proven safe (duplicates named, not doubled)

## K. Rate card (the most important configuration)

- [ ] The ACTUAL chart received (Excel/PDF/clear photo, front and back)
- [ ] Shape triage: FAT-banded per milk type in **kg** → **configuration, not engineering**; litres or FAT×SNF grid → **STOP: bounded engineering first (G-04/G-05)** — schedule before any promise
- [ ] Configured: card → matrices per product (cow/buffalo separate) → bands → effective date
- [ ] **Four-eyes human review** against the photographed chart
- [ ] Maharashtra floor check — a human looks up the current GR that day (reference point in the repo runbook: 3.5 FAT / 8.5 SNF cow — verify against the current GR, never assume)
- [ ] **Dairy approves before publish**; published with correct effective date
- [ ] **Paisa reconciliation**: one known recent real collection recomputed through the published card — must match the dairy's own arithmetic **to the paisa**

## L. Settlement rules

- [ ] Cycle captured as the dairy actually runs it (10-day / fortnight / month — all free `period_from`/`period_to`, no code)
- [ ] Approver named; deductions listed (recorded; advances/loans **not in scope** — V1)
- [ ] Dry-run settlement reconciles: lines = collections = parchis
- [ ] Dairy confirms the dry-run figures

## M. Legal & regulatory (the dairy is the regulated entity)

- [ ] Signed pilot agreement incl. processor clause
- [ ] Privacy notice + consent line adopted (templates exist in the onboarding pack)
- [ ] FSSAI licence/registration copy on file
- [ ] Legal Metrology certificate copy per trade scale on file
- [ ] Not applicable before pilot (per the regulatory audit): BIS, DPDPA module, e-invoicing, any "compliance module" — **none exists, none is needed**

## N. Technical verification (Lacteva runs — the Day-0 technical half)

- [ ] Org/centres/users/roles created; access spot-checked (operator refused office page; driver → mobile experience)
- [ ] Farmers/outlets imported — **counts match**
- [ ] Rate card published + reviewed (incl. floor check)
- [ ] Settlement rules configured; **dry-run reconciles**
- [ ] **One real collection end to end**: identify → milk type → weight → FAT/SNF → price → accept → complete → **parchi** printed/shared
- [ ] **One delivery run** (if in scope): generate → driver phone → outcome → invoice visible
- [ ] Reporting surfaces answer; audit trail populated
- [ ] **Backup verified + off-site; production retention set to 30 days**

## O. Day-0 reconciliation (the business half — the dairy proves the arithmetic)

**What Lacteva configures:** everything in §I–§N, from the dairy's own inputs.
**What the dairy verifies:** its own numbers, on its own paper.

Procedure:
1. Pick one real, recent collection the dairy has already paid on (its own parchi/register entry).
2. Recompute it through the published rate card in Lacteva.
3. Compare: quantity, FAT/SNF, rate applied, amount — against the dairy's own arithmetic.
4. The dairy confirms: the parchi matches what a farmer should receive; the recomputed collection matches its own arithmetic **to the paisa**; the settlement cycle and figures are correct.

**PASS** = every §N technical box green **and** the dairy's three confirmations hold, byte-identical/to-the-paisa — no percentage tolerance exists and none may be invented.
**STOP** = any §R genuine stop condition, or the arithmetic does not match and the cause is not a transcription/config item fixable on the spot (then fix the card/config, re-verify, re-run — that is correction, not go-live).
**Sign-off:** the **named dairy owner** signs to begin the 7-day pilot; the pilot lead countersigns the technical half.

## P. Seven-day pilot control plan (preserved from the runbook)

| Day | Objective | Monitor | By | Evidence | PASS | STOP |
|---|---|---|---|---|---|---|
| 0 | Onboarding | Full setup + Day-0 checklist | Pilot lead | Screenshots, counts, reconciled sample | All §N/§O green + sign-off | Any §R condition |
| 1 | First real day | Both shifts captured; quality; **pricing correct**; parchi handed over | Operator + lead | Parchis, transaction list | Collections match reality | Rate/parchi mismatch |
| 2 | Full volume | Full-volume capture; deviation flags re-tested (information, not accusation); offline+sync if used; backup ran | Operator | Day's transactions, sync log | No data loss; flags sane | Sync loss / backup fail |
| 3 | Sales side | Deliveries + invoices; receivables | Office | Delivery report, invoices | Figures reconcile | Billing mismatch |
| 4 | Settlement | Close period; review lines; finalize; statements; payments | Finance | Settlement + statements | **Lines = parchis** | Settlement mismatch |
| 5 | Reporting | Dashboard + by-supplier/centre/receivables | Owner | Report views | Week reconciles | Unexplained variance |
| 6 | Resilience drill | Airplane-mode capture + replay-once; operator retry (**must 409, not duplicate**); **restore last backup to a scratch instance**; off-site replication green | Pilot lead | Drill log | Replay-once; restore clean | Duplicate / restore fail |
| 7 | Review | The two paper reconciliations + owner review | Owner + lead | Reconciliation sheet | **Both reconcile** | Material gap |

**Daily rhythm (every day, from the onboarding pack):** every shift — open
session with the right label, capture fully, hand over the parchi; every
evening — owner reads the dashboard (collections vs yesterday, quantity,
value, average FAT; skipped stops — ask why; "who owes money"); settlement on
the dairy's own cycle day(s).

**The two Day-7 paper reconciliations (verbatim procedure):**
- **Milk bought:** any 3 parchis at random → `quantity × rate = amount` on each slip → each found in the settlement's lines → settlement total = sum of lines → paid/payable matches.
- **Milk sold:** any customer → standing order → the week's generated deliveries → driver outcomes → invoice lines → invoice total → payments/receivables.
Every figure must trace; any mismatch at any step is a finding, and the
figures are byte-traceable end to end, so the discrepancy is locatable.

**Day-7 decision:** the owner decides **GO** (convert to paid per-centre
subscription — same tenant, all data survives; price **TO CONFIRM**),
**STOP** (end at trial close, no obligation), or **EXTEND** (remaining trial
days; terms **TO CONFIRM**). Thresholds/acceptable variance: **TO CONFIRM with
the dairy — no success percentages are defined anywhere and none may be
invented; "correct" means byte-identical to the dairy's own arithmetic.**

## Q. Daily evidence to collect

Per day: session labels + counts; the day's parchis (or transaction list);
sync log if offline used; backup/watchdog status line; any deviation-flag
events and their re-test outcome; delivery/invoice records (if in scope); a
one-paragraph pilot-lead note naming anything classified under §R. Evidence is
screenshots/exports of real records — never reconstructed after the fact.

## R. Stop conditions (classification discipline — preserved verbatim)

**Genuine STOP (halt the pilot; investigate):** incorrect rate calculation ·
settlement mismatch · data corruption · duplicate transaction not caught ·
unauthorized access / wrong centre visibility · import corruption ·
offline-sync data loss · parchi ≠ recorded transaction · production backup
failure · required legal/business artifact missing at go-live.

**Classify before halting — these are NOT engineering defects:**

| Class | Meaning | Response |
|---|---|---|
| Operator error | Wrong entry by a person | Correct via the platform's own correction path; coach |
| Bad input / data quality | The dairy's file/chart had a wrong value | Fix the source, re-import/re-configure; never patch code |
| Bad configuration | Period/scope/setting chosen wrong | Reconfigure; re-verify |
| Business decision | The dairy wants a different rule | Record; configure if supported; else TO CONFIRM/roadmap |
| Legal blocker | Artifact missing/expired | Pause the gate, not the code |
| **Engineering defect** | The platform computes/stores/authorizes **incorrectly given correct input** | **STOP; document precisely; propose the smallest fix; never silently fix** |

## S. Go-live gate (all ten, with sign-off)

| Gate | Condition | Status | Owner | Evidence | Blocking? | Sign-off |
|---|---|---|---|---|---|---|
| G1 Commercial | Dairy qualified; trial terms presented; scope agreed | OPEN | Lacteva sales | Qualification form | YES | Pilot lead |
| G2 Legal | Agreement signed; FSSAI + LM copies filed; consent adopted | OPEN | Dairy | Signed copies on file | YES | Owner |
| G3 Organization | Org + hierarchy + centres configured + readiness (scale registered) | OPEN (mechanics READY) | Lacteva | Portal records | YES | Pilot lead |
| G4 Users | All staff invited/accepted/granted; access spot-checks pass | OPEN (mechanics READY) | Lacteva | Login + refusal checks | YES | Pilot lead |
| G5 Master data | Farmers + outlets imported; counts confirmed by the dairy | OPEN (path proven) | Joint | Import receipts + counts | YES | Dairy office |
| G6 Rate card | Configured from the real chart; four-eyes + floor check; dairy-approved; published; **paisa-reconciled** | OPEN (**DATA-DEPENDENT — STOP until the real chart exists**) | Joint | Review record + reconciliation | YES | Owner/accountant |
| G7 Settlement | Rules configured; dry-run reconciles; dairy confirms | OPEN | Joint | Dry-run output | YES | Finance + dairy |
| G8 Technical | §N all green; **production `BACKUP_RETAIN_DAYS=30`**; backup verified + off-site | OPEN (platform READY; one config line) | Lacteva | §N checklist + backup status | YES | Pilot lead |
| G9 Day-0 reconciliation | §O PASS — to the paisa; dairy's three confirmations | OPEN | Dairy | Signed Day-0 sheet | YES | **Owner** |
| G10 GO-LIVE | G1–G9 green; every §S/§N box checked | OPEN | Joint | This sheet, countersigned | YES | Owner + pilot lead |

Nothing above is marked GREEN, because no real dairy input exists yet —
exactly as the readiness verdict requires. Platform *mechanics* behind G3–G5,
G7–G8 are READY (proven on DEV and on glass).

## T. Commercial gate

- [x] Model decided in code: **per active collection centre**, monthly; not per user, not per litre
- [x] Trial: `LACTEVA_TRIAL`, 30 days, everything on, not billable
- [x] Users/records/devices are never billable seats
- [ ] Price per centre (INR): **TO CONFIRM** — config key exists, value absent
- [ ] Payment collection: **TO CONFIRM** — no gateway contracted (provider `disabled`); pilot requires none
- [ ] Pilot commercial terms (discounts, extension terms): **TO CONFIRM**
- [ ] Conversion mechanics: GO → `LACTEVA_STANDARD` on subscribed centres; same tenant, all data/config survives; billing starts only on continuation

## U. Future / Coming Soon (preserved — nothing blocks the pilot, nothing is deleted)

Per the canonical roadmap classification; every item stays a truthful,
non-interactive label (test-enforced by the claims guards):
**V1:** messaging (WhatsApp/SMS — DLT/BSP paperwork) · QR scanning (rendering
ships; scanning does not) · receipt/invoice PDFs · GST/FSSAI document fields ·
anomaly detection · advances/loans at settlement · supplier trend analytics ·
hardware connector / Centre Connector MVP (**discovery-gated, P0-HW-002**) ·
automated scale/analyzer read-assist (V1+, after the gate).
**V2:** forecasting · advanced analytics · chilling centre (location type) ·
BMC (asset) · plant/processing (V2/ENT) · procurement transport.
**FUTURE / FUTURE OPTION:** GPS (never a pilot dependency) · farmer app · web
outlet/customer portal · consumer app · advanced AI.
**TO CONFIRM:** payment gateway · module/add-on pricing · production-hardening
items beyond the retention line as commercial scale demands.

## V. Enterprise evolution (preserved, not started)

Enterprise SSO · global identity · federation/parent groups · org-to-org
trading relationships (consented projections, **never widened RLS**) ·
enterprise integration/API layer · SAP/ERP (no vendor, no module names/OData/
BAPI/IDoc assumed; master-data SoR **TO CONFIRM** at engagement). The first
pilot requires none of these; the architecture reaches them additively
(Identity/Enterprise Audit: GO, no rewrite). The wider ecosystem — farmer →
centre → chilling/BMC → procurement transport → plant → distribution → outlet
→ consumer, across dairy firms, cooperatives, processors, collection
organizations, transporters, distributors, enterprise groups — remains
architecturally distinguishable per the Ecosystem & Operating Model; the two
transport legs are never merged.

## W. Open decisions (TO CONFIRM register for this execution)

| # | Decision | Owner | Needed by |
|---|---|---|---|
| 1 | Which dairy (qualification outcome) | Business | G1 |
| 2 | Pilot scope: centres; sales side in/out; household-customer opt-in | Business + dairy | G1 |
| 3 | Operating model confirmation (M1 assumed) | Dairy | G3 |
| 4 | NDA required? | Dairy | G1 |
| 5 | Rate-chart shape (kg-FAT vs litres/grid → conditional engineering) | Dairy's chart | G6 |
| 6 | Settlement cycle specifics | Dairy | G7 |
| 7 | Price per centre; pilot terms; extension terms | Commercial | Day 7 |
| 8 | Payment collection method (no gateway) | Commercial | Post-GO |
| 9 | Success thresholds/acceptable variance beyond exactness | Business + dairy | G9 |
| 10 | Statements by email? (SMTP config — conditional) | Dairy | G8 |

## X. Final sign-off

| Checkpoint | Name | Signature | Date |
|---|---|---|---|
| Day-0 technical verification (Lacteva) | | | |
| Day-0 business reconciliation (Dairy owner) | | | |
| Go-live approval (G10) | | | |
| Day-7 decision: GO / STOP / EXTEND (circle) | | | |

## Y. Appendices / templates (existing instruments — not duplicated here)

- Dairy-facing information request: `LACTEVA-DAIRY-ONBOARDING-INFORMATION-REQUEST-PACK.md` (fillable, shareable)
- Operational runbook + gate: `LACTEVA-P0-PILOT-008-REAL-DAIRY-ONBOARDING-READINESS.md`
- Day-0/legal templates (privacy notice, consent line, processor clause, handset script): `LACTEVA-PILOT-ONBOARDING-PACK.md`
- Sales materials (handout, WhatsApp/email intros, proposal, qualification form): `LACTEVA-FIRST-DAIRY-SALES-AND-PILOT-PACKAGE.md`
- Readiness evidence: `LACTEVA-GO-LIVE-READINESS.md` · `LACTEVA-P0-PILOT-006-DEV-ONBOARDING-REHEARSAL.md`

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Pilot Lead | First-dairy execution control sheet: reconciled current state (GREEN/DATA/BUSINESS/LEGAL/CONFIG/GATED/ENTERPRISE), 26-step owner-tagged onboarding sequence, exact data checklist mapped to the request pack, identity/user matrix on the unchanged architecture, application access matrix, Day-0 procedure (technical half + dairy paisa reconciliation, PASS/STOP/sign-off), 7-day control matrix with the day-6 resilience drill and day-7 paper reconciliations preserved verbatim, stop-condition classification discipline, ten-gate go-live structure (nothing GREEN — no real dairy input exists), commercial gate with TO CONFIRMs, preserved Coming-Soon/Enterprise tracks, open-decision register, sign-off block, and pointers to the existing instruments. No thresholds, prices, data, or capabilities invented (P0-GO-LIVE-001). |
