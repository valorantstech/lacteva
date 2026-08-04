---
id: NOTIFICATION-ENGINE
title: Notification Engine
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-05
last-updated: 2026-08-05
related: [BR-REGISTER, PROJECTION-LIFECYCLE, CLAUDE-CONTEXT]
baseline: ARCH-BASELINE-V1
---

# Notification Engine

How Lacteva composes, delivers, retries, and audits outbound messages. Established by NOT-001 as platform infrastructure — the engine is a **consumer of the event log**, not a service business modules call.

**The two guarantees:**

- **BR-0016** — a business module never sends a message. Notifications originate only from durable domain events.
- **BR-0017** — every message is rendered from a registered template and delivered at most once per (event, template, channel).

## 1. Why the engine is a consumer

The naive design gives each module a notifier and lets it send at the moment something happens. That design fails in four ways a dairy cannot tolerate:

| Failure | Consequence of the naive design | What the consumer design does |
| --- | --- | --- |
| Transaction rolls back after sending | The farmer is told about a delivery that does not exist | The event is discarded with the transaction; nothing was queued |
| The SMS provider is down | The milk collection request fails or hangs | Collection commits; delivery retries later against the log |
| The message was never sent | Nothing to replay from — the moment is gone | The event is durable; replay re-derives the message |
| Two modules send the same news | Duplicate messages, no single owner | One consumer owns dispatch; idempotent on (event, template, channel) |

The producer's only obligation is to emit its event with enough payload for a message to be composed later. It holds no notifier dependency and cannot acquire one without a review catching it.

## 2. Flow

```
business transaction
      └─ commits, writing its event to the outbox (Relay, SPRINT-008A)
             │
             ▼
   notification-recipient-directory   (a projection, replay order 5)
      └─ maintains phone/email/locale per subject, rebuildable from the log
             │
             ▼
   notification-dispatch              (a consumer, runs after projections)
      └─ event → EventMapping → template key + channel + variables
             │
             ▼
   NotificationService.dispatch()
      ├─ idempotency check on (event_id, template_key, channel)
      ├─ resolve recipient (directory, or the address the event carried)
      ├─ render template — missing variable is an error, never a half message
      └─ provider.send()  →  sent | failed (retry) | dead
```

Ordering matters: the recipient directory is an **input** to dispatch, so `registered_consumers()` returns projections first (by replay order) and plain consumers after. Without that, dispatch would run against a directory that had not yet seen the supplier's registration and would record "no recipient address on file".

## 3. Templates

A template is `(key, channel, language)` and declares its variables by the `{placeholder}` names appearing in its title and body. Rendering with a missing variable raises — a farmer never receives `Hello {name}`.

Language resolves to the requested locale, falling back to the platform default (`en`). A market pack can therefore ship one locale at a time: Swahili exists today for `supplier_registered` and `settlement_finalized`, and every other key still delivers in English rather than not at all.

Templates are platform data declared in code. Per-tenant overrides are deliberate technical debt (§7) — the registry shape, keyed by `(key, channel, language)`, is exactly what an override table would populate.

## 4. Providers

`ChannelProvider` is a Protocol with one method. Two adapters ship:

- **`LoggingProvider`** (default) — delegates to the existing notifier port, so notifications appear in structured logs and the port stays the single outbound seam.
- **`PlaceholderProvider`** — accepts and discards, for load tests and environments that must send nothing.

**No production provider exists.** There is no AWS SES, no Twilio, no vendor SDK, and no credential handling anywhere in this module. Adding one means writing an adapter and naming it in settings; nothing else in the platform changes.

## 5. Retry, failure, and the dead letter

Delivery failure is a property of the **notification**, not of the event. The event was consumed correctly — it was the send that failed. Raising from the consumer handler would roll back the very history this module exists to keep, so the handler does not raise; the notification row owns its own retry lifecycle instead, reusing the consumer framework's constants so operators learn one backoff model:

| State | Meaning | Next |
| --- | --- | --- |
| `sent` | The provider accepted it | terminal |
| `failed` | Attempt failed, budget remains | retried after `backoff_delay(attempt)` |
| `dead` | `MAX_CONSUMER_ATTEMPTS` (5) exhausted | manual retry only |
| `pending` | Created, not yet attempted | next sweep |

The background loop calls `retry_pending()` for due notifications; `POST /v1/notifications/{id}/retry` forces one immediately, bypassing the wait, and works on dead letters too.

## 6. API

| Endpoint | Permission | Purpose |
| --- | --- | --- |
| `GET /v1/notifications` | `notification.read` | History: search recipient/text, filter by status, channel, template, event |
| `GET /v1/notifications/stats` | `notification.read` | Totals by status and channel, retryable count |
| `GET /v1/notifications/{id}` | `notification.read` | One notification with its rendered text, payload, and error |
| `POST /v1/notifications/{id}/retry` | `notification.manage` | Retry now |
| `POST /v1/notifications/retry-pending` | `notification.manage` | Run the due sweep immediately |
| `GET /v1/notification-templates` | `notification.read` | The registry — every message the platform can send |
| `POST /v1/notification-templates/{key}/preview` | `notification.read` | Render with supplied values |

## 7. Known limits

- **Templates are code, not tenant data.** A tenant cannot yet reword a message or add a locale without a deploy.
- **No production channel.** Delivery is logged, not transmitted. A real SMS adapter is the next step toward field use.
- **No recipient preferences.** Everyone who has an address receives every notification their events produce; there is no opt-out, quiet-hours, or digest logic.
- **Directory covers suppliers only.** Users receive messages when the event itself carries an address (password reset, invitation). A user-directory projection would generalize this.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Engineering | Established by NOT-001. |
