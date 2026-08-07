---
id: INDEX
title: Master Documentation Index
type: reference
status: Approved
version: "1.8"
owner: Documentation Engineering
created: 2026-08-02
last-updated: 2026-08-06
baseline: ARCH-BASELINE-V1
---

# Master Documentation Index

Complete inventory of every document in the repository, by domain. Task-oriented entry points: [NAVIGATION.md](NAVIGATION.md). Machine-generated reference map: [XREF.md](XREF.md). **Maintenance rule:** updated in the same PR as any document addition, retitle, or status change (reviewers check per [GOV-0001](01-governance/GOV-0001-review-workflow.md)); to be generated automatically once the `tools/` validators exist.

Snapshot: 2026-08-02 — 87 markdown files (47 with formal document IDs, plus README/index, reference, and root files). Verified by `tools/validate/validate_docs.py`.

## Root

| Document | Purpose |
| --- | --- |
| [`ARCHITECTURE_BASELINE_V1.md`](../ARCHITECTURE_BASELINE_V1.md) | **Official source of truth** — locked architecture + precedence rules |
| [`docs/ai/CLAUDE_CONTEXT.md`](ai/CLAUDE_CONTEXT.md) | **Permanent AI-engineer onboarding guide** — read first when joining |
| [`docs/03-architecture/01-business-layer/BUSINESS-RULES.md`](03-architecture/01-business-layer/BUSINESS-RULES.md) | **Business Rules Register** — source of truth for BR-NNNN platform invariants |
| [`docs/product/PRODUCT_STRATEGY.md`](product/PRODUCT_STRATEGY.md) | Product strategy — segments, editions, pricing, deployment, ICPs, V1.0 definition |
| [`docs/03-architecture/04-technology-layer/PROJECTION-LIFECYCLE.md`](03-architecture/04-technology-layer/PROJECTION-LIFECYCLE.md) | Projection lifecycle & replay — states, rebuild, versioning, verification |
| [`REPOSITORY_AUDIT.md`](../REPOSITORY_AUDIT.md) | Baseline-migration audit (findings F-A1…F-A6, health score) |
| [`REPOSITORY_MIGRATION_PLAN.md`](../REPOSITORY_MIGRATION_PLAN.md) | Migration steps, manual-review queue MR-1…MR-8, deprecation ledger |
| [`DEVELOPMENT_ROADMAP.md`](../DEVELOPMENT_ROADMAP.md) | Code implementation sequence M0–M4 |
| [`README.md`](../README.md) | Repository entry point and map |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | Contribution workflow and rules |
| [`CHANGELOG.md`](../CHANGELOG.md) | Repository-level change history |
| [`.github/CODEOWNERS`](../.github/CODEOWNERS), [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) | Review enforcement and PR checklist |

## 00 — Standards ([index](00-standards/README.md))

| ID | Title | Status | Version |
| --- | --- | --- | --- |
| [STD-0001](00-standards/STD-0001-markdown-writing-standards.md) | Markdown Writing Standards | Approved | 1.2 |
| [STD-0002](00-standards/STD-0002-naming-conventions.md) | Naming Conventions | Approved | 1.0 |
| [STD-0003](00-standards/STD-0003-document-numbering.md) | Document Numbering Conventions | Approved | 1.3 |
| [STD-0004](00-standards/STD-0004-versioning-strategy.md) | Versioning Strategy | Approved | 1.0 |
| [STD-0005](00-standards/STD-0005-mermaid-standards.md) | Mermaid Standards | Approved | 1.0 |
| [STD-0006](00-standards/STD-0006-plantuml-standards.md) | PlantUML Standards | Approved | 1.0 |
| [STD-0007](00-standards/STD-0007-phoenix-software-engineering-standard.md) | Phoenix Software Engineering Standard | Approved | 1.0 |

## 01 — Governance ([index](01-governance/README.md))

