---
id: NAVIGATION
title: Repository Navigation Guide
type: reference
status: Approved
version: "1.1"
owner: Documentation Engineering
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# Repository Navigation Guide

Task-oriented entry points into the repository. The [master index](INDEX.md) answers "what exists"; this page answers **"where do I go to do X"**. What the architecture *is* — and which document wins any conflict — is [ARCHITECTURE_BASELINE_V1](../ARCHITECTURE_BASELINE_V1.md).

## I am new here

1. [Repository README](../README.md) — what this repository is and the ground rules.
2. [CAP-0001 Business Capability Master Map](05-capabilities/CAP-0001-business-capability-master-map.md) — what the business does; the anchor of everything.
3. [EA workspace overview](03-architecture/README.md) — the five architecture layers.
4. [Glossary](11-glossary/GLOSSARY.md) and [Taxonomy](11-glossary/TAXONOMY.md) — speak the language.

## I want to author a document

1. Find the type and its home: [STD-0003 prefix registry](00-standards/STD-0003-document-numbering.md#3-prefix-registry).
2. Copy the template: [template index](02-templates/README.md).
3. Follow the workflow: [CONTRIBUTING](../CONTRIBUTING.md) → [review](01-governance/GOV-0001-review-workflow.md) → [approval](01-governance/GOV-0002-approval-workflow.md); architecture artifacts also pass [GOV-0003 checklists](01-governance/GOV-0003-architecture-review-checklists.md).
4. Before opening the PR: run `python3 tools/validate/validate_docs.py` and `python3 tools/xref/generate_xref.py`; update your domain index and [INDEX.md](INDEX.md).

## I want to understand the architecture

| Question | Go To |
| --- | --- |
| What can the business do? | [Capability model](05-capabilities/README.md) (86 capabilities, 10 domains) |
| How do the layers fit together? | [EA overview](03-architecture/README.md) |
| What traces to what? | [Architecture traceability](03-architecture/TRACEABILITY.md) · [QR-0003 pipeline matrix](12-quality/QR-0003-traceability-matrix.md) |
| Who cites whom? | [XREF auto-map](XREF.md) (existing refs) · [Cross-reference rules](03-architecture/CROSS-REFERENCE.md) (legal refs) |
| What order is work done in? | [Dependency map](03-architecture/DEPENDENCY-MAP.md) · [Roadmap QR-0004](12-quality/QR-0004-documentation-roadmap.md) · [Work queue QR-0006](12-quality/QR-0006-next-work-queue.md) |
| Why is something the way it is? | [ADR index](03-architecture/adr/README.md) (empty until Phase 1) |

## I want to know the state of the repository

- [QR-0005 Documentation Coverage Report](12-quality/QR-0005-documentation-coverage-report.md) — done / in progress / missing, with statistics.
- [QR-0001 Health Report](12-quality/QR-0001-repository-health-report.md) — findings register.
- [CHANGELOG](../CHANGELOG.md) — what changed at repository level.

## Section navigation

[Standards](00-standards/README.md) · [Governance](01-governance/README.md) · [Templates](02-templates/README.md) · [Architecture](03-architecture/README.md) ([Concepts](03-architecture/00-concepts/README.md) · [Business](03-architecture/01-business-layer/README.md) · [Domain](03-architecture/02-domain-layer/README.md) · [Application](03-architecture/03-application-layer/README.md) · [Technology](03-architecture/04-technology-layer/README.md) · [ADRs](03-architecture/adr/README.md) · [Domain models](03-architecture/domain-models/README.md) · [Diagrams](03-architecture/diagrams/README.md)) · [Requirements](04-requirements/README.md) ([Business](04-requirements/business/README.md) · [Product](04-requirements/product/README.md) · [Software](04-requirements/software/README.md)) · [Capabilities](05-capabilities/README.md) · [API](06-api/README.md) · [Data](07-data/README.md) · [AI](08-ai/README.md) · [Events](09-events/README.md) · [Operations](10-operations/README.md) · [Glossary](11-glossary/README.md) · [Quality](12-quality/README.md) · [Products](13-products/README.md) ([Lacteva Collect](13-products/lacteva-collect/README.md))

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-02 | Lacteva Collect Product Team | Added Products section (Lacteva Collect package). |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial navigation guide. |
