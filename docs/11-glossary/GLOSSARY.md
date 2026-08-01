---
id: GLOSSARY
title: Lacteva Company-Wide Glossary
type: reference
status: Approved
version: "1.2"
owner: Docs Guild
created: 2026-08-02
last-updated: 2026-08-02
---

# Lacteva Company-Wide Glossary

Terminology source of truth for all Lacteva documentation. Entry format and rules: [TPL-0011](../02-templates/TPL-0011-glossary-template.md). Seeded with core terms; the glossary grows with the documentation — add missing terms in the same PR that first uses them.

## Dairy Domain Terms

### Adulteration

**Definition:** Deliberate addition of foreign substances to milk (water, neutralizers, extraneous fats or solids) to increase volume or mask spoilage; a food-safety violation and settlement fraud.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Not *contamination* (unintentional presence of a harmful substance).
**Source:** Food-law standard usage.

### Bulk Tank

**Definition:** Refrigerated on-farm storage vessel where milk from one or more milkings is held before collection.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Bulk milk tank. Not a *silo* (processor-side storage).
**Source:** Industry standard usage.

### Cold Chain

**Definition:** The unbroken sequence of temperature-controlled storage and transport that keeps milk and dairy products within safe temperature bounds from farm to consumer.
**Context:** Company-wide
**Synonyms / Do not confuse with:** —
**Source:** Industry standard usage.

### Chilling Center

**Definition:** An intermediate facility where milk deliveries — typically from smallholders — are aggregated, cooled, and stored pending bulk transport to processing.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Milk collection center, bulk milk cooling unit. Not on-farm storage (a *bulk tank*).
**Source:** Industry standard usage.

### Extension Services

**Definition:** Organized delivery of agricultural knowledge and advisory to producers — training, campaigns, and field visits — by cooperatives, buyers, or public agencies.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Farm advisory. Not platform-generated advisory (see capability DIA.ADV.01), which extension may deliver.
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

### Patronage

**Definition:** The cooperative principle and practice of allocating surplus (profit) to members in proportion to their use of the cooperative — for dairy, typically in proportion to milk delivered.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Patronage dividend/refund. Not a *share dividend* (return on capital, not on use).
**Source:** Cooperative-sector standard usage.

### Somatic Cell Count (SCC)

**Definition:** Concentration of somatic cells in milk (cells/mL), used as a key indicator of udder health and milk quality.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Not *bacterial count* (a separate hygiene indicator).
**Source:** Industry standard measure.

### Traceability

**Definition:** The ability to follow a milk quantity or product batch backward to its contributing sources and forward to its destinations, one step at a time, across the whole chain.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Not *provenance* alone (origin story) — traceability is bidirectional and operational.
**Source:** Food-law standard usage (one-step-back / one-step-forward principle).

### Withdrawal Period

**Definition:** The legally mandated time after an animal's treatment with a veterinary medicine during which its milk (or meat) must not enter the food chain.
**Context:** Company-wide
**Synonyms / Do not confuse with:** Withholding period. Not *market withdrawal* of product (see recall terminology).
**Source:** Veterinary regulation, standard across markets.

## Platform and Architecture Terms

### Business Capability

**Definition:** A discrete business ability — what the business does, independent of organization and technology — cataloged in the capability model with a hierarchical ID (e.g. `FPR.HLT.02`).
**Context:** Company-wide
**Synonyms / Do not confuse with:** Not a *feature* (product behavior) or a *service* (implementation unit).
**Source:** [CAP-0001](../05-capabilities/CAP-0001-business-capability-master-map.md).

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
| B2B | Business-to-Business |
| BRD | Business Requirements Document |
| CAP | Business Capability (document prefix) |
| DBD | Database Design (document prefix) |
| DDD | Domain-Driven Design |
| DOM | Domain Model (document prefix) |
| EVT | Event Specification (document prefix) |
| FSSAI | Food Safety and Standards Authority of India |
| IaC | Infrastructure as Code |
| KPI | Key Performance Indicator |
| MoSCoW | Must / Should / Could / Won't (prioritization scheme) |
| OTIF | On Time In Full (delivery performance measure) |
| PRD | Product Requirements Document |
| QR | Quality Review report (document prefix) |
| RLS | Row-Level Security |
| RPO | Recovery Point Objective |
| RPS | Requests Per Second |
| RTO | Recovery Time Objective |
| SCC | Somatic Cell Count |
| SLA | Service Level Agreement |
| SLI / SLO | Service Level Indicator / Objective |
| SNF | Solids-Not-Fat (milk solids excluding fat) |
| SRS | Software Requirements Specification |
| UHT | Ultra-High Temperature (milk treatment) |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.2 | 2026-08-02 | Documentation Engineering | QR-0001 remediation: added Adulteration, Cold Chain, Traceability; added 11 abbreviations found in use but undefined (B2B, FSSAI, IaC, KPI, MoSCoW, OTIF, QR, RPS, SLA, SNF, UHT). |
| 1.1 | 2026-08-02 | Enterprise Architecture | Added capability-model terms: Chilling Center, Extension Services, Patronage, Withdrawal Period, Business Capability. |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial seeded glossary. |
