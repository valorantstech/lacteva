---
id: LACTEVA-PILOT-ONBOARDING-PACK
title: Pilot Onboarding Pack
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-PILOT-READINESS-GATE, LACTEVA-REGULATORY-APPLICABILITY-AUDIT, LACTEVA-RATE-CHART-QUESTIONNAIRE, LACTEVA-HARDWARE-INTEGRATION-SPEC]
baseline: ARCH-BASELINE-V1
---

# Pilot Onboarding Pack (P0-PILOT-002, Track D)

The operational and legal artifacts for onboarding one real Indian dairy.
**These are documents, not software** — per P0-REG-001, nothing here needs a
compliance module, and nothing here builds one. Bracketed values are filled
in per dairy.

---

## 1. Day-0 onboarding checklist (run in this order)

Everything below uses surfaces that exist and are tested today. Steps marked
⚑ need a business artifact from the dairy first.

**Before touching software**

- [ ] Signed pilot agreement including the processor clause (§4)
- [ ] File copy: the dairy's **FSSAI license/registration** (per unit —
      P0-REG-001 §1; verify the number appears on their current sale bills)
- [ ] File copy: **Legal Metrology verification certificate** for every trade
      scale at every centre, with validity date (P0-REG-001 §2)
- [ ] ⚑ The four business artifacts: rate chart (photographed), farmer list,
      outlet list with agreed prices/quantities, settlement-cycle rules
      (see LACTEVA-RATE-CHART-QUESTIONNAIRE for the exact questions)
- [ ] Privacy notice (§2) printed for each collection centre; consent line
      (§3) added to the dairy's supplier/outlet onboarding forms

**Platform (platform admin)**

- [ ] Create the organization with `country_code: "IN"` — INR,
      Asia/Kolkata, en-IN + hi-IN arrive by default (proven)
- [ ] Invite the tenant admin; they accept and sign in

**Organization (tenant admin)**

- [ ] Workspaces/branches to match the dairy's structure
- [ ] Collection centres (one per physical centre), operating hours, status
      `active`
- [ ] Declare equipment in the device registry (category `scale` per centre —
      it is a blocking readiness check; analyzer/printer as present)
- [ ] Invite people with the right roles: centre operators, one login per
      **driver** (role `DRIVER` only — they get the mobile run experience and
      the portal correctly refuses them), office/finance
- [ ] Link each driver login to their driver profile
      (`POST /v1/drivers/{id}/user`)
- [ ] ⚑ Farmer list → **Suppliers → Import CSV** in the portal (or
      `POST /v1/suppliers/import`); preview, import, fix failed rows;
      activate; print QR cards if used
- [ ] ⚑ Outlet list → **Customers → Import CSV** in the portal (or
      `POST /v1/customers/import`) — each row may carry its standing order
      (plan_product/quantity/unit/price); a re-import names duplicates
      instead of creating them twice
- [ ] Routes and stops; vehicles; assign drivers (logistics surface)
- [ ] ⚑ Rate card: create → matrices per product (cow / buffalo) → bands
      from the photographed chart → **human review** (next section) →
      approve → publish with the correct effective date

**Rate-card review (human check, five minutes — not software)**

- [ ] Bands transcribed against the photograph, four eyes
- [ ] **Maharashtra floor**: the configured outcome at the reference quality
      (3.5 fat / 8.5 SNF for cow) pays at or above the **current** GR
      minimum — look the current figure up that day, do not trust a cached
      one (P0-REG-001 §6)
- [ ] One known collection from the dairy's own recent parchi recomputed
      through the published card **to the paisa** before go-live

**Prove the day works (with the dairy watching)**

- [ ] One real collection end to end: identify → milk type → weight →
      quality → price → accept → complete → **parchi printed/shared**
- [ ] One delivery run: generate → driver phone → outcome → invoice visible
- [ ] ⚑ Settlement dry run for the dairy's cycle dates
      (`period_from`/`period_to` are free — 10-day, fortnight and month all
      work today)
- [ ] Confirm last night's backup exists and replicated off-site
      (`backup.cli status` / `offsite-list`; watchdog green)

## 2. Privacy notice (print per centre; one page)

