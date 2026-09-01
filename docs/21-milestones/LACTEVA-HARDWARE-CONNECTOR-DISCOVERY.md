---
id: LACTEVA-HARDWARE-CONNECTOR-DISCOVERY
title: Hardware Connector Discovery & MVP Gate
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-HARDWARE-INTEGRATION-SPEC, LACTEVA-BUSINESS-OPERATING-MODEL, LACTEVA-IDENTITY-ENTERPRISE-ARCHITECTURE-AUDIT, LACTEVA-GO-LIVE-READINESS, LACTEVA-RATE-CHART-QUESTIONNAIRE]
baseline: ARCH-BASELINE-V1
---

# Hardware Connector Discovery & MVP Gate (P0-HW-002)

**Discovery and MVP definition only — no code, schema, migration, API, mobile,
pricing, settlement, or collection change; no vendor, no manufacturer, no
protocol chosen.** This turns the P0-HW-001 architectural specification into a
**precise, evidence-based implementation gate** to take to a real Indian dairy.
Every "what exists" claim below is verified against the code (§B). Every device
attribute is a **field to collect**, never a guess — unverified interface
families are tagged **UNKNOWN / TO CONFIRM**.

Tag taxonomy: **GREEN** (exists/verified) · **CONFIG** · **NEXT** · **V1** ·
**V2** · **ENTERPRISE** · **FUTURE OPTION** · **COMING SOON** · **UNKNOWN/TO
CONFIRM**.

---

## 1. Executive summary

Lacteva already holds the entire *platform side* of hardware integration:
source-attributed weight/quality capture, a device registry with lifecycle and
health, production-refused mock adapters whose dataclasses **are** the adapter
contract, and an offline/idempotent capture path. **Nothing on the platform
blocks a connector.** What is missing is **physical evidence from the real
dairy** — the make/model/interface and, above all, **captured raw output** of
the actual scale and analyzer. This document verifies the platform state,
defines the field discovery checklist, and sets a **hard gate**: connector
implementation (P0-HW-003) may begin only when the §29 evidence exists. Until
then the pilot runs manual-first, which is a first-class mode, not a
degradation. **The connector is V1/V1+ and must never block the pilot.**

## 2. Current hardware architecture (verified)

Per P0-HW-001 (LACTEVA-HARDWARE-INTEGRATION-SPEC), unchanged and confirmed:
hardware supplies **measurements + provenance only**; the transaction, pricing,
settlement and parchi are **source-blind**; manual entry is a permanent
first-class fallback; the intended seam is a **Centre Connector** feeding the
existing capture endpoints (read-assist); the server stays printer-ignorant.

## 3. Existing device registry — GREEN

`operational_readiness.Device` (verified):
- Categories: **scale** (readiness *blocking*), **milk_analyzer** (*warning*),
  **printer** (*warning*), qr_scanner, rfid_reader, camera (*none*).
- Fields: `tenant_id`, `center_id` (nullable), `category`, `name`,
  `serial_number`, `status`; unique `(tenant_id, serial_number)`.
- Lifecycle statuses: `registered → assigned → active → maintenance → retired`.
- Health: `DeviceHealthReport` (states `ok | degraded | failed`), tenant-owned
  (SEC-002 denormalised `tenant_id`).
- Permissions: `operations.device.read` / `operations.device.manage`.
- **A device is an ASSET attached to a location (`center_id`)** — exactly the
  model the identity/enterprise audit requires; BMC/analyzer/scale/printer at a
  future chilling centre would be rows under that location. **Do not model a
  device as a user.**

## 4. Existing measurement provenance — GREEN

- `MilkCollectionTransaction.weight_source` and `.quality_source` are stored on
  every reading and copied into the immutable completion snapshot.
- Source vocabulary today: weight = `manual | mock_scale`; quality =
  `manual | mock_analyzer` (a real adapter registers a *real* source name,
  never a `mock_*` one).
- `WeightCaptured` / `QualityCaptured` events carry the measurement; the source
  rides on the record and the snapshot. DEMO-007's principle holds: a reading
  without its source is dishonest.

## 5. Current manual capture workflow — GREEN (first-class)

Capture wizard (proven on a real handset, P0-PILOT-004): identify → milk type →
**weight** (`source=manual`, gross+tare) → **quality** (`source=manual`,
fat/snf/clr) → price → accept → complete → parchi. Endpoints
`POST /v1/milk-transactions/{id}/weight` and `/quality`. Offline-capable and
idempotent (§24). **This mode is permanent and sufficient for the pilot.**

