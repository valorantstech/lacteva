---
id: LACTEVA-P0-PILOT-008-REAL-DAIRY-ONBOARDING-READINESS
title: Real Dairy Onboarding & Production Readiness
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-MASTER-PRODUCT-ROADMAP, LACTEVA-GO-LIVE-READINESS, LACTEVA-PILOT-ONBOARDING-PACK, LACTEVA-COMMERCIAL-MODEL-AND-PACKAGING, LACTEVA-P0-PILOT-006-DEV-ONBOARDING-REHEARSAL, LACTEVA-IDENTITY-ENTERPRISE-ARCHITECTURE-AUDIT, LACTEVA-HARDWARE-CONNECTOR-DISCOVERY, LACTEVA-REGULATORY-APPLICABILITY-AUDIT]
baseline: ARCH-BASELINE-V1
---

# Real Dairy Onboarding & Production Readiness (P0-PILOT-008)

**Operational readiness definition only — no code, schema, migration, or
production change.** This consolidates the committed onboarding pack, go-live
readiness, commercial model, and the P0-PILOT-006 synthetic rehearsal into one
**executable runbook** for onboarding the first real Indian dairy. It changes
no prior decision. **No dairy data, rate chart, farmer, outlet, settlement rule,
FSSAI/GST detail, or signature is invented** — every such item is requested from
the dairy and tagged accordingly.

Tag legend: **READY** (exists/proven) · **CONFIG** (operator configuration) ·
**DATA** (dairy must supply) · **BUSINESS** (commercial) · **LEGAL** (paperwork/
signature) · **ENG** (engineering — none unless a defect is found) ·
**TO CONFIRM**.

---

## A. Executive verdict

**Technically READY; the remaining critical path is DATA / BUSINESS / LEGAL,
not engineering.** The platform (deployed `main-2867a55`) runs the full dairy
lifecycle; onboarding mechanics — org creation, hierarchy, invitation-based
users with one identity and scoped roles, farmer/outlet CSV import, rate-card
publish, settlement, collection, parchi, delivery, billing — are all proven
(P0-PILOT-006 synthetic rehearsal end to end; P0-PILOT-004 on a physical
handset). **No engineering blocks the first dairy.** The gates are: the four
business artifacts + FSSAI/LM copies + a signed agreement + one production
config (backup retention → 30 days). This milestone produces the exact runbook
to execute the day those arrive. **No genuine defect found; no code changed.**

## B. Real-dairy onboarding lifecycle (per step)

| Step | Status |
|---|---|
| Prospect dairy → commercial agreement | **BUSINESS + LEGAL** (30-day trial terms, signed) |
| Organization creation (`country_code: IN`) | **READY / CONFIG** (INR/Asia-Kolkata/en-IN+hi-IN by default) |
| Centre setup (branches → centres, hours, active, scale device) | **CONFIG** + **DATA** (which centres) |
| User / role onboarding (invite → accept → grant scope) | **READY / CONFIG** + **DATA** (who + role + centre) |
| Farmer import (`/suppliers/import`, portal CSV) | **READY** + **DATA** (the list) |
| Outlet import (`/customers/import`, portal CSV, inline plans) | **READY** + **DATA** (the list + agreed prices) |
| Rate card (create → matrices per product → bands → **human review** → publish) | **DATA** (the chart) → **CONFIG**; **ENG only if the chart needs litres/FAT×SNF** |
| Settlement rules (period, cycle) | **DATA** (rules) → **CONFIG** (free `period_from`/`period_to`) |
| Operational configuration (readiness, devices, routes/vehicles) | **CONFIG** + **DATA** |
| Legal / document check (FSSAI, LM, agreement) | **LEGAL** |
| Day-0 reconciliation (§L) | **CONFIG** + **DATA** + dairy sign-off |
| Production | **READY** once above complete |
| 7-day pilot (§M) | operational |
| Paid subscription / expansion | **BUSINESS** (per-centre STANDARD; prices TO CONFIRM) |

**Conditional ENG (only if the real chart demands it):** litres support (kg-only
today), FAT×SNF grid / SNF deduction (engine is single-axis). Both bounded
increments; neither known to be needed. **DATA-DEPENDENT until the chart is seen.**

## C. Required dairy information checklist (request pack)

