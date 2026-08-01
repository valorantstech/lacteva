---
id: TPL-0008
title: Event Specification Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# TPL-0008 — Event Specification Template

> Template guidance: Copy everything below the rule into `docs/09-events/EVT-NNNN-<short-title>.md`. One document per **event type**. Events are contracts: producers own them, but consumers depend on them, so changes follow the approval matrix in GOV-0002 and the versioning rules in [STD-0004 §5](../00-standards/STD-0004-versioning-strategy.md). Event names: `<domain>.<past-tense-fact>.v<major>` per STD-0002.

---

```yaml
---
id: EVT-NNNN
title: <Event title>
type: evt
status: Draft
version: "0.1"
owner: <producing team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<SRS-ID of producer>, <DOM-ID>]
---
```

# EVT-NNNN — \<Event Title\>

## 1. Overview

- **Event name:** `<domain>.<fact>.v1` (e.g. `collection.milk-collected.v1`)
- **Meaning:** \<the business fact this event records — past tense, one sentence\>
- **Producer:** \<service; link SRS\>
- **Kind:** Domain event / Integration event / Notification

## 2. Semantics

- **Emitted when:** \<the exact condition, including edge cases that do NOT emit it\>
- **Emission guarantee:** \<at-least-once / exactly-once mechanism (e.g. outbox); can duplicates occur?\>
- **Ordering:** \<ordering guarantee and partition key, e.g. ordered per `tenant_id` + `farm_id`\>
- **Timing:** \<emitted before/after the state change commits; transactional relationship\>

## 3. Schema

> Template guidance: The machine-readable schema (JSON Schema / Avro) lives in the schema registry and `assets/EVT-NNNN-schema.json`; this table is authoritative for field semantics.

Envelope: follows the platform event envelope (id, type, source, time, tenant context, trace context) — \<link envelope ADR/spec\>.

Payload:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `tenant_id` | \<type\> | Yes | Owning tenant. |
| \<field\> | \<type\> | Yes/No | \<meaning, unit, valid values — glossary terms\> |

**Example**

```json
{
  "id": "<uuid>",
  "type": "<domain>.<fact>.v1",
  "time": "2026-08-02T10:15:00Z",
  "tenantId": "<uuid>",
  "data": {
    "<field>": "<value>"
  }
}
```

## 4. Consumers

> Template guidance: Keep current — this list drives the approval set for breaking changes.

| Consumer | Why It Consumes | Idempotent? | Contact Team |
| --- | --- | --- | --- |
| \<service\> | \<purpose\> | Yes/No | \<team\> |

## 5. Consumer Obligations

- Consumers MUST tolerate unknown additional fields (additive changes are non-breaking).
- Consumers MUST handle duplicates per §2's guarantee.
- \<event-specific obligations, e.g. maximum processing lag before data-quality impact\>

## 6. Versioning and Evolution

- **Compatibility promise:** additive-only within v1; breaking changes mint `<domain>.<fact>.v2` with parallel-run migration per STD-0004 §5.
- **Deprecation of prior versions:** \<process and notice period\>

## 7. Volume and Retention

- **Expected volume:** \<events/day at target scale; peak factors (e.g. morning milking)\>
- **Retention on the bus:** \<duration; replay support\>

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
