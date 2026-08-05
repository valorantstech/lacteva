---
id: OBSERVABILITY
title: Observability Architecture
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-05
related: [METRICS, ALERTING, TRACING, RUNBOOK, DASHBOARDS, SECURITY]
baseline: ARCH-BASELINE-V1
---

# Observability Architecture

How an operator sees what the platform is doing. Established by OBS-001 (Phase B).

**The acceptance test is about people, not code:** an operator can determine platform, consumer, projection, notification, payment, and security health *without reading application logs*. Everything below exists to make that true.

## 1. Why an event-driven platform needs this specifically

A synchronous system fails loudly: a request errors and someone sees a 500. This platform is not that. Collection commits, an event lands in the outbox, a consumer picks it up, a notification is dispatched, a receipt is generated. **Every one of those steps can stop while the API keeps answering perfectly.**

That is the failure shape this layer is built for. The most dangerous state is not "the platform is down" — it is "the platform looks fine and nothing downstream is happening." Hence:

- `background_workers` is a first-class health component, because a dead loop is invisible from the outside.
- Consumer **lag** is a headline metric, not a curiosity.
- Every alert names the *business* consequence, not the technical symptom.

## 2. The four pillars, and what each is for

| Pillar | Answers | Where |
| --- | --- | --- |
| **Metrics** | How much, how fast, how often — over time | `/metrics`, [METRICS.md](METRICS.md) |
| **Structured logs** | What happened in this specific case | stdout, JSON |
| **Traces** | Where the time went, and what caused what | OTel, [TRACING.md](TRACING.md) |
| **Health & alerts** | Is anything wrong, and what do I do | `/v1/_ops/*`, [ALERTING.md](ALERTING.md) |

They are deliberately not interchangeable. Metrics cannot tell you *which* farmer's receipt failed; logs cannot tell you the p95 latency; neither tells you whether to wake up.

## 3. Metrics: one registry, enforced cardinality

Every metric is defined in `core/metrics.py` — once. Scattering `Counter(...)` across modules is how a metrics surface becomes unreviewable: nobody can answer "what do we expose?" without grepping, and nobody notices when a label starts carrying a tenant id.

The cardinality rule is enforced by a test, not by discipline: labels are **bounded vocabularies, never identities**. A `tenant_id` label multiplies every series by the customer count, and at 1M dairies that is not a bill anyone wants. Per-tenant breakdown is a *business data* question, answered by querying the platform, not by exploding counters.

One consequence worth calling out: HTTP metrics label the **templated full path** (`/v1/payments/{payment_id}`). During OBS-001 this was found to be dropping the `/v1` prefix, which would have collided a future v2 API into the same series.

## 4. Structured logging

Every log line is JSON with a fixed field set: timestamp, level, request_id, correlation_id, tenant_id, and the operation's own facts. Free-form messages are event *names* (`consumer_processed`, `notification_failed`), so they can be filtered and counted rather than grepped.

**Never logged:** credentials, tokens, key material, or PII. Security events name the subject and the outcome; the payload carries identifiers an operator can act on, never material an attacker could use.

Stack traces belong at ERROR, never at INFO — an INFO stream full of tracebacks is a stream nobody reads.

## 5. Correlation: one request, one id, end to end

This is the property that makes an event-driven platform debuggable at all.

```
HTTP request           X-Request-ID (supplied or generated)
   └─ contextvars      request_id + correlation_id bound
       └─ outbox row   correlation_id persisted with the event
           └─ consumer rebinds correlation_id into its own log context
               └─ notification / receipt / projection inherit it
```

A notification that failed at 05:14 can be traced back to the collection that caused it, through a chain that crossed a process boundary and a queue. The consumer rebinding step was added by OBS-001 — before it, the chain broke exactly where it mattered most.

## 6. Health: four levels, worst wins

`healthy` → `warning` → `degraded` → `critical`, per component, with the overall status equal to the **worst** component. Averaging hides outages.

Eight components, each answering a question in the operator's terms: database, redis, outbox, consumers, projections, notifications, jwt_keys, background_workers. Details in [RUNBOOK.md](RUNBOOK.md).

Two design decisions:

- **A probe never raises.** An exception becomes `critical` for that component with the reason attached. A health endpoint that 500s tells an operator nothing except that health is broken.
- **Degraded is still ready.** `/health/ready` stays a single bit for load balancers and returns false only on `critical`. Pulling a degraded instance from rotation removes capacity that still works and does not fix the degradation.

## 7. Operator surface

| Endpoint | Purpose |
| --- | --- |
| `GET /health/live` | Process is up (load balancer) |
| `GET /health/ready` | Safe to route traffic (load balancer) |
| `GET /v1/_ops/overview` | **The first screen** — status, components, firing alerts, counts |
| `GET /v1/_ops/health` | Per-component detail with actionable data |
| `GET /v1/_ops/alerts` | What is firing, worst first, with the action to take |
| `GET /v1/_ops/alert-rules` | Every rule the platform can fire |
| `GET /metrics` | Prometheus scrape |
| `POST /v1/_consumers/{name}/pause` \| `/resume` | Stop and restart a consumer without losing its place |

Plus the pre-existing `/v1/_consumers`, `/v1/_projections`, `/v1/_relay`, and `/v1/notifications` operations.

All `_ops` endpoints require `platform.relay.manage` — platform staff, not tenant users.

## 8. Performance

Observability that costs latency gets turned off, so:

- Metric increments are in-process, lock-free, and sub-microsecond. No I/O.
- The access log is one line per request, already on the hot path before OBS-001.
- Health probes are bounded queries and in-memory reads — no table scans — and run only when polled, never per request.
- Tracing is a **no-op** unless an exporter is configured, costing one context-manager enter and exit.
- **No business endpoint gained a query.** The statement-counting tests still pass unchanged.

## 9. Known limits

- **`sync_pending_operations` and `projection_drift_rows` are only set when something computes them** (a sync push, a verify run). They are not continuously sampled.
- **Health probes run per request to `/v1/_ops/health`.** A very aggressive poller would create load; there is no caching layer yet.
- **No log aggregation ships with the platform.** Logs go to stdout as JSON; shipping them is a deployment concern.
- **Tracing requires installing the OTel SDK**, which is deliberately not a platform dependency.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Established by OBS-001. |
