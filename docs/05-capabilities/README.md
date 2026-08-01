# 05 — Business Capabilities

The business capability map describes **what Lacteva does** — stable business abilities like "Milk Quality Assessment" or "Producer Settlement" — independent of organization structure and technology. Capabilities change over years; the systems realizing them change over quarters. The map is the shared vocabulary between business strategy and platform architecture.

- Template: [TPL-0009](../02-templates/TPL-0009-business-capability-template.md)
- Naming: `CAP-NNNN-<capability-name>.md` per [STD-0002](../00-standards/STD-0002-naming-conventions.md)
- Approval: Architecture Board member + domain owner ([GOV-0002](../01-governance/GOV-0002-approval-workflow.md))

## How the Map Is Organized

The model has three levels, defined in the master map ([CAP-0001](CAP-0001-business-capability-master-map.md)):

- **Level 1 — Domains (10):** partitions of the entire dairy ecosystem, one `CAP` document each.
- **Level 2 — Subdomains (~40):** coherent ability groupings inside a domain, registered in the domain document.
- **Level 3 — Capabilities (86):** discrete business abilities with hierarchical IDs `<DOMAIN>.<SUBDOMAIN>.<NN>` (e.g. `FPR.HLT.02`), cataloged inside their domain document with purpose, actors, value, dependencies, business events, AI opportunities, reports, and KPIs.

*Usage amendment to [TPL-0009](../02-templates/TPL-0009-business-capability-template.md):* at industry-model scale, capabilities live in domain catalogs; TPL-0009 is reserved for single-capability deep-dives, which must reference their catalog ID.

## Relationship to Other Documents

- Capabilities reference the **domain models** ([`DOM`](../03-architecture/domain-models/README.md)) whose concepts they center on.
- BRDs and PRDs SHOULD state which capabilities they strengthen — this is how investment maps to the business.

## Index

| ID | Title | Scope | Status | Version |
| --- | --- | --- | --- | --- |
| [CAP-0001](CAP-0001-business-capability-master-map.md) | Business Capability Master Map — Dairy Ecosystem | All domains, inventory, dependency model, future-document index | Draft | 0.1 |
| [CAP-0002](CAP-0002-farm-production.md) | Farm Production (FPR) | 5 subdomains, 17 capabilities | Draft | 0.1 |
| [CAP-0003](CAP-0003-milk-collection-logistics.md) | Milk Collection & Logistics (MCL) | 4 subdomains, 9 capabilities | Draft | 0.1 |
| [CAP-0004](CAP-0004-quality-food-safety.md) | Quality & Food Safety (QFS) | 4 subdomains, 9 capabilities | Draft | 0.1 |
| [CAP-0005](CAP-0005-processing-manufacturing.md) | Processing & Manufacturing (PRO) | 4 subdomains, 7 capabilities | Draft | 0.1 |
| [CAP-0006](CAP-0006-commerce-market-access.md) | Commerce & Market Access (CMA) | 5 subdomains, 8 capabilities | Draft | 0.1 |
| [CAP-0007](CAP-0007-producer-economics-financial-services.md) | Producer Economics & Financial Services (PEF) | 5 subdomains, 8 capabilities | Draft | 0.1 |
| [CAP-0008](CAP-0008-cooperative-producer-relations.md) | Cooperative & Producer Relations (CPR) | 4 subdomains, 8 capabilities | Draft | 0.1 |
| [CAP-0009](CAP-0009-sustainability-welfare-compliance.md) | Sustainability, Welfare & Compliance (SWC) | 4 subdomains, 7 capabilities | Draft | 0.1 |
| [CAP-0010](CAP-0010-dairy-intelligence-advisory.md) | Dairy Intelligence & Advisory (DIA) | 4 subdomains, 8 capabilities | Draft | 0.1 |
| [CAP-0011](CAP-0011-ecosystem-tenant-enablement.md) | Ecosystem & Tenant Enablement (ETE) | 4 subdomains, 5 capabilities | Draft | 0.1 |
