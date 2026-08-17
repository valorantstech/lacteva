---
id: LACTEVA-COLLECTION-HARDWARE-AUDIT
title: Collection Centre & Hardware Architecture Audit
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-17
last-updated: 2026-08-17
related: [LACTEVA-PILOT-MASTER-ROADMAP, LACTEVA-PRODUCT-AUDIT]
baseline: ARCH-BASELINE-V1
---

# Collection Centre & Hardware Architecture Audit

The final architecture challenge before P0 engineering starts. Every statement
below is repository evidence, file-and-line verified on 2026-08-17. Nothing was
implemented or modified.

**Headline:** the collection centre is the *most* complete part of Lacteva —
richer than the master roadmap represented — and the hardware question was
answered by design two product-specs ago: **PSP-0007 defines "Basic profile"
(operator-entered readings, written receipts) as a legitimate equipment class,
not a degraded mode.** A real Indian collection centre can run the pilot on the
Basic/Standard profile with zero hardware integration, and the capture seams
(`weight_source` / `quality_source`, production-refused mocks) are already
shaped for devices to arrive later without schema change.

---

## 1. Collection domain — what exists

**Entities (all REAL, RLS-forced, deployed):**

| Entity | Evidence | Notes |
|---|---|---|
| `CollectionCenter` (+Config, OperatingWindow, CalendarEntry) | `collection_center/models.py` | branch-owned, own timezone, hours, holiday calendar |
| `CollectionSession` | `milk_collection/models.py:45` | open/close per centre, **`label` e.g. "morning" — the shift concept exists** |
| `MilkCollectionTransaction` | `models.py:58` | the star of this audit — see field list below |
| `TransactionEvent` (append-only, sequenced) | `:112` | `WeightCaptured` etc. — full capture audit trail |
| `TransactionSnapshot` | `:127` | immutable completed-state record |
| Supplier (+profile, documents, bank accounts, centre placements, QR, **CSV import**) | supplier module | |
| Rate cards → pricing matrices → resolution → calculator | pricing module | single-axis bands (roadmap P0-BIZ-001 stands) |
| Settlement (periods, immutability, carry-forward, statements) → payment records → receipts | settlement/payment/receipt | |

**The transaction model carries the entire centre workflow** (`models.py:58–109`):
supplier, operator, session (shift), centre, state machine; `milk_type` +
`milk_type_custom` (**cow/buffalo/custom — already supported**); container type/id,
arrival temperature; `gross/tare/net_weight` + `weight_unit` + **`weight_source`**;
`fat`, `snf`, `clr`, `density`, quality temperature/remarks + **`quality_source`**;
`unit_price`, `gross_amount`, `currency`, `calculation_id`, `pricing_detail`
(rate provenance); accept/reject with reason and decider; timestamps.

**Farmer → collection → quality → quantity → rate → settlement is complete and
proven** — it is the platform's oldest, most-tested path (the seeder builds a
month of it; settlements carry BR-0008…12 and the PILOT-001 carry-forward fix).

**Missing (confirming the roadmap, adding two details):**
1. Farmer-facing slip/parchi — P0-BIZ-003, confirmed (see §4).
2. A **human-readable transaction reference** — transactions are UUID-only; no
   number is minted for them (`document_numbers.py` exists and is extensible by
   `doc_type`, so this is small). Fold into P0-BIZ-003.
