---
id: TPL-0009
title: Business Capability Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# TPL-0009 — Business Capability Template

> Template guidance: Copy everything below the rule into `docs/05-capabilities/CAP-NNNN-<short-title>.md`. A capability describes **what the business does** (e.g. "Milk Quality Assessment"), independent of org chart and technology. Capabilities are stable for years; systems that realize them change. Level 1 = top-level capability, Level 2 = sub-capability; go deeper only when it earns its keep.

---

```yaml
---
id: CAP-NNNN
title: <Capability name — a noun phrase>
type: cap
status: Draft
version: "0.1"
owner: <domain owner>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<parent CAP-ID>, <DOM-IDs>]
---
```

# CAP-NNNN — \<Capability Name\>

## 1. Definition

\<one paragraph: what ability this capability represents, in business language, no system names\>

- **Level:** 1 / 2
- **Parent capability:** \<CAP-ID or "None (Level 1)"\>

## 2. Why It Matters

\<the business outcome this capability enables and its importance to Lacteva's strategy\>

## 3. Sub-Capabilities

| ID | Sub-Capability | One-Line Definition |
| --- | --- | --- |
| CAP-XXXX | \<name\> | \<definition\> |

## 4. Inputs and Outputs

| Direction | What | From / To |
| --- | --- | --- |
| Input | \<information/material the capability consumes\> | \<capability or external party\> |
| Output | \<what it produces\> | \<capability or external party\> |

## 5. Key Business Objects

\<the domain concepts this capability centers on — glossary terms, e.g. Milk Collection, Quality Grade; link DOM-IDs\>

## 6. Realization

> Template guidance: The only section where systems appear. Keep it a mapping, not a design.

| Realized By | Type | Status |
| --- | --- | --- |
| \<service / product area / manual process\> | System / Manual / Hybrid | Live / Planned / Being replaced |

## 7. Maturity Assessment

| Dimension | Current | Target | Gap Notes |
| --- | --- | --- | --- |
| Automation | 1–5 | 1–5 | \<notes\> |
| Data quality | 1–5 | 1–5 | \<notes\> |
| Scalability | 1–5 | 1–5 | \<notes\> |

## 8. Dependencies

| Depends On | Nature of Dependency |
| --- | --- |
| \<CAP-ID\> | \<why\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
