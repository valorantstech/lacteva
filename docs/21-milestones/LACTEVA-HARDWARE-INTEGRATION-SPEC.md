---
id: LACTEVA-HARDWARE-INTEGRATION-SPEC
title: Dairy Collection Hardware Discovery & Integration Specification
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-COLLECTION-HARDWARE-AUDIT, LACTEVA-RATE-CHART-QUESTIONNAIRE, LACTEVA-PILOT-MASTER-ROADMAP, PSP-0007]
baseline: ARCH-BASELINE-V1
---

# Dairy Collection Hardware Discovery & Integration Specification

**P0-HW-001 — discovery and specification only.** Nothing in this document is
implemented by it. No schema, code or production state changes with this
milestone; the deliverable is the exact shape of the integration and the exact
list of facts the pilot dairy must supply before a line of connector code is
justified. Where this document names a device family or protocol, it is a
*discovery hypothesis to verify*, never an assumption to build on.

The governing verdict is inherited from the hardware audit
(LACTEVA-COLLECTION-HARDWARE-AUDIT): **the pilot can run with zero hardware
integration** on PSP-0007's Basic/Standard profile — operator-entered
readings are a legitimate equipment class, not a degraded mode. Hardware
integration is an *upgrade to trust and speed*, not a launch dependency.

---

## 1. Current architecture (verified in code, 2026-08-18)

The observed dairy workflow maps onto the platform one-to-one, and every stage
already exists:

```
FARMER
  ↓ supplier identity        Supplier + SupplierProfile; QR/code/phone/manual
MILK COLLECTION CENTRE       CollectionCenter + CollectionSession (shift label)
  ↓
QUALITY MEASUREMENT          capture_quality → fat/snf/clr/density/temp + quality_source
  ↓
QUANTITY MEASUREMENT         capture_weight → gross/tare/net kg + weight_source
  ↓
RATE CALCULATION             PricingResolution → PricingCalculation (FAT bands, per product)
  ↓
COLLECTION TRANSACTION       MilkCollectionTransaction (state machine, event log, snapshot)
  ↓
PARCHI / RECEIPT             slip_number (SLP-YYYY-NNNNNN) + GET /milk-transactions/{id}/slip
  ↓
SETTLEMENT                   SettlementService, period aggregation, STL- series
```

The state machine is spec-mandated and immutable after completion:
`NEW → SUPPLIER_IDENTIFIED → MILK_RECEIVED → WEIGHT_CAPTURED →
QUALITY_PENDING → QUALITY_CAPTURED → PRICING_PENDING → PRICED →
ACCEPTED | REJECTED → COMPLETED`. Every step is state-guarded, appended to an
ordered per-transaction event log, audited, and published on the outbox bus.

## 2. Existing collection capability (the audit the work order asked for)

| # | Asked | What exists — file-verified |
|---|---|---|
| 1 | Transaction model | `modules/milk_collection/models.py` — `MilkCollectionTransaction` with tenant/session/center/supplier/operator ids, state, container identity, timestamps, `slip_number` |
| 2 | Quality fields | `fat, snf, clr, density, quality_temperature_c, quality_remarks` + plausibility bounds (`QUALITY_RANGES`: fat 0–15, snf 0–15, clr 20–40, density 1.000–1.150, temp 0–50) |
| 3 | Quantity fields | `weight_unit ("kg" only, enforced), gross_weight, tare_weight, net_weight` (rounded to 3 dp), `MAX_GROSS_KG = 200`, tare < gross enforced |
| 4 | Source fields | `weight_source` / `quality_source`, vocabulary today `manual \| mock_scale` and `manual \| mock_analyzer`; **mocks are production-refused twice** — in the adapter (`infrastructure/hardware.py`) and in the service (`_refuse_mock_source`), so HTTP, offline replay, and any future caller all hit the guard (SEC-003/F-01, born from FINAL-001 where a SHA-256 of a container id got priced, settled and paid) |
| 5 | Equipment/profile concepts | PSP-0007 hardware profiles (Basic/Standard/Advanced) **and** a live device registry: `operational_readiness.Device` (`category ∈ scale, milk_analyzer, printer, qr_scanner, rfid_reader, camera`; statuses registered→assigned→active→maintenance→retired; unique `(tenant, serial_number)`) + `DeviceHealthReport` (ok/degraded/failed). An **active assigned scale is a blocking readiness check** for opening a session; analyzer and printer are warnings — PSP-0007's profile ladder, already executable |
| 6 | Collection APIs | `POST /v1/milk-transactions` then per-step `/identify /milk /weight /quality /accept /reject /complete /cancel`; sessions `/collection-sessions` open/close |
| 7 | Parchi | P0-BIZ-003: `slip_number` minted at completion from the shared document series; `GET /v1/milk-transactions/{id}/slip` returns every receipt field + shareable bilingual text; portal prints slip-only |
| 8 | Audit/events | Ordered `TransactionEvent` log (`WeightCaptured` / `QualityCaptured` events **carry the source**), tenant audit log, outbox bus events `collection.*.v1`, immutable `TransactionSnapshot` at completion |
| 9 | Permissions/RLS | `collection.*` and `operations.device.read/manage` permission keys; every table above is tenant-owned under PostgreSQL RLS (FORCED), enforced in the database and proven by the PG suites |
| 10 | Offline | OFF-001: mobile queue + `SyncService.push` replaying `open_session, close_session, create_transaction, identify_supplier, receive_milk, capture_weight, capture_quality, accept, reject, complete, cancel` — each maps 1:1 onto an online endpoint (deliberately no offline-only kind), with idempotent operation ids, so the entire capture flow already tolerates a dead network |

