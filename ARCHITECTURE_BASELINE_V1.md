---
id: ARCH-BASELINE-V1
title: Lacteva Architecture Baseline V1
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
related: [CAP-0001, PDT-0001, QR-0004, QR-0006]
---

# Lacteva Architecture Baseline V1

**This document is the official source of truth for the Lacteva architecture.** It is a *consolidating index with binding precedence rules*, not a restatement: each element below names the authoritative document and locks it. Anything conflicting with this baseline is wrong until the baseline is superseded (V2) through [GOV-0002](docs/01-governance/GOV-0002-approval-workflow.md).

## 1. What Is Locked

### 1.1 Governance & Method

| Element | Authoritative Document(s) |
| --- | --- |
| Authoring standards (Markdown, naming, numbering, versioning, diagrams) | [STD-0001…0006](docs/00-standards/README.md) |
| Review / approval / architecture checklists | [GOV-0001…0003](docs/01-governance/README.md) |
| Templates (all 23) | [TPL-0001…0023](docs/02-templates/README.md) |
| Machine enforcement | `tools/validate/`, `tools/xref/` (CI-gated) |

### 1.2 Business Architecture

| Element | Authoritative Document(s) |
| --- | --- |
| The dairy-ecosystem model: **10 domains, ~40 subdomains, 86 capabilities**, capability IDs `<DOM>.<SUB>.<NN>` | [CAP-0001](docs/05-capabilities/CAP-0001-business-capability-master-map.md) + CAP-0002…0011 |
| Cross-domain dependency model & global-variability rules | CAP-0001 §6–§7 |
| Glossary & taxonomy (terminology source of truth) | [GLOSSARY](docs/11-glossary/GLOSSARY.md) · [TAXONOMY](docs/11-glossary/TAXONOMY.md) |

*Status caveat (open item MR-1):* the CAP suite is content-locked by this baseline but formally `Draft` pending the staffed GOV-0002 approval cycle.

### 1.3 Enterprise Architecture Framework

| Element | Authoritative Document(s) |
| --- | --- |
| Five-layer model (concepts → business → domain → application → technology) and artifact types (CON, BPR, DOM, AGG/ENT/VAL/REP/POL/SPC, PSV, PDT, AGT) | [EA workspace](docs/03-architecture/README.md) |
| Trace rules, citation legality, authoring order | [TRACEABILITY](docs/03-architecture/TRACEABILITY.md) · [CROSS-REFERENCE](docs/03-architecture/CROSS-REFERENCE.md) · [DEPENDENCY-MAP](docs/03-architecture/DEPENDENCY-MAP.md) |

### 1.4 Product Architecture

| Element | Authoritative Document(s) |
| --- | --- |
| Product: **Lacteva Collect** (proposition, capability surface, boundaries) | [PDT-0001](docs/03-architecture/03-application-layer/PDT-0001-lacteva-collect.md) |
| Collect chapters 1–3: actors, collection center, hardware profiles, shift engine (lifecycle, opening, closing), rules R01–R12, event register | [PSP-0001…0010](docs/13-products/lacteva-collect/README.md) |
| Collect assumption/question register (binding until answered) | [REVIEW-NOTES](docs/13-products/lacteva-collect/REVIEW-NOTES.md) |

### 1.5 Platform Implementation Baseline

| Element | Locked As |
| --- | --- |
| Backend stack | Python 3.13 / FastAPI / SQLAlchemy 2 / Alembic / PostgreSQL / Redis / RabbitMQ / MinIO-S3 / OpenSearch / uv / Ruff / Pytest / Docker |
| Clients | Flutter (mobile), Next.js + TypeScript + Tailwind + shadcn/ui (admin portal) |
| Cloud | AWS |
| Deployment shape | Modular monolith `services/platform-core`; internal modules are the service seams (split criteria in [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md)) |
| Tenancy | `Organization.id` **is** the tenant id, platform-wide |
| Permissions | Central registry (`modules/authz/permissions.py`); keys `<module>.<action>`; RBAC with wildcard system role |
| Events | Envelope + `<domain>.<fact>.v<major>` types on topic exchange `lacteva.events` |
| Implementation sequence | [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md) M0–M4 |

*Status caveat (open item MR-2):* the stack is locked here but its founding ADRs are unwritten — backfill is queue item B4; the ADRs will cite this baseline, not re-decide it.

## 2. Precedence Rules (conflict resolution)

1. This baseline outranks every other document on *what the architecture is*; the referenced document outranks the baseline on *detail* (the baseline never restates detail).
2. Between documents: **Approved beats Draft; more specific beats more general; newer version beats older** — in that order.
3. Roadmaps: [QR-0004](docs/12-quality/QR-0004-documentation-roadmap.md) governs documentation order; [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md) governs code order; [QR-0006](docs/12-quality/QR-0006-next-work-queue.md) is the merged actionable queue. On conflict between them, QR-0006 is corrected to match the other two.
4. Terminology conflicts resolve to the [GLOSSARY](docs/11-glossary/GLOSSARY.md); a document using a term otherwise is defective.
5. Code vs documentation: approved documents describe intent; code describes reality. Divergence is a defect tracked in `docs/12-quality/` — never silently resolved in either direction.

## 3. How Documents Reference This Baseline

Every formal document carries front matter `baseline: ARCH-BASELINE-V1` (registered in [STD-0001 §2](docs/00-standards/STD-0001-markdown-writing-standards.md)); domain indexes carry a governance line. Exception: `docs/XREF.md` is generator-owned. New documents inherit the requirement via the templates' front-matter blocks (migration plan step M5).

## 4. Changing the Baseline

- **V1 is immutable once ratified.** Changes produce `ARCHITECTURE_BASELINE_V2.md` with a supersession record, approved by the Architecture Board per GOV-0002.
- Adding detail to referenced documents (new ADRs, approved DOMs) does **not** require a new baseline version — the baseline locks structure and precedence, not content growth within it.
- Ratification of V1 itself is open item MR-3 in the [migration plan](REPOSITORY_MIGRATION_PLAN.md) (requires staffed Architecture Board).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Architecture Board (pending ratification, MR-3) | Initial baseline consolidating governance, capability model, EA framework, Collect product, and platform implementation. |
