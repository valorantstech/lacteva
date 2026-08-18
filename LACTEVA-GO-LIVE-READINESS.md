---
id: LACTEVA-GO-LIVE-READINESS
title: Real Dairy Go-Live Readiness
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-PILOT-READINESS-GATE, LACTEVA-PILOT-ONBOARDING-PACK, LACTEVA-REGULATORY-APPLICABILITY-AUDIT, LACTEVA-RATE-CHART-QUESTIONNAIRE, LACTEVA-PRODUCT-GAP-REVIEW, LACTEVA-HARDWARE-INTEGRATION-SPEC]
baseline: ARCH-BASELINE-V1
---

# Real Dairy Go-Live Readiness (P0-PILOT-005)

**Verdict: DATA-DEPENDENT — not GREEN.** The platform is go-live ready and
verified live on the deployed system (`main-2867a55`); the sole gate is the
**four real dairy artifacts, which do not exist yet** in the repository or the
related `../Master` workspace. No dairy, rate chart, farmer list, outlet list,
settlement rules, FSSAI/licence information, or signed agreement was invented —
per the milestone's absolute rule. GREEN is reachable only when the dairy
supplies its inputs.

This document is configuration, reconciliation, and readiness evidence — **no
code was changed** (Phase 11: no genuine engineering blocker exists).

---

## Phase 1 — Readiness reconciliation (verified live, `main-2867a55`)

Read-only checks against the deployed platform on 2026-08-18. Green = the
platform side is ready; the dairy's real data is a separate axis (below).

| Element | Live result | Status |
|---|---|---|
| Deployed release | `/opt/lacteva/current → main-2867a55` (P0-PILOT-004 fixes live) | READY |
| Platform health | `/health/ready` 200 | READY |
| India org defaults | INR · Asia/Kolkata · en-IN · [en-IN, hi-IN] | READY |
| Collection centres | reachable, seeded example org has 3 active | READY (config per dairy) |
| Operators | COLLECTION_OPERATOR role + login proven on glass (P0-PILOT-004) | READY |
| Drivers | driver login → driver experience, own-run scoping, proven on glass | READY |
| Suppliers | `/suppliers` + `/suppliers/import` (200) + portal Import CSV page (200) | READY |
| Customers/outlets | `/customers` + `/customers/import` (200) + portal Import CSV page (200) | READY |
| Standing orders | delivery plans (inline on customer import) | READY |
| Routes / vehicles | routes+stops+vehicles+runs proven; driver run completed on glass | READY |
| Rate cards | engine live; example org has published INR cards (RC-2026-MAIN) | READY (chart config = DAIRY INPUT) |
| Settlement | `/settlements` (200); free `period_from`/`period_to` cycles | READY (cycle = DAIRY INPUT) |
| Billing / receivables | `/reports/receivables` (200); INV-/CPY-/CRC- series | READY |
| Reports | dashboard, daily collection, receivables all 200 (12 report endpoints) | READY |
| Backup / restore | Phase 8 below — verified backup, off-site, healthy chain | READY |
| Audit trail | `/v1/audit` 200 | READY |
| RBAC / RLS | foreign-tenant resource → 404 (isolation holds) | READY |
| Mobile APK | debug APK wired to DEV; both personas proven on a real Motorola (P0-PILOT-004) | READY |

**Nothing was modified** — no blocker found on the platform side.

## Phase 2 — Real dairy onboarding sequence

