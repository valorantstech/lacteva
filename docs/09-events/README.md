# 09 — Event Catalog

Specifications for every event on the platform's event-driven backbone. Events are **contracts between teams**: the producer owns the spec, consumers depend on it, and changes follow the same rigor as API changes.

- Template: [TPL-0008](../02-templates/TPL-0008-event-specification-template.md)
- Naming: `EVT-NNNN-<event-title>.md`; event names are `<domain>.<past-tense-fact>.v<major>` (e.g. `collection.milk-collected.v1`) per [STD-0002](../00-standards/STD-0002-naming-conventions.md)
- Versioning: additive-only within a major; breaking changes mint `v2` with a parallel-run migration, per [STD-0004 §5](../00-standards/STD-0004-versioning-strategy.md)
- Approval: event platform owner + producing team lead ([GOV-0002](../01-governance/GOV-0002-approval-workflow.md))

## Rules

- Events record **facts that happened** (past tense), not commands or requests.
- Every spec states its emission guarantee (duplicates possible?) and ordering guarantee (partition key) — consumers design against these, so vagueness here becomes someone else's outage.
- The **Consumers** table in each spec drives the approval set for breaking changes; producers keep it current.
- Machine-readable schemas live in the schema registry and the spec's `assets/` folder; the spec is authoritative for semantics.

## Index

| ID | Event Name | Producer | Status |
| --- | --- | --- | --- |
| — | *No event specifications yet — the first events are specified with the first service designs.* | | |
