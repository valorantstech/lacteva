---
id: PSP-0008
title: Lacteva Collect — Operational Metrics
type: psp
layer: application
status: Draft
version: "0.1"
owner: Lacteva Collect Product Team
created: 2026-08-02
last-updated: 2026-08-02
related: [PSP-0003, PSP-0006, CAP-0003, CAP-0010]
---

# PSP-0008 — Operational Metrics

## 1. Purpose

Defines the measures the product computes from shift and center records, with precise definitions so every market computes them identically. Metrics here are **operational** (per shift/center); farm-facing and cross-market analytics belong to DIA capabilities (DIA.ANL.01/02) which consume these records — the product computes, DIA compares.

## 2. Per-Shift Metrics

| Metric | Definition | Source |
| --- | --- | --- |
| Collections count | Accepted transactions in the shift | Transaction stream |
| Accepted volume | Sum of accepted quantities | Transaction stream |
| Volume by grade | Accepted volume split by field-test outcome class | QFS.TST.03 results |
| Refusal rate | Refused deliveries ÷ total deliveries | Transactions + refusals |
| Refusals by reason | Counts per refusal reason (quality fail, ineligible, withdrawal exclusion) | Refusal records |
| Shift variance | Per [PSP-0006 §3.5](PSP-0006-shift-closing.md); signed % of recorded intake | Closing record |
| Members served | Distinct members with ≥ 1 accepted delivery | Transaction stream |
| Shift duration | Shift Opened → Shift Closed | Lifecycle events |
| Exception count | Opening + in-shift + closing exceptions and overrides | Exception records |
| Suspension time | Total time in Suspended | Lifecycle events |

## 3. Per-Center Metrics (rolling)

| Metric | Definition | Feeds |
| --- | --- | --- |
| Session coverage | Shifts opened ÷ sessions scheduled | MCL.RTE.01 planning |
| Mean absolute variance | Rolling mean of \|shift variance\| | Fraud/equipment signals (MCL.PCK.01 AI opportunity) |
| Calibration compliance | Instrumented checks passed without override ÷ required | SWC.REG.02 audit readiness |
| Cold-chain compliance | Time within temperature spec ÷ cooled storage time (cooled profiles) | MCL.CCH.02 KPI |
| Dispatch reconciliation | Center-dispatched vs plant-received quantities | MCL.PCK.02 transit-loss KPI |
| Member attendance trend | Members served vs member base (CPR.MEM.01) trend | Churn early-warning (CPR.MEM.01 AI opportunity) |

## 4. Metric Principles

1. **Defined once, here** — downstream reports cite these definitions; no report redefines a metric.
2. **Computed from records, never entered** — a metric an operator can type is an opinion, not a metric.
3. **Comparability before richness** — a metric only enters cross-center benchmarking after DIA.ANL.02's comparability rules are satisfied.
4. Thresholds/targets are market-parameterized (with R05's tolerance the canonical example); this document defines *meaning*, not *targets*.

## 5. Future Artifact Trace

| Aspect | Realized Later By |
| --- | --- |
| Metric computation & storage | Future SRS/DBD *(placeholder)* |
| Center/supervisor dashboards | Future UI spec *(placeholder)* |
| Cross-center benchmarking | DIA.ANL.02 realization *(placeholder)* |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | 2026-08-02 | Lacteva Collect Product Team | Initial draft from approved chapter 3. |
