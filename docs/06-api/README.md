# 06 — API Specifications

Human-readable contracts for every public, partner, and internal API on the platform. Each `API` document pairs with a machine-readable OpenAPI file in its `assets/` folder; the OpenAPI file is authoritative for schemas, the document for semantics — the PR that changes one changes both.

- Template: [TPL-0005](../02-templates/TPL-0005-api-specification-template.md)
- Naming: `API-NNNN-<api-name>.md` per [STD-0002](../00-standards/STD-0002-naming-conventions.md); REST paths are plural-noun kebab-case (`/v1/milk-collections`)
- Versioning: URI major versions, additive-only within a version, per [STD-0004 §5–6](../00-standards/STD-0004-versioning-strategy.md)
- Approval: API platform owner + every consuming team listed in the spec ([GOV-0002](../01-governance/GOV-0002-approval-workflow.md))

## Rules

- **No undocumented APIs.** An endpoint that serves traffic without an approved `API` document is an incident, not a shortcut.
- Platform-wide conventions (auth, tenancy propagation, pagination, error envelope, rate limiting) will be fixed in a conventions ADR; individual specs record only deviations.
- Breaking-change review starts from the spec's **Consumers** table — keeping it current is the producing team's obligation.

## Index

| ID | API | Audience | Major Version | Status |
| --- | --- | --- | --- | --- |
| [API-0001](API-0001-platform-core.md) | Platform Core REST API | Internal, and public-ready | v1 | Approved |

API-0001 records the platform-wide conventions this README anticipated — auth, tenancy propagation, pagination, the error envelope, rate limiting, retry safety — so individual future specs record only their deviations.
