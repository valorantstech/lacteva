# Domain Models

One document per **bounded context**, from [TPL-0010](../../02-templates/TPL-0010-domain-model-template.md), named `DOM-NNNN-<context-name>.md`.

## Rules

- The domain model is the semantic source of truth for its context: database designs (`DBD`) and API specifications (`API`) realize it and link back to it.
- Every term in a domain model exists in the [glossary](../../11-glossary/GLOSSARY.md), context-qualified where meanings differ between contexts.
- Context boundaries are architecture decisions — significant boundary choices get an ADR.
- A context-map overview diagram showing all contexts and their relationships will live in [`../diagrams/`](../diagrams/README.md) once two or more contexts exist.

## Index

| ID | Bounded Context | Status |
| --- | --- | --- |
| — | *No domain models yet. Candidate first contexts, aligned with the capability model ([CAP-0001](../../05-capabilities/CAP-0001-business-capability-master-map.md)): Farm Production (FPR), Milk Collection & Logistics (MCL), Quality & Food Safety (QFS), Producer Economics & Settlement (PEF), Dairy Intelligence & Advisory (DIA). Sequencing in [QR-0004](../../12-quality/QR-0004-documentation-roadmap.md).* | |
