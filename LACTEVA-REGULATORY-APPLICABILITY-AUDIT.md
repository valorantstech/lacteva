---
id: LACTEVA-REGULATORY-APPLICABILITY-AUDIT
title: Indian Dairy Regulatory Applicability Audit
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-PILOT-READINESS-GATE, LACTEVA-RATE-CHART-QUESTIONNAIRE, LACTEVA-HARDWARE-INTEGRATION-SPEC, LACTEVA-PILOT-MASTER-ROADMAP]
baseline: ARCH-BASELINE-V1
---

# Indian Dairy Regulatory Applicability Audit (P0-REG-001)

**Audit only. Nothing implemented, no schema touched, no compliance module
built.** The question is not "what regulations exist" but "which government
requirements actually change what Lacteva must store, enforce, or ship —
and which are the dairy's own operational duties that software must merely
not obstruct."

**Headline findings, before the detail:**

1. **The dairy, not Lacteva, is the regulated entity everywhere.** FSSAI
   licenses the food business; Legal Metrology stamps the dairy's scale; GST
   binds the seller. Lacteva is never the license holder and enforces
   nothing by law.
2. **Lacteva already stores almost everything an FSSAI inspection asks a
   dairy for** — supplier-linked, timestamped, source-attributed,
   operator-attributed quality and quantity records with rejection reasons.
   The record-keeping burden regulators impose is Lacteva's core product,
   not a new requirement.
3. **A March 2026 FSSAI advisory pushed registration down to independent
   milk producers and vendors** — newly relevant to the pilot's farmers,
   but a farmer's own registration is their duty (and the dairy's awareness
   problem), not a software field.
4. **DPDPA's core obligations are not yet in force.** The DPDP Rules were
   notified 13 Nov 2025 with phased commencement: notice/consent/security/
   retention/rights obligations commence **13 May 2027**; penalties and
   consent-manager registration 13 Nov 2026. At pilot time (Aug 2026) the
   minimum notice+consent kit from P0-PILOT-001 is *prudent contract
   hygiene*, *not* a statutory blocker — a material correction to that
   audit's framing.
5. **One state rule genuinely touches the rate chart:** Maharashtra sets a
   minimum cow-milk procurement price by Government Resolution (₹34/L at
   3.5% fat / 8.5% SNF reference when issued, 2023; the current figure must
   be checked at configuration time). The dairy must not pay below it; in
   Lacteva that is a *rate-card review check*, not code.

---

## 1. FSSAI (Food Safety and Standards Act 2006 + Regulations)

The old Milk and Milk Products Order (MMPO 1992) is subsumed by the FSS Act
— it is **not** a separate live requirement, and this audit deliberately
does not resurrect it.