3. Two-axis fat×SNF / kg-fat pricing — the P0-BIZ-001 question, unchanged.
4. Centre→plant **dispatch/handover** (PSP-0001's Transporter actor, MCL.PCK.02)
   — no trip/handover entity exists. **Not a pilot need** for a single-site
   dairy; V1/V2 (see §10-C).

**Verdict: the data model is sufficient for a real collection centre pilot.**

## 2. Personas — who exists, who is conflated

| Persona | Reality in the repository |
|---|---|
| **Farmer/supplier** | Data subject only. No supplier-scoped principal (verified: `tenancy.py` has customer scope only). Roadmap correctly defers the farmer app; the slip is their artifact. |
| **Collection operator** | **REAL persona.** `COLLECTION_OPERATOR` role; mobile *collection experience* (wizard, sessions, offline); scoped to procurement — holds **no** `sales.*` or `logistics.*` grants. |
| **Delivery driver** | Record only (`driver` table, nullable `user_id`), **no persona** — the P0 gap, confirmed. |
| **Dairy operator/admin** | REAL — tenant-admin / ORGANIZATION_MANAGER, full portal. |
| **Customer** | REAL, read-only mobile portal (customer scope). |
| **Sales officer** | REAL — "runs the milk round and the customer book"; holds `logistics.run.manage`. |
| **Transporter** (centre→plant) | Named in PSP-0001, **not modeled**. Not pilot-relevant. |
| **Maintenance technician** | Named in PSP-0007 (calibration events), not modeled. V2. |

**Conflation check — one real risk found:** the mobile "delivery experience" is
keyed on `sales.delivery.record` (`session.dart:249`) — a *sales-operator*
capability. If P0-MOB-002 reused that key, every sales officer would land in the
driver experience and vice versa. **P0-MOB-001 must introduce a distinct driver
capability** (e.g. own-runs read/execute) rather than overloading the operator
grant. The roadmap said "DRIVER role"; this audit sharpens it to *a new
capability key, not a reuse*.

Otherwise the separation is clean: collection roles cannot touch delivery,
delivery roles cannot touch procurement, and the shared `vehicle`/`driver`
registry is direction-neutral **by explicit design** (MCL.LGX.01: "transport
capability, shared with collection") — reuse, not coupling.

## 3. Hardware — every reference in the tree

| Finding | Evidence |
|---|---|
| **Mock adapters only**: `MockScaleAdapter`, `MockAnalyzerAdapter` — deterministic readings hashed from container id | `infrastructure/hardware.py` |
| **Production-refused**: `mock_hardware_enabled` gate + `MockHardwareRefused`, enforced in the adapter *and* the service (`_refuse_mock_source`), because SEC-003/F-01 found a fabricated weight had been priced, settled, paid and receipted | `hardware.py:8–17`, `milk_collection/service.py:443` |
| **The seam is the `source` vocabulary**: `WeightCaptured`/quality commands carry `source: "manual" \| "mock_scale"` / `"manual" \| "mock_analyzer"`, persisted per transaction as `weight_source`/`quality_source` | `service.py:138,145`; `models.py:81,90` |
| **Device registry + reported health + readiness engine**: categories scale, milk_analyzer, **printer**, qr_scanner, rfid_reader, camera; statuses registered→assigned→active→maintenance→retired; readiness classes blocking/warning/none | `operational_readiness/models.py` |
| **No device protocol anywhere**: zero serial/USB/Bluetooth/RS-232/TCP-device code (every "serial" hit is a `serial_number` registry field or English prose) | verified grep |
| **The hidden design the roadmap missed: PSP-0007 Hardware Profiles** — Basic / Standard / Automated equipment classes per centre; which measurements are instrument-read vs operator-entered; opening checks; calibration windows; **declared fallbacks** (analyzer down → lactometer + flag; printer down → written receipt + flag) | `docs/13-products/lacteva-collect/PSP-0007` |

**What the roadmap missed:** not an integration — a *classification*. PSP-0007
already answers "is hardware required?" with profile classes, and the pilot
simply runs on Basic/Standard. The profile itself is documentation-only today
(not a field on the centre); realizing it as data belongs with the first real
device (V1).

## 4. Receipt / parchi

The current receipt module is **payment receipts only** (immutable
proof-of-payment from completed payments). No collection-level artifact exists.

**But every required parchi field already exists on the transaction:**

| Parchi field | Source |
|---|---|
| Farmer ID/name/code | `supplier_id` → supplier profile |
| Milk type (cow/buffalo) | `milk_type` / `milk_type_custom` |
| Quantity | `net_weight` (+gross/tare) + `weight_unit` |
| FAT / SNF / CLR | `fat`, `snf`, `clr` (+density, temperature) |
| Rate | `unit_price` + `pricing_detail` provenance |
| Amount | `gross_amount` + `currency` |
| Shift | `session_id` → `CollectionSession.label` ("morning") |
| Date/time | `created_at` / `completed_at` |
| Collection centre | `center_id` → centre name/code |
| Reference number | **missing** — UUID only; extend `DocumentSequence` (exists, per-doc-type) or derive a short code |

**Conclusion: P0-BIZ-003 is a render-and-share task plus a reference number —
no schema beyond (at most) the sequence row, no new capture logic.** Thermal
printing is V1 (PSP-0007's Basic fallback — written/printed slip — is
legitimate); the digital slip shareable via WhatsApp when the channel lands is
*better* than the Basic profile requires.

## 5. Quantity + quality — how values actually arrive

**Manually entered, and only manually, in production.** The capture commands
accept `source="manual"`; the only alternative values are the mocks, which are
production-refused at two layers. Nothing is imported, nothing is hardware-fed,
and the mock path cannot leak into real data (that exact leak is the defect
SEC-003 fixed, with the guard placed so *no* caller — HTTP, offline replay,
script, future module — can bypass it). Rate is **calculated** by the pricing
engine from the captured values; amount is stored with full provenance.

This is exactly how a Basic/Standard-profile Indian centre operates today with
paper registers — the operator reads the analyzer's display and types it.

## 6. Collection logistics vs delivery logistics — coupling check

Correctly separated, verified at four layers:

* **Tables**: `route_stop.customer_id` — routes/runs are *delivery-side* only;
  collection has sessions/transactions, no routes.
* **Permissions**: `collection.*` vs `sales.*`/`logistics.*` — disjoint role
  grants (COLLECTION_OPERATOR holds none of the latter).
* **Modules**: `milk_collection` and `delivery` are separate bounded contexts
  ("a collection is a payable, a delivery is a receivable — they share a shape
  and nothing else"); `logistics` composes `delivery` only.
* **The one shared thing is deliberate**: the vehicle/driver registry is
  direction-neutral per MCL.LGX.01 so a future collection trip reuses the same
  fleet — that is the capability register's requirement, not an accident.

No accidental coupling found.

## 7. P0-MOB-001/002 — delivery driver, verified

Confirmed **unambiguously the delivery driver**: the experience is built on
`delivery_run` → route → `route_stop.customer_id` → customer deliveries.
Nothing in it touches suppliers, sessions or collection. A milk-collection
driver/transporter would need the (non-existent) dispatch/handover domain —
out of scope, and the backlog should say so explicitly (§10-C).

One sharpening (from §2): the driver experience must key on a **new**
capability, not `sales.delivery.record`, or operators and drivers collapse into
one persona again.

## 8. GPS — removing it breaks nothing

Verified: **zero** location assumptions exist anywhere — no coordinate column,
no map, no location permission in the mobile app, no API expecting position.
Every existing workflow (collection, delivery, runs, reports) is
location-free. Dropping GPS from the pilot is the *status quo*, not a removal.
`P1-HW-001` (event-based capture at delivery confirmation) remains an optional
stretch aligned with "event-based proof, later, optional" — and is explicitly
**not** vehicle tracking. Lacteva is not becoming a GPS company; nothing in the
tree pulls it that way.

## 9. Indian collection-centre gaps beyond the roadmap

From repository evidence only:

| Item | Status | Disposition |
|---|---|---|
| Shift (morning/evening) accounting | **exists** (session labels) | none |
| Cow/buffalo | **exists** | none |
| CLR/lactometer + density | **exists** as quality dimensions/fields | none |
| Per-shift centre totals for the operator | exists via reports; centre summary on mobile | none |
| Transaction reference for the slip | missing | fold into P0-BIZ-003 |
| Farmer ledger view ("what do I owe this farmer to date") | exists (settlements/statements); portal supplier detail | none |
| Farmer **advances/loans & deductions** (feed, cattle-feed credit) | settlements carry an `adjustments_amount` and BR-0011 currently pins adjustments **fixed at 0** — line-item deductions are NOT modeled | **V1** — common cooperative practice; ask the pilot dairy (a second P0-BIZ-001-style question), do not build speculatively |
| Centre→plant dispatch/handover | not modeled | V1/V2, multi-site dairies only |
| Calibration/opening checks | readiness engine covers device health; calibration windows are PSP-0007 paper only | V1 with first device |

The **advances/deductions question** is the one genuinely new business finding
of this audit: if the pilot cooperative nets feed advances out of farmer
settlements (many do), BR-0011's "adjustments fixed at 0" placeholder becomes a
pilot conversation. Ask alongside the rate chart; classify after the answer.

## 10. Roadmap challenge — verdict against LACTEVA-PILOT-MASTER-ROADMAP.md

**A. KEEP** — driver as P0 (scoped to delivery); slip as P0; rate-chart question
as P0-BIZ-001; no-GPS pilot; channel strategy and vendor paperwork as the
critical path; onboarding kit; consent; hardware out of the pilot; the four
checkpoints; the seven-gap blocker list.

**B. CHANGE**
1. **P0-MOB-001**: specify a *new driver capability key*; do not reuse
   `sales.delivery.record` (conflation risk, §2/§7).
2. **P0-BIZ-003**: scope now includes a human-readable transaction reference
   (DocumentSequence extension or derived code) — still 1–2 days.
3. **P0-BIZ-001** widens into the *pilot dairy questionnaire*: rate chart **and**
   advances/deductions practice **and** equipment profile (PSP-0007 class of
   their centre). Three questions, one conversation, zero code.

**C. ADD**
* **P1-OPS-006 — Pilot hardware discovery (zero code):** record the pilot
  centre's actual devices, makes/models, and PSP-0007 profile class during
  onboarding; feeds V1 device selection. Effort ~0.
* **P2-BIZ-010 — Settlement deductions/advances line items** (conditional on
  the questionnaire; supersedes BR-0011's fixed-0 placeholder deliberately).
* **P3-BIZ-011 — Centre→plant dispatch/handover** (Transporter actor,
  MCL.PCK.02) for multi-site dairies.
* **(fold) hardware-profile-as-data + calibration checks** into P2-HW-002
  (first scale integration) rather than as separate items.

**D. REMOVE/DEFER** — nothing over-prioritized found; reaffirm deferrals:
printer-direct integration (browser/share print suffices), analyzer integration,
continuous GPS, farmer app.

**E. PILOT BLOCKERS — unchanged seven**, with the two scope sharpenings above.
Hardware is **not** added to the blockers.

**F. V1** — first weighing-scale integration (one model, one protocol, behind
the existing `source` seam + profile-as-data + calibration checks); thermal
slip printing; deductions/advances if the questionnaire says so; Tally export;
broadcast; cash reconciliation.

**G. V2/FUTURE** — analyzer integration (auto per-member capture), dispatch/
handover, cold-chain/IoT, dedicated trackers/geofencing, maintenance-technician
workflows.

## 11. The hardware decision

**Hardware integration is: PILOT DISCOVERY ONLY.** Not a blocker, not pilot
engineering.

The decision is grounded in code, not preference:

1. **The product spec already legitimizes hardware-free operation** — PSP-0007's
   Basic profile (operator-entered, written receipts) is an equipment *class*,
   with Standard (instrument-read, operator-typed) as the realistic pilot centre.
   Lacteva running profile-appropriate is by-design, not a compromise.
2. **The capture path is already device-shaped**: `source` vocabulary on every
   weight/quality capture, persisted per transaction, with the mock branch
   production-refused at two layers. A real scale is a new `source` value and an
   adapter behind the same commands — **no schema, no workflow change** when V1
   arrives.
3. **The registry, health reporting and readiness engine already exist** for the
   day devices appear.
4. **No protocol exists and no device model is confirmed** — integrating now
   would mean picking hardware before the pilot centre tells us what it owns,
   which is backwards. The discovery item (§10-C) captures that answer for free.

First hardware engineering: **V1, the weighing scale** — it closes the largest
trust gap (typed weights) with the smallest protocol surface. Analyzer follows
in V2.

---

*Audit only. No code, schema, migration, production or DEMO change was made.*

## Change Log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-17 | Collection-centre + hardware challenge of the pilot master roadmap; roadmap amended per §10, hardware classified pilot-discovery-only. |
