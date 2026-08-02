---
id: TPL-0015
title: Platform Service Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# TPL-0015 — Platform Service (PSV) Template

> Template guidance: Copy below the rule into `docs/03-architecture/03-application-layer/PSV-NNNN-<service-name>.md`. A platform service is a **logical** service: a stable responsibility boundary inside one bounded context. No endpoints, no schemas, no technology — the SRS/API/DBD documents that later realize this service carry those and cite this document.

---

```yaml
---
id: PSV-NNNN
title: <Service name per STD-0002, e.g. "milk-collection-service">
type: psv
layer: application
context: <DOM-NNNN>
status: Draft
version: "0.1"
owner: <owning team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<DOM-ID>, <ADR-IDs>, <CON-IDs>]
---
```

# PSV-NNNN — \<Service Name\>

## 1. Mission

\<one paragraph: what this service is responsible for, and — as important — what it refuses to be responsible for\>

## 2. Capabilities Realized

| Capability ID | Extent |
| --- | --- |
| \<e.g. MCL.PCK.01\> | Fully / Partially — \<which part\> |

## 3. Responsibility Boundary

- **Owns (system of record for):** \<aggregates, by AGG-ID\>
- **Decides:** \<the business decisions made inside this service\>
- **Never does:** \<explicit exclusions that keep the boundary stable\>

## 4. Collaboration

| With | Direction | Nature (business terms) |
| --- | --- | --- |
| \<PSV-ID / external party\> | Consumes / Provides / Emits to / Listens to | \<what flows, e.g. "collection facts for settlement"\> |

> Template guidance: interfaces stay abstract here ("provides collection records to settlement"); the realizing API/EVT documents specify them.

## 5. Key Behaviors

\<3–7 sentences or bullets on the service's essential runtime behaviors in business language — what it does when its triggers occur, including its most important failure behaviors\>

## 6. Quality Attribute Priorities

> Template guidance: rank what this service optimizes for — drives the future SRS. E.g. a settlement service ranks correctness > availability; a field-capture service ranks offline tolerance > consistency freshness.

1. \<top priority + why\>
2. \<second\>
3. \<third\>

## 7. Realization Trace

| Realized By | Status |
| --- | --- |
| SRS | \<SRS-ID or "Not started"\> |
| APIs / Events / Data | \<API/EVT/DBD IDs or "Not started"\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
