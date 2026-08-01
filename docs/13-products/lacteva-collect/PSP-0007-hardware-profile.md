---
id: PSP-0007
title: Lacteva Collect — Hardware Profile
type: psp
layer: application
status: Draft
version: "0.1"
owner: Lacteva Collect Product Team
created: 2026-08-02
last-updated: 2026-08-02
related: [PSP-0002, PSP-0005, PSP-0009]
---

# PSP-0007 — Hardware Profile

## 1. Definition

A **hardware profile** describes the equipment class a collection center operates with, and therefore: which opening checks apply ([PSP-0005](PSP-0005-shift-opening.md)), which measurements are instrument-read vs operator-entered, and which fallback modes exist. Profiles absorb the global variability axis "manual vs automated" (CAP-0001 §7) — one product, three equipment realities.

## 2. Profile Classes

| Equipment | **Basic** | **Standard** | **Advanced** |
| --- | --- | --- | --- |
| Weighing | Manual scale, operator-entered | Electronic scale, instrument-read | Integrated scale, automatic capture |
| Quality testing | Lactometer + alcohol test, operator-entered | Electronic milk analyzer (fat/SNF), instrument-read | Analyzer with automatic per-member capture |
| Member identification | Manual lookup | Card / code lookup | Card/code + automated queue |
| Receipts | Handwritten/pre-printed | Thermal printer | Printer + digital receipt to member |
| Storage | Cans, ambient | Cans / small cooler | Bulk cooler with temperature telemetry |
| Power | None assumed | Mains + basic backup | Mains + UPS/solar backup |
| Connectivity | Intermittent at best | Intermittent | Regular, telemetry-capable |

## 3. Profile Consequences

| Concern | Rule |
| --- | --- |
| Opening checks | Only present equipment is checked; instrument checks (scale known-weight, analyzer calibration) apply from Standard up (R04) |
| Data provenance | Every measurement records whether it was instrument-read or operator-entered — provenance is part of the record, feeding trust analytics (DIA.ANL.01) and fraud detection |
| Calibration | Instrumented profiles carry calibration validity windows; expired calibration = failed opening check (R04); calibration events recorded by Maintenance Technician ([PSP-0001](PSP-0001-actors-and-roles.md)) |
| Fallback | Each instrument declares its fallback (analyzer down → lactometer + flag; printer down → written receipt + flag); fallback use is always visible in the shift record |
| Cold chain | Cooling-equipped profiles participate in MCL.CCH.02 monitoring; others rely on time-to-dispatch discipline |

## 4. Profile Assignment

- Each center carries exactly one active profile ([PSP-0002 §2](PSP-0002-collection-center.md)); profile changes are recorded center events (equipment upgrades are a core cooperative investment path, CPR.INP.02).
- Profiles are descriptive classes, not device inventories — the specific device registry is a future artifact *(placeholder: future DBD/API)*.

## 5. Future Artifact Trace

| Aspect | Realized Later By |
| --- | --- |
| Device integration (scale/analyzer protocols) | Future SRS + technology ADRs *(placeholder — no technology is decided here)* |
| Calibration records | Future DBD/EVT *(placeholder)* |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | 2026-08-02 | Lacteva Collect Product Team | Initial draft from approved chapter 2. |
