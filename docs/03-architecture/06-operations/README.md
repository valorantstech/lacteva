# Layer 06 — Operations

How the platform is watched, alerted on, and repaired. Established by OBS-001 (Phase B).

Operations is documented as its own layer because it answers a different question from every other layer: not "what does the platform do" but **"how do I know it is doing it, and what do I do when it is not."** An operator at 5 a.m. needs a different document from an architect.

## Rules

- Every alert names the **action**, not just the condition. A rule without one is a notification, and notifications train people to ignore alerts.
- Every threshold is documented with the **judgement behind it**, so an operator can argue with the number rather than guess at it.
- Documents that describe generated artifacts (metrics, dashboards, Prometheus rules) are **generated from the source of truth**, so they cannot drift.
- Nothing here changes business behaviour. Observability that alters what the platform decides is a defect.

## Index

| Document | Purpose |
| --- | --- |
| [OBSERVABILITY.md](OBSERVABILITY.md) | The architecture: metrics, logs, traces, health, correlation |
| [METRICS.md](METRICS.md) | Every metric, its labels, and the cardinality rule (generated) |
| [ALERTING.md](ALERTING.md) | Alert rules, severities, thresholds and the judgement behind them |
| [TRACING.md](TRACING.md) | OpenTelemetry support, what is instrumented, what is not |
| [DASHBOARDS.md](DASHBOARDS.md) | The seven Grafana dashboards and who opens each |
| [RUNBOOK.md](RUNBOOK.md) | What to do when something is wrong |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Layer established by OBS-001. |
