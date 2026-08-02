---
id: PSP-0010
title: Lacteva Collect — Business Events
type: psp
layer: application
status: Draft
version: "0.1"
owner: Lacteva Collect Product Team
created: 2026-08-02
last-updated: 2026-08-02
related: [PSP-0004, PSP-0005, PSP-0006, CAP-0003]
baseline: ARCH-BASELINE-V1
---

# PSP-0010 — Business Events

## 1. Purpose

The register of business facts the product records, aligned with the capability model's event pre-inventory ([CAP-0003](../../05-capabilities/CAP-0003-milk-collection-logistics.md), [QR-0003 §5](../../12-quality/QR-0003-traceability-matrix.md)). Names are past-tense facts. Each event will be formalized as an `EVT` contract (TPL-0008) when the event backbone ADR exists — the Future column is the placeholder trace. **This register adds no events beyond what the specified workflows record.**

## 2. Shift Lifecycle Events

| Event | Emitted When | Source Spec | Capability Alignment | Future EVT |
| --- | --- | --- | --- | --- |
| Shift Scheduled | Shift created for a session | PSP-0004 | MCL.CCH.01 | *(placeholder)* |
| Shift Opening Started | Operator begins opening | PSP-0005 | MCL.CCH.01 | *(placeholder)* |
| Equipment Check Recorded | Each opening check completes | PSP-0005 | MCL.LGX.02 | *(placeholder)* |
| Opening Exception Recorded | Check failed / override used | PSP-0005 | MCL.CCH.01 (Equipment Fault) | *(placeholder)* |
| Shift Opened | Opening declaration confirmed | PSP-0004/0005 | MCL.CCH.01 (Center Intake opens) | *(placeholder)* |
| Shift Suspended / Resumed | Suspension begins/ends | PSP-0004 | MCL.CCH.01 | *(placeholder)* |
| Shift Closing Started | Intake stops | PSP-0004/0006 | MCL.CCH.01 | *(placeholder)* |
| Pending Transaction Voided | In-flight record voided with reason | PSP-0006 | MCL.PCK.01 | *(placeholder)* |
| Shift Totals Computed | Closing computation done | PSP-0006 | MCL.CCH.01 (mass balance) | *(placeholder)* |
| Closing State Recorded | Physical measurement recorded | PSP-0006 | MCL.CCH.02 | *(placeholder)* |
| Variance Breach Recorded | Tolerance exceeded (R05) | PSP-0006 | MCL.PCK.03 (dispute trigger) | *(placeholder)* |
| Shift Closed | Operator declaration | PSP-0004/0006 | MCL.CCH.01 | *(placeholder)* |
| Shift Reconciled | Supervisor verification | PSP-0004/0006 | MCL.CCH.01 | *(placeholder)* |
| Shift Aborted | Scheduled/Opening shift terminated | PSP-0004 | MCL.CCH.01 | *(placeholder)* |

## 3. Transaction Events (within an open shift)

| Event | Emitted When | Source Spec | Capability Alignment | Future EVT |
| --- | --- | --- | --- | --- |
| Member Checked In | Identity + eligibility resolved | README flow | CPR.MEM.01 | *(placeholder)* |
| Delivery Refused | Eligibility or quality gate failed (R10, R12) | README flow | MCL.PCK.01 (Collection Rejected), QFS.TST.03 (Milk Failed Field Test) | *(placeholder)* |
| Field Test Performed | Rapid test completed | README flow | QFS.TST.03 | *(placeholder)* |
| Milk Collected | Quantity recorded, receipt issued | README flow | MCL.PCK.01 (canonical event) | *(placeholder)* |
| Sample Taken | Formal sample registered (where scheme requires) | README flow | QFS.TST.01 | *(placeholder)* |
| Dispatch Handover Countersigned | Bulk handed to transporter (R11) | PSP-0006 | MCL.CCH.01 (Bulk Dispatched) | *(placeholder)* |

## 4. Event Principles

- **Facts, not commands** (per `docs/09-events/` rules); every event carries actor-and-role attribution (R08) and shift identity.
- Events are recorded offline and synchronized (R09); ordering guarantee within a shift is total, across shifts per center is by shift sequence.
- Producer of the future EVT contracts is the collection platform service *(placeholder — PSV per dependency map Phase 1)*.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | 2026-08-02 | Lacteva Collect Product Team | Initial event register from approved chapters. |
