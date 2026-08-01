# Layer 02 — Domain Layer

The modeled heart of the platform: bounded contexts and their tactical building blocks, in Domain-Driven Design terms. Strategic design (`DOM` documents — one per bounded context) lives in [`../domain-models/`](../domain-models/README.md); this folder holds the **tactical artifacts inside those contexts**, one subfolder per context once modeling begins (`<dom-id>-<context-slug>/`, e.g. `dom-0001-collection/`).

## Artifact Types

| Prefix | Artifact | Template | One-Line Definition |
| --- | --- | --- | --- |
| `AGG` | Aggregate | [TPL-0017](../../02-templates/TPL-0017-aggregate-template.md) | Consistency boundary: a cluster of objects whose invariants hold transactionally |
| `ENT` | Entity | [TPL-0018](../../02-templates/TPL-0018-entity-template.md) | Object with identity and lifecycle inside an aggregate |
| `VAL` | Value Object | [TPL-0019](../../02-templates/TPL-0019-value-object-template.md) | Immutable value defined by its attributes (e.g. a quality measurement) |
| `REP` | Repository | [TPL-0020](../../02-templates/TPL-0020-repository-template.md) | Access abstraction for an aggregate: how the business retrieves and stores it — implementation-free |
| `POL` | Policy | [TPL-0021](../../02-templates/TPL-0021-policy-template.md) | Business rule with parameters and enforcement points |
| `SPC` | Specification | [TPL-0022](../../02-templates/TPL-0022-specification-template.md) | Named, testable predicate over a domain object ("milk acceptable for collection") |

Domain events are modeled in the owning `DOM` (§6) and formalized as `EVT` contracts in [`docs/09-events/`](../../09-events/README.md) — no separate template here.

## Rules

- **Context first.** No tactical artifact exists without an approved `DOM`; every artifact's front matter carries `context: DOM-NNNN`.
- **Granularity discipline.** Aggregates always get documents. Entities/value objects get standalone documents only when referenced across aggregates or carrying non-trivial rules; trivial ones are defined inline in their `AGG` and listed in its contents table.
- Naming: `<PREFIX>-NNNN-<name>.md`; IDs are global per prefix ([STD-0003](../../00-standards/STD-0003-document-numbering.md)).
- No persistence, framework, or API language — that arrives in SRS/DBD/API documents, which cite these artifacts.
- Approval: context owner + Architecture Board member.

## Index

| ID | Artifact | Kind | Context | Status |
| --- | --- | --- | --- | --- |
| — | *None yet — awaits the first approved domain models (roadmap Phase 1, [QR-0004](../../12-quality/QR-0004-documentation-roadmap.md)).* | | | |
