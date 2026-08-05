---
id: TRACING
title: Distributed Tracing
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-05
related: [OBSERVABILITY, METRICS]
baseline: ARCH-BASELINE-V1
---

# Distributed Tracing

How a single farmer's collection is followed across processes and queues. Established by OBS-001.

## 1. What tracing adds that metrics and logs do not

Metrics say *how much*. Logs say *what happened in this case*. Neither answers the question that matters in an event-driven platform: **where did the time go, and what caused what?**

One collection becomes a pricing resolution, an outbox row, a consumer run, a notification dispatch, and a receipt generation — across two processes and a queue, seconds or minutes apart. No log line explains that chain. A trace does.

## 2. Supported, not required

OpenTelemetry is a **large dependency tree and a deployment concern**. A village-scale install with one collection centre should not carry a tracing pipeline it will never export to.

So `core/tracing.py` is a thin seam with two modes:

| Condition | Behaviour |
| --- | --- |
| OTel SDK installed **and** `LACTEVA_OTEL_EXPORTER_ENDPOINT` set | Real spans, exported OTLP/HTTP |
| Anything else | Every span is a no-op: one context-manager enter and exit |

Instrumentation is written once and does not know which mode it is in.

**Configured-but-not-installed logs a warning rather than failing silently.** Believing you have tracing when you do not is worse than knowing you do not.

## 3. Enabling it

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
export LACTEVA_OTEL_EXPORTER_ENDPOINT=http://collector:4318/v1/traces
```

Startup logs `tracing=true` when it took effect. That field exists precisely so an operator can confirm rather than assume.

## 4. What is instrumented

| Span | Attributes | Why it earns its place |
| --- | --- | --- |
| `consumer.<name>` | event name, event id, correlation id | The process boundary — where a chain is otherwise lost |
| HTTP request | method, route, status | Entry point; correlates the trace with the access log |

The consumer span is the important one: it is where an in-process trace would otherwise end and a new, unconnected one would begin.

Repository, outbox, notification, payment, receipt, and projection spans are **not yet instrumented**. The seam exists and adding them is a one-line `with span(...)`; they were left out rather than added speculatively, because a trace full of uninformative spans is harder to read than a sparse one. Recorded as debt.

## 5. Correlation works without OTel

This matters: the platform's own correlation id flows request → outbox → consumer → notification **whether or not tracing is enabled**, because it rides in the event envelope and the log context, not in a tracing library.

Tracing enriches that story with timing and causality. It does not create it, and turning tracing off does not blind the platform.

## 6. Attribute discipline

Span attributes are stored per span, so an id is fine here even though it is forbidden as a metric label — the cardinality concern does not apply.

**PII and secrets are still forbidden.** A trace is exported to a third-party backend; a farmer's phone number does not belong in one.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Established by OBS-001. |