**A. Organization** — legal/business name; org details; operating locations;
branches/centres; contact person(s). *(DATA)*
**B. Collection centres** — name; address; centre code; operating hours; centre
manager/operator names. *(DATA)*
**C. Users** — person name; mobile/email; role; centre scope; which apps.
*(DATA)*
**D. Farmers** — farmer code (if any); name; mobile; village/address; centre;
milk type (cow/buffalo). *(DATA)*
**E. Customers/outlets** — code (if any); name; address; contact; route (if
any); agreed price + standing quantity. *(DATA)*
**F. Rate card** — the **actual chart photographed**; milk types; cow/buffalo;
**litres or kg**; FAT/SNF/CLR rules *if actually used*; effective date;
slabs/bands; deductions/additions. *(DATA — see LACTEVA-RATE-CHART-QUESTIONNAIRE)*
**G. Settlement** — period length + start day; reconciliation/approval rules;
any deductions. *(DATA)*
**H. Legal/business documents** — **only what prior audits require**: FSSAI
licence copy; Legal Metrology scale certificate (where applicable); signed pilot
agreement + privacy notice/consent (onboarding pack §2–4). **No other
regulatory item is invented** (per LACTEVA-REGULATORY-APPLICABILITY-AUDIT).
*(LEGAL)*

## D. Organization / centre setup checklist

- [ ] Create org `country_code: IN` — verify INR / Asia-Kolkata / en-IN+hi-IN. *(READY/CONFIG)*
- [ ] Onboard the tenant-admin (invite → accept). *(READY)*
- [ ] Workspace(s) → Branch(es) matching the dairy's structure. *(CONFIG + DATA)*
- [ ] One collection centre per physical centre; operating hours; status `active`. *(CONFIG + DATA)*
- [ ] Register the centre's scale device (blocking readiness check). *(CONFIG + DATA)*

## E. User onboarding checklist

For each person: invite (role) → accept (sets credential) → grant the named role
at scope → confirm login + `/auth/me`. **One identity per person; no per-app
credential.** *(READY — proven in P0-PILOT-006 for all nine roles.)*

- [ ] Owner / org admin / org manager (org scope)
- [ ] Centre manager, collection operator (centre scope)
- [ ] Finance manager/officer, sales officer (org scope)
- [ ] Driver (create profile → invite → **link** `/drivers/{id}/user` → assign vehicle/route)
- [ ] Auditor (org read)

## F. Role + application access matrix (real dairy)

| Role | Identity | Centre scope | Portal | Collection App | Driver App | Future apps |
|---|---|---|---|---|---|---|
| Org owner/admin/manager | one | org | ✓ | (as needed) | — | Coming Soon |
| Centre manager | one | centre | ✓ | ✓ | — | — |
| Collection operator | one | centre | refused office | ✓ | — | — |
| Finance manager/officer | one | org | ✓ | — | — | Coming Soon |
| Sales officer | one | org | ✓ | — | — | Coming Soon |
| Driver | one | own runs | refused office | — | ✓ | — |
| Auditor | one | org read | ✓ (read) | — | — | — |

**Login users** = the rows above. **Business records (NOT logins):** farmers,
customers/outlets. **Assets (NOT logins):** devices. *(Unchanged from the
identity/enterprise audit; future farmer/customer portals are FUTURE OPTION,
shown only as Coming Soon.)*

## G. Farmer import checklist

- [ ] CSV columns: code, full_name, phone, village, center_codes. *(READY)*
- [ ] Preview; rows missing the required column are flagged **before** send.
- [ ] Import; **duplicates named, not silently created**; one bad row fails alone.
- [ ] Verify count matches the file; spot-check representative records.
- [ ] Activate; assign to centres; print QR cards if used. *(DATA)*

## H. Outlet / customer import checklist

- [ ] CSV columns: name, customer_type, phone, address, plan_* (product,
      quantity, unit, price). *(READY)*
- [ ] Preview; import; **re-import names duplicates** (name+phone).
- [ ] Verify count; confirm standing orders (plans) created. *(DATA — agreed prices)*

## I. Rate-card checklist

- [ ] Transcribe the **photographed** chart into card → matrices per product
      (cow/buffalo) → FAT bands. *(DATA → CONFIG)*
- [ ] **Human review, four eyes**: bands vs the photograph.
- [ ] **Maharashtra floor check**: outcome at the reference quality (3.5 fat /
      8.5 SNF for cow) pays ≥ the **current** GR minimum — look it up that day.
      *(CONFIG check, not code; LACTEVA-REGULATORY-APPLICABILITY-AUDIT §6)*
- [ ] Recompute one known collection from the dairy's own recent parchi through
      the published card **to the paisa** before go-live.
- [ ] Publish with the correct effective date. *(published cards immutable;
      corrections are new versions)*
- [ ] **If the chart is litres or FAT×SNF grid → raise the conditional ENG
      increment first.** *(DATA-DEPENDENT)*

## J. Settlement checklist

- [ ] Configure the period per the dairy's cycle (`period_from`/`period_to` —
      10-day / fortnight / month all work). *(DATA → CONFIG)*
- [ ] Dry-run a settlement for one period; review lines vs parchis; confirm
      totals. *(CONFIG)*
