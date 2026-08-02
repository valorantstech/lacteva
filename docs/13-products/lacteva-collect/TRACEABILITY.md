---
id: LC-TRACE
title: Lacteva Collect — Traceability Tables
type: reference
status: Draft
version: "0.1"
owner: Lacteva Collect Product Team
created: 2026-08-02
last-updated: 2026-08-02
related: [PDT-0001, QR-0003]
baseline: ARCH-BASELINE-V1
---

# Lacteva Collect — Traceability Tables

Package-level traceability: capability → product spec → rule → event → future artifacts. Feeds the repository-wide matrices ([QR-0003](../../12-quality/QR-0003-traceability-matrix.md), [architecture TRACEABILITY](../../03-architecture/TRACEABILITY.md)). Placeholder markers (`API-TBD`, `DBD-TBD`, `UI-TBD`, `PSV-TBD`, `POL-TBD`, `EVT-TBD`) are work items, not errors — they resolve as Phase 1–3 artifacts land, and each replacement updates this file in the same PR.

## 1. Capability → Product → Rule → Event → Future Artifacts

| Business Capability | Product Spec | Business Rules | Events (PSP-0010) | Future API | Future Database | Future UI |
| --- | --- | --- | --- | --- | --- | --- |
| MCL.CCH.01 Chilling Center Operations | PSP-0002, PSP-0003, PSP-0004 | R01, R02, R07 | Shift Scheduled/Opened/Suspended/Closed/Reconciled/Aborted | API-TBD (shift control) | DBD-TBD (shift store) | UI-TBD (operator shift screens) |
| MCL.PCK.01 Farm Pickup & Quantity Recording (center delivery) | PSP-0003, README flow | R02, R08, R12 | Milk Collected; Delivery Refused; Pending Transaction Voided | API-TBD (collection recording) | DBD-TBD (transaction store) | UI-TBD (collection screen, receipts) |
| MCL.PCK.02 Reception & Acceptance (dispatch side) | PSP-0006 | R11 | Dispatch Handover Countersigned | API-TBD (dispatch) | DBD-TBD | UI-TBD (dispatch screen) |
| MCL.PCK.03 Collection Dispute Resolution | PSP-0006 §5, PSP-0009 | R05 | Variance Breach Recorded | API-TBD (investigation) | DBD-TBD | UI-TBD (supervisor review) |
| MCL.CCH.02 Cold Chain Monitoring | PSP-0002, PSP-0007 | R04 | Closing State Recorded; Equipment Check Recorded | API-TBD (telemetry) | DBD-TBD | UI-TBD (alerts) |
| MCL.LGX.02 Fleet & Equipment Utilization (center equipment) | PSP-0007 | R04 | Equipment Check Recorded | API-TBD (calibration log) | DBD-TBD | UI-TBD (maintenance view) |
| QFS.TST.03 Rapid & Field Testing | PSP-0002 §3, README flow | R12 | Field Test Performed; Delivery Refused | API-TBD (test capture) | DBD-TBD | UI-TBD (test screen) |
| QFS.TST.01 Sampling & Test Orchestration | README flow | — | Sample Taken | API-TBD | DBD-TBD | UI-TBD |
| CPR.MEM.01 Producer Registry & Membership | PSP-0001, README flow | R03 (operators), R10 (members) | Member Checked In | API-TBD (member lookup) | DBD-TBD (reference data) | UI-TBD (check-in) |
| FPR.HLT.04 Treatment & Withdrawal Management | README flow | R10 | Delivery Refused (withdrawal reason) | API-TBD (exclusion feed) | — (consumed) | UI-TBD (refusal messaging) |
| PEF.SET.01 Producer Settlement Calculation *(consumer of records)* | PSP-0003 §4 | R05, R06 (record integrity) | Milk Collected; Shift Reconciled | API-TBD (records export) | — (consumed) | — |
| DIA.ANL.01 Performance Analytics *(consumer)* | PSP-0008 | — | all metric sources | API-TBD | — | UI-TBD (dashboards) |

## 2. Architecture-Layer Trace

| Package Element | EA Artifact (per [DEPENDENCY-MAP](../../03-architecture/DEPENDENCY-MAP.md)) | Status |
| --- | --- | --- |
| Product | [PDT-0001](../../03-architecture/03-application-layer/PDT-0001-lacteva-collect.md) | Draft |
| Shift, Collection Center as domain objects | Collection context `DOM` + `AGG` | PSV/DOM-TBD — Phase 1 |
| Rules R01–R12 | `POL` policies in Collection context | POL-TBD — Phase 1 |
| Opening/closing workflows | `BPR` business processes | BPR-TBD — Phase 1 (collection-to-settlement BPR already queued, QR-0006 B6) |
| Event register | `EVT` contracts | EVT-TBD — after event backbone ADR |
| Owning services | `PSV` | PSV-TBD — Phase 1 |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | 2026-08-02 | Lacteva Collect Product Team | Initial traceability tables with placeholders. |
