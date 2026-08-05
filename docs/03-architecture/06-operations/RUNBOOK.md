---
id: RUNBOOK
title: Operations Runbook
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-05
related: [OBSERVABILITY, ALERTING, METRICS, DASHBOARDS, SECURITY-CHECKLIST]
baseline: ARCH-BASELINE-V1
---

# Operations Runbook

What to do when something is wrong. Established by OBS-001.

## 0. Start here

```
GET /v1/_ops/overview
```

One call: overall status, every component's status, and every firing alert with its action. If that is `healthy` with no alerts, the platform is fine and the problem is elsewhere (client, network, or expectation).

Then, if needed: `GET /v1/_ops/health` for per-component detail, and the [dashboards](DASHBOARDS.md) for trend.

## 1. The failure that looks like health

**Read this first, because it is the one that catches people out.**

This platform is event-driven. Collection commits, then an outbox event, then a consumer, then a notification and a receipt. **Every step after the commit can stop while the API keeps returning 200.** Milk gets recorded; nobody gets told, nothing gets paid, no report updates.

Symptoms: `background_worker_stopped`, `consumer_stopped`, `consumer_lag`, or `outbox_backlog` — with a perfectly healthy API dashboard.

First question, always: **is the work actually flowing?** `consumer_lag_events` trending up and `consumer_processed_total` flat is the signature.

## 2. Component playbooks

### `database` — critical

The platform cannot serve. There is no degraded mode.

1. Check the host, the connection pool, and disk.
2. Check for a failover in progress — a 60–90 second blip is expected and the alert's `for: 2m` should have absorbed it.
3. Nothing to do in the application; it recovers on its own once the database returns.

### `redis` — degraded

Rate limits are **failing open** by design (see SECURITY.md). Collection is unaffected.

1. Restore Redis.
2. While it is down there is no abuse protection: watch `auth_failures_total` and `http_requests_total{status="401"}`.
3. Do **not** fail closed in response to an outage unless you have decided that policy deliberately — it would stop milk collection to protect a rate limit.

### `background_workers` — degraded or critical

A loop has stopped. See §1.

1. `GET /v1/_ops/health` → `background_workers.data.workers` names which one.
2. The logs will have the exception that killed it (the task's traceback, at ERROR).
3. **Restart the process.** Work is durable: the relay resumes from `pending` rows, consumers resume from their cursor. Nothing is lost, only delayed.
4. If it dies repeatedly, pause the offending consumer (below) to get the rest of the platform moving, then fix the handler.

### `consumers` — warning or degraded

| Detail | Meaning | Action |
| --- | --- | --- |
| `paused: [...]` | Deliberately stopped | If unintended: `POST /v1/_consumers/{name}/resume` |
| `lagging: [...]` | Behind the log | Check whether it is failing or merely slow (below) |
| `dead_lettering: [...]` | Giving up on events | **Investigate — a business effect is not happening** |

**Lagging but not failing** — usually a burst. Watch `consumer_processed_total` rate: if it is high, it is catching up. If lag grows while processing is flat, the consumer is stuck.

**Dead-lettering:**

1. `GET /v1/_consumers/dead-letters` — read the error.
2. Fix the handler and deploy.
3. `POST /v1/_consumers/executions/{id}/replay`.
4. Dead events stay replayable **forever**; there is no rush and no data loss. Fix properly rather than quickly.

**To pause a consumer** (deploying a fix, or it is thrashing):

```
POST /v1/_consumers/{name}/pause     # cursor stays put
POST /v1/_consumers/{name}/resume    # works through the backlog
```

Pausing loses nothing. It writes the same config key the runner reads, so there is exactly one kill switch.

### `projections` — warning or degraded

Projections feed reporting and notification recipients. A wrong projection produces confidently wrong answers, which is worse than no answer.

| Detail | Action |
| --- | --- |
| `outdated` | The code version moved ahead. `POST /v1/_projections/{name}/rebuild` |
| `failed` | A rebuild failed. Read the error, fix, re-run |
| `behind` | Catching up; watch it |

After any rebuild: `POST /v1/_projections/{name}/verify?deep=true`. Deep verification shadow-replays the log and compares, in a transaction that is always rolled back. **A rebuild is always safe** — BR-0015 guarantees every projection is reconstructible from the log.

### `notifications` — warning or degraded

| Detail | Action |
| --- | --- |
| Dead notifications | A farmer was never told. `GET /v1/notifications?status=dead`, fix the cause, retry individually |
| High failure ratio | The provider is broken. Check `notification_provider_duration_seconds` and the provider's own status |

`POST /v1/notifications/retry-pending` runs the due sweep immediately. Failures retry on backoff automatically and dead-letter after five attempts.

### `jwt_keys` — warning or critical

| Status | Meaning | Action |
| --- | --- | --- |
| warning | Signing key expires within 14 days | Rotate now — JWT-ROTATION.md §2. Rotation is additive and invalidates nothing |
| critical | No usable key, or expired | **Outage.** Every login and refresh fails. JWT-ROTATION.md §5 |

Never wait for a maintenance window to rotate. That is the whole point of additive rotation.

### `outbox` — warning or degraded

Events are not leaving. Everything downstream is stalled behind it.

1. Is the relay worker alive? (`background_workers`)
2. Is the transport reachable?
3. `relay_pending_events` and `oldest_pending_minutes` show whether it is a backlog or a stall.
4. Events are durable — this is delay, never loss.

## 3. Investigating one farmer's problem

"Amina says she was never told about her payment."

1. Find the payment: `GET /v1/payments?q=<supplier or reference>`.
2. Find its receipt: `GET /v1/receipts?payment_id=<id>`.
3. Find the notification: `GET /v1/notifications?q=<phone>` — status tells you sent, failed, or dead, with the error.
4. If nothing exists at all, the chain broke earlier: check consumer lag and dead letters for the window.
5. To follow the whole chain in logs, filter on the **correlation id** from the originating request — it flows request → event → consumer → notification.

## 4. Escalation

| Condition | Response |
| --- | --- |
| Any `critical` alert | Page |
| `security.token.reuse_detected` | Page — see SECURITY-CHECKLIST.md incident response |
| Two or more `warning` alerts on the same component | Treat as degraded; investigate now |
| Dead letters growing over an hour | Page — business effects are being lost |

## 5. After the incident

- Was there an alert? If not, add a rule — an incident nobody was told about is a gap.
- Did the alert say what to do? If not, fix the `action`.
- Did the runbook cover it? If not, add a playbook section.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Established by OBS-001. |
