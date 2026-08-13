---
id: NOTIFICATION-ENGINE
title: Notification Engine
type: reference
status: Approved
version: "1.2"
owner: Engineering
created: 2026-08-05
last-updated: 2026-08-13
related: [BR-REGISTER, PROJECTION-LIFECYCLE, MOBILE-EXPERIENCES, CLAUDE-CONTEXT]
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
| 1.2 | 2026-08-13 | Engineering | DEMO-012: `push` as a channel on this engine — device registry, token lifecycle, customer-scoped resolution, vendor-neutral adapter, disabled by default. |
| 1.1 | 2026-08-07 | Architecture Board | MSG-001: real delivery. Provider contract returns a DeliveryResult; permanent failures stop being retried; gateway idempotency key; PII masking; vendor-neutral HTTP adapter. |
| 1.0 | 2026-08-05 | Engineering | Established by NOT-001. |

## Email transport (PROD-001)

Email had no transport at all: `notification_email_provider` accepted only
`logging` and `placeholder`, both of which return `ACCEPTED`. A production
deployment rendered every message, recorded every delivery as accepted, kept
every dashboard green, and told no supplier anything.

`SmtpEmailProvider` is the production adapter.

**Why SMTP rather than a vendor SDK.** Every transactional email service —
SES, SendGrid, Postmark, Mailgun, and a cooperative's own relay — speaks SMTP.
One adapter reaches all of them with no vendor dependency, and a market whose
regulator requires mail to stay on national infrastructure uses the same code
path. A vendor API adapter implements the same `ChannelProvider` protocol.

**Why a worker thread.** `smtplib` is stdlib and blocking. `asyncio.to_thread`
keeps the consumer loop unblocked without adding a dependency to the delivery
path for a protocol that has not changed in twenty years.

**Failure classification is the load-bearing part.** MSG-001's finding was that
retrying an unretryable failure costs a real connection and a backoff window
each time and cannot succeed. SMTP states this exactly:

| Outcome | Classification |
| --- | --- |
| `SMTPRecipientsRefused`, `SMTPSenderRefused` | **Permanent** — the address is wrong |
| `SMTPAuthenticationError`, `SMTPNotSupportedError` | **Permanent** — credential/capability; every message fails identically |
| 5xx `SMTPResponseException` | **Permanent** |
| 4xx `SMTPResponseException` | Transient |
| Connect/disconnect/timeout/`OSError` | Transient |
| Anything unfamiliar | Transient — a supplier's message must not be dropped on an unknown failure |

**Idempotency.** SMTP has no idempotency key. The `Message-ID` is derived from
the notification id and is **stable across retries**, so a receiving MTA that
deduplicates on it recognises a resend of a message the gateway already
accepted but whose response was lost. (Built by hand: `email.utils.make_msgid`
mixes in a timestamp and random bytes, which produced a new id per attempt and
defeated the purpose — caught by a test.)

**PII.** `mask_phone()` handles addresses as well as numbers
(`grace@example.com` → `g****@example.com`) and is applied at every log site.
Provider error detail is truncated to 200 characters, because gateways echo the
request often enough that a raw copy can carry the credential just rejected.

**Configuration.** `LACTEVA_SMTP_HOST`, `_PORT`, `_USERNAME`, `_PASSWORD`,
`_SECURITY` (`starttls` | `ssl` | `none`), `_TIMEOUT_SECONDS`,
`_FROM_ADDRESS`, `_FROM_NAME`. Credentials reach the process through Docker
Secrets (`secrets_dir`) or the environment; none is in source. Production
refuses `smtp` with no host, and refuses `logging`/`placeholder` on either
channel outright.

## Push to a field user's handset (DEMO-012)

The mobile application needed to reach a rider or a household when the app is
closed. It did not need a second notification system, and does not have one:
**push is a channel on this engine**, and inherits BR-0016, BR-0017, the
retry ladder, the dead letter and the delivery history without restating any
of them. One `EventMapping` entry and one template per message, as with every
other channel.

What is genuinely different is the ADDRESS. `notification_device` holds the
delivery token a phone registers for itself after sign-in, and a token is not
a phone number:

- **Capability-like.** Whoever holds it can push to that handset through a
  configured gateway. So it is never returned by any endpoint — `GET
  /v1/notification-devices` shows a six-character suffix, enough for a
  support call and useless to a sender — never logged in full, and deleted
  rather than deactivated on revocation. A revoked token is not evidence of
  anything.
- **Re-registered constantly.** The app registers on every start, because the
  gateway hands out the same token until it rotates. Registration is
  idempotent by token; a row per launch would be five copies of every message.
- **Movable.** A token already held by another user MOVES rather than being
  rejected. A shared handset is a real situation in a dairy, and rejecting
  would leave the old binding in place — which is the outcome that leaks.
- **Silently mortal.** An uninstalled app leaves a token that fails forever.
  A `PermanentSendError` on the push channel makes the platform forget it,
  rather than spend a gateway call learning the same thing every time.

`notification_device.customer_id` is what lets `sales.invoice-issued.v1` —
which knows a customer id and has never heard of a user account — resolve to a
handset without this module reading an identity table. The API layer copies it
from the authenticated principal.

**Bodies carry no figures.** A push renders on a lock screen, which is a
public surface: `invoice_issued` announces that a bill is ready and does not
quote it. The amount is one tap away, behind the sign-in, where it is also the
platform's own figure rather than a copy that can go stale.

**Configuration.** `LACTEVA_NOTIFICATION_PUSH_PROVIDER` defaults to
**`disabled`**, not `logging`: no messaging vendor has been chosen or paid
for, and a deployment that has not made that decision must fail a push
visibly rather than mark it delivered. `http` selects `HttpPushProvider`,
which speaks the same vendor-neutral JSON contract as the SMS adapter and
needs `LACTEVA_PUSH_API_URL` and `LACTEVA_PUSH_API_KEY`. Production refuses
`http` with either missing, and refuses `logging`/`placeholder` outright.

**What is not proven.** `HttpPushProvider` has never delivered a real push.
Its contract, status classification and idempotency key are exercised against
a stub gateway in `tests/test_push_devices.py`; that no particular vendor has
accepted a message from it is stated here rather than left to be discovered.
See [MOBILE-EXPERIENCES](MOBILE-EXPERIENCES.md) for the phone's half.

