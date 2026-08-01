---
id: GLOSSARY
title: Lacteva Company-Wide Glossary
type: reference
status: Approved
version: "1.0"
owner: Docs Guild
created: 2026-08-02
last-updated: 2026-08-02
---

# Lacteva Company-Wide Glossary

Terminology source of truth for all Lacteva documentation. Entry format and rules: [TPL-0011](../02-templates/TPL-0011-glossary-template.md). Seeded with core terms; the glossary grows with the documentation — add missing terms in the same PR that first uses them.

## Dairy Domain Terms

### Bulk Tank

**Definition:** Refrigerated on-farm storage vessel where milk from one or more milkings is held before collection.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Bulk milk tank. Not a *silo* (processor-side storage).
**Source:** Industry standard usage.

### Herd

**Definition:** The set of animals managed as one production group by a dairy business, typically at a single farm location.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Not synonymous with *farm* — one farm may run multiple herds.
**Source:** Industry standard usage.

### Lactation

**Definition:** The milk-producing period of an animal following calving, conventionally numbered (first lactation, second lactation, …) and measured in days in milk.
**Context:** Company-wide
**Synonyms / Do not confuse with:** —
**Source:** Industry standard usage.

### Milk Collection

**Definition:** The recorded act of transferring milk from a producer's storage to a collector, with measured quantity and, where available, quality attributes.
**Context:** Company-wide (context-specific refinements belong to the owning bounded context's domain model)
**Synonyms / Do not confuse with:** Pickup. Not a *delivery* (processor-side receipt).
**Source:** Internal definition.

### Milk Quality Grade

**Definition:** A classification assigned to a milk quantity based on measured attributes (e.g. fat, protein, somatic cell count, bacterial count) against a grading scheme; grading schemes vary by country and buyer.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Not a single global scale — a grade is always relative to a named scheme.
**Source:** Internal definition.

### Producer

**Definition:** A dairy business that produces milk — from a smallholder with a few animals to an industrial farm. The primary tenant persona of the platform.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Farmer (informal). Not a *processor* (buys and transforms milk) or *collector* (transports it).
**Source:** Internal definition.

### Somatic Cell Count (SCC)

**Definition:** Concentration of somatic cells in milk (cells/mL), used as a key indicator of udder health and milk quality.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Not *bacterial count* (a separate hygiene indicator).
**Source:** Industry standard measure.

## Platform and Architecture Terms

### Bounded Context

**Definition:** A defined boundary within which a domain model and its ubiquitous language apply consistently; the unit of domain-model documentation (`DOM`).
**Context:** Company-wide
**Synonyms / Do not confuse with:** Not necessarily one service — a context may be realized by several services.
**Source:** Domain-Driven Design (Evans).

### Domain Event

**Definition:** An immutable record of a business fact that occurred, named in past tense and published on the event backbone under an `EVT` specification.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Not a *command* (a request to do something).
**Source:** Internal definition; DDD usage.

### Tenant

**Definition:** A customer organization with a contractual relationship to Lacteva, whose data and configuration are isolated from all other tenants on the shared platform.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Not a *user* — a tenant has many users.
**Source:** Internal definition.

### Tenant Isolation

**Definition:** The set of mechanisms guaranteeing one tenant's data and workload cannot be read, modified, or inferred by another tenant.
**Context:** Company-wide
**Synonyms / Do not confuse with:** —
**Source:** Internal definition; mechanism per the platform tenancy ADR (to be authored).

## AI and Data Terms

### Model Card

**Definition:** The mandatory documentation for a production AI capability (`AIM` document): intended use, data, segmented evaluation, limitations, and operations.
**Context:** Company-wide
**Synonyms / Do not confuse with:** —
**Source:** Adapted from Mitchell et al., "Model Cards for Model Reporting" (2019).

### Model Drift

**Definition:** Degradation of a model's real-world performance over time as production data diverges from the data it was trained or evaluated on.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Covers both *data drift* (input distribution shift) and *concept drift* (relationship shift); specify which when precision matters.
**Source:** Industry standard usage.

### System of Record

**Definition:** The single service/datastore that owns the authoritative copy of a data entity; all other copies are derived and may be stale.
**Context:** Company-wide
**Synonyms / Do not confuse with:** —
**Source:** Internal definition.

## Business and Commercial Terms

### Cooperative

**Definition:** A producer-owned organization that aggregates its members' milk for collection, quality assessment, and sale; a key multi-producer tenant type.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Co-op. Not a *processor*, though some cooperatives also process.
**Source:** Industry standard usage.

### Processor

**Definition:** A business that purchases raw milk and transforms it into dairy products.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Dairy (ambiguous — avoid as a business-type term).
**Source:** Industry standard usage.

### Settlement

**Definition:** The calculation and execution of payment from a milk buyer to producers for collected milk over a period, typically adjusted for measured quality.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Milk payment. Not *pricing* (the scheme used to compute it).
**Source:** Industry standard usage.

## Abbreviations

| Abbreviation | Expansion |
| --- | --- |
| ADR | Architecture Decision Record |
| AIM | AI Model documentation (document prefix) |
| BRD | Business Requirements Document |
| CAP | Business Capability (document prefix) |
| DBD | Database Design (document prefix) |
| DDD | Domain-Driven Design |
| DOM | Domain Model (document prefix) |
| EVT | Event Specification (document prefix) |
| PRD | Product Requirements Document |
| RLS | Row-Level Security |
| RPO | Recovery Point Objective |
| RTO | Recovery Time Objective |
| SCC | Somatic Cell Count |
| SLI / SLO | Service Level Indicator / Objective |
| SRS | Software Requirements Specification |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial seeded glossary. |