- [ ] Confirm any deductions/advances handling (**advances/loans is a V1 gap** —
      if the dairy needs it at collection time, flag as V1, not a pilot blocker).

## K. Legal / business artifact checklist

- [ ] Signed pilot agreement incl. the **processor clause** (onboarding pack §4).
- [ ] **FSSAI licence** copy on file (the dairy's; verify the number appears on
      its current sale bills). *(LEGAL/DATA)*
- [ ] **Legal Metrology scale certificate** + validity, per centre. *(LEGAL/DATA)*
- [ ] Privacy notice printed per centre; consent line on the dairy's onboarding
      forms (onboarding pack §2–3). **DPDPA remains general data-governance,
      not a dairy regulation or a feature.**

## L. Day-0 execution checklist

**Technical verification (Lacteva runs):**
- [ ] Org, centres, users, roles, permissions created; access spot-checked
      (operator refused office page; driver → mobile). *(READY)*
- [ ] Farmers, outlets imported — counts match. *(DATA)*
- [ ] Rate card published + reviewed (incl. floor check). *(DATA/CONFIG)*
- [ ] Settlement rules configured; dry-run reconciles. *(DATA/CONFIG)*
- [ ] **One real collection end to end**: identify → milk type → weight →
      FAT/SNF → price → accept → complete → **parchi** printed/shared. *(READY)*
- [ ] **One delivery run** (if in scope): generate → driver phone → outcome →
      invoice visible. *(READY)*
- [ ] Reporting surfaces answer (dashboard, daily, receivables). *(READY)*
- [ ] Audit trail populated. *(READY)*
- [ ] **Backup verified + off-site**; production retention set to 30 days. *(CONFIG)*

**Dairy business sign-off (the dairy confirms):**
- [ ] The parchi matches what the dairy expects a farmer to receive.
- [ ] The recomputed collection matches the dairy's own arithmetic **to the
      paisa**.
- [ ] The settlement cycle and figures are correct.
- [ ] Named owner signs off to begin the 7-day pilot.

## M. 7-day pilot control plan

| Day | Monitor | By | Evidence | PASS | STOP |
|---|---|---|---|---|---|
| **0 Onboarding** | full setup + Day-0 checklist | pilot lead | screenshots, counts, reconciled sample | all §L green + sign-off | any §N condition |
| **1** | both shifts captured; quality; **pricing correct**; parchi | operator + lead | parchis, tx list | collections match reality | rate/parchi mismatch |
| **2** | full-volume capture; deviation flags re-tested; offline+sync if used; backup ran | operator | sync log, backup status | no data loss; flags sane | sync loss / backup fail |
| **3** | deliveries + invoices; receivables | office | invoices, receivables report | figures reconcile | billing mismatch |
| **4 Settlement** | close period; review lines; finalize; statements; payments | finance | settlement statement | lines = parchis | settlement mismatch |
| **5 Reporting** | dashboard + by-supplier/centre/receivables | owner | reports | week reconciles | unexplained variance |
| **6 Resilience** | airplane-mode capture + replay-once; operator retry (must 409); **restore last backup to scratch** | lead | restore log | replay-once; restore clean | duplicate / restore fail |
| **7 Review** | two paper reconciliations (parchi→settlement→payment; plan→delivery→invoice) | owner + lead | reconciliation sheet | both reconcile | material gap |

**Values (thresholds, acceptable variance): TO CONFIRM with the dairy** — do not
invent success metrics. "Correct pricing" means byte-identical to the dairy's
own arithmetic, which is objective.

## N. Stop conditions

**Genuine STOP (halt the pilot; investigate):** incorrect rate calculation;
settlement mismatch; data corruption; duplicate transaction that is not caught;
unauthorized access / wrong centre visibility; import corruption; offline-sync
data loss; parchi ≠ recorded transaction; **production backup failure**;
required legal/business artifact missing at go-live.

