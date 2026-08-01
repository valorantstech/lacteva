---
id: ARCH-XREF
title: Architecture Cross-Reference Index
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
related: [ARCH-TRACE]
---

# Architecture Cross-Reference Index

**Horizontal** referencing: how artifacts cite each other, which citation directions are legal, and the register of heavily-referenced artifacts. Where [TRACEABILITY.md](TRACEABILITY.md) answers "does everything trace up?", this index answers "who depends on whom sideways — and is that allowed?"

## Citation Rules

1. **Cite by ID, link on first mention** ([STD-0003 §6](../00-standards/STD-0003-document-numbering.md)). Machine-readable citations go in front matter `related:`; prose links are for readers.
2. **Legal reference directions** (A → B means A may cite B):

| From \ To | CON | CAP | BPR | DOM | Tactical | PSV | PDT | AGT | ADR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CON | ✓ | ✓ | — | — | — | — | — | — | ✓ |
| CAP | ✓ | ✓ | — | — | — | — | — | — | — |
| BPR | ✓ | ✓ | ✓ | — | — | — | — | — | — |
| DOM | ✓ | ✓ | ✓ | ✓ | own only | — | — | — | ✓ |
| Tactical | ✓ | — | — | own context | same context ✓ | — | — | — | ✓ |
| PSV | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ |
| PDT | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | ✓ | ✓ |
| AGT | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | ✓ |
| ADR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

   Key prohibitions the matrix encodes: **capabilities cite nothing below the business layer** (they must stay implementation-blind); **tactical artifacts never cite other contexts' tactical artifacts** (cross-context coupling goes through events/interfaces at the PSV level); **nothing cites a PDT except PDTs and ADRs** (products consume architecture, architecture never depends on products).

3. **Cross-context references** between domain artifacts are expressed as context relationships in the two `DOM` documents (TPL-0010 §7), never as direct tactical citations.

## High-Fan-In Register

Artifacts cited by many others are change-risk concentrators; register any artifact with ≥ 5 inbound citations so reviewers know a change has blast radius:

| Artifact | Inbound Citations | Nature of Dependency |
| --- | --- | --- |
| — | *None yet — populated as the workspace fills* | |

## Reference Integrity

- Dangling ID citations are review-blocking; `tools/validate/validate_docs.py` checks capability-ID references today and will cover all prefixes as artifacts appear.
- When an artifact is superseded, the superseding PR MUST update every inbound citation (find them: `grep -r "<ID>" docs/`).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Architecture Board | Citation rules, legality matrix, and registers established. |
