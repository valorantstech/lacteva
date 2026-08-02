---
id: PSP-0009
title: Lacteva Collect — Business Rules
type: psp
layer: application
status: Draft
version: "0.1"
owner: Lacteva Collect Product Team
created: 2026-08-02
last-updated: 2026-08-02
related: [PSP-0003, PSP-0004, PSP-0005, PSP-0006, PSP-0010]
baseline: ARCH-BASELINE-V1
---

# PSP-0009 — Business Rules

## 1. Purpose

The numbered rule register for the first three chapters. Rule IDs (`R01`…) are stable and cited across the package; parameters marked *(market)* vary per operating market under ETE.LOC.01 governance and are never hard-coded. Each rule will later be formalized as a domain policy (`POL`) — the Future column tracks that.

## 2. Rules

| ID | Rule | Enforced At | Parameters | Future |
| --- | --- | --- | --- | --- |
| R01 | A center MUST have at most one shift in Open/Opening/Suspended/Closing state at any moment. | Shift scheduling & opening | — | POL *(placeholder)* |
| R02 | Collection transactions MUST be recorded only while their shift is Open; outside Open the center accepts nothing. | Transaction recording | — | POL *(placeholder)* |
| R03 | A shift MUST have exactly one assigned, authenticated Center Operator; reassignment before opening is recorded; an operator holds at most one open shift. | Opening; reassignment | — | POL *(placeholder)* |
| R04 | Equipment readiness checks per the center's hardware profile MUST pass before opening; any failure proceeds only under a recorded Supervisor override. | Opening ([PSP-0005](PSP-0005-shift-opening.md)) | Check list per profile | POL *(placeholder)* |
| R05 | Shift variance MUST be computed from recorded opening state, intake, dispatch, and closing state; breaches beyond tolerance MUST be flagged for investigation before reconciliation. | Closing ([PSP-0006](PSP-0006-shift-closing.md)) | Variance tolerance *(market)* | POL *(placeholder)* |
| R06 | A shift MUST NOT close with unresolved pending transactions — each is completed or voided with reason. | Closing | — | POL *(placeholder)* |
| R07 | Suspension exceeding the threshold duration MUST be escalated to the Supervisor with cause. | Suspension | Threshold *(market)* | POL *(placeholder)* |
| R08 | Every transaction, exception, override, and declaration MUST be attributed to an identified person acting in a named role; overrides additionally record the reason. | Everywhere | — | POL *(placeholder)* |
| R09 | All shift operations MUST function offline; records queue locally and synchronize; a shift's reconciliation requires the synced record. | Whole lifecycle | Max offline age before escalation *(market)* | POL *(placeholder)* |
| R10 | Milk from a member with an active withdrawal exclusion (FPR.HLT.04) MUST be refused at check-in, with the refusal recorded. | Check-in | Exclusion source feed | POL *(placeholder)* |
| R11 | Dispatch handover quantities MUST be countersigned by the Transporter; uncountersigned dispatch is an exception, not a record. | Dispatch / closing | — | POL *(placeholder)* |
| R12 | Refused deliveries MUST be recorded with reason — a refusal invisible to the member's history is a trust defect. | Testing / check-in | Refusal reason list *(market)* | POL *(placeholder)* |

## 3. Rule Principles

- Rules bind the **product's behavior**, not the member's — the product records and enforces at its own gates; it never physically prevents anything.
- A rule with a *(market)* parameter has one meaning everywhere and different values per market — the same pattern as pricing schemes (PEF.MPR.01).
- Conflicts between rules are defects: none are known; report any found via [REVIEW-NOTES](REVIEW-NOTES.md).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | 2026-08-02 | Lacteva Collect Product Team | Initial rule register R01–R12 from approved chapters 1–3. |