**Conclusion of the audit:** the platform does not need a hardware
architecture — it already has one, missing only real device protocol
adapters and the local process to run them in.

## 3. The hardware boundary (the one rule)

```
HARDWARE (analyzer / scale / printer)
   ↓  raw reading, device identity, timestamp
LOCAL CONNECTOR / DEVICE ADAPTER          ← the ONLY new component
   ↓  authenticated call, source-attributed reading
LACTEVA COLLECTION API                    ← existing /weight and /quality steps
   ↓
COLLECTION TRANSACTION                    ← existing engine, unchanged
   ↓
RATE ENGINE → SETTLEMENT → PARCHI         ← existing, source-agnostic
```

**A device changes only the `*_source` value and who types the number.**
Hardware supplies measurements and provenance — never a price, never a
decision, never a settlement figure. The transaction stays owned by Lacteva;
the rate engine and settlement remain byte-for-byte indifferent to where a
reading came from. Pricing or settlement logic inside a device integration is
a defect by definition.

## 4. Device classes

No manufacturer, model, or protocol below is decided. Each subsection states
what the platform already holds, what the connector must obtain, and what
discovery must answer. Interface families named (RS-232, USB-serial,
Bluetooth SPP, LAN, ESC/POS) are the families commonly met in Indian
collection centres — listed so the connector design stays open to all of
them, **not** so any is presumed.

### A. FAT/SNF milk analyzer

Platform side (exists): `capture_quality` accepts fat, snf, clr, density,
temperature_c; plausibility bounds enforced; `quality_source` stored;
`milk_analyzer` device category registered as a *warning-level* readiness
check. The mock adapter's `AnalyzerReading` dataclass (fat/snf/clr/density/
temperature_c) is the exact shape a real adapter must fill.

Discovery must establish (per §11): manufacturer, model, physical interface
(RS-232 / USB / Bluetooth / LAN), wire format (line protocol, CSV, binary
frame, vendor software export), polling vs push, whether the device reports
FAT, SNF, CLR/density, temperature; whether it reports **milk type** (some
analyzers carry a cow/buffalo mode switch — if so the connector reports it as
*metadata to reconcile*, never as the authority: the operator's declared milk
type on the transaction remains canonical); whether readings carry a device
serial and timestamp; calibration indication.

### B. Weighing / quantity device

Platform side (exists): `capture_weight` accepts gross+tare in **kg only**
(`unit != "kg"` is refused today), net computed and rounded to 3 dp, 200 kg
gross ceiling, blocking readiness check. `ScaleReading(gross_kg, tare_kg)` is
the adapter shape.

Discovery must establish: manufacturer, model, interface, output precision and
stability signal (many scales stream until the weight settles — the connector
must send only a *stable* reading), whether the display is kg or litres.
**If the dairy buys by litres**, conversion is a *pricing/business* question
answered by the rate-chart questionnaire (§A.5 there), not a connector
feature: the connector reports what the instrument measured, in the unit it
measured; unit expansion of `capture_weight` is a platform increment with its
own tests, not a device-side conversion. Tare handling (weighed empty can vs
stored tare table) must also be discovered.

