---
id: DEMO-031-FINAL
title: DEMO-031 — First Notification Gateway & Sandbox Delivery
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-16
last-updated: 2026-08-16
related: [DEMO-030-FINAL, DEMO-029-FINAL, DEMO-025-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-031 — First Notification Gateway & Sandbox Delivery

Crossing the vendor boundary safely. **No vendor was contacted, no account
created, no credential configured, and no message was sent to anyone.**

---

## 1. What already existed

The vendor boundary was already crossed generically. `HttpSmsProvider` speaks
"a small, documented JSON contract configured entirely by environment" and
classifies outcomes by HTTP status; `HttpWhatsAppProvider` subclasses it;
`_build()` maps configuration to adapter; `register_provider` is the seam for
anything that does not fit. Settings already carry URL, key, sender and timeout
per channel, and startup validation already refuses `http` without both URL and
key, and refuses `logging`/`placeholder` in production.

Also complete and reused unchanged: dispatch, idempotency, the retry
classification, templates in four languages, tenant channel selection, business
dates, the delivery-status model, DEMO-029's webhook security boundary, HMAC
verification, replay protection, receipts, contact repair, reachability, RLS
and the PostgreSQL proofs.

**Two gaps, and the second is the interesting one.**

## 2. Provider research

**No vendor was contacted and no account exists.** What follows is from public
documentation as it stood at the time of writing, marked by confidence exactly
as §2 requires. **Every commercial term must be confirmed with the vendor
before a contract**; pricing and coverage change and none of it is verifiable
from here.

### What Lacteva actually needs

| Capability | Why |
|---|---|
| Transactional SMS, India + Kenya | settlement slips, bills |
| WhatsApp, India + Kenya | the channel tenants ask for |
| Delivery receipts by webhook | DEMO-029's `delivered` is only reachable this way |
| HTTPS API, key/token auth | the existing adapter shape |
| Sandbox or test credentials | §6 |
| Registered sender identity | required in both markets |
| Template registration | required by WhatsApp, and by Indian SMS regulation |

### Structural facts

* **[PUBLIC]** The WhatsApp Business Platform requires a **business-initiated**
  message to use a **pre-approved template**, identified by name and supplied
  with positional parameters. Free-form text is permitted only inside a
  24-hour customer-service window opened by the customer. Access is either
  directly through Meta's Cloud API or through a Business Solution Provider.
* **[PUBLIC]** Commercial SMS in **India** requires **TRAI DLT registration**:
  the sender identity and the message templates are registered with a registry
  before traffic flows. A generic "send arbitrary text" integration does not
  satisfy it.
* **[PUBLIC]** Delivery reports over webhook are a standard capability of SMS
  gateways generally.
* **[INFERRED]** Alphanumeric sender identities in **Kenya** require
  registration through the operator or regulator, in the same shape as India's
  but under a different regime.
* **[UNKNOWN]** Every price, every per-market rate, every coverage guarantee,
  and every vendor's current sandbox terms.

### Candidates

| Candidate | SMS IN | SMS KE | WhatsApp | Notes |
|---|---|---|---|---|
| Global CPaaS (e.g. Twilio, Infobip) | [PUBLIC] offered | [PUBLIC] offered | [PUBLIC] as BSP | One contract, one adapter shape; commercial terms [UNKNOWN] |
| Meta Cloud API direct | — | — | [PUBLIC] | WhatsApp only; still needs an SMS vendor |
| Africa-focused gateway (e.g. Africa's Talking) | [UNKNOWN] | [PUBLIC] regional focus | [UNKNOWN] | Strong for Kenya; India unproven |
| India-domestic gateway (e.g. MSG91, Gupshup, Kaleyra) | [PUBLIC] DLT-aware | [UNKNOWN] | [PUBLIC] several are BSPs | Strong for India; Kenya unproven |

**[INFERRED] conclusion:** no candidate is *established* by public
documentation to serve both markets and both channels well. Either one global
CPaaS covers everything at a price nobody here can verify, or two regional
adapters do — which is exactly the case the existing abstraction was built for.

## 3. Provider decision

**No vendor was selected, and that is the finding rather than an omission.**

Selecting one would have required a commercial decision nobody has made, and
"implementing the X adapter" from documentation I cannot execute against would
have produced code that has never met the API it claims to speak. By this
repository's own standing rule, that is not evidence of anything.

What the survey established instead is that **the difference that matters is
not between vendors — it is between channels.** SMS takes text; WhatsApp takes
a template name and positional parameters. Lacteva's boundary carried only
text, so *every* candidate would have needed the same change first.

So the smallest practical strategy, and what DEMO-031 built:

1. **Close the template gap** in the boundary, so any WhatsApp-capable adapter
   can be written without touching the domain.
2. **Add the mode gate**, so a gateway can be configured without the platform
   being able to send.
3. **Ship a sandbox gateway** that enforces the constraints a real platform
   enforces, so the whole journey is executed rather than described.
4. **Keep the generic HTTP adapter** for any vendor whose API matches
   Lacteva's documented contract — that vendor needs no code at all.

## 4. Why

Because the alternative was a plausible-looking adapter for a named vendor that
had never been run against that vendor. Four milestones in a row here have
drawn the same line — DEMO-027 built a payment boundary and refused to invent a
gateway, and this is the same refusal.

## 5. Adapter implementation

**Nothing was redesigned.** `ChannelProvider`, `DeliveryResult`, the registry,
`register_provider` and dispatch are untouched. Two additions to the boundary:

```python
@dataclass(frozen=True)
class OutboundMessage:
    ...
    parameters: tuple[str, ...] = ()      # the template's variables, IN ORDER
    vendor_template: str | None = None    # the vendor's name for our template
```

`parameters` is derived from `Template.variables`, which has always exposed the
declared order — so a WhatsApp `{{1}}, {{2}}` maps to it with **no new concept
in the domain**. Adapters that take text keep using `body` and ignore both.

`SandboxGatewayProvider` is the concrete adapter, and it is not a stub that
returns success. It enforces what a real platform enforces:

* a WhatsApp message with no approved template name → **permanent** failure,
  because a retry cannot approve a template that was never submitted;
* a template message with no parameters → permanent failure;
* an implausible recipient → permanent failure;
* the recipient's last digit selects accepted / transient / permanent, so the
  retry classification is addressable without a clock or a random source.

It also implements `parse_receipt`, so the delivery-receipt path runs through
**DEMO-029's boundary unchanged**.

## 6. Configuration

```
LACTEVA_MESSAGING_MODE=test|sandbox|production      # DEFAULT: test
LACTEVA_NOTIFICATION_<CHANNEL>_PROVIDER=…|sandbox
LACTEVA_<CHANNEL>_API_URL / _API_KEY / _SENDER_ID   # existing
LACTEVA_NOTIFICATION_RECEIPT_SECRET                 # existing (DEMO-029)
LACTEVA_NOTIFICATION_VENDOR_TEMPLATES               # {"key.channel": "name"}
```

Every secret comes from deployment configuration. **Nothing is hard-coded,
committed, printed, stored in the database, or exposed through the portal or
the API** — asserted by four tests, including one that sweeps the OpenAPI
schema and one that sweeps `config_entry` on PostgreSQL.

A vendor template name is configuration and never a constant: an approved name
is issued per business account and per market, and hard-coding one would put a
vendor's registry into this repository.

## 7. Sandbox / test mode

**The gate that makes an accidental real send impossible.**

| Mode | Meaning |
|---|---|
| `test` | **the default.** No network call is attempted at all |
| `sandbox` | the gateway's test environment, or Lacteva's in-process sandbox |
| `production` | real messages to real people. Requires saying so |

Provider selection says *which* gateway; the mode says whether the platform may
talk to it at all. Before DEMO-031 a deployment that set `http` with a URL and
a key started sending the moment it came up, and the only protection was
remembering to choose `dry_run`. **Forgetting a safety is not a safety**, so
the safety is now the default.

A network adapter in `test` mode raises `MessagingModeError` — a **permanent**
failure, so it surfaces in the notification history with a reason rather than
spinning in a retry loop against a setting. Production refuses `sandbox` mode
and the `sandbox` adapter outright, alongside DEMO-025's existing refusal of
`logging` and `placeholder`.

## 8. End-to-end flow

Both journeys, one path, no second implementation:

```
settlement finalized / invoice issued
  → event → dispatch consumer (recipient, tenant channel, language)
  → NotificationService.dispatch  (idempotent: one event, one message)
  → OutboundMessage {body, parameters, vendor_template}
  → provider adapter  ← the mode gate is here
  → DeliveryResult {provider_message_id, status=accepted}
  → notification: status=sent, provider_status=accepted
  → signed receipt → DEMO-029 boundary → status=delivered
```

Proven on PostgreSQL for both settlement and invoice, including that eight
concurrent dispatches produce **one** row and **one** gateway call.

## 9. Webhook

**DEMO-029's boundary, reused — not duplicated.** The sandbox gateway's
`parse_receipt` calls the same `_parse_documented_receipt`, which calls the
same `core/webhook_security`. A test still fails if a second `hmac.new` or
`compare_digest` appears in any webhook file.

Proven: a valid receipt delivers; an invalid signature changes nothing; a
replay does nothing; an unknown reference writes nothing; six concurrent
receipts apply exactly once; and a contradictory later failure **never
un-delivers** an arrived message.

## 10. Retry and failure

The existing classification decides, unchanged. Proven on PostgreSQL: a
transient gateway failure leaves the message `failed` **with a next attempt
scheduled**; a permanent rejection leaves it `dead` with **no** next attempt;
and a mode refusal is permanent, because retrying a setting is just a slower
refusal.

## 11. Portal

One panel on the existing notifications page — no new page, no new component.
Per channel: provider name, **configured**, **can send now**, **delivery
receipts** — three yes/no answers, plus the mode and a plain sentence when no
real message can be sent.

**Never a credential and never a gateway URL.** A URL is not a secret, but it
names the vendor and the account path and nothing here needs it. A test asserts
neither appears on the screen.

## 12. Mobile

**MOBILE UNCHANGED.** The app already consumes the existing notification and
delivery contracts, including `provider`, and nothing in this milestone changes
either. No mobile code was touched.

## 13. Security and RLS

| Attempt | Result |
|---|---|
| Read another tenant's channel configuration | zero rows under RLS |
| Read another tenant's notifications or receipts | zero rows |
| Read another tenant's message content | zero rows |
| Credential in an API response | none — schema swept |
| Credential in the database | none — `config_entry` swept |
| Unsigned receipt | refused |

Provider configuration is deployment-wide because the gateway is shared; what
is per-tenant is the channel choice, which lives in the configuration store
behind RLS.

## 14. PostgreSQL proof

`./infra/ci/verify-postgres.sh` — **PASSED**, **184 tests in step 3** (up from
167), 0 skipped, 69 policies.

`tests/test_gateway_sandbox_postgres.py` is in the proof's explicit file list
and covers all fifteen properties §15 names.

## 15. Tests

| Suite | Result |
|---|---|
| Backend (`pytest tests/`) | **1968 passed**, exit 0 |
| `tests/test_gateway_sandbox.py` (new) | 24 |
| `tests/test_gateway_sandbox_postgres.py` (new) | 23, on real PostgreSQL |
| Admin portal (`vitest`) | **276 passed** (20 files) |
| Mobile `flutter analyze` / `flutter test` | no issues / **125 passed** |
| Lint, format, tsc, eslint, build, docs, xref | all green |

Four guards mutation-checked, each failing a test: the mode gate, the WhatsApp
template requirement, the sandbox's production refusal, and the parameters
reaching the boundary.

## 16. Production verification

*(completed after deployment — see §16 in the released version)*

## 17. Financial safety

A gateway is a way to tell someone about money, not to move it. Asserted on
SQLite and again on PostgreSQL for both journeys: settlement, invoice, payment,
receipt, customer-payment and collection counts plus settlement net and
receivables are snapshotted around a complete send-and-receipt cycle and
required identical.

## 18. REAL versus TEST

**REAL**
* The provider adapter contract, the registry, and configuration-driven
  selection.
* The messaging-mode gate and its production refusals.
* The template-parameter boundary that WhatsApp structurally requires.
* Dispatch, idempotency, retry classification, delivery state.
* Webhook security, replay protection, receipts — DEMO-029's, reused.
* RLS and the PostgreSQL proof.

**TEST / SANDBOX**
* Every message in every test goes to `SandboxGatewayProvider`, in-process.
  **Nothing opens a socket.**

**NOT PROVEN**
* **Real production delivery.** No vendor was contacted, no account created, no
  credential configured, and no SMS or WhatsApp message was sent to anybody.
  Nothing here is evidence that a particular vendor behaves as its
  documentation says.

## 19. Known limitations

* No vendor is selected, so no real message can be sent (§3).
* The sandbox enforces the constraints this survey established. A real gateway
  will have others.
* `notification_vendor_templates` is process-wide, not per tenant. If two
  tenants ever need different approved templates for the same message, this
  needs a key.
* Optional template segments are deliberately excluded from positional
  parameters — a template message with a varying parameter count is not a
  template — so a WhatsApp template cannot carry the optional quantity line
  that SMS and email now show.
* No WhatsApp session-window handling: the platform only ever sends
  business-initiated messages, and has no inbound path.
* No per-message cost accounting.

## 20. What is required before real production messaging

1. **A commercial decision and a contract** with a gateway per market (§2).
2. **Regulatory registration** — TRAI DLT sender IDs and templates for India;
   the equivalent sender-identity registration for Kenya.
3. **WhatsApp template approval** for each message, per market, and the
   approved names in `LACTEVA_NOTIFICATION_VENDOR_TEMPLATES`.
4. **An adapter**, if the vendor's API does not match Lacteva's documented HTTP
   contract: one class implementing `ChannelProvider`, one line in `_build`.
5. **Deployment configuration**: provider, URL, key, sender id, receipt secret.
6. **The webhook URL registered** with the vendor:
   `https://<host>/v1/notifications/receipts/<provider>`.
7. **`LACTEVA_MESSAGING_MODE=sandbox`**, and an executed run against the
   vendor's sandbox — including a real delivery receipt arriving.
8. **Then `production`**, deliberately, with a small pilot audience first.

Step 7 is the one that matters. Everything in this milestone is evidence about
Lacteva; none of it is evidence about a vendor until it has been run.

## 21. Recommended DEMO-032

**Recommended: the commercial and regulatory groundwork, which is not
engineering.** The next real blocker is a signed contract and a DLT/sender-id
registration, and no amount of code advances it. What *can* be built alongside
is the small piece that registration makes necessary: a **template registry
mapping** view so an operator can see which of Lacteva's templates have an
approved vendor name in which market, and which do not — the same shape as the
reachability report, for templates instead of farmers.

**Then: the first real adapter**, once a vendor exists, following §20 exactly.

**Not recommended yet:** per-tenant vendor accounts, cost accounting, or
inbound message handling. All three are only meaningful after real traffic.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-16 | Platform Engineering | DEMO-031: a messaging-mode gate that makes an accidental real send impossible, the template-parameter boundary WhatsApp structurally requires, and a sandbox gateway that enforces real constraints — with no vendor selected, contacted or credentialed. |
