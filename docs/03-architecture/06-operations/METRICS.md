---
id: METRICS
title: Metrics Reference
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-05
related: [OBSERVABILITY, ALERTING, DASHBOARDS]
baseline: ARCH-BASELINE-V1
---

# Metrics Reference

Every Prometheus metric the platform exposes. Established by OBS-001.

**This document is generated from `core/metrics.py`.** It describes what the
platform actually exports rather than what someone remembered to write down;
regenerate it whenever the registry changes.

## Conventions

- `<subsystem>_<thing>_<unit>`; counters end `_total`, durations end
  `_seconds`, gauges are plain nouns.
- Units are base units. A duration is **seconds**, never milliseconds.
- Labels are **bounded vocabularies, never identities**. See the cardinality
  rule below; a test enforces it.

## The cardinality rule

A time series exists per distinct label-value combination. These may never be
labels, because each would multiply the series count by a customer-driven
factor:


`actor`, `actor_id`, `email`, `error`, `id`, `message`, `path`, `payment_number`, `phone`, `receipt_number`, `reference`, `supplier`, `supplier_id`, `tenant`, `tenant_id`, `url`, `user`, `user_id`, `uuid`


Per-tenant breakdown is a *business data* question, answered by querying the
platform — not by exploding every counter by customer. At the platform's
target scale (1M dairies) a single tenant label would be an existential
metrics bill.

**Route labels are templated full paths** (`/v1/payments/{payment_id}`), so an
id can never leak into a label and two API versions cannot collide.

## Metrics


### HTTP

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `http_request_duration_seconds` | histogram | `method`, `route` | HTTP request latency |
| `http_requests` | counter | `method`, `route`, `status` | HTTP requests |
| `http_requests_in_flight` | gauge | — | Requests currently being served |

### Security

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `auth_failures` | counter | `reason` | Authentication failures |
| `authz_denials` | counter | `permission` | Authorization denials |
| `jwt_verification_failures` | counter | `reason` | Tokens rejected during verification |
| `rate_limited` | counter | `rule` | Requests refused by a rate limit |
| `rate_limiter_unavailable` | counter | — | Rate-limit checks that could not reach their backend |
| `rls_denials` | counter | — | Statements refused by row-level security |

### Relay (outbox)

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `relay_dead` | counter | — | Events moved to the dead letter queue |
| `relay_delivered` | counter | — | Events delivered by the relay |
| `relay_delivery_seconds` | histogram | — | Time from publish to successful delivery |
| `relay_pending_events` | gauge | — | Outbox events awaiting delivery |
| `relay_retries` | counter | — | Delivery attempts that failed and were retried |

### Consumers

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `consumer_dead` | counter | `consumer` | Events dead-lettered |
| `consumer_enabled` | gauge | `consumer` | 1 when a consumer is enabled, 0 when paused |
| `consumer_failed` | counter | `consumer` | Handler failures |
| `consumer_lag_events` | gauge | `consumer` | Events behind the log head |
| `consumer_latency_seconds` | histogram | `consumer` | Time from event creation to processing |
| `consumer_processed` | counter | `consumer` | Events successfully processed |
| `consumer_retried` | counter | `consumer` | Retries scheduled |

### Projections

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `projection_drift_rows` | gauge | `projection` | Rows that differ from a shadow replay |
| `projection_events_replayed` | counter | `projection` | Events replayed into projections |
| `projection_lag_events` | gauge | `projection` | Events the projection has not yet applied |
| `projection_outdated` | gauge | `projection` | 1 when the built version is behind the code version |
| `projection_rebuild_duration_seconds` | histogram | `projection` | Wall time of a projection rebuild |
| `projection_rebuilds` | counter | `projection` | Projection rebuilds started |
| `projection_rows` | gauge | `projection` | Rows held by a projection |

### Notifications

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `notification_provider_duration_seconds` | histogram | `channel`, `provider` | Time spent inside a channel provider |
| `notification_retries` | counter | `channel` | Delivery attempts after the first |
| `notifications_dead` | counter | `channel`, `template` | Notifications that exhausted retries |
| `notifications_failed` | counter | `channel`, `template` | Notification delivery failures |
| `notifications_sent` | counter | `channel`, `template` | Notifications delivered |

### Payments

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `payments_cancelled` | counter | `method` | Payments cancelled |
| `payments_completed` | counter | `method` | Payments completed |
| `payments_created` | counter | `method` | Payments created |
| `payments_failed` | counter | `method` | Payment attempts that failed |

### Receipts

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `receipt_render_duration_seconds` | histogram | `format` | Time to render a receipt artifact |
| `receipts_generated` | counter | — | Receipts generated |

### Offline sync

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `sync_batch_duration_seconds` | histogram | — | Time to apply one device batch |
| `sync_conflicts` | counter | `reason` | Replayed operations that conflicted |
| `sync_operations` | counter | `kind`, `status` | Device operations replayed |
| `sync_pending_operations` | gauge | — | Device operations recorded but not yet applied |

### Pricing

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `pricing_failures` | counter | `stage` | Resolutions or calculations that produced no price |
| `pricing_resolution_duration_seconds` | histogram | — | Rate-card resolution latency |

### Settlements

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `settlements_cancelled` | counter | — | Settlements cancelled |
| `settlements_created` | counter | — | Settlements created |
| `settlements_finalized` | counter | — | Settlements finalized |

### Platform health

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `alerts_firing` | gauge | `severity` | Alert rules currently firing |
| `component_health` | gauge | `component` | Component health as a number: 3 healthy, 2 warning, 1 degraded, 0 critical |

## Estimated cardinality

50 metric families. The largest contributors are `route`
(~120 templated paths x 6 methods x ~8 status codes) and `permission`
(~40 keys). Everything else is single digits. Total series stay in the low
thousands regardless of how many dairies use the platform — which is the
entire point of the rule above.

## Histogram buckets

- **API buckets** (5 ms → 10 s) for anything a person waits on.
- **Job buckets** (10 ms → 15 min) for background work; a rebuild can
  legitimately take minutes and bucketing it like an API call would lose all
  resolution.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Generated from the registry established by OBS-001. |
