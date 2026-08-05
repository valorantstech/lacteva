---
id: DASHBOARDS
title: Dashboards
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-05
related: [OBSERVABILITY, METRICS, ALERTING, RUNBOOK]
baseline: ARCH-BASELINE-V1
---

# Dashboards

The seven Grafana dashboards, what each answers, and who opens it. Established by OBS-001.

Definitions live in [`infra/observability/grafana/`](../../../infra/observability/grafana/) as importable JSON. They are **generated** rather than hand-maintained: seven hand-edited dashboards drift from the metrics they claim to show, and nobody notices until an incident.

## Setup

```bash
# Prometheus: scrape config + generated alert rules
infra/observability/prometheus/prometheus.yml
infra/observability/prometheus/alerts.yml

# Grafana: import each dashboard, pointing $datasource at Prometheus
infra/observability/grafana/*.json
```

Each dashboard uses a `$datasource` variable, so no rebuild is needed per environment.

## The seven

### `lacteva-api` — "is it slow, is it erroring?"

Request rate by route, 4xx/5xx rates, latency p50/p95/p99, the five slowest routes, in-flight requests, and rate limiting.

**Opened by:** anyone responding to "the portal is slow."
**Read the p95-by-route panel first** — an overall p95 hides one bad endpoint.

### `lacteva-consumers` — "is work flowing?"

Lag per consumer, processed vs failed rates, processing latency p95, dead letters, retries, enabled/paused state, outbox depth, relay latency.

**Opened by:** anyone responding to a lag or dead-letter alert.
**The panel that matters:** lag climbing while `consumer_processed_total` is flat means stuck, not busy. That distinction decides everything you do next.

### `lacteva-projections` — "are the read models trustworthy?"

Projection lag, **drift rows (must be zero)**, rebuild duration, rows held, outdated flags, replay throughput.

**Opened by:** anyone about to trust a report, and anyone after a rebuild.
Non-zero drift means the read model disagrees with the event log; the log wins.

### `lacteva-notifications` — "are farmers being told?"

Sent vs failed rates by channel, failure ratio, **provider latency p95**, dead notifications by template, retries.

**Opened by:** anyone responding to a notification alert.
Provider latency is the panel that tells you whether a backlog is the gateway's fault or ours.

### `lacteva-payments` — "is money moving, and is it provable?"

Payments created vs completed by method, failures and cancellations, receipts generated, receipt render p95, settlement lifecycle.

**Opened by:** finance-facing staff and anyone investigating a payment complaint.
A gap between created and completed is money that was intended but not moved.

### `lacteva-security` — "is anyone attacking us?"

Authentication failures by reason, JWT verification failures, top authorization denials, rate limiting and limiter availability, 401/403/5xx rates, RLS denials, signing-key health.

**Opened by:** whoever is on security duty; reviewed weekly regardless.
A denial spike concentrated on one permission is usually a broken client; spread across many is usually probing.

### `lacteva-business` — "what is the platform doing for the dairy?"

Platform health across all eight components, pricing resolution latency and failures by stage, offline sync operations and conflicts, sync batch duration, alerts firing.

**Opened by:** the daily standing view. Start here, drill down elsewhere.

## Design notes

**Panels answer questions, not "show metrics."** Every title is phrased as something an operator wants to know.

**Rates use 5-minute windows** for operational panels and 15 minutes to 1 hour for business ones — a payment rate over 5 minutes is noise at dairy volumes.

**Health is numeric so it can be graphed:** `component_health` is 3 (healthy) → 0 (critical). A status string cannot be alerted on or trended.

**No per-tenant panels.** The cardinality rule (METRICS.md) forbids tenant labels; per-tenant breakdown is a business-data question answered by querying the platform, not by exploding every series by customer.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Established by OBS-001. |