## 6. Hardware integration seam — GREEN (contracts already exist)

The mock adapters define the exact reading contracts a real adapter must fill:
- `ScaleReading(gross_kg: float, tare_kg: float)`
- `AnalyzerReading(fat: float, snf: float, clr: float, density: float,
  temperature_c: float)`
Both are production-refused (`_refuse_mock_source` in the service **and** the
adapter — SEC-003/F-01), so a real source cannot be spoofed. A connector reads
a device, fills the contract, and calls the **same** capture endpoint with a
real source name; nothing downstream changes.

## 7. Candidate device classes

**Scale (priority 1)**, **milk analyzer (priority 2)**, **printer (optional,
secondary)**. The registry also anticipates qr_scanner / rfid_reader / camera
(future). No class is assumed to use any particular interface until §12
evidence exists.

## 8. Actual unknowns that MUST be confirmed at the dairy

Nothing about the physical devices is known. **UNKNOWN / TO CONFIRM:** every
make, model, interface, port, protocol, baud rate, data format, existing
software/driver, computer, OS, network, and whether any device even has a data
port at all. Interface families named anywhere (RS-232/USB/Bluetooth/Ethernet/
ESC/POS/Modbus) are *possibilities to verify*, **not facts**.

## 9. Physical discovery checklist (the core deliverable)

Take this to the dairy. **Fill only from evidence; leave unknowns blank.**
For **every** physical device at **every** centre in scope:

| Field | Notes |
|---|---|
| Device category | scale / milk_analyzer / printer / other |
| Device name | as the dairy calls it |
| Manufacturer | from the label |
| Model | from the label |
| Serial number | from the label |
| Photo — front | required |
| Photo — rear panel | required (shows ports) |
| Photo — labels/nameplate | required |
| Interface | ONLY if observed (do not guess) |
| Port type | e.g. DB9/USB-B/RJ45/BT — if present |
| Cable type | what is actually plugged in |
| Protocol (if printed/documented) | from manual/label only |
| Baud rate (if applicable) | from settings/manual only |
| Data format (if known) | from manual or capture |
| Existing software/driver | name + version |
| Connected computer | which machine, if any |
| Network address | if LAN device |
| Currently operational? | yes/no |
| **Sample raw output** | see §12 — the single most important field |
| Who operates it | role |
| Which centre | code |
| Another app already consuming it? | yes/no + which |
| Can Lacteva safely READ it? | assessment after evidence |
| Should Lacteva WRITE to it? | usually no; printer only |
| Security implications | shared port, exclusive lock, etc. |
| Fallback if unavailable | manual (default) |

## 10. Device label / model / serial checklist
Photograph the nameplate of each device; transcribe manufacturer, model,
serial. If a device has no data port, record that — it is a valid finding that
means "manual only."

## 11. Rear-panel / interface evidence checklist
Photograph the rear/side panel showing all ports. Do not infer an interface
from the front; a display-only scale often has **no** data port.

## 12. Raw output capture procedure (highest priority)

For scale and analyzer, capture **real output for ~5 real samples** by whatever
path exists, in priority order:
1. If a vendor PC application shows/exports readings — export the file / copy
   the values.
2. If a serial/USB port streams — capture with a terminal (record the exact
   bytes/lines, timestamps, and the port settings used).
3. If neither is possible — record that, with the reason.
Store the raw payloads verbatim; **the adapter contract is derived from real
output, never assumed.**

## 13. Scale discovery requirements (priority 1)

Collect: make · model · **capacity** · **accuracy/resolution** · **Legal
Metrology verification/stamping status + certificate + validity** · interface ·
**raw output format** · **stable-weight behaviour** (does it stream until
settled?) · **gross/tare/net behaviour** · **units** · **continuous vs
command-based output** · error/status messages · whether an existing app reads
it · whether **simultaneous access** is possible · whether a **proprietary
driver** is required · whether it can be read **read-only** · confirmation that
**manual capture remains available**. **Do not decide the protocol until raw
output exists.**

## 14. Milk analyzer discovery requirements (priority 2)