> **[DAIRY NAME] — How we use your information**
>
> To run milk collection, delivery and payments, [DAIRY NAME] records in its
> Lacteva system: your name, code, phone number, village, milk type, and the
> quantity, quality (FAT/SNF/CLR) and value of the milk you supply or
> receive. For drivers and staff it records name, phone and work activity.
>
> This information is used only to operate the dairy's business — weighing,
> testing, pricing, receipts (parchi), settlements, deliveries and accounts
> — and to meet legal record-keeping duties. It is not sold and it is not
> used for advertising.
>
> The data is stored securely in India (AWS Mumbai region) by our software
> provider, Phoenix Software, which processes it only on our instructions.
> It is kept for as long as the law requires business and financial records
> to be kept.
>
> To see or correct your information, or for any question, contact:
> [NAME, PHONE] at [DAIRY NAME]. You may also raise concerns under the
> Digital Personal Data Protection Act, 2023.
>
> *[Hindi rendering to be printed alongside — the dairy's language wins.]*

## 3. Consent wording (one line on the onboarding form / register)

> "मैं सहमत हूँ / I agree that [DAIRY NAME] may record and use my name,
> phone number and milk transaction details in its computer system to run
> milk collection, receipts and payments, as described in the privacy
> notice."
>
> Name · signature/thumb · date. Keep the signed register at the centre.

Recorded operationally in the dairy's register — deliberately not a software
feature at pilot stage (P0-REG-001 §5: core DPDPA obligations commence
13 May 2027; this is hygiene and trust, done cheaply and honestly).

## 4. Processor clause (insert into the pilot agreement)

> **Data processing.** For personal data recorded in the Lacteva platform,
> [DAIRY NAME] is the Data Fiduciary and Phoenix Software ("Provider") is a
> Data Processor under the Digital Personal Data Protection Act, 2023. The
> Provider shall: (a) process such personal data only to provide and support
> the platform and only on the Dairy's documented instructions; (b) apply
> reasonable security safeguards, including tenant isolation, role-based
> access, encrypted transport, audit logging and scheduled verified backups;
> (c) not disclose such personal data to third parties except sub-processors
> required to host and operate the service (currently: Amazon Web Services,
> Mumbai region), or where required by law; (d) inform the Dairy without
> undue delay of any personal data breach affecting the Dairy's data;
> (e) on termination of the pilot, return or delete the Dairy's personal
> data on written instruction, subject to legally required retention of
> financial records; and (f) assist the Dairy, on reasonable request, in
> answering data principals' requests to access or correct their data.

*(Reviewed wording, not legal advice — the dairy's and Phoenix's signatories
adopt it as part of the commercial agreement.)*

## 5. Days 1–7 — running the pilot (P0-PILOT-003)

Daily rhythm; the responsible person in brackets. Everything here uses
surfaces that exist today.

**Every morning and evening shift** *(operator)* — open the session with the
right label; capture every collection fully (farmer → milk type → weight →
FAT/SNF → price shown → accept/reject → complete); hand over the parchi
(print or share). A `QualityDeviationFlagged` line in a transaction's trail
is information, not an accusation — re-test the sample, note the outcome.
*(driver)* — start the run on the phone, record every stop (delivered /
skipped / returned), complete the run; airplane-mode capture is fine, sync
when signal returns.

**Every evening** *(owner/office)* — portal dashboard: collections vs
yesterday, quantity, value, average FAT; deliveries and any skipped stops
(ask why); "who owes money" for anything unexpected.

**Settlement day(s), per the dairy's cycle** *(office)* — create the
settlement for the period, review lines against the parchis, finalize, print
statements; record payments as they are made.

**Day 6, deliberately** *(pilot lead)* — the failure drill: one airplane-mode
collection and replay; one operator retry (must 409, not duplicate); confirm
last night's backup replicated off-site (`backup.cli status` / watchdog
green).

**Day 7** *(owner + pilot lead)* — reconciliation, below, then the review.

### The two reconciliations (day 7, on paper)

**Milk bought:** pick any 3 parchis at random →
`quantity × rate = amount` on each slip → find each in the settlement's
lines → settlement total = sum of its lines → the amount paid/payable
matches. Any mismatch at any step is a finding — Lacteva's figures are
byte-traceable end to end, so the discrepancy is locatable.

**Milk sold:** pick any customer → standing order (plan) → the week's
generated deliveries → driver outcomes → invoice lines → invoice total →
payments/receivables. Same rule: every figure must trace.

## 6. Physical-handset validation script (Track C — run when a handset is available)

Device: any Android 10+ phone, Chrome not required. Install
`app-release.apk` (built against `https://dev.phoenixsoft.in`). Two runs:
one as a **driver** login, one as a **collection operator** login. Tick only
what is *seen on the glass*.

Driver: [ ] login · [ ] driver identity (linked profile loads; unlinked
login shows the calm "not set up as a driver" state) · [ ] today's route
with stops, names, phones, addresses · [ ] start run · [ ] record
delivered / skipped / returned · [ ] **airplane mode**: record two outcomes
offline, banner shows pending count · [ ] network back: sync replays each
outcome **once** (verify no duplicates on the portal) · [ ] complete run
(only when no stop is open) · [ ] Hindi locale walk of the same screens ·
[ ] no clipped/overflowing text on the smallest available handset.

Operator: [ ] login · [ ] open session (shift) · [ ] full capture: farmer →
milk type → weight → quality → price shown → accept → complete · [ ]
airplane-mode capture and replay-once · [ ] parchi visible/shared from the
portal for the captured transaction · [ ] Hindi walk.

Record the handset model, Android version, and every deviation. **Fix only
genuine defects found** (P0-UX-001 discipline).

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Initial pack: day-0 checklist, privacy notice, consent line, processor clause, handset validation script (P0-PILOT-002 Track D). |