| Requirement | Class | Who is responsible | Lacteva impact |
|---|---|---|---|
| **License/registration for the dairy business** — Registration (petty FBO), State License (dairy units ~501–50,000 L/day or 2.5–2,500 MT solids/yr), Central License (>50,000 L/day). Milk chilling/collection units are explicitly covered categories | **MANDATORY BY LAW** | Dairy (per premises/unit) | Lacteva stores nothing by law. **Product value (C):** an org/centre-level FSSAI license-number field, because of the invoice rule below |
| **FSSAI number on sale documents** — FSSAI order (8 Jun 2021, in force 1 Oct 2021): the FBO's 14-digit license/registration number must appear on invoices/cash receipts/bills | **MANDATORY BY LAW** (for the dairy's sale documents) | Dairy | **The one FSSAI item that touches Lacteva documents**: customer invoices/receipts Lacteva prints should carry the dairy's FSSAI number. Pilot: handled operationally (pre-printed stationery / the number typed into the org name line). **V1 (B): org-level FSSAI number field rendered on invoices/receipts.** The farmer parchi is a *purchase* record from an unregistered-supplier context — not the document this order targets |
| **Milk composition standards** (FSSR 2011: e.g. cow milk min ~3.2% fat / 8.3% SNF, buffalo ~5.0/9.0 — state-schedule variations) — milk below standard cannot be *sold* as milk | **MANDATORY BY LAW** (at point of sale) | Dairy | Lacteva stores FAT/SNF per collection already. **Not enforced by software**: procurement below sale standards is legal (dairies buy low-fat milk at low rates); the *sale* side is the dairy's blending/QC duty. Optional product value: the existing plausibility bounds + the recommended anomaly flag |
| **Hygiene (Schedule 4)** — premises, equipment, personnel, storage/transport (food-grade containers, chilling ≤ prescribed temp, clean tankers) | **MANDATORY BY LAW** (conditions of license) | Dairy, collection centre, transporter | **Operational, no software.** Lacteva's arrival-temperature field and container identity are supporting evidence, already captured, never a legal duty of the software |
| **Quality/testing records; procurement source records** — license conditions require dairy units to keep records of raw-milk source, testing, production | **MANDATORY BY LAW** (record-keeping condition) | Dairy | **Lacteva IS this record** — supplier-linked, timestamped FAT/SNF/CLR with operator, source, rejection reason, immutable snapshots and an event log. Nothing new to store. This is a selling point, not a gap |
| **2026 enforcement drive** — nationwide surveillance of licensed and unlicensed dairy units; fortnightly state reporting; rapid-test-kit availability and test-result records at vending points | **MANDATORY where ordered** (directions to states/FBOs) | Dairy (and state authorities) | None for the pilot's software. Lacteva's records make an inspection *easier*; kiosk rapid-test-kit logs are out of pilot scope (no vending kiosks in the pilot model) |
| **11 Mar 2026 advisory: registration for independent milk producers/vendors** | **MANDATORY (advisory directing existing law's application)** | Farmer/vendor themselves | Nothing to store or enforce. The dairy should *know* which of its farmers are registered; if a pilot dairy asks, a supplier-level "FSSAI reg. no." note fits the existing supplier profile's extra fields — **Optional (C), on request only** |
| FSMS (Food Safety Management System) guidance documents for dairy | **GUIDANCE / BEST PRACTICE** | Dairy | None. Do not convert guidance into software requirements |

**Should Lacteva eventually capture** (recommendation only, no fields added
now): the org's and each centre's FSSAI license number (for documents), and
— it already captures — supplier identity, milk type, quantity, FAT/SNF,
quality result, rejection reason, date/time, operator, device presence,
arrival temperature. The traceability ask is already answered by the
existing transaction chain.

**Pilot blocker? No.** The dairy must hold its license (its duty, existing
or obtainable independently of Lacteva); everything else is operational or
already stored.

## 2. Legal Metrology (Act 2009 + General Rules 2011)

| Requirement | Class | Who | Lacteva impact |
|---|---|---|---|
| **Any weighing instrument used for trade** (milk bought by weight = trade) must be an approved model, **verified and stamped** by Legal Metrology, and **re-verified periodically** (annually for most electronic scales; up to 24 months for some classes; state practice varies) | **MANDATORY BY LAW** | Dairy / collection centre (the user of the instrument) | Lacteva stores nothing by law and must enforce nothing. The dairy keeps the verification certificate at the centre |
| Verification certificate retention; producing it on inspection | **MANDATORY BY LAW** | Dairy | None mandatory. **Optional product value (C):** the existing `Device` registry (category `scale`, serial number, status) is the natural home for verification metadata — `verified_until`, certificate reference — and the readiness check could *warn* on expiry. Genuinely useful; **not required for the pilot**; would be a natural part of P0-HW-002 |
| **Milk analyzers (FAT/SNF)** — quality instruments, not weight-or-measure instruments; not in the notified verification categories of the General Rules. Some states have periodically pushed to verify "fat testing machines" | **NOT MANDATORY under central rules; VERIFY with the pilot state's LM office** (discovery item, added to the hardware checklist conversation) | Dairy, if the state requires it | None now |
| Packaged Commodities Rules (declarations on pre-packed goods) | **NOT APPLICABLE TO PILOT** (loose-milk collection and B2B supply; applies if the dairy retails pre-packed products) | Dairy | None |

**What the dairy must do:** keep every trade scale stamped and in-date.
**What Lacteva may optionally record:** manufacturer, model, serial (exists
today), verification status/date/certificate (future columns on the existing
registry — recommended for P0-HW-002, not before).

**Pilot blocker? No.** An unstamped scale is the dairy's legal problem on
day −1, with or without software.

## 3. BIS

| Standard area | Class | Lacteva impact |
|---|---|---|
| IS methods of test for dairy (e.g. fat/SNF determination methods), IS specs for milk cans, dairy equipment | **VOLUNTARY** (industry practice; FSSAI references test methods for official analysis) | None |
| Scales/load cells — model approval under Legal Metrology (which leans on OIML/IS specs) | Mandatory only *via* Legal Metrology model approval, which attaches to the **manufacturer**, not the dairy | None — the dairy buys an approved model; §2 covers the use |
| Quality Control Orders (QCOs) | **No QCO applies to raw-milk collection or to dairy management software** | None |
| ISI-marked packaged products (if the dairy later makes such products) | Product-specific, future | None for pilot |

**Nothing in BIS affects Lacteva's software for this pilot.**

## 4. GST / taxation

Post the 56th GST Council (effective 22 Sep 2025): **fresh and pasteurised
milk are exempt; UHT milk, paneer and curd (incl. pre-packaged) exempt;
butter/ghee/cheese 5%**. The pilot's business — raw/fresh milk procurement
from farmers and B2B fresh-milk supply — is therefore an **exempt-supply
business end to end**.

| Item | Class | Lacteva impact |
|---|---|---|
| GST registration (₹40 lakh goods threshold; exempt-only suppliers not required to register) | Dairy's duty, fact-dependent | None to enforce |
| Document form: a registered dealer supplying exempt goods issues a **bill of supply**, not a tax invoice; unregistered dealers issue ordinary invoices | **MANDATORY BY LAW** (for a GST-registered dairy) | **V1 (B):** document title/GSTIN/HSN (0401) fields on customer documents. **Pilot:** at exempt-milk scale, current invoices carry no tax and are substantively correct; the title nuance is handled operationally |
| Agriculturist exemption — farmers supplying their own milk are outside GST; no reverse charge on fresh milk | Settled law | None — farmer settlements correctly carry no tax |
| E-invoicing (₹5 crore turnover, taxable supplies) | **NOT APPLICABLE** to an exempt-only pilot | None now; FUTURE if the dairy sells taxable products (ghee/butter) through Lacteva billing |
| TDS/income-tax on farmer payments | Dairy's accountant's domain | **NOT LACTEVA RESPONSIBILITY** |

**Verdict: no pilot blocker. V1: GSTIN + FSSAI number + document-type
polish on invoices. FUTURE: tax lines/e-invoicing only if taxable products
enter scope.**

## 5. DPDPA (Digital Personal Data Protection Act 2023 + Rules 2025) — the challenge, answered

- **Is it a dairy-industry regulation? No** — it is a horizontal data law;
  it applies because names and phone numbers of farmers, customers' contact
  people, and drivers are digital personal data.
- **Data principals:** farmers/suppliers, drivers, operators, customer
  contact persons.
- **Roles:** the **dairy is the Data Fiduciary** (it decides why farmer data
  is collected). **Lacteva/Phoenix is a Data Processor** processing on the
  dairy's behalf under contract. Phoenix is a fiduciary only for its own
  direct relationships (e.g. portal user accounts it manages for itself).
- **What is in force at pilot time (Aug 2026):** the Act and Rules are
  notified, the Data Protection Board machinery exists, **but the core
  operational obligations (notice, consent artefacts, security/breach/
  retention rules, data-principal rights) commence 13 May 2027**; penalty
  provisions and consent-manager registration begin 13 Nov 2026.
- **Therefore:** the P0-PILOT-001 "DPDPA minimum kit" is **not a statutory
  pilot blocker**. What is *actually* required at pilot stage:
  1. a **processor clause in the pilot agreement** (dairy = fiduciary,
     Phoenix = processor acting on instruction, deletion on termination) —
     paperwork, not software;
  2. the one-page **privacy notice and consent line remain recommended**
     — they are cheap, they build farmer trust, and they make the dairy
     ready for May 2027 — but they are downgraded from "blocker" to
     "before-pilot hygiene";
  3. existing security (RLS, RBAC, audit, TLS, backups-once-scheduled) is
     the processor-control substance and already exceeds pilot needs.
- **Not required now:** consent managers, DPO, DPIAs, breach-notification
  tooling, a compliance module. Do not build any of it.

## 6. Other central/state requirements (pilot state assumed Maharashtra)

| Requirement | Class | Lacteva impact |
|---|---|---|
| **Maharashtra minimum cow-milk procurement price** (GR-set floor for cooperatives and private dairies; ₹34/L at 3.5/8.5 when issued in 2023 — **check the current GR at rate-card configuration time**); monthly reporting by district dairy officers | **MANDATORY (state direction)** | The dairy must configure rate cards whose outcomes respect the floor. **Operational**: a check in the rate-card approval step's human review. No code; noted in the rate-chart questionnaire conversation. Lacteva's rate history is the dairy's *evidence of compliance* |
| State Dairy Development Commissioner registrations/schemes (cooperative registration, subsidies) | Dairy's corporate matter | **OUTSIDE LACTEVA** |
| Prevention of adulteration enforcement (now under FSSA; state FDA drives) | Covered in §1 | Records already exist |
| Animal husbandry / cattle rules, pollution consent for processing plants, shop & establishment, labour law | Real laws, **not milk-collection-software-relevant** | **OUTSIDE LACTEVA** — listed once to close the question, per the "no giant catalogue" instruction |

## 7. Responsibility matrix

| Requirement | Authority | Dairy | Centre | Farmer | Transporter | Retail/customer | **Lacteva** |
|---|---|---|---|---|---|---|---|
| FSSAI license/registration | FSSAI / State FDA | **License holder** | Covered under dairy's license (per-premises) | Own registration (Mar 2026 advisory) if selling independently | Own registration as FBO | Own license for resale | **None** |
| FSSAI number on sale documents | FSSAI | **Must display** | — | — | — | — | Render the number on invoices (V1 field; pilot via stationery) |
| Milk sale composition standards | FSSAI | **Must meet at sale** | Quality gatekeeping | Delivers what it delivers | — | — | Stores the readings (already) |
| Hygiene/storage/transport (Sch. 4) | FSSAI | **Comply** | **Comply** | Clean containers | **Comply** | — | None |
| Procurement/testing records | FSSAI | **Keep records** | Operates the capture | — | — | — | **Is the record system** (already) |
| Scale verification & stamping | Legal Metrology (state) | **Get stamped, keep certificate** | Uses only stamped scale | — | — | — | Optional registry metadata (P0-HW-002) |
| Minimum procurement price | State (GR) | **Pay ≥ floor** | — | Beneficiary | — | — | Rate-card review is where the dairy checks it |
| GST documents | CBIC | **Correct document type** | — | Exempt (agriculturist) | — | Receives documents | V1 document fields |
| DPDPA (from Nov 2026 / May 2027) | MeitY / DPB | **Fiduciary** | — | Data principal | Data principal (drivers) | Contacts are principals | **Processor** — contract clause now, notice/consent hygiene |

## 8. Lacteva product impact

**A. MUST IMPLEMENT BEFORE FIRST PILOT — nothing.** No regulation compels a
software change before a pilot whose dairy holds its own licenses and a
stamped scale.

**B. MUST IMPLEMENT FOR V1** — org/centre **FSSAI license number** rendered
on customer invoices/receipts; **GSTIN + HSN + document-type** ("bill of
supply") polish on the same documents; DPDPA processor-grade paperwork
templates as part of the standard customer contract (legal artifact, tiny
config surface).

**C. OPTIONAL PRODUCT VALUE** — scale **verification metadata + expiry
warning** on the existing device registry (fold into P0-HW-002); supplier
FSSAI-registration note in the existing profile extras (only if a dairy
asks); the FAT/SNF anomaly flag (supports the adulteration-surveillance
climate; already the chosen AI MVP).

**D. CUSTOMER OPERATIONAL RESPONSIBILITY** — holding FSSAI licenses;
scale stamping and certificates; hygiene/cold chain; paying at or above the
state floor; GST registration decisions; farmer-registration awareness.

**E. OUTSIDE LACTEVA** — farmer/transporter/retailer licensing, animal
husbandry and environmental rules, labour law, subsidies, state dairy
scheme paperwork.

## 9. Final answer

### What government requirements actually matter to Lacteva (≤10)

1. **FSSAI number on sale documents** — the one FSSAI rule that touches
   Lacteva's printed output. V1 field; stationery for the pilot.
2. **The dairy's FSSAI license existing at all** — verify it during pilot
   onboarding (a question, not a feature).
3. **Legal Metrology stamping of the centre's scale** — dairy's duty;
   verify certificate exists at onboarding; optional registry metadata
   later.
4. **Maharashtra's minimum procurement price** — a floor the configured
   rate card must respect; check the current GR on configuration day.
5. **GST document correctness for a registered dairy** (bill of supply,
   GSTIN, HSN 0401) — V1 polish; substance already correct for exempt milk.
6. **DPDPA processor clause in the pilot agreement** — paperwork now;
   notice/consent hygiene before pilot; full obligations land May 2027.
7. **FSSAI record-keeping conditions** — already satisfied by the product;
   say so in sales conversations, keep it true in engineering ones.
8. **The Mar 2026 farmer-registration advisory** — awareness item for the
   dairy's supplier relations; at most an optional profile note.
9. **State-specific analyzer-verification practice** — one question for the
   state LM office, folded into hardware discovery.
10. **2026 FSSAI surveillance drive** — context, not requirement: it makes
    the dairy value exactly the records Lacteva already keeps.

### What we should NOT build (≤10)

1. A compliance module, dashboard, or "FSSAI mode".
2. Any enforcement of sale-composition standards at procurement time.
3. A GST engine, tax lines, or e-invoicing for an exempt-milk pilot.
4. DPDPA consent managers, DPO tooling, DPIA workflows, breach-notification
   machinery.
5. Legal-metrology certificate management ahead of P0-HW-002.
6. BIS anything.
7. State-subsidy / cooperative-scheme paperwork features.
8. Rapid-test-kit kiosk logging (no kiosks in the pilot).
9. Traceability features beyond the existing chain (it already answers the
   ask).
10. Any field "because a regulation exists" rather than because the pilot
    dairy's documents or inspectors need it.

### What should happen next

Unchanged from P0-PILOT-001, now regulator-checked — the four real blockers,
with one softened and one added question:

1. **Install and prove the scheduled off-host backup** (unchanged; also the
   substance of processor-grade data protection).
2. **Obtain the four business artifacts** (chart — checked against the
   current Maharashtra floor GR — farmer list, outlet list, settlement
   rules).
3. **DPDPA minimum**: processor clause in the pilot agreement (paperwork),
   plus the notice + consent line as before-pilot hygiene — *no longer
   framed as a statutory blocker*.
4. **Physical-handset validation day** (unchanged).
5. **At onboarding, ask for two documents**: the dairy's FSSAI license and
   the scale's Legal Metrology certificate — file copies, zero code.

---

*Primary sources consulted: FSSAI licensing categories and dairy-unit
thresholds; FSSAI order of 8 Jun 2021 (license number on documents); FSSAI
2026 enforcement-drive directions and the 11 Mar 2026 milk-producer
registration advisory; Legal Metrology Act 2009 / General Rules 2011
verification and re-verification practice; 56th GST Council outcomes
effective 22 Sep 2025 (PIB); DPDP Rules 2025 notification of 13 Nov 2025
and phased commencement (PIB); Government of Maharashtra minimum cow-milk
rate notification (₹34/L at 3.5/8.5, effective 21 Jul 2023). Where state
practice varies (re-verification intervals, analyzer verification), this
audit says "verify with the state office" rather than asserting.*

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Initial regulatory applicability audit: FSSAI, Legal Metrology, BIS, GST, DPDPA commencement analysis, Maharashtra floor price, responsibility matrix, product impact A–E, final ≤10 lists (P0-REG-001). |
