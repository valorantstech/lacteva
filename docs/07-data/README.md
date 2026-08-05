# 07 — Data and Database Documentation

Database designs (`DBD`) and data-governance documentation for every datastore on the platform. In Lacteva's service architecture, **each service owns its datastore**; a database shared between services requires an explicit ADR.

- Template: [TPL-0006](../02-templates/TPL-0006-database-design-template.md)
- Naming: `DBD-NNNN-<datastore-title>.md`; schema objects are `snake_case`, singular table names, per [STD-0002 §6](../00-standards/STD-0002-naming-conventions.md)
- Versioning: forward-only migrations; the DBD maps design versions to migration ranges per [STD-0004 §5](../00-standards/STD-0004-versioning-strategy.md)
- Approval: data platform owner + owning service team lead ([GOV-0002](../01-governance/GOV-0002-approval-workflow.md))

## Non-Negotiables for Every DBD

- **Multi-tenancy section is mandatory** — the isolation mechanism must be stated and must make cross-tenant access impossible by construction.
- **Data lifecycle section is mandatory** — retention, archival, deletion (including tenant offboarding and right-to-erasure) per the target markets' regulations.
- Every index is justified by the query it serves; every constraint names the business rule it enforces.
- The DBD documents *intent*; migrations are authoritative for structure. Divergence between them is a defect.

## Index

| ID | Datastore | Owning Service | Engine | Status |
| --- | --- | --- | --- | --- |
| [DBD-0001](DBD-0001-platform-core-database.md) | Platform Core Database | `platform-core` | PostgreSQL 16 | Approved |

DBD-0001 is also the **Database Architecture Reference**: complete table inventory, ERDs, module dependency graph, lifecycle classification, volumetrics, partitioning assessment, and the standing optimization findings (F-1 … F-13).
