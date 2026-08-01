---
id: STD-0003
title: Document Numbering Conventions
type: standard
status: Approved
version: "1.2"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# STD-0003 — Document Numbering Conventions

## 1. Purpose

Every formal document has a permanent, unique ID. IDs make documents citable ("per ADR-0007"), traceable across requirements → design → implementation, and immune to retitling.

## 2. ID Format

```
<PREFIX>-<NNNN>
```

- `PREFIX` — the document-type prefix from the registry below.
- `NNNN` — zero-padded, monotonically increasing four-digit number **per prefix**, starting at `0001`.

## 3. Prefix Registry

| Prefix | Document Type | Home | Template |
| --- | --- | --- | --- |
| `STD` | Standard | `docs/00-standards/` | — (standards are self-shaped) |
| `GOV` | Governance document | `docs/01-governance/` | — |
| `TPL` | Template | `docs/02-templates/` | — |
| `ADR` | Architecture Decision Record | `docs/03-architecture/adr/` | [TPL-0001](../02-templates/TPL-0001-adr-template.md) |
| `DOM` | Domain model | `docs/03-architecture/domain-models/` | [TPL-0010](../02-templates/TPL-0010-domain-model-template.md) |
| `BRD` | Business requirements document | `docs/04-requirements/business/` | [TPL-0002](../02-templates/TPL-0002-business-requirements-template.md) |
| `PRD` | Product requirements document | `docs/04-requirements/product/` | [TPL-0003](../02-templates/TPL-0003-product-requirements-template.md) |
| `SRS` | Software requirements specification | `docs/04-requirements/software/` | [TPL-0004](../02-templates/TPL-0004-software-requirements-template.md) |
| `CAP` | Business capability | `docs/05-capabilities/` | [TPL-0009](../02-templates/TPL-0009-business-capability-template.md) |
| `API` | API specification | `docs/06-api/` | [TPL-0005](../02-templates/TPL-0005-api-specification-template.md) |
| `DBD` | Database design | `docs/07-data/` | [TPL-0006](../02-templates/TPL-0006-database-design-template.md) |
| `AIM` | AI model / AI system documentation | `docs/08-ai/` | [TPL-0007](../02-templates/TPL-0007-ai-model-card-template.md) |
| `EVT` | Event specification | `docs/09-events/` | [TPL-0008](../02-templates/TPL-0008-event-specification-template.md) |
| `OPS` | Runbook / operational document | `docs/10-operations/` | — (template to be added with first runbook) |
| `QR` | Quality review report (repository/documentation audits) | `docs/12-quality/` | — (reports are review-shaped, not templated) |
| `CON` | Concept | `docs/03-architecture/00-concepts/` | [TPL-0013](../02-templates/TPL-0013-concept-template.md) |
| `BPR` | Business process | `docs/03-architecture/01-business-layer/` | [TPL-0014](../02-templates/TPL-0014-business-process-template.md) |
| `AGG` | Aggregate | `docs/03-architecture/02-domain-layer/` | [TPL-0017](../02-templates/TPL-0017-aggregate-template.md) |
| `ENT` | Entity | `docs/03-architecture/02-domain-layer/` | [TPL-0018](../02-templates/TPL-0018-entity-template.md) |
| `VAL` | Value object | `docs/03-architecture/02-domain-layer/` | [TPL-0019](../02-templates/TPL-0019-value-object-template.md) |
| `REP` | Repository (domain access abstraction) | `docs/03-architecture/02-domain-layer/` | [TPL-0020](../02-templates/TPL-0020-repository-template.md) |
| `POL` | Policy | `docs/03-architecture/02-domain-layer/` | [TPL-0021](../02-templates/TPL-0021-policy-template.md) |
| `SPC` | Specification (domain predicate) | `docs/03-architecture/02-domain-layer/` | [TPL-0022](../02-templates/TPL-0022-specification-template.md) |
| `PSV` | Platform service | `docs/03-architecture/03-application-layer/` | [TPL-0015](../02-templates/TPL-0015-platform-service-template.md) |
| `PDT` | Product definition (architecture object — not a PRD) | `docs/03-architecture/03-application-layer/` | [TPL-0016](../02-templates/TPL-0016-product-template.md) |
| `AGT` | AI agent charter | `docs/03-architecture/03-application-layer/` | [TPL-0023](../02-templates/TPL-0023-ai-agent-template.md) |

New prefixes require a PR updating this registry, approved by the Architecture Board.

## 4. Assigning Numbers

1. Check the domain's `README.md` index for the highest allocated number.
2. Take the next number. The index update in your PR **is** the reservation; merge conflicts on the index are the collision-detection mechanism.
3. Numbers are **never reused**, even if a document is abandoned before approval — mark the ID as `Withdrawn` in the index.

## 5. Requirement-Level IDs

Within requirements documents, individual requirements get stable sub-IDs:

```
<DOC-ID>-<KIND><NN>
```

- Kinds: `G` (goal), `F` (functional), `N` (non-functional), `C` (constraint), `A` (assumption), `R` (risk).
- Examples: `BRD-0002-G01`, `SRS-0012-F04`, `SRS-0012-N02`.
- Sub-IDs are never renumbered; deleted requirements keep their ID with status `Removed`.

These sub-IDs are the anchor for traceability matrices linking BRD → PRD → SRS → design → tests.

## 6. Citing Documents

- In prose: link the ID on first mention (pattern `[<DOC-ID>](<relative-path>.md)`); plain ID text thereafter.
- In commits and PR titles: bare ID, e.g. `docs(adr): add ADR-0007 event bus selection`.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.2 | 2026-08-02 | Architecture Board | Registered 11 Enterprise Architecture prefixes (CON, BPR, AGG, ENT, VAL, REP, POL, SPC, PSV, PDT, AGT) with the EA workspace. |
| 1.1 | 2026-08-02 | Documentation Engineering | Added `QR` prefix for quality review reports; editorial link-example fix (QR-0001 finding). |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial approved version. |
