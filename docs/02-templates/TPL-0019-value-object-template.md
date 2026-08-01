---
id: TPL-0019
title: Value Object Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# TPL-0019 — Value Object (VAL) Template

> Template guidance: Copy below the rule into `docs/03-architecture/02-domain-layer/<context-folder>/VAL-NNNN-<name>.md`. A value object is defined entirely by its attributes: no identity, immutable, freely shared — e.g. a quality measurement, a quantity, a grade. Standalone documents are for value objects used across aggregates or with real validity rules; trivial ones stay inline in their AGG.

---

```yaml
---
id: VAL-NNNN
title: <Value object name>
type: val
layer: domain
context: <DOM-NNNN>
status: Draft
version: "0.1"
owner: <context owner team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<using AGG/ENT IDs>]
---
```

# VAL-NNNN — \<Value Object Name\>

## 1. Definition

\<what the value expresses, one paragraph; glossary terms\>

## 2. Attributes

| Attribute | Kind | Meaning | Unit / Format |
| --- | --- | --- | --- |
| \<name\> | \<kind\> | \<meaning\> | \<SI unit, ISO format, scheme reference\> |

## 3. Validity Rules

> Template guidance: an invalid instance must be impossible to construct — state every rule that guarantees that.

| # | Rule |
| --- | --- |
| V1 | \<e.g. fat content within 0–15%, two decimals\> |

## 4. Semantics

- **Equality:** two instances are the same value when \<attribute equality definition\>.
- **Immutability consequence:** \<what "changing" it means — always replacement, e.g. a corrected measurement is a NEW value with its own provenance\>
- **Derived values / operations:** \<meaningful computations, e.g. price component from composition\>

## 5. Examples

| Example | Valid? | Why |
| --- | --- | --- |
| \<concrete example\> | Yes | |
| \<counter-example\> | No | \<violated rule #\> |

## 6. Used By

| Artifact | As |
| --- | --- |
| \<AGG/ENT IDs\> | \<attribute/role\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