| ID | Title | Status | Version |
| --- | --- | --- | --- |
| [GOV-0001](01-governance/GOV-0001-review-workflow.md) | Review Workflow | Approved | 1.0 |
| [GOV-0002](01-governance/GOV-0002-approval-workflow.md) | Approval Workflow | Approved | 1.0 |
| [GOV-0003](01-governance/GOV-0003-architecture-review-checklists.md) | Architecture Review Checklists | Approved | 1.0 |

## 02 — Templates ([index](02-templates/README.md))

| ID | Title | Status | Version |
| --- | --- | --- | --- |
| [TPL-0001](02-templates/TPL-0001-adr-template.md) | ADR Template | Approved | 1.0 |
| [TPL-0002](02-templates/TPL-0002-business-requirements-template.md) | BRD Template | Approved | 1.0 |
| [TPL-0003](02-templates/TPL-0003-product-requirements-template.md) | PRD Template | Approved | 1.0 |
| [TPL-0004](02-templates/TPL-0004-software-requirements-template.md) | SRS Template | Approved | 1.0 |
| [TPL-0005](02-templates/TPL-0005-api-specification-template.md) | API Specification Template | Approved | 1.0 |
| [TPL-0006](02-templates/TPL-0006-database-design-template.md) | Database Design Template | Approved | 1.0 |
| [TPL-0007](02-templates/TPL-0007-ai-model-card-template.md) | AI Model Card Template | Approved | 1.0 |
| [TPL-0008](02-templates/TPL-0008-event-specification-template.md) | Event Specification Template | Approved | 1.0 |
| [TPL-0009](02-templates/TPL-0009-business-capability-template.md) | Business Capability Template | Approved | 1.0 |
| [TPL-0010](02-templates/TPL-0010-domain-model-template.md) | Domain Model Template | Approved | 1.0 |
| [TPL-0011](02-templates/TPL-0011-glossary-template.md) | Glossary Template | Approved | 1.0 |
| [TPL-0012](02-templates/TPL-0012-changelog-template.md) | Change Log Template | Approved | 1.0 |
| [TPL-0013](02-templates/TPL-0013-concept-template.md) | Concept Template | Approved | 1.0 |
| [TPL-0014](02-templates/TPL-0014-business-process-template.md) | Business Process Template | Approved | 1.0 |
| [TPL-0015](02-templates/TPL-0015-platform-service-template.md) | Platform Service Template | Approved | 1.0 |
| [TPL-0016](02-templates/TPL-0016-product-template.md) | Product Template | Approved | 1.0 |
| [TPL-0017](02-templates/TPL-0017-aggregate-template.md) | Aggregate Template | Approved | 1.0 |
| [TPL-0018](02-templates/TPL-0018-entity-template.md) | Entity Template | Approved | 1.0 |
| [TPL-0019](02-templates/TPL-0019-value-object-template.md) | Value Object Template | Approved | 1.0 |
| [TPL-0020](02-templates/TPL-0020-repository-template.md) | Repository Template | Approved | 1.0 |
| [TPL-0021](02-templates/TPL-0021-policy-template.md) | Policy Template | Approved | 1.0 |
| [TPL-0022](02-templates/TPL-0022-specification-template.md) | Specification Template | Approved | 1.0 |
| [TPL-0023](02-templates/TPL-0023-ai-agent-template.md) | AI Agent Template | Approved | 1.0 |

## 03 — Enterprise Architecture Workspace ([overview](03-architecture/README.md))

Five architecture layers, each with a README and index: [Concepts](03-architecture/00-concepts/README.md) · [Business](03-architecture/01-business-layer/README.md) · [Domain](03-architecture/02-domain-layer/README.md) · [Application](03-architecture/03-application-layer/README.md) · [Technology](03-architecture/04-technology-layer/README.md). Cross-layer: [ADRs](03-architecture/adr/README.md) · [Domain models](03-architecture/domain-models/README.md) · [Diagrams](03-architecture/diagrams/README.md).

