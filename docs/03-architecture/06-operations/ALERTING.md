---
id: ALERTING
title: Alerting
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-05
related: [OBSERVABILITY, METRICS, RUNBOOK]
baseline: ARCH-BASELINE-V1
---

# Alerting

Which conditions wake a human, and what that human should do. Established by OBS-001.

**An alert is a promise that someone will act.** Every rule here therefore carries an `action` — the field most alerting systems omit and the reason most alerting systems get ignored. A rule with no action is a notification, and notifications train operators to dismiss alerts, including the one that mattered.

A test enforces this: every rule must have an action of substance, because an action has to be usable at 3 a.m. by someone who did not write the code.

## Severity means response time, not importance

| Severity | Response | `for:` | Example |
| --- | --- | --- | --- |
| `critical` | Page now | 2 min | Database unreachable; no usable signing key |
| `warning` | Look within a day | 10 min | Consumer lag climbing; key expiring |
| `info` | Review at leisure | 30 min | A consumer is deliberately paused |

The `for:` durations exist so a transient blip does not page anyone. A database that is unreachable for 90 seconds during a failover is not an incident; one unreachable for 3 minutes is.

## One definition, two consumers

Rules are declared once in `core/alerts.py` and drive **both** the operator API (`GET /v1/_ops/alerts`) and the exported Prometheus rules (`infra/observability/prometheus/alerts.yml`, generated from the same definitions). A single source means the dashboard and the pager cannot hold two different opinions about what "lagging" means.

## The rules

| Alert | Severity | Fires when | Business consequence |
| --- | --- | --- | --- |
| `database_unavailable` | critical | Database probe fails | The platform is down; no degraded mode exists |
| `background_worker_stopped` | critical | Relay or consumer loop is not running | **The API looks healthy while nothing downstream happens** |
| `dead_letter_growth` | critical | Any consumer dead-lettering | Some business effect — a notification, a receipt — is not happening |
| `projection_rebuild_failed` | critical | A rebuild failed | Reports and recipients read a partial model: confidently wrong answers |
| `projection_drift` | critical | A projection disagrees with a replay | The read model has diverged from the source of truth |
| `jwt_keys_unusable` | critical | No usable signing key | Every login and refresh fails |
| `redis_unavailable` | warning | Redis unreachable | Collection unaffected; rate limits fail open, so no abuse protection |
| `consumer_stopped` | warning | A consumer is paused | If deliberate, none. If not, work is queueing |
| `consumer_lag` | warning | Lag above threshold | Downstream effects are delayed |
| `outbox_backlog` | warning | Events not leaving the outbox | Everything downstream stalls behind it |
| `notification_failure_spike` | warning | Deliveries failing | Farmers are not being told about their money |
| `jwt_key_expiring` | warning | Signing key within 14 days of expiry | Rotate before it becomes an outage |

## Thresholds, and the judgement in them

These live in `core/health_probes.py` so they are enforced in one place. They encode judgement, not arithmetic, and an operator is invited to argue with them:

| Threshold | Value | Why this number |
| --- | --- | --- |
| Consumer lag → warning | 500 events | A morning collection peak can legitimately produce this |
| Consumer lag → degraded | 5,000 events | Milk is being recorded that nothing downstream has seen |
| Outbox pending → warning | 1,000 | Normal under burst |
| Outbox pending → degraded | 10,000 | The relay is not keeping up, not merely busy |
| Oldest pending event | 15 min | Longer than any legitimate retry backoff |
| Notification failure ratio | 25% | Below this is a flaky recipient; above it is a broken provider |
| Dead notifications | 1 | A farmer was never told. One is worth knowing about |
| Key expiry warning | 14 days | Two weeks is comfortably more than one rotation cycle |

## What is deliberately *not* alerted

- **Individual request errors.** A 4xx is a client's problem; a single 5xx is a bug report, not a page. Only sustained 5xx rates matter, and those surface on the API dashboard.
- **Business anomalies** (a farmer delivering unusually little milk). That is a product question with a product answer, not an operations alert.
- **Rate-limit hits.** Being rate limited is the system *working*. Sustained limiter *unavailability* is the alertable condition.

## Disk and memory

Not implemented in the platform, deliberately: container-level resource pressure is the orchestrator's job and it already has better signals (cgroup limits, OOM kills, node conditions) than an application can synthesise. Wire `kube-state-metrics` or the node exporter and alert there. Recorded as debt in the OBS-001 report so it is a decision rather than an omission.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Established by OBS-001. |