Every step tagged: **READY** (works today) · **CONFIG** (operator config, no
code, no dairy data) · **DAIRY** (needs the dairy's real input) · **LEGAL**
(paperwork/signature) · **ENG** (engineering — none required unless the chart
proves otherwise, Phase 4).

| # | Step | How | Tag |
|---|---|---|---|
| A | Dairy organisation | Create org `country_code: IN` — INR/Kolkata/en-IN+hi-IN arrive by default | READY / CONFIG |
| B | Collection centres | One per physical centre; operating hours; status active; declare scale (blocking readiness check) | CONFIG + **DAIRY** (which centres) |
| C | Operator accounts | Invite COLLECTION_OPERATOR per centre; accept; login | READY / CONFIG |
| D | Driver accounts | Invite DRIVER; link to driver profile (`/drivers/{id}/user`) | READY / CONFIG |
| E | Farmer/supplier import | **Suppliers → Import CSV** (code, name, phone, village, centre codes); per-row validation; duplicates named | READY — **DAIRY** (the list) |
| F | Customer/outlet import | **Customers → Import CSV** with inline standing orders; re-import names duplicates | READY — **DAIRY** (the list + agreed prices) |
| G | Standing orders | Inline in F (plan: product, quantity, unit, agreed price) | READY — **DAIRY** |
| H | Routes | Routes + stops + vehicles; assign drivers | CONFIG — **DAIRY** (which routes) |
| I | Rate card | Create card → matrices per product (cow/buffalo) → FAT bands → **human review** → approve → publish | **DAIRY** (the chart) → CONFIG; **ENG only if Phase 4 finds an unsupported shape** |
| J | Settlement cycle | `period_from`/`period_to` per the dairy's cycle (10-day/fortnight/month all work) | READY — **DAIRY** (the rules) |
| K | Legal/business docs | FSSAI licence copy, LM scale certificate, signed pilot agreement, privacy notice + consent line (onboarding pack §2–4) | **LEGAL** |
| L | First-day checklist | Onboarding pack §1 (day-0) + Phase 9 below | READY |

**No engineering appears in this sequence** unless Phase 4 proves the chart
needs a shape the engine cannot represent.

## Phase 3 — Regulatory / paperwork boundary (from P0-REG-001, unchanged)

Only what actually applies before go-live; the dairy remains the regulated
entity. **No compliance module, no GST engine, no DLT/WhatsApp software.**

- **FSSAI licence copy** — the dairy's; verify it exists at onboarding
  (the number belongs on its own sale documents — a V1 field, stationery for
  the pilot). **LEGAL/DAIRY.**
- **Legal Metrology scale certificate** — the dairy's stamped trade scale;
  file copy at onboarding. **LEGAL/DAIRY.**
- **Pilot agreement + processor/privacy/consent** — onboarding pack §2–4
  (privacy notice, consent line, processor clause). **LEGAL.**
- **Maharashtra floor-price** — a human check in the rate-card review that the
  configured outcome at the reference quality pays ≥ the current GR floor;
  **not code.** Look up the current GR that day. **CONFIG/DAIRY.**
- BIS, DPDPA-module, e-invoicing: **not applicable / not before pilot.**

## Phase 4 — Rate card — DATA-DEPENDENT (STOP)

**No real rate chart exists in the repository.** Per the rule, none was
invented. What is confirmed on the platform side, live:

- The pricing engine is deployed and healthy; the example org carries a
  **published INR rate card** with cow/buffalo as separate products, and
  cow-vs-buffalo differentiated pricing was proven end-to-end (P0-BIZ-001).
- Engine shape today: FAT-banded, per-product, effective windows, per-centre
  scoping, **kg**, single-dimension (SNF captured, not priced).

**When the dairy's chart arrives**, compare against the engine per
LACTEVA-RATE-CHART-QUESTIONNAIRE. Implement **G-04 (litres)** or **G-05
(FAT×SNF grid / SNF deduction)** *only if the real chart requires them* — both
are bounded increments, not rebuilds. If the chart is FAT-banded per milk type
in kg, it is **configuration, not engineering.** **This phase cannot complete
without the chart.**

## Phase 5 — Real data import — DATA-DEPENDENT (STOP)

**No real farmer or outlet files exist.** The import path is proven and live
(`/suppliers/import`, `/customers/import`, portal CSV pages, per-row
validation, duplicate-naming, RLS) — but there is nothing real to import.
**When the files arrive**: validate, report duplicates/errors, import through
the existing paths, verify counts and representative records, confirm the
imported records participate in the real workflows. **No source data will be
altered or invented.**

## Phase 6 — Day-0 drill — platform proven; real-artifact drill DATA-DEPENDENT

The **platform's day-0 capability is already proven live** (P0-PILOT-004, on a
real handset against DEV):

