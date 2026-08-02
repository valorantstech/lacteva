---
id: TPL-0003
title: Product Requirements Document Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# TPL-0003 — Product Requirements Document (PRD) Template

> Template guidance: Copy everything below the rule into `docs/04-requirements/product/PRD-NNNN-<short-title>.md`. A PRD defines **what the product does for users** — user problems, journeys, and feature behavior. It traces up to a BRD (why) and down to SRSs (how the software must behave). It does not prescribe architecture.

---

```yaml
---
id: PRD-NNNN
title: <Product/feature title>
type: prd
status: Draft
version: "0.1"
owner: <product team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<BRD-ID it traces to>]
---
```

# PRD-NNNN — \<Title\>

## 1. Overview

- **Problem statement:** \<the user problem, in one paragraph\>
- **Traces to:** \<BRD-ID and the specific goals, e.g. BRD-0002-G01\>
- **Target release / milestone:** \<milestone\>

## 2. Users and Personas

> Template guidance: Real segments of Lacteva's market — e.g. smallholder farmer, cooperative quality manager, processor procurement lead. Reference shared persona definitions once they exist rather than redefining.

| Persona | Description | Key Need Addressed |
| --- | --- | --- |
| \<persona\> | \<who they are, context, constraints — connectivity, language, device\> | \<need\> |

## 3. User Journeys

> Template guidance: One subsection per journey. Describe today's journey (if any) and the target journey. Use a Mermaid `journey` or `flowchart` per STD-0005 when it clarifies.

### 3.1 \<Journey name\>

\<narrative\>

## 4. Functional Requirements

> Template guidance: Numbered, testable, prioritized with MoSCoW. Write behavior ("When X, the product does Y"), not implementation. Acceptance criteria in Given/When/Then.

### 4.1 \<Feature area\>

| ID | Requirement | Priority |
| --- | --- | --- |
| PRD-NNNN-F01 | \<the product MUST/SHOULD …\> | Must / Should / Could / Won't (this release) |

**Acceptance criteria — PRD-NNNN-F01**

- Given \<precondition\>, when \<action\>, then \<observable outcome\>.

## 5. Non-Functional Expectations (User-Facing)

> Template guidance: Only user-perceivable qualities here — responsiveness, availability from a user's view, languages, accessibility, offline behavior. Engineering targets go to the SRS.

| ID | Expectation |
| --- | --- |
| PRD-NNNN-N01 | \<e.g. usable on low-bandwidth rural connections; specify what "usable" means\> |

## 6. Scope Boundaries

- **Out of scope for this PRD:** …
- **Explicit non-goals:** …

## 7. Dependencies

| Dependency | Type | Notes |
| --- | --- | --- |
| \<other PRD, capability, external system\> | Internal / External | \<impact if late\> |

## 8. Metrics and Success Criteria

| Metric | Definition | Target | Measurement Source |
| --- | --- | --- | --- |
| \<metric\> | \<precise definition\> | \<target\> | \<analytics event / report\> |

## 9. Open Questions

| # | Question | Owner | Due |
| --- | --- | --- | --- |
| 1 | \<question\> | \<who\> | \<date\> |

## 10. Downstream Documents

| Document | Status |
| --- | --- |
| SRS(s) tracing to this PRD | \<IDs or "Not yet created"\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