| Document | Purpose | Status | Version |
| --- | --- | --- | --- |
| [ARCH-INDEX](03-architecture/INDEX.md) | Architecture artifact index | Approved | 1.0 |
| [ARCH-TRACE](03-architecture/TRACEABILITY.md) | Layer traceability index + capability coverage | Approved | 1.0 |
| [ARCH-XREF](03-architecture/CROSS-REFERENCE.md) | Cross-reference rules and registers | Approved | 1.0 |
| [ARCH-DEPMAP](03-architecture/DEPENDENCY-MAP.md) | Authoring-order dependency maps | Approved | 1.0 |

First application-layer artifact: [PDT-0001 — Lacteva Collect](03-architecture/03-application-layer/PDT-0001-lacteva-collect.md) (Draft 0.1). No ADRs or domain models yet — those are Phase 1 of [QR-0004](12-quality/QR-0004-documentation-roadmap.md).

## 04 — Requirements ([index](04-requirements/README.md))

No BRDs, PRDs, or SRSs yet — BRD-0001 is roadmap item 1.1. Sub-indexes: [Business](04-requirements/business/README.md) · [Product](04-requirements/product/README.md) · [Software](04-requirements/software/README.md).

## 05 — Capabilities ([index](05-capabilities/README.md))

| ID | Title | Status | Version |
| --- | --- | --- | --- |
| [CAP-0001](05-capabilities/CAP-0001-business-capability-master-map.md) | Business Capability Master Map — Dairy Ecosystem | Draft | 0.1 |
| [CAP-0002](05-capabilities/CAP-0002-farm-production.md) | Farm Production (FPR) | Draft | 0.1 |
| [CAP-0003](05-capabilities/CAP-0003-milk-collection-logistics.md) | Milk Collection & Logistics (MCL) | Draft | 0.1 |
| [CAP-0004](05-capabilities/CAP-0004-quality-food-safety.md) | Quality & Food Safety (QFS) | Draft | 0.1 |
| [CAP-0005](05-capabilities/CAP-0005-processing-manufacturing.md) | Processing & Manufacturing (PRO) | Draft | 0.1 |
| [CAP-0006](05-capabilities/CAP-0006-commerce-market-access.md) | Commerce & Market Access (CMA) | Draft | 0.1 |
| [CAP-0007](05-capabilities/CAP-0007-producer-economics-financial-services.md) | Producer Economics & Financial Services (PEF) | Draft | 0.1 |
| [CAP-0008](05-capabilities/CAP-0008-cooperative-producer-relations.md) | Cooperative & Producer Relations (CPR) | Draft | 0.1 |
| [CAP-0009](05-capabilities/CAP-0009-sustainability-welfare-compliance.md) | Sustainability, Welfare & Compliance (SWC) | Draft | 0.1 |
| [CAP-0010](05-capabilities/CAP-0010-dairy-intelligence-advisory.md) | Dairy Intelligence & Advisory (DIA) | Draft | 0.1 |
| [CAP-0011](05-capabilities/CAP-0011-ecosystem-tenant-enablement.md) | Ecosystem & Tenant Enablement (ETE) | Draft | 0.1 |

## 06–10 — API, Data, AI, Events, Operations

Indexes: [API](06-api/README.md) · [Data](07-data/README.md) · [AI](08-ai/README.md) · [Events](09-events/README.md) · [Operations](10-operations/README.md). Only the data layer is populated; the rest await Phase 3–4 of the roadmap.

| Document | Status | Version |
| --- | --- | --- |
| [DBD-0001](07-data/DBD-0001-platform-core-database.md) — Platform Core Database (the Database Architecture Reference) | Approved | 1.0 |

## 11 — Glossary ([index](11-glossary/README.md))

| Document | Status | Version |
| --- | --- | --- |
| [GLOSSARY](11-glossary/GLOSSARY.md) — company-wide glossary | Approved | 1.3 |
| [TAXONOMY](11-glossary/TAXONOMY.md) — taxonomy of business terms | Approved | 1.1 |

## 12 — Quality ([index](12-quality/README.md))