### C. Receipt printer

Platform side (exists): the parchi is complete without any printer — the
portal prints the slip through the browser (slip-only print stylesheet), and
the slip's plain text is shareable (WhatsApp/SMS-ready, bilingual). PSP-0007
already defines the fallback ladder: printer down → written receipt + flag.

Strategy (§10 details): browser printing is sufficient for the pilot's
office; a *centre-side thermal printer* is the likely field reality and, if
discovery confirms one, printing becomes a **connector responsibility**
(render the slip's text to the printer's command set — commonly ESC/POS, to
be verified), fed from the existing slip endpoint. Lacteva's server never
talks to a printer directly.

## 5. Proposed adapter architecture

One new deployable: the **Lacteva Centre Connector** — a small agent on
whatever machine the centre already has (discovery item: Windows PC / Android
device / nothing), structured as:

```
┌────────────────────────── centre connector ──────────────────────────┐
│  device adapters (one per protocol)     core                         │
│  ┌───────────────┐  ┌───────────────┐   ┌────────────────────────┐   │
│  │ analyzer      │  │ scale         │   │ reading buffer (local, │   │
│  │ adapter       │  │ adapter       │──▶│ deduplicated, stamped  │   │
│  └───────────────┘  └───────────────┘   │ with device id + time) │   │
│  ┌───────────────┐                      └───────────┬────────────┘   │
│  │ printer       │◀── slip text/commands            │ authenticated  │
│  │ adapter       │                                  ▼ HTTPS          │
│  └───────────────┘                        Lacteva Collection API     │
└──────────────────────────────────────────────────────────────────────┘
```

Design rules, all inherited from what exists:

* **Adapters implement the shapes the mocks defined** (`ScaleReading`,
  `AnalyzerReading`) — the mock adapters are the interface contract, and they
  stay production-refused; a real adapter registers under a real source name.
* **Readings enter through the existing capture endpoints.** No new
  transaction API. The recommended interaction is *read-assist*: the reading
  lands in the operator's capture screen pre-filled and source-attributed,
  and the operator confirms — the human stays in the loop at Standard
  profile. Hands-free auto-capture is an Advanced-profile increment, later.
* **Source vocabulary extends, schema does not.** `weight_source`/
  `quality_source` gain instrument values (e.g. `scale`, `analyzer`) with the
  reading's `device_id` recorded in the already-source-carrying
  `WeightCaptured`/`QualityCaptured` events; the columns, states and
  downstream flow are untouched — exactly the seam P0-BIZ-001/003 documented.
* **The connector is registered equipment.** It authenticates as a
  device-scoped principal tied to one tenant and one centre, using the
  existing `Device` registry as its identity anchor (§9).

## 6. Data flow (one collection, Standard profile with connector)

1. Operator opens the session; readiness checks (active scale — blocking)
   pass as today.
2. Operator starts a transaction, identifies the farmer (QR/code/phone/
   manual) — unchanged.
3. Milk step: operator declares milk type (cow/buffalo/…) — canonical,
   unchanged.
4. Weight step: scale adapter reports a stable reading → pre-filled
   gross/tare with `weight_source=scale` + device id → operator confirms →
   `capture_weight`. Scale silent? Operator types the numbers,
   `weight_source=manual`. Same endpoint, same validation, same event.
5. Quality step: analyzer adapter reports fat/snf/clr/… →
   `quality_source=analyzer` → operator confirms → `capture_quality`.
   Same fallback symmetry.
6. Pricing, accept/reject, complete, slip minting — entirely unchanged and
   source-blind.
7. Parchi: portal print, shared text, or (if discovery confirms a thermal
   printer) the connector's printer adapter renders the slip.

## 7. Source attribution

Provenance is already a first-class fact (PSP-0007 §3; DEMO-007 surfaced it
to the API "the difference between 10 kg and 10 kg, entered by hand"). The
rules going forward:

* Every reading records **how it was obtained** (`manual` vs instrument
  source) and, for instruments, **which registered device** produced it.
* The parchi and the API keep showing the source; trust analytics and fraud
  detection consume it (per PSP-0007).
* Mock sources remain production-refused, permanently — the double guard
  stays, and a real adapter never reuses a `mock_*` name.
* Fallback use is visible: a manual reading at an instrumented centre is not
  an error, but it is *recorded as manual* — the shift record shows it,
  exactly as PSP-0007 prescribes.