Collect the same envelope, and record **exactly which fields the device
provides** — do not assume all: **FAT**, **SNF**, **CLR**, **density**,
**temperature**, and any **added-water/adulteration** or other indicator *only
if actually output*. The real payload determines which of the `AnalyzerReading`
fields the adapter can populate; missing fields stay manual. Also: does it have
a cow/buffalo **mode switch**? (If so it is metadata to reconcile — the
operator's declared milk type stays canonical, per P0-HW-001 §4.A.)

## 15. Printer discovery requirements (secondary — do not over-build)

Collect: does the dairy **already have a printer**? · make/model · connection ·
connected to the operator computer? · **thermal?** · **ESC/POS or other command
language confirmed?** · **is browser printing already sufficient?** (the parchi
prints from the portal today and shares as text) · **is direct integration
actually necessary?** **Do not build printer integration merely because a
printer exists** — the slip already reaches the farmer.

## 16. Centre computer / local network discovery
What computer exists at the centre (make/OS, or none)? Is it shared? On a LAN?
Internet reliability (4G/WiFi/dead zones)? Power reliability? Who would install
and restart a connector box/app?

## 17. Operating system / runtime discovery
Windows (version?) / Android / Linux / nothing. This decides the connector's
runtime form (desktop agent vs Android service vs small box). **Record, do not
decide.**

## 18. USB / serial / Ethernet / Bluetooth evidence
Only from photographs and observed connections. A port existing ≠ a port being
usable (may be display-only, or locked by another app). Capture the actual
cable in use.

## 19. Existing software that may already own the port
Name any vendor PC application / dairy software already reading each device.
Exclusive serial locks are common; coexistence (file-export tailing) vs
replacement is a scoping decision made **on evidence**, not now.

## 20. Security / credential requirements (within current architecture)

The connector authenticates as a **device-scoped principal** — **not a user
login** (identity/enterprise audit: a device is an asset, never a person),
anchored to the existing `Device` registry row and its (tenant, centre). Rules,
all satisfiable by what exists:
- **Per-device credential**, revocable — `retired` status must kill access.
- **Never a `mock_*` source**; never bypasses `_refuse_mock_source`.
- **Never bypasses RLS** — the credential carries exactly one tenant; a session
  binds to that one org (RLS FORCED, foreign resource = 404).
- **Never bypasses authorization** — readings enter through the existing
  authenticated capture flow (read-assist); the operator's action stays
  attributable to the operator.
- **Auditable** — instrument readings add the `device_id` to the events they
  produce; the existing audit trail + snapshot carry provenance.
- **Replay-safe** — §24. **Do not invent a security architecture beyond this.**

## 21. Device lifecycle requirements — GREEN
The registry already covers registration → assignment → active → maintenance →
retired, plus health (ok/degraded/failed) and replacement (register the new
serial, retire the old). The connector consumes this; **no new lifecycle model
is needed.**

## 22. Health / connectivity requirements — GREEN foundation
`DeviceHealthReport` exists. The connector reports device reachability into it;
a degraded/failed device surfaces on the readiness screen (scale = blocking,
analyzer/printer = warning), and the operator **falls back to manual**.

## 23. Offline behaviour — GREEN (must be preserved)
The full capture flow is offline-capable and replays through `SyncService`
(kinds include `capture_weight`, `capture_quality`) with per-operation
idempotency. A connector must **feed the same offline-capable path** — a
device-assisted reading is still just a value in the operator's capture screen,
queued if offline. **A failed/absent device must never break the offline
workflow** (P0-PILOT-004 hardened exactly this path).

## 24. Idempotency / replay requirements — GREEN (must be preserved)
Keyed requests go through `IdempotentRoute`; offline ops carry per-operation
ids; replay is once-only (proven live). The connector introduces **no new
transaction API** — it pre-fills existing capture calls — so idempotency is
inherited. Connector-side reading **dedup** (device id + stable-reading id/
timestamp) is a connector requirement so a single physical reading is not sent
twice.

## 25. Source attribution requirements — GREEN
Every reading keeps its source; instruments add `device_id`. Manual at an
instrumented centre is recorded **as manual** (fallback is visible). Mocks stay
refused. This is a security control, not cosmetics.

## 26. Manual fallback requirements — GREEN (permanent)
Manual capture is first-class and permanent. **Read-assist** is the model: the
device pre-fills the operator's field, the operator confirms; the operator can
always type instead. Hands-free auto-capture is a later, Advanced-profile
increment — not the MVP.

## 27. Proposed connector MVP boundary (definition only — do not build)

**In scope for the eventual MVP (P0-HW-003), once §29 evidence exists:**
- One small **Centre Connector** (runtime form decided by §17 evidence).
- **One scale adapter** and **one analyzer adapter** for the *specific
  confirmed devices*, filling `ScaleReading` / the available `AnalyzerReading`
  fields from **captured raw output**.
- **Read-assist** into the existing capture endpoints with a real source name +
  `device_id`; manual fallback untouched.
- Device-scoped credential anchored to the registry; health reporting;
  connector-side reading dedup.
- Platform-side: a **source-vocabulary increment** (real instrument sources
  beside `manual`, mocks still refused) with mutation-checked tests and PG
  proofs — the *only* code the platform needs, and it is small and additive.
- **Printer adapter only if §15 confirms a thermal printer AND browser printing
  is insufficient** — rendered from the existing slip text.

## 28. Explicitly out of scope

Auto-capture (Advanced profile); any second vendor/model; server-side printing
or PDF pipelines; pricing/settlement/acceptance logic in an adapter; any change
to the transaction/pricing/settlement/parchi/RLS/auth; chilling/BMC/plant;
procurement transport; GPS; SAP; AI; farmer/customer portals; enterprise SSO;
global identity. **None of these are touched by the connector.**

## 29. Hardware MVP gate (the hard gate for P0-HW-003)

Implementation may begin **only when all of the following exist**:

**Required — scale:** make + model + serial (photos), rear-panel interface
photo, **captured raw output for ≥5 real samples**, units + gross/tare/net +
stable-weight behaviour, whether another app owns the port, read-only
feasibility, LM certificate/validity.

**Required — analyzer:** make + model + serial (photos), interface photo,
**captured raw output for ≥5 real samples**, the exact fields it outputs,
cow/buffalo mode behaviour, port ownership.

**Optional — printer:** make/model/connection *and* a decision that browser
printing is insufficient; otherwise **skip**.

**Required — environment:** the centre computer/OS (or "none"), network + power
reliability, who installs/restarts, any existing dairy software owning the
devices.

**Required — access/ownership/operational/safety:** which centre each device
belongs to, who operates it, confirmation the device is operational,
confirmation simultaneous/read-only access is safe, and that **manual capture
remains available** throughout.

**If any Required item is missing, P0-HW-003 does not start** — the pilot
proceeds manual-first.

## 30. Discovery acceptance checklist
The gate (§29) is met when: every in-scope centre's scale and analyzer have
photos + raw output + interface evidence + port-ownership; the environment
sheet is complete; and a go/no-go on read-only safe access is recorded. Printer
is pass-through-or-skip.

## 31. Questions for the dairy
Which centres are in the connector's scope? Does any existing software already
read these devices? Is the operator willing to keep manual as the fallback? Is
there a computer at the centre or must a connector box be provided? Who owns and
restarts centre IT? (Rate-chart / settlement questions live in
LACTEVA-RATE-CHART-QUESTIONNAIRE, not here.)

## 32. Risks / unknowns
- **Display-only devices** (no data port) — a valid outcome meaning "manual
  only"; the centre still runs.
- **Exclusive serial lock** by a vendor app — coexistence vs replacement
  decided on evidence.
- **No protocol documentation** — mitigated by raw-output capture; line
  protocols are usually readable from ~5 samples.
- **Analyzer field variance** — the adapter maps only fields actually output.
- **Environment fragility** (power/OS/who reboots) — the connector must fail
  toward manual, never toward blocking collection.
- **UNKNOWN:** everything physical, until the visit.

## 33. Recommended next engineering milestone
**P0-HW-003 — Centre Connector MVP**, gated strictly on §29. Scope = §27.
Until the gate opens, no connector code. The **pilot go-live** (business-gated)
remains the immediate objective and is independent of hardware.

## 34. No-fabrication statement
No device, manufacturer, model, protocol, interface, baud rate, data format, or
raw payload was invented. No vendor was chosen. No hardware code, schema,
migration, API, or mobile change was made. Interface families are named only as
possibilities to verify. The connector MVP is defined, not built.

---

## Final report

**A. What already exists (GREEN):** device registry (categories, lifecycle,
health, per-location, permissions); source-attributed weight/quality capture;
the `ScaleReading`/`AnalyzerReading` adapter contracts; production-refused mock
adapters (double guard); manual-first capture proven on a real handset;
offline/idempotent capture + replay; the immutable snapshot + audit trail; the
architectural seam and rules from P0-HW-001.

**B. Verified from code:** `DEVICE_CATEGORIES`/`DEVICE_STATUSES`/`HEALTH_STATES`;
`Device.center_id` (asset-at-location); `weight_source`/`quality_source` on the
transaction + snapshot; `WeightCaptured`/`QualityCaptured` events;
`ScaleReading(gross_kg,tare_kg)` and `AnalyzerReading(fat,snf,clr,density,
temperature_c)`; `_refuse_mock_source` in adapter and service; sync
`capture_weight`/`capture_quality` replay kinds; `operations.device.*`
permissions.

**C. Genuinely missing:** only the connector itself (an agent + adapters) and a
small platform source-vocabulary increment — **and both are gated on physical
evidence.** Nothing on the platform blocks it.

**D. Must be discovered physically:** every device's make/model/serial/
interface/port/protocol; **raw output** for scale and analyzer; the centre
computer/OS/network; existing software owning the ports; operational + safe-
access confirmation.

**E. Must NOT be invented:** any make/model/protocol/interface/baud/format/raw
payload; any vendor; any printer command language; any device reading; any
"Coming Soon" that looks functional.

**F. Dairy discovery checklist:** §9–§19 + §29 gate — take it to the dairy.

**G. Connector MVP boundary:** §27 — read-assist agent, one scale + one analyzer
adapter for the confirmed devices, real source + device_id into the existing
capture endpoints, device-scoped credential, health + dedup; printer only if
justified; small additive platform source-vocabulary increment; manual fallback
untouched.

**H. Acceptance gate for implementation:** §29 — all Required scale/analyzer/
environment/access evidence, above all **captured raw output**; missing any →
P0-HW-003 does not start.

**I. Risks:** display-only devices, exclusive port locks, missing protocol docs,
analyzer field variance, environment fragility — all mitigated by
evidence-first + manual fallback (§32).

**J. Recommended next milestone:** the dairy go-live (business-gated) now;
P0-HW-003 later, §29-gated.

**K. Impact on the pilot:** **none.** The connector is V1/V1+ and **must not
block the pilot**; manual-first is a first-class, sufficient mode.

**L. Roadmap preservation confirmation:** AI (MVP flag + future trends/anomaly/
forecasting), SAP/ERP, GPS, chilling centre, BMC, plant/processing, enterprise
SSO, global identity, parent/federation, org-to-org, farmer app, customer/outlet
portal, messaging providers, advanced analytics — **all remain explicitly on the
master roadmap and none was removed, implemented, mocked, or fabricated in this
milestone.**

### "Coming Soon" note (do not build now)
Hardware-related future capabilities may later appear as **non-interactive
labels only** on the existing nav registry: *Hardware Connector — Discovery* ·
*Automated Scale Capture — Coming Soon* · *Automated Analyzer Capture — Coming
Soon* · *Printer Integration — Optional*. **No fake buttons, APIs, readings, or
demo data.**

### What the Milk Day Book is, and is not (D-17; BATCH B7.2)

The Day Book answers "where did the day's milk go" as a **flow ledger**:
collected minus sold minus dispatched leaves a remainder. It is arithmetic over
records the platform already holds, and it is labelled as such on the screen.

It is **not tank metering, and not stock**. Nothing here measures what is
physically in a vessel, accounts for evaporation, spillage, sampling or
transfer loss, or reconciles a dip reading. A remainder is what the books say
should be left, not what a tank contains, and the difference between those two
numbers is a real quantity this platform does not know.

Chilling-centre and BMC stock modelling therefore **stays parked**, exactly as
§28 leaves it. Building the Day Book does not unpark it: a flow ledger is the
honest thing that can be built from collections, deliveries and dispatches,
and a stock model needs vessels, capacities and physical measurements that no
part of this platform records.

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Hardware connector discovery: code-verified platform state, the field discovery checklist (per-device attributes + raw-output procedure), scale/analyzer/printer/environment discovery requirements, security within the current architecture, the connector MVP boundary, and the hard §29 evidence gate for P0-HW-003. Discovery only — no code, no vendor, no protocol; roadmap fully preserved (P0-HW-002). |
