---
id: TPL-0001
title: Architecture Decision Record Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# TPL-0001 — Architecture Decision Record Template

> Template guidance: Copy everything below the horizontal rule into `docs/03-architecture/adr/ADR-NNNN-<short-title>.md`. An ADR records **one** decision. Approved ADRs are immutable — to change course, write a new ADR that supersedes this one. Keep it under two pages; link out for detail.

---

```yaml
---
id: ADR-NNNN
title: <Decision title — a noun phrase, e.g. "Event Bus Selection">
type: adr
status: Draft
version: "0.1"
owner: <owning team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
supersedes: <ADR-ID or "None">
superseded-by: None
related: [<doc IDs>]
---
```

# ADR-NNNN — \<Title\>

## 1. Status

`Draft` | `In Review` | `Approved` | `Superseded by ADR-XXXX`

## 2. Context

> Template guidance: The forces at play — technical constraints, business drivers, scale targets, deadlines, prior decisions. A reader in three years must understand *why this decision was needed*. State facts, not opinions.

\<context\>

## 3. Decision Drivers

> Template guidance: The criteria the options were judged against, in priority order (e.g. multi-tenant isolation, operational cost at 1M-tenant scale, team familiarity, vendor lock-in).

1. \<driver 1\>
2. \<driver 2\>

## 4. Options Considered

> Template guidance: Minimum two real options. "Do nothing" counts when honest. For each: one-paragraph description, then pros/cons against the drivers.

### 4.1 Option A — \<name\>

\<description\>

- **Pros:** …
- **Cons:** …

### 4.2 Option B — \<name\>

\<description\>

- **Pros:** …
- **Cons:** …

## 5. Decision

> Template guidance: One sentence in the form "We will \<decision\>", followed by the rationale tying it back to the drivers. Name the losing options and why they lost.

We will \<decision\>.

## 6. Consequences

> Template guidance: Honest accounting — positive, negative, and neutral. Negative consequences do not weaken an ADR; hiding them does.

- **Positive:** …
- **Negative:** …
- **Neutral / follow-up decisions now required:** …

## 7. Compliance

> Template guidance: How conformance will be checked — lint rule, review checklist item, fitness function, or "manual review" (say so explicitly).

\<how we will know teams follow this decision\>

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