## 8. Offline / failure behaviour (specified, mostly already true)

| Condition | Required behaviour | Status |
|---|---|---|
| Device unavailable | Operator captures manually; `*_source=manual`; transaction identical in shape | **Exists** — manual is the default path today |
| Network unavailable | Whole capture flow queues on the operator device and replays through `SyncService` with idempotent operation ids | **Exists** (OFF-001; all 11 kinds) |
| Device connected, no reading | Connector must never block the operator: read-assist times out silently and the manual fields stay usable | Specify in connector; no platform change |
| Duplicate device reading | Connector deduplicates at the buffer (device id + reading id/stable-timestamp); the platform's state machine independently refuses a second `capture_weight` on a `WEIGHT_CAPTURED` transaction (409) | **Platform half exists**; connector half specified |
| Operator retry | Step endpoints are state-guarded — a stale retry gets a clean 409, not a duplicate | **Exists** |
| Transaction retry / replay | Offline replay is idempotent per operation id; keyed HTTP requests go through `IdempotentRoute` | **Exists** (and RLS-proven since P0-MOB) |

Nothing here requires implementation now; the two "specify" rows are
connector requirements for P0-HW-002.

## 9. Security requirements

* **Device authentication:** the connector holds a credential issued at
  registration time, bound to (tenant, centre, device). The existing `Device`
  registry row is the identity anchor; the credential form (scoped token vs
  mTLS) is an implementation decision for P0-HW-002 — what is non-negotiable
  is that it is *per-device*, revocable (`retired` status must kill access),
  and **never stored in source control**.
* **Local connector authentication:** operators do not authenticate *to* the
  connector; the connector feeds readings into the operator's authenticated
  session flow (read-assist), so the human action stays attributable to the
  human. A hands-free future mode would act under the device principal with
  its own permission key — registry entry first, guard second, test third.
* **Tenant isolation:** unchanged — RLS FORCED on every table involved; a
  device credential carries exactly one tenant and can name no other. The
  cross-tenant answer stays 404.
* **Replay protection / duplicate prevention:** idempotency keys on keyed
  routes, per-operation ids in sync, state-machine 409s, and connector-side
  reading dedup (§8).
* **Audit trail:** existing — transaction event log with source, tenant audit
  log, immutable snapshot. Instrument readings add the device id to the
  events they produce; no new audit machinery.
* **Source attribution:** §7; the attribution *is* a security control — it is
  what makes a fabricated reading distinguishable after the fact.

## 10. Printer strategy

1. **Pilot day one (no integration):** portal browser printing (exists,
   slip-only stylesheet) + shareable slip text + PSP-0007's written-receipt
   fallback. This is sufficient to start; the parchi already reaches the
   farmer.
2. **If discovery confirms a centre thermal printer:** the connector's
   printer adapter renders the slip — sourced from the existing slip
   endpoint's `text` (already short-line, printer-plain, bilingual) — to the
   printer's command set (verify ESC/POS or vendor dialect). Lacteva's
   server-side stays printer-ignorant.
3. **Printer down:** fall back to 1; the slip number and record are already
   durable, so a copy can be printed or shared later without re-minting.
4. **Not built:** server-side print spooling, PDF pipelines, or cloud print
   services — the parchi is deliberately plain text plus a browser page.

## 11. Exact pilot information required (the discovery checklist)

Collect at the pilot centre, alongside the rate-chart questionnaire's
equipment section (§G there). Photograph everything.

**Analyzer** — □ manufacturer & model (photo of label) · □ physical ports
(photo of rear panel) · □ interface in use (RS-232 / USB / Bluetooth / LAN /
none) · □ vendor software or PC connection currently used, with name/version
· □ user/service manual (or photo of protocol pages) · □ **sample raw
output** (cable capture or vendor-software export for ~5 real samples) ·
□ fields reported (FAT / SNF / CLR / density / temp / milk-type mode) ·
□ push-vs-poll behaviour · □ calibration routine and who performs it.

**Scale** — □ manufacturer & model · □ interface (many are display-only:
confirm a data port exists at all) · □ unit and precision · □ stable-weight
signalling · □ kg or litres, and how the dairy converts today · □ tare
practice (weighed empty can vs fixed tare list) · □ sample raw output.

**Printer** — □ manufacturer & model · □ interface (USB / Bluetooth / serial)
· □ paper width · □ command set if known (ESC/POS?) · □ what it prints today
(sample parchi — same artifact the rate-chart questionnaire collects).

