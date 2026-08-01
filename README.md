# Lacteva Engineering Repository

Lacteva is an AI-first, cloud-native, multi-tenant **Dairy Intelligence Platform** with a long-term vision of serving 1M+ dairy businesses across 50+ countries. This repository is the **single source of truth** for Lacteva's engineering organization: documentation, architecture decisions, requirements, and (over time) the platform's code.

## Repository Map

| Path | Purpose |
| --- | --- |
| `docs/00-standards/` | Writing, naming, numbering, versioning, and diagram standards. Read these before authoring anything. |
| `docs/01-governance/` | Review and approval workflows that every document must pass through. |
| `docs/02-templates/` | Reusable templates for every document type (ADR, BRD, PRD, SRS, API, database, AI, events, capabilities, domain models, glossary, change log). |
| `docs/03-architecture/` | Approved architecture documentation: ADRs, domain models, system diagrams. |
| `docs/04-requirements/` | Business, product, and software requirements. |
| `docs/05-capabilities/` | The business capability map — what the company does, independent of how. |
| `docs/06-api/` | API specifications for all public and internal APIs. |
| `docs/07-data/` | Database designs, data dictionaries, and data governance documents. |
| `docs/08-ai/` | AI/ML documentation: model cards, evaluation reports, prompt specifications. |
| `docs/09-events/` | The event catalog for the platform's event-driven backbone. |
| `docs/10-operations/` | Runbooks and operational documentation. |
| `docs/11-glossary/` | The company-wide glossary and taxonomy of domain and technical terms. |
| `docs/12-quality/` | Repository quality reports, traceability matrix, and the documentation roadmap. |
| `docs/INDEX.md` | Master index of every document in the repository. |
| `services/` | Platform microservices (code). |
| `libs/` | Shared libraries used across services. |
| `infra/` | Infrastructure as code. |
| `tools/` | Internal developer tooling. |

## Getting Started

1. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) — how work enters this repository.
2. Read the standards in [`docs/00-standards/`](docs/00-standards/README.md) — non-negotiable authoring rules.
3. Find the right template in [`docs/02-templates/`](docs/02-templates/README.md) — never start a document from a blank page.
4. Follow the review and approval workflows in [`docs/01-governance/`](docs/01-governance/README.md).

## Ground Rules

- **Nothing is official unless it is in this repository and has status `Approved`.** Slide decks, chat messages, and wikis are not sources of truth.
- **Every document starts from a template** and carries YAML front matter (ID, version, status, owner).
- **Every change goes through a pull request.** Direct pushes to the default branch are prohibited.
- **Documents are versioned and never silently rewritten.** History is part of the record.

## Repository Status

The repository is in its **foundation phase**: standards, governance, and templates are established here before product documentation begins. Product and system documentation will populate the numbered `docs/` domains as the platform is designed.
