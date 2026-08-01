# 02 — Templates

Every formal document in this repository starts from a template in this folder. **Never start from a blank page** — templates encode the standards, so starting from one is the fastest way to pass review.

## How to Use a Template

1. Copy the template file to the target domain folder.
2. Rename it per [STD-0002](../00-standards/STD-0002-naming-conventions.md), assigning the next ID per [STD-0003](../00-standards/STD-0003-document-numbering.md).
3. Replace all `<angle-bracket>` placeholders and delete the `> Template guidance:` blockquotes — they are instructions to you, not document content.
4. Fill **every** section. A section that does not apply gets `Not applicable — <reason>`; it is never deleted, so reviewers can see the question was considered.
5. Set front matter: `status: Draft`, `version: "0.1"`, your team as `owner`.

## Index

| ID | Template | Produces | Home Domain |
| --- | --- | --- | --- |
| [TPL-0001](TPL-0001-adr-template.md) | Architecture Decision Record | `ADR` | `03-architecture/adr/` |
| [TPL-0002](TPL-0002-business-requirements-template.md) | Business Requirements Document | `BRD` | `04-requirements/business/` |
| [TPL-0003](TPL-0003-product-requirements-template.md) | Product Requirements Document | `PRD` | `04-requirements/product/` |
| [TPL-0004](TPL-0004-software-requirements-template.md) | Software Requirements Specification | `SRS` | `04-requirements/software/` |
| [TPL-0005](TPL-0005-api-specification-template.md) | API Specification | `API` | `06-api/` |
| [TPL-0006](TPL-0006-database-design-template.md) | Database Design | `DBD` | `07-data/` |
| [TPL-0007](TPL-0007-ai-model-card-template.md) | AI Model Card | `AIM` | `08-ai/` |
| [TPL-0008](TPL-0008-event-specification-template.md) | Event Specification | `EVT` | `09-events/` |
| [TPL-0009](TPL-0009-business-capability-template.md) | Business Capability | `CAP` | `05-capabilities/` |
| [TPL-0010](TPL-0010-domain-model-template.md) | Domain Model | `DOM` | `03-architecture/domain-models/` |
| [TPL-0011](TPL-0011-glossary-template.md) | Glossary | glossary sections | `11-glossary/` |
| [TPL-0012](TPL-0012-changelog-template.md) | Change Log | change logs | any component/service |
| [TPL-0013](TPL-0013-concept-template.md) | Concept | `CON` | `03-architecture/00-concepts/` |
| [TPL-0014](TPL-0014-business-process-template.md) | Business Process | `BPR` | `03-architecture/01-business-layer/` |
| [TPL-0015](TPL-0015-platform-service-template.md) | Platform Service | `PSV` | `03-architecture/03-application-layer/` |
| [TPL-0016](TPL-0016-product-template.md) | Product | `PDT` | `03-architecture/03-application-layer/` |
| [TPL-0017](TPL-0017-aggregate-template.md) | Aggregate | `AGG` | `03-architecture/02-domain-layer/` |
| [TPL-0018](TPL-0018-entity-template.md) | Entity | `ENT` | `03-architecture/02-domain-layer/` |
| [TPL-0019](TPL-0019-value-object-template.md) | Value Object | `VAL` | `03-architecture/02-domain-layer/` |
| [TPL-0020](TPL-0020-repository-template.md) | Repository (domain access) | `REP` | `03-architecture/02-domain-layer/` |
| [TPL-0021](TPL-0021-policy-template.md) | Policy | `POL` | `03-architecture/02-domain-layer/` |
| [TPL-0022](TPL-0022-specification-template.md) | Specification | `SPC` | `03-architecture/02-domain-layer/` |
| [TPL-0023](TPL-0023-ai-agent-template.md) | AI Agent | `AGT` | `03-architecture/03-application-layer/` |

Enterprise Architecture artifacts reuse existing templates where they already exist: ADRs → TPL-0001, business capabilities → TPL-0009 (as amended for domain catalogs), domain models/bounded contexts → TPL-0010, event contracts → TPL-0008. Review checklists for all EA artifact types: [GOV-0003](../01-governance/GOV-0003-architecture-review-checklists.md).

## Changing a Template

Templates are Architecture Board–approved documents. To change one, open a PR with rationale; consider the migration cost for in-flight documents based on the old version. Template changes never retroactively invalidate approved documents.
