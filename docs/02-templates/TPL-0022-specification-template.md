---
id: TPL-0022
title: Specification Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# TPL-0022 — Specification (SPC) Template

> Template guidance: Copy below the rule into `docs/03-architecture/02-domain-layer/<context-folder>/SPC-NNNN-<name>.md`. A specification (DDD pattern) is a NAMED, TESTABLE predicate over one domain object — "milk acceptable for collection", "animal eligible for insurance", "member in good standing". Policies (POL) compose specifications into rules; repositories (REP) select by them. One object kind, one question, yes/no answer.

---

```yaml
---
id: SPC-NNNN
title: <Specification name — an adjective phrase, e.g. "Acceptable For Collection">
type: spc
layer: domain
context: <DOM-NNNN>
status: Draft
version: "0.1"
owner: <context owner team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<candidate AGG/ENT/VAL>, <using POL/REP/BPR IDs>]
---
```

# SPC-NNNN — \<Specification Name\>

## 1. Question Answered

- **Candidate object:** \<AGG/ENT/VAL ID — the thing being tested\>
- **Question:** Is \<object\> \<specification name\>? → yes/no
- **Asked by:** \<the situations that need the answer\>

## 2. Criteria

> Template guidance: numbered clauses, each independently testable; state whether ALL must hold or a stated combination. Parameterized thresholds reference the owning POL's parameters — never hard-code.

| # | Clause | Data Needed |
| --- | --- | --- |
| C1 | \<testable condition\> | \<which attributes/facts\> |

**Combination rule:** \<ALL of C1–Cn / C1 AND (C2 OR C3) …\>

## 3. Indeterminate Cases

\<what the answer is when required data is missing or stale — a specification without this section is untestable in the field\>

## 4. Examples

| Case | C1 | C2 | … | Verdict |
| --- | --- | --- | --- | --- |
| \<realistic satisfying case\> | ✓ | ✓ | | Satisfied |
| \<realistic failing case\> | ✓ | ✗ | | Not satisfied — \<clause\> |

## 5. Used By

| Artifact | Usage |
| --- | --- |
| \<POL-ID\> | \<in which rule\> |
| \<REP-ID\> | Selection criterion |
| \<BPR-ID\> | Decision at step \<#\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
