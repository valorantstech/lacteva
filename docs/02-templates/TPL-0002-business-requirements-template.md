---
id: TPL-0002
title: Business Requirements Document Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# TPL-0002 — Business Requirements Document (BRD) Template

> Template guidance: Copy everything below the rule into `docs/04-requirements/business/BRD-NNNN-<short-title>.md`. A BRD states **what the business needs and why** — outcomes, not features or systems. Solutions belong in PRDs and SRSs that trace back to this document. Requirement IDs (`BRD-NNNN-G01`, `-C01`, …) follow [STD-0003 §5](../00-standards/STD-0003-document-numbering.md).

---

```yaml
---
id: BRD-NNNN
title: <Business need title>
type: brd
status: Draft
version: "0.1"
owner: <business sponsor / unit>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<doc IDs>]
---
```

# BRD-NNNN — \<Title\>

## 1. Executive Summary

> Template guidance: Five sentences maximum: the need, the opportunity size, the proposed direction, and what happens if we do nothing.

\<summary\>

## 2. Business Context

### 2.1 Problem / Opportunity

\<what is broken or possible today, with evidence — market data, customer feedback, operational metrics\>

### 2.2 Strategic Alignment

\<which company objective this serves; for Lacteva, tie to the 1M-businesses / 50-countries vision where relevant\>

## 3. Business Goals

> Template guidance: Each goal gets an ID, is outcome-oriented, and is measurable. "Increase milk-quality premium capture" beats "build a quality module".

| ID | Goal | Success Metric | Target | Baseline |
| --- | --- | --- | --- | --- |
| BRD-NNNN-G01 | \<goal\> | \<metric\> | \<target\> | \<current value\> |

## 4. Scope

### 4.1 In Scope

- \<included business processes, markets, segments\>

### 4.2 Out of Scope

> Template guidance: Explicit exclusions prevent scope creep. State them even when "obvious".

- \<excluded, with one-line reason\>

## 5. Stakeholders

| Stakeholder | Role / Interest | Involvement |
| --- | --- | --- |
| \<who\> | \<their stake\> | Sponsor / Consulted / Informed |

## 6. Constraints

| ID | Constraint | Source |
| --- | --- | --- |
| BRD-NNNN-C01 | \<budget, regulatory, timeline, market constraint\> | \<where it comes from\> |

## 7. Assumptions

| ID | Assumption | Validation Plan |
| --- | --- | --- |
| BRD-NNNN-A01 | \<what we believe but haven't proven\> | \<how/when we'll validate\> |

## 8. Risks

| ID | Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| BRD-NNNN-R01 | \<risk\> | Low/Med/High | Low/Med/High | \<mitigation\> |

## 9. Financial Analysis

> Template guidance: Order-of-magnitude is fine early; say so. Include cost of delay.

- **Expected benefit:** …
- **Estimated cost:** …
- **Cost of doing nothing:** …

## 10. Downstream Documents

| Document | Status |
| --- | --- |
| PRD(s) tracing to this BRD | \<IDs or "Not yet created"\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