**Environment** — □ what computer/phone exists at the centre (Windows
version? Android? nothing?) · □ does any existing dairy software already own
these devices (name it — coexistence or replacement is a scoping decision) ·
□ does the operator currently type readings by hand? · □ power reliability ·
□ network (4G/WiFi/dead zones) · □ who would install and restart a connector
box/app.

**Business artifacts** (shared with LACTEVA-RATE-CHART-QUESTIONNAIRE §4) —
□ actual rate chart · □ three real parchis · □ one settlement statement ·
□ a full sample collection transaction as the dairy records it today.

## 12. Implementation estimate (for the milestone after discovery)

Contingent on discovery; stated as engineering effort once **sample raw
output and the actual devices** are in hand — estimating protocol work
before seeing a protocol is guessing:

| Increment | Scope | Estimate |
|---|---|---|
| Connector skeleton | Registration + device credential + read-assist plumbing to capture screens, manual fallback untouched | ~1 week |
| First scale adapter | One confirmed model, stable-reading logic, dedup | 2–4 days with device in hand |
| First analyzer adapter | One confirmed model, field mapping to `AnalyzerReading` | 3–5 days with device in hand |
| Printer adapter | Slip text → confirmed command set | 2–4 days with device in hand |
| Source vocabulary + tests | Platform-side instrument sources, event device id, mutation-checked guards, PG proofs | 2–3 days |

Serial total ≈ **2–3 weeks** with devices physically available; zero of it on
the pilot's critical path, because the Basic/Standard profile runs today.

## 13. Risks

* **Display-only hardware.** Many field scales (and some analyzers) have no
  data port. Mitigation: this is why read-assist is the architecture — the
  centre still runs; the connector simply has nothing to adapt. Discovery
  item, not a blocker.
* **A vendor PC application already owns the serial port.** Exclusive port
  locks are common. Mitigation: discovery asks explicitly; coexistence
  (file-export tailing) vs replacement is decided then, on evidence.
* **Protocol documentation unavailable.** Mitigation: raw-output capture is
  on the checklist; line protocols are usually reverse-readable from five
  samples, but the effort estimate moves if not.
* **Litres-vs-kg mismatch** between instrument and rate chart. Mitigation:
  surfaced in both questionnaires; resolved as a pricing increment, never as
  a silent connector conversion.
* **Analyzer milk-type switch contradicting the operator's declaration.**
  Mitigation: operator declaration stays canonical; connector reports the
  device mode as metadata so the discrepancy is *visible* rather than
  silently resolved.
* **Environment fragility** (power, OS, who reboots the box). Mitigation:
  environment section of the checklist; the connector must fail toward
  manual, never toward blocking collection.

## 14. What must NOT be built

* No pricing, rate, settlement or acceptance logic in any device adapter or
  connector — measurements and provenance only.
* No second business workflow: manual and instrument paths converge on the
  same transaction structure through the same endpoints, differing only in
  `*_source`.
* No schema change in this milestone, and none anticipated for read-assist —
  the source columns, device registry, event log and offline replay already
  carry the design.
* No vendor selection, no hardware purchase, no protocol guessed from
  memory — every adapter starts from captured raw output of the pilot's
  actual device.
* No un-refusing of mock adapters, ever; no reuse of `mock_*` source names by
  real devices.
* No GPS, AI, SAP, WhatsApp, farmer-app or unrelated work under a hardware
  heading.

## 15. Recommended implementation milestone

**P0-HW-002 — Centre Connector MVP (read-assist).** Gated on §11 being
answered — specifically: device photos, interface confirmation, and at least
one sample raw output per instrument. Scope: connector skeleton + the one
scale adapter and one analyzer adapter the pilot actually owns + platform
source-vocabulary increment with mutation-checked tests and PG proofs +
(if confirmed) the printer adapter. Explicitly out: auto-capture
(P1, Advanced profile), calibration records (future DBD per PSP-0007 §5),
any second vendor.

Until that gate opens, the pilot proceeds on the Basic/Standard profile with
operator-entered readings — which this repository treats, correctly, as a
first-class way to run a dairy.

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Initial specification: existing-capability audit, hardware boundary, device classes, connector architecture, offline/security requirements, printer strategy, pilot discovery checklist, estimates, risks, non-goals, P0-HW-002 recommendation (P0-HW-001). |