| ID | Title | Status | Version |
| --- | --- | --- | --- |
| [QR-0001](12-quality/QR-0001-repository-health-report.md) | Repository Health Report | Approved | 1.1 |
| [QR-0002](12-quality/QR-0002-gap-analysis.md) | Gap Analysis | Approved | 1.0 |
| [QR-0003](12-quality/QR-0003-traceability-matrix.md) | Traceability Matrix | Approved | 1.0 |
| [QR-0004](12-quality/QR-0004-documentation-roadmap.md) | Documentation Roadmap & Dependency Graph | Approved | 1.0 |
| [QR-0005](12-quality/QR-0005-documentation-coverage-report.md) | Documentation Coverage Report | Approved | 1.0 |
| [QR-0006](12-quality/QR-0006-next-work-queue.md) | Next Work Queue | Approved | 1.0 |

## 13 — Products ([index](13-products/README.md))

**Lacteva Collect** ([package](13-products/lacteva-collect/README.md); product object [PDT-0001](03-architecture/03-application-layer/PDT-0001-lacteva-collect.md)):

| ID | Title | Status | Version |
| --- | --- | --- | --- |
| [PSP-0001](13-products/lacteva-collect/PSP-0001-actors-and-roles.md) | Actors & Operational Roles | Draft | 0.1 |
| [PSP-0002](13-products/lacteva-collect/PSP-0002-collection-center.md) | Collection Center Architecture | Draft | 0.1 |
| [PSP-0003](13-products/lacteva-collect/PSP-0003-shift.md) | Shift | Draft | 0.1 |
| [PSP-0004](13-products/lacteva-collect/PSP-0004-shift-lifecycle.md) | Shift Lifecycle | Draft | 0.1 |
| [PSP-0005](13-products/lacteva-collect/PSP-0005-shift-opening.md) | Shift Opening | Draft | 0.1 |
| [PSP-0006](13-products/lacteva-collect/PSP-0006-shift-closing.md) | Shift Closing | Draft | 0.1 |
| [PSP-0007](13-products/lacteva-collect/PSP-0007-hardware-profile.md) | Hardware Profile | Draft | 0.1 |
| [PSP-0008](13-products/lacteva-collect/PSP-0008-operational-metrics.md) | Operational Metrics | Draft | 0.1 |
| [PSP-0009](13-products/lacteva-collect/PSP-0009-business-rules.md) | Business Rules | Draft | 0.1 |
| [PSP-0010](13-products/lacteva-collect/PSP-0010-business-events.md) | Business Events | Draft | 0.1 |
| [TRACEABILITY](13-products/lacteva-collect/TRACEABILITY.md) · [REVIEW-NOTES](13-products/lacteva-collect/REVIEW-NOTES.md) | Package traceability & review registers | Draft | 0.1 |

## Code Roots

[`services/`](../services/README.md) · [`libs/`](../libs/README.md) · [`infra/`](../infra/README.md) · [`tools/`](../tools/README.md). Code delivered so far: [`tools/validate/`](../tools/validate/README.md) (documentation validator) and [`tools/xref/`](../tools/xref/README.md) (cross-reference generator).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.8 | 2026-08-06 | Architecture Board | DBR-001: DBD-0001 Platform Core Database listed under 06–10. |
| 1.7 | 2026-08-04 | Engineering | Added the projection lifecycle reference (PLT-001). |
| 1.6 | 2026-08-04 | Product | Added docs/product/PRODUCT_STRATEGY.md. |
| 1.5 | 2026-08-03 | Architecture Board | Added the Business Rules Register (BR-REGISTER, business layer). |
| 1.4 | 2026-08-03 | Engineering | Added docs/ai/CLAUDE_CONTEXT.md (permanent AI-engineer onboarding guide). |
| 1.3 | 2026-08-02 | Lacteva Collect Product Team | Added 13-products section (Lacteva Collect package: PSP-0001…0010, PDT-0001); refreshed version columns. |
| 1.2 | 2026-08-02 | Documentation Engineering | Added navigation page, XREF map, QR-0005/0006; own Change Log section added (validator finding). |
| 1.1 | 2026-08-02 | Architecture Board | EA workspace: GOV-0003, TPL-0013…0023, architecture indexes. |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial master index. |