- Procurement: farmer → centre → operator → weight → FAT/SNF → **rate** →
  transaction → **parchi (SLP-2026-000001)**; the collection COMPLETED and the
  slip rendered with byte-traceable figures.
- Sales: customer standing order → route → **driver run → delivery outcomes →
  completion**; invoices/receivables reachable.
- Reconciliation boundaries (parchi→settlement→payment; plan→delivery→invoice)
  are byte-traceable and were exercised in P0-PILOT-002/004.

The **drill on the DAIRY'S OWN artifacts** — the one that reconciles a real
collection to the dairy's own arithmetic to the paisa — is DATA-DEPENDENT and
is the first item of the go-live day (onboarding pack §1, "prove the day
works").

## Phase 7 — Mobile (no re-run of P0-PILOT-004)

Confirmed: the validation APK is built against DEV; **both personas were proven
on a real Motorola moto g57 power (Android 16)** with six on-glass defects
fixed and shipped (`main-2867a55`). Login, operator capture, driver run,
offline mode, and sync are proven. Running the app against the **real dairy's
tenant and data** is DATA-DEPENDENT (needs the org + imports). A second handset
is optional, not a blocker.

## Phase 8 — Backup / recovery (verified active, live)

Confirmed on the host on 2026-08-18 — **do not redesign, it is healthy:**

- Scheduled backup timers all active (nightly, weekly, verify, watchdog,
  disk-guard).
- **Newest backup verified** (`verified: true`, 42,113 rows).
- **Off-site S3 replication present** (recent objects listed).
- Restore path healthy — the drill was proven in P0-PILOT-002 (including the
  schema-revision fix so it does not false-fail on deploy days).
- **No active failure marker.**
- DEV retention deliberately trimmed to 2; **production must restore the
  30-day retention** (`BACKUP_RETAIN_DAYS`) before real financial operations —
  the one production-config note.

## Phase 9 — 7-day pilot control plan

Daily verification; responsible person in brackets. Every item uses a surface
that exists today. Fuller day-0 sequence in the onboarding pack §1; days 1–7
operations in §5.

| Day | Verify |
|---|---|
| **0 — Onboarding** *(pilot lead)* | Org + centres + logins created; farmers & outlets imported (counts match the files); rate card published after human review incl. the Maharashtra floor check; one real collection reconciled to the dairy's own arithmetic to the paisa; backup + off-site confirmed; legal docs on file |
| **1** *(operator/driver)* | Both shifts captured; quality recorded; **pricing correct** vs the chart; parchi handed over; one delivery run completed; audit trail populated |
| **2** *(operator)* | Full-volume capture; any `QualityDeviationFlagged` re-tested; offline capture + sync if signal drops; backup ran overnight |
| **3** *(operator + office)* | Collection continues; deliveries + invoices; receivables reviewed; exceptions logged |
| **4 — Settlement** *(office)* | Close the period per the dairy's cycle; review lines vs parchis; finalize; print statements; record payments |
| **5 — Reporting** *(owner)* | Dashboard + by-supplier + by-centre + receivables reviewed for the week; reconcile a sample end to end |
| **6 — Resilience** *(pilot lead)* | Airplane-mode capture + replay-once; operator retry (must 409, not duplicate); **restore last night's backup to a scratch instance**; off-site confirmed |
| **7 — Review** *(owner + pilot lead)* | Two reconciliations on paper — parchi→settlement→payment and plan→delivery→invoice→receivable; go/no-go on continuation |

## Phase 10 — Stop conditions

| Condition | Class |
|---|---|
| Four dairy artifacts absent (chart, farmers, outlets, settlement rules) | **PILOT BLOCKER** (data, not code) |
| Signed pilot agreement + FSSAI/LM copies | **PILOT BLOCKER** (legal/paperwork) |
| Production backup retention set to 30 days | **PILOT BLOCKER** (one config line) |
| Litres-based buying | **PILOT-CONDITIONAL** (only if the chart says litres — G-04) |
| FAT×SNF grid / SNF deduction | **PILOT-CONDITIONAL** (only if the chart is a grid — G-05) |
| Physical handset for the pilot dairy's own staff | **PILOT-CONDITIONAL** (validated generally; their device is onboarding) |
| Second handset, mobile-browser portal pass | PILOT-CONDITIONAL |
| Email (SMTP) for statements | PILOT-CONDITIONAL (config only) |
| SMS/DLT, WhatsApp/BSP | **V1** (vendor paperwork; never gates day 1) |
| Hardware connector (P0-HW-002) | **V1** (gated on discovery visit) |
| FSSAI number + GST fields on documents | **V1** |
| Advances/loans in settlements | **V1** |
| Payment gateway, SAP/ERP, GPS, farmer app, advanced AI/analytics | **FUTURE** |

**No V1/FUTURE item blocks the pilot.**

## Phase 11 — Engineering

**No code was changed.** No real-dairy requirement exposed a product defect,
and no chart is available to prove a pricing-shape gap. The milestone produced
configuration reconciliation, onboarding sequence, readiness evidence, and the
7-day plan — as intended.

---

## Final report (Phase 12)

1. **Executive verdict** — **DATA-DEPENDENT.** Platform go-live ready and
   verified live (`main-2867a55`); GREEN awaits the dairy's four artifacts,
   the legal signatures, and the one production backup-retention config.
2. **Real dairy artifacts received** — **none.** No rate chart, farmer list,
   outlet list, or settlement rules exist in the repository or `../Master`.
3. **Artifacts still missing** — all four, plus FSSAI/LM copies and a signed
   agreement.
4. **Organisation readiness** — READY (IN defaults verified live).
5. **Supplier/farmer readiness** — import path READY; **the list is DAIRY INPUT.**
6. **Outlet/customer readiness** — import path READY; **the list + agreed
   prices are DAIRY INPUT.**
7. **Rate-card readiness** — engine READY; **the chart is DAIRY INPUT**;
   G-04/G-05 engineering only if the real chart demands it.
8. **Settlement readiness** — engine READY; **the cycle rules are DAIRY INPUT.**
9. **Regulatory/paperwork readiness** — boundary defined; **licence copies +
   signatures are LEGAL/paperwork**, not software.
10. **Day-0 drill result** — platform capability proven live (P0-PILOT-004);
    the real-artifact reconciliation drill is DATA-DEPENDENT.
11. **Mobile readiness** — READY (both personas proven on a real handset);
    real-dairy-tenant run is DATA-DEPENDENT.
12. **Backup/recovery readiness** — READY and active (verified backup +
    off-site + healthy restore); production retention → 30 days is the one
    config to set.
13. **7-day pilot plan** — delivered (Phase 9 + onboarding pack).
14. **Remaining blockers** — the four artifacts; the legal signatures; the
    production backup-retention config. Nothing else.
15. **NOT PROVEN** — anything requiring the dairy's real data: rate
    configuration against the actual chart, real farmer/outlet import, the
    paisa-level reconciliation drill, and the app against the real tenant.
16. **Engineering changes** — **none** (no genuine blocker).
17. **Exact next action** — **obtain the four artifacts and the two document
    copies from the dairy, and get the pilot agreement signed.** Then: create
    the org, import, configure + review the rate card (implement G-04/G-05
    only if the chart needs it), set production backup retention to 30 days,
    and run the day-0 reconciliation. That is the go-live, and it is gated on
    the dairy, not on engineering.

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Go-live readiness: live Phase-1 reconciliation, onboarding sequence with per-step classification, regulatory boundary, backup verification, 7-day control plan, stop-condition matrix; verdict DATA-DEPENDENT (no artifacts fabricated) — P0-PILOT-005. |
