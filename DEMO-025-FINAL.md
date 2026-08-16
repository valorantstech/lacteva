---
id: DEMO-025-FINAL
title: DEMO-025 — Commercial Foundation I: Message Delivery
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-16
last-updated: 2026-08-16
related: [DEMO-024-COMPETITIVE-REVIEW, DEMO-023-FINAL, DEMO-012-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-025 — Commercial Foundation I: Message Delivery

**Read this first: DEMO-024 got the premise partly wrong, and this milestone is
smaller and different because of it.**

---

## 0. A correction to DEMO-024

DEMO-024 reported that *"the notification module has one adapter —
`LoggingNotifier` — and a code TODO for real SMS and email"*, and made that the
headline reason to build this milestone.

**That was wrong.** I found `infrastructure/notifications.py`, which does hold a
`LoggingNotifier` and a TODO, and stopped there. The actual messaging
implementation is `modules/notification/`, and this survey found it already
contained:

| Already built | Where |
|---|---|
| A provider-independent `ChannelProvider` boundary | `providers.py` |
| **A real HTTP SMS gateway adapter** | `HttpSmsProvider` |
| **A real SMTP email adapter** | `SmtpEmailProvider` |
| **A real HTTP push adapter** | `HttpPushProvider` |
| Dev/test providers: logging, placeholder, dry-run, disabled | `providers.py` |
| Configuration-driven provider selection with startup validation | `config.py` |
| Idempotency as a UNIQUE CONSTRAINT on (event, template, channel) | `models.py` |
| Retry with attempt counting and backoff | `service.py` |
| Permanent-vs-retryable failure classification | `ProviderSendError` / `PermanentSendError` |
| Phone masking before logging | `mask_phone` |
| A template catalog with per-language variants | `templates.py` |
| Event→template mapping through a consumer | `notification_dispatch.py` |
| A settlement-finalized SMS journey, working end to end | since NOT-001 |

The `LoggingNotifier` I cited is the *innermost* port that `LoggingProvider`
delegates to in development — not the platform's only way of sending anything.

**What this means commercially.** Lacteva was closer to being able to message
people than DEMO-024 claimed. The remaining gap was real but narrower: no
WhatsApp channel, no Hindi or Arabic message templates, a customer who could
not be reached at all, and a bill that named the wrong day.

---

## 1. What already existed

See §0. In addition: `Notification` already carried every field Part 2 of the
work order asks for — message, recipient, template, channel, provider, status,
failure reason, created/sent timestamps and the external provider reference.
**No new messaging domain was needed and none was created.**

## 2. What DEMO-025 added

**A WhatsApp channel.** `HttpWhatsAppProvider` subclasses `HttpSmsProvider`
because the HTTP contract and its status classification are identical — what
differs is a URL, a credential and a sender identity, all configuration. It
defaults to `disabled`, so a deployment that has contracted no gateway fails
visibly rather than recording an undelivered message as sent.

**Hindi and Arabic message templates.** The catalog had English and Swahili
only — a gap nobody had noticed because the *portal* has en/hi/ar and the
*message catalog* did not. Both business journeys now exist in en/hi/ar (and
Swahili, which was already there), across SMS and WhatsApp.

**The invoice default was NOT changed.** I briefly moved it from `push` to
`sms` and the full suite caught it: DEMO-012 built the push journey for
households that have the app, and changing the default would have silently
taken it away from them. The default stays `push`; a dairy whose households
have no app sets `notification.channel.invoice_issued` to `sms` or `whatsapp`.
**New capability, no behaviour removed.**

**A customer who can be reached.** The recipient directory is built from
supplier events; customers emit none, so a household had no contact record and
could not be billed by SMS at all. The `invoice.issued` event now carries the
household's name and phone, exactly as supplier events already carry contact
details. **No second directory was created.**

**Tenant-chosen channels.** `resolve_channel` reads
`notification.channel.<template_key>` from the existing tenant configuration
store. An Indian dairy on WhatsApp and a Kenyan one on SMS differ by a
configuration row — **there is no country anywhere in the path**, and a test
asserts that against the source.

**Richer, honest content.** The settlement slip now names the period it covers
and shows gross beside net. Both are shown even though they are equal today,
because the deduction engine is still a placeholder — a slip that showed only
one figure would have to change shape the day deductions land.

## 3. Defects found

**1. The invoice message named the wrong day.** `_invoice_issued` fell back to
`envelope.time[:10]` — a slice of a **UTC** timestamp — for the billing period.
For an Indian dairy issuing after 18:30 local, that is the previous day, on the
customer's own bill. Fixed by carrying the invoice's own business dates on the
event.

**2. WhatsApp would have resolved to an email address.** `_resolve_recipient`
mapped `sms → phone` and everything else to `email`. A WhatsApp message would
have been addressed to an inbox and failed on every send.

**3. A household could not be reached.** As above — no directory entry, no
contact on the event.

**4. Tenant configuration was read from a contextvar the consumer never sets.**
`ConfigurationService.resolve` scopes itself from the tenant context variable;
the dispatch consumer carries the tenant on the event and sets no variable. The
lookup therefore found nothing and every tenant silently kept its default —
a configuration feature that did not work. The tenant is now passed explicitly
and the variable set for the duration of the read.

**5. The portal could not filter for push or WhatsApp failures.** The channel
filter listed only `sms` and `email`, so a push failure — a channel live since
DEMO-012 — could not be found.

**6. Concurrent dispatch poisoned its own transaction — found by the
PostgreSQL proof.** `dispatch` guards the idempotency race with a SAVEPOINT and
catches `IntegrityError`, but the `session.add` sat *outside* the savepoint.
Entering `begin_nested()` can autoflush the pending insert first, so the unique
violation happened outside the savepoint, poisoned the outer transaction, and
the caller's `commit()` raised `PendingRollbackError` — the `except` caught
nothing because nothing had been contained. Eight concurrent dispatches on real
PostgreSQL produced one row and **seven broken transactions**. It survived
because SQLite's test stack shares one connection and never actually races. The
`add` now sits inside the savepoint, matching the pattern the supplier
directory already used.

I also removed a duplicate I had just introduced: an explicit-recipient check
inside `_resolve_recipient` that `_attempt` already performed one level up. A
mutation check caught it by *not* failing.

## 4. Messaging architecture

```
BUSINESS EVENT            settlement.finalized.v1 / sales.invoice-issued.v1
      ↓                   (outbox → relay → consumer, all pre-existing)
EVENT MAPPING             template key + default channel + payload builder
      ↓
CHANNEL RESOLUTION        tenant configuration, never country      ← DEMO-025
      ↓
TEMPLATE                  key × channel × language                 ← extended
      ↓
NOTIFICATION ROW          idempotent on (event, template, channel)
      ↓
CHANNEL PROVIDER          sms · whatsapp · email · push
      ↓                   configuration selects logging/placeholder/
EXTERNAL GATEWAY          dry_run/disabled/http/smtp
```

The business domain never names a provider. Billing publishes an event; it does
not know a message exists.

## 5. Provider adapter design

| Provider | Purpose | Sends anything? |
|---|---|---|
| `LoggingProvider` | dev/test default | **No** — logs only |
| `PlaceholderProvider` | market not yet contracted | **No** |
| `DryRunProvider` | staging against real config | **No** |
| `DisabledProvider` | channel deliberately off | **No** — refuses |
| `HttpSmsProvider` | generic HTTP SMS gateway | **Yes**, if configured |
| `HttpWhatsAppProvider` | generic HTTP WhatsApp gateway | **Yes**, if configured |
| `SmtpEmailProvider` | any SMTP relay | **Yes**, if configured |
| `HttpPushProvider` | generic HTTP push | **Yes**, if configured |

A gateway that does not fit the contract implements `ChannelProvider` and is
installed with `register_provider`. No vendor SDK is imported anywhere.

## 6. Farmer settlement journey (DEMO A)

`collect → calculate → finalize` publishes `settlement.finalized.v1` carrying
the settlement's number, gross, net, currency, line count and **business
dates**. The consumer maps it to `settlement_finalized`, resolves the tenant's
channel, renders in the farmer's language and dispatches.

Every figure is read from the finalized settlement. **Nothing in the messaging
path computes money.**

## 7. Customer invoice journey (DEMO B)

`issue_invoice` publishes `sales.invoice-issued.v1` carrying the invoice
number, amount due, currency, business dates and the household's name and
phone. The default channel remains `push`; a dairy configures its way to SMS or
WhatsApp, which is what the invoice tests exercise.

The amount is the invoice's own `amount_due`. **There is no second billing
calculation.**

## 8. Templates and localization

| Journey | SMS | WhatsApp | Email | Push |
|---|---|---|---|---|
| `settlement_finalized` | en, hi, ar, sw | en, hi, ar, sw | en | — |
| `invoice_issued` | en, hi, ar, sw | en, hi, ar | en | en, sw (kept) |

Currency is carried, never converted. Dates are business dates. No message text
exists outside the catalog.

## 9. Idempotency and retries

Unchanged and reused: `uq_notification_event` on `(event_id, template_key,
channel)`. Running the dispatch worker three times produces one row and one
gateway call. Retries reuse the same row and the same gateway idempotency key,
so a send that succeeded but timed out on our side is recognised rather than
delivered twice. A permanent rejection becomes `dead` and is not retried.

**No second scheduler was created.** Dispatch rides the existing consumer loop.

## 10. Security, tenancy and secrets

RLS unchanged — `notification` was already tenant-owned and forced. Credentials
live in environment configuration and are never logged, never rendered into a
template and never stored on a row. Phone numbers are masked before logging.
The one-time invitation token continues to travel by the secret-payload path
rather than through the event outbox.

## 11. Known limitations

* **Delivery confirmation is not modelled.** Statuses are `pending → sent →
  failed/dead`. A gateway that later confirms actual handset delivery has
  nowhere to report it, and Lacteva deliberately does **not** claim
  `delivered`. Adding a delivery-receipt webhook is the natural next step.
* **WhatsApp template approval is out of scope.** Markets that require
  pre-approved WhatsApp templates must register them with their gateway;
  Lacteva sends text and records the response.
* **The customer contact travels on the event.** It is contact information,
  already present in the customer row and in every backup — but it does mean a
  phone number is in the outbox, which is not pruned. A customer directory fed
  by customer events would be the cleaner long-term shape.
* **Channel choice is per template key, not per recipient.** A farmer who wants
  SMS in a WhatsApp-configured dairy cannot say so.
* **No delivery-cost accounting.** The SMS adapter records what the gateway
  reports about cost; nothing aggregates it.

## 12. Recommended DEMO-026

**Commercial Foundation II: SaaS subscription, trial and entitlement.** It is
the other half of Phase 1 in DEMO-024's roadmap and the remaining blocker on
charging anyone. Messaging now gives a trial something to demonstrate.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-16 | Platform Engineering | DEMO-025: WhatsApp channel, Hindi/Arabic message templates, reachable customers, tenant-chosen channels, and four defects fixed — including a bill that named a UTC day. Corrects DEMO-024's claim that only a logging adapter existed. |
