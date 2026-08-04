# Layer 04 — Technology Layer

Where technology finally appears: runtime, infrastructure, and deployment architecture. This layer is deliberately the **thinnest** documentation layer, because its two sources of truth live elsewhere:

- **Decisions** are ADRs in [`../adr/`](../adr/README.md) — cloud/runtime baseline, tenancy realization, event backbone, observability stack, and every other technology selection.
- **Actual state** is code in [`infra/`](../../../infra/README.md) once it exists — IaC is self-documenting for the *what*; this layer documents the *shape and why*.

What belongs here: deployment topology views (C4 deployment diagrams per [STD-0006](../../00-standards/STD-0006-plantuml-standards.md)), environment architecture descriptions, and technology-standard summaries that aggregate ADR decisions into a readable current-state picture.

## Rules

- Nothing in this layer may *introduce* a technology choice — every choice cites its ADR. A view that shows an undecided technology is review-blocking.
- Views carry no separate prefix: they are named diagram/description files indexed below, versioned like all repository content. If technology-layer documents later need formal IDs, a prefix will be registered in [STD-0003](../../00-standards/STD-0003-document-numbering.md) first.
- Upper layers (business, domain, application) MUST remain readable without this layer — if removing a technology view breaks the understanding of a domain artifact, the domain artifact is contaminated.
- Approval: Architecture Board (this layer is platform-wide by nature).

## Index

| File | Shows | Backing ADRs | Status |
| --- | --- | --- | --- |
| [PROJECTION-LIFECYCLE.md](PROJECTION-LIFECYCLE.md) | How derived read models are built, rebuilt, verified, and versioned from the event log ([BR-0015](../01-business-layer/BUSINESS-RULES.md)) | — (realizes the event-backbone baseline) | Approved |
| [NOTIFICATION-ENGINE.md](NOTIFICATION-ENGINE.md) | How outbound messages are composed, delivered, retried, and audited as a consumer of the event log ([BR-0016](../01-business-layer/BUSINESS-RULES.md), BR-0017) | — (realizes the event-backbone baseline) | Approved |
| [RECEIPT-RENDERING.md](RECEIPT-RENDERING.md) | How immutable receipts are rendered on demand into JSON/HTML/PDF artifacts through a swappable renderer registry ([BR-0020](../01-business-layer/BUSINESS-RULES.md)) | — (realizes the event-backbone baseline) | Approved |

*Deployment topology views still follow the founding platform ADRs (roadmap Phase 1.2, [QR-0004](../../12-quality/QR-0004-documentation-roadmap.md)).*
