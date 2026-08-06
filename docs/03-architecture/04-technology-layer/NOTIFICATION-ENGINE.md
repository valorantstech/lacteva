---
id: NOTIFICATION-ENGINE
title: Notification Engine
type: reference
status: Approved
version: "1.1"
owner: Engineering
created: 2026-08-05
last-updated: 2026-08-07
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

## Delivery, for real (MSG-001)

NOT-001 shipped adapters only — a logging provider and a placeholder — and said so plainly. The consequence was that the platform rendered every message, dispatched it, retried it and recorded it, and then handed it to something that threw it away. **A farmer was never told they had been paid.**

### The provider contract

`send()` returns a `DeliveryResult` rather than a bare string, because an operator asking "did it arrive?" needs more than a reference:

| Field | Why |
| --- | --- |
| `provider_message_id` | What a support conversation with the gateway quotes |
| `status` | `accepted` \| `sent` \| `delivered` \| `unknown` |
| `metadata` | Segment count, cost, the gateway's own status string — never credentials |

### Retryable versus permanent — the defect this work exposed

**Every failure used to be retried.** An invalid phone number consumed five gateway calls and five backoff windows to reach the answer it had on the first attempt. A missing template — a deployment fault, not a delivery fault — did the same, burying the real signal under a retry backlog.

Providers now state permanence, and the retry engine honours it:

| Kind | Examples | Engine |
| --- | --- | --- |
| **Transient** (`ProviderSendError`) | Timeout, network, 429, 5xx | Backoff and retry, to the existing budget |
| **Permanent** (`PermanentSendError`) | Invalid number, bad credential, rejected sender, malformed request, missing template | Straight to `dead`, first attempt |

The base class stays retryable, so every pre-MSG-001 raiser behaves as it did. **Permanence has to be claimed**: when a provider says something unfamiliar, the safe default is to try again, not to give up on a farmer's message.

A permanent failure still goes to `dead` rather than being silently dropped — visible in the history, counted, and retryable by an operator who has fixed the underlying data.

### The one double-send the platform cannot prevent alone

A message the gateway accepted and whose response we lost. Only the gateway knows it already has it, so it is told: every send carries an `Idempotency-Key` of `lacteva-{notification_id}`, **stable across every retry**. The platform's own idempotency (unique on `(event_id, template_key, channel)`) stops a duplicate *dispatch*; this stops a duplicate *delivery*.

### Vendor neutrality

`HttpSmsProvider` speaks a small documented JSON contract and classifies outcomes by **HTTP status**, which every gateway agrees on even when their payloads do not. Dairy markets differ by country and a deployment may change provider without changing code. A gateway whose shape does not fit implements `ChannelProvider` and is installed with `register_provider` — the seam NOT-001 already built, unchanged.

### Modes

| `LACTEVA_NOTIFICATION_SMS_PROVIDER` | Behaviour |
| --- | --- |
| `logging` | Delegates to the notifier port. Dev default |
| `placeholder` | Accepts, discards. "No gateway configured yet" |
| `dry_run` | Renders and logs a **real** message against production-shaped config without sending. Staging |
| `http` | The gateway |
| `disabled` | Refuses **permanently** — for a market that is not live |

`dry_run` and `placeholder` differ in intent, and the difference is operational: one means a gateway is configured and deliberately unused, the other that none exists. `disabled` raises rather than silently succeeding, because a notification marked sent that was never sent is a lie the platform would repeat to whoever asks why a supplier was not told.

### What is logged

Never an API key, never an Authorization header, never a full phone number. `mask_phone()` turns `+254700123456` into `+2547****3456` — enough to correlate with a support conversation, not enough to be a contact list. A log carrying every supplier's number is a copy of the directory with weaker access control than the database it came from.

Gateway error bodies are truncated to 200 characters before they reach an exception, because they echo the request often enough to carry the number and occasionally the credential.

### Cost visibility

`_segments()` reports the SMS segment count — 160 GSM-7 characters, 70 for anything outside that alphabet. Segments are what a gateway bills, so a template that quietly crosses a boundary doubles the cost of every message it sends. It is in the delivery metadata and in the dry-run log.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-07 | Architecture Board | MSG-001: real delivery. Provider contract returns a DeliveryResult; permanent failures stop being retried; gateway idempotency key; PII masking; vendor-neutral HTTP adapter. |
| 1.0 | 2026-08-05 | Engineering | Established by NOT-001. |