**Classify before halting** (these are **not** engineering defects): operator
entry error; wrong rate-card value transcribed (fix the card); missing/late
dairy data; a configuration choice (period, scope) set wrong. **A genuine
engineering defect** is only when the platform computes/stores/authorizes
*incorrectly given correct input* — then document precisely and propose the
smallest fix (per the milestone's rule). None is known.

## O. Real vs Test vs Not Proven

| | REAL / LIVE PROVEN | TEST / SYNTHETIC PROVEN | NOT YET PROVEN |
|---|---|---|---|
| Collection → parchi | ✓ live on DEV + on a physical handset (P0-PILOT-004) | ✓ synthetic org end-to-end (P0-PILOT-006) | with the **real dairy's chart/data** |
| Driver run / delivery | ✓ on a physical handset (P0-PILOT-004) | ✓ existing suite | with real routes/outlets |
| Offline capture + sync | ✓ on glass (P0-PILOT-004) | ✓ suite | real dead-zone field test |
| Onboarding + roles + RLS | ✓ RLS 404 live (P0-PILOT-005) | ✓ 9 roles, multi-centre, RLS (P0-PILOT-006) | with real people/data |
| Rate configuration | — | engine proven (cow/buffalo) | **the real chart** |
| Settlement cycle | ✓ engine | ✓ suite | **real rules + reconciliation to paisa** |
| Backup / restore | ✓ verified + off-site live | ✓ | production retention → 30d |
| Mobile (this milestone) | — | — | **NOT PROVEN this milestone** (already REAL in P0-PILOT-004; no handset attached now) |

**Prior real evidence is not downgraded; synthetic evidence is not upgraded to
real-world proof.**

## P. Hardware boundary

Manual-first is a **first-class, sufficient** mode for the pilot. **P0-HW-003
remains strictly evidence-gated** (LACTEVA-HARDWARE-CONNECTOR-DISCOVERY §29).
This milestone implements **no** connector functionality. Devices are assets in
the registry, not logins.

## Q. Future / Coming Soon boundary

Not implemented; shown only as **non-interactive roadmap labels** where useful:
AI beyond the MVP flag; SAP/ERP; GPS; WhatsApp/SMS providers; farmer app;
customer/outlet portal; chilling/BMC; plant/processing; enterprise SSO; global
identity; advanced analytics; hardware automation (before its gate). **No fake
screens/APIs/data/buttons.**

## R. Ownership matrix — Dairy vs Lacteva

| Item | Dairy | Lacteva |
|---|---|---|
| Rate chart, farmer/outlet lists, settlement rules | **provides** | configures |
| FSSAI licence, Legal Metrology certificate | **holds/provides** | files copy, verifies presence |
| Signed agreement, consent register | **signs/keeps** | provides templates |
| Org/centre/user setup | approves | **executes** |
| Imports, rate-card build, settlement config | validates | **executes** |
| Day-0 reconciliation | **signs off** | runs verification |
| Backup/restore, production config | — | **owns** |
| Scale stamping, hygiene, cold chain, floor-price compliance | **owns (regulated entity)** | records/evidences |
| Paying the subscription | **buyer** | invoices (when billing exists) |

## S. Final go-live checklist (the gate)

- [ ] Signed agreement (incl. processor clause). *(LEGAL)*
- [ ] FSSAI licence + Legal Metrology certificate copies on file. *(LEGAL/DATA)*
- [ ] Four artifacts received: rate chart, farmer list, outlet list, settlement
      rules. *(DATA)*
- [ ] Org + centres + users + roles created and access-checked. *(CONFIG)*
- [ ] Farmers + outlets imported; counts verified. *(DATA/CONFIG)*
- [ ] Rate card published + human-reviewed + floor-checked + paisa-reconciled.
      *(DATA/CONFIG)*
- [ ] Settlement rules configured + dry-run reconciles. *(DATA/CONFIG)*
- [ ] Production backup retention set to 30 days; backup verified + off-site.
      *(CONFIG)*
- [ ] Day-0 technical verification green + **dairy business sign-off**.
- [ ] Conditional ENG (litres / FAT×SNF) done **only if the chart required it**.

**When every box is checked, Lacteva is go-live for this dairy.** Not before —
and none of the unchecked boxes is engineering (barring the conditional).

## T. Open questions / TO CONFIRM

The dairy's operating model (M1 assumed); rate-chart shape (drives conditional
ENG); settlement cycle + reconciliation rules; pilot commercial terms + whether
the trial is the standard 30 days; per-currency STANDARD price + PSP (billing);
pilot success thresholds/variance; whether procurement transport or advances/
loans are in the pilot's scope (assumed no). **All business/data, none blocking
the runbook itself.**

## U. Exact next action

**Send the §C request pack to the dairy and get the agreement signed.** When the
four artifacts + two document copies arrive, execute §D–§L, set production backup
retention to 30 days, and run the Day-0 reconciliation. That sequence **is** the
go-live. **No engineering precedes it** (barring a chart-driven conditional
increment). Do **not** start P0-HW-003 (evidence-gated) or any other milestone
automatically.

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Real-dairy onboarding readiness runbook: per-step lifecycle, dairy information request pack, org/centre/user/farmer/outlet/rate-card/settlement/legal checklists, role+application access matrix, Day-0 technical-verification vs business-sign-off, 7-day pilot control plan, stop conditions, real/test/not-proven matrix, hardware + Coming-Soon boundaries, dairy-vs-Lacteva ownership matrix, final go-live gate, open questions. Definition only — no code, no invented data/prices/regulations; all prior decisions preserved (P0-PILOT-008). |
