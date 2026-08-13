---
id: MOBILE-EXPERIENCES
title: Mobile Field Experiences
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-13
last-updated: 2026-08-13
related: [OFFLINE-SYNC, NOTIFICATION-ENGINE, BR-REGISTER, CLAUDE-CONTEXT]
baseline: ARCH-BASELINE-V1
---

# Mobile Field Experiences

How one Flutter application serves three different people in the field, and where the boundary sits between what the phone does and what the platform decides. Established by DEMO-012.

**The guarantee:** the mobile application is a *client*. It renders what the platform says and captures what a person did. It contains no pricing, no billing, no settlement, no payment and no tenancy logic, and it never computes a financial figure the platform has already produced.

## 1. One application, three experiences

The three field users are a **collection operator** at a centre, a **delivery rider** on a household round, and a **customer** looking at their own account.

They differ in their screens and agree in everything underneath: the same authentication, the same tenancy, the same offline queue, the same API client, the same release pipeline. Three applications would triplicate all of that so that each could hold one folder the others do not — and the offline engine is the last thing in this codebase that should exist in three slightly diverging copies.

So: one application, and `lib/src/home.dart` routes a sign-in to the experience it earns.

## 2. Routing is by capability, never by role name

DEMO-008 made roles rows in a database that an administrator may edit and add to. A client that switched on `role == 'COLLECTION_OPERATOR'` would be wrong the moment somebody created a role that does the same job under another name — which is exactly what the registry exists to allow.

`experienceFor()` therefore asks what the principal **can do**, using the permission set from `/v1/auth/me`:

| Signal | Experience |
| --- | --- |
| `customer_id` is set | the customer's own account |
| `sales.delivery.record` or `sales.delivery.read` | the delivery round |
| `collection.session.manage` or `supplier.read` | the collection centre |
| none of the above | an honest dead end |

A customer scope wins over every other capability, because it is the narrower fact and the platform enforces it regardless of what the app does.

The dead end matters. Before DEMO-012 every sign-in landed on the collection-centre list, so a household met a wall of 403s: the platform refused correctly and the app had promised something it could not deliver. A menu is a promise. An account with real and useful grants that this app does not cover — a finance officer's, say — is told so, and pointed at the web portal.

**Frontend hiding is never the control.** Every screen above is also enforced by `require_permission` on the route and, for a customer, by `enforce_customer_scope` in the service. The app hides what the platform would refuse so that it does not make promises; the platform refuses it because that is where the boundary lives.

## 3. The customer scope

Tenancy answers "which organization". It cannot answer "which household inside it": every `sales.*` permission is tenant-wide, so a customer granted `sales.invoice.read` so it could read its own bill would read every other household's bill in the same dairy.

`user_account.customer_id` answers that. A contextvar carries it (`core/tenancy.py`), the `CUSTOMER_PORTAL` role grants exactly five read permissions, and every customer-facing query passes its filter through `enforce_customer_scope`, which:

- returns the scope when the caller asked for nothing, so a query cannot omit the filter;
- raises **not found** — never forbidden — when the caller asks for somebody else's id, because 403 confirms the row exists and that is exactly what one household must not learn about another;
- is NULL for every staff account, so a scope that fails to apply can only ever show a customer *nothing*. It cannot widen anybody's access.

## 4. What the phone must never compute

The rule is not "avoid arithmetic". It is that **a figure the platform has already produced must never be recomputed on the phone**, because whichever number the app shows is the number the customer believes.

- A bill renders the platform's own `totals_match_lines` verdict rather than re-adding the lines in Dart. A second billing engine's only possible contribution is to disagree with the first in front of the person being billed.
- The balance card shows `outstanding` as issued. It does not subtract paid from invoiced — the platform knows about adjustments the phone does not.
- A queued delivery carries **no amount**. The phone does not know what the milk is worth: the rate lives on the customer's plan and the arithmetic is the platform's.
- The day's totals on the round are the server's aggregate, not a sum of the rows on screen.

`test/screens_test.dart` asserts this by making the platform's answer *disagree* with the obvious local arithmetic and requiring the platform's.

## 5. Offline

The delivery round inherits OFF-001's queue and its rule: offline changes how work reaches the platform, never what the platform decides. Two things are specific to deliveries.

**One request, not a batch.** A delivery is a single idempotent POST, so it replays directly with the key it was captured with rather than going through the collection batch protocol, which exists for a multi-step state machine. `delivery_router` is an `IdempotentRoute`, so a delivery recorded before the phone lost the reply is recognised rather than written twice.

**A refusal is an answer.** A 4xx is the platform's considered verdict — "this slot is already recorded" — and it reaches the rider. Hiding it in a queue that replays it nightly turns one clear error into a haunting. Only transport failures fall back to the queue.

The round always shows what is waiting on the phone. A rider must never have to guess whether the last twenty minutes of work is on the handset or at the dairy.

## 6. Push notifications

Push is a **channel on the existing notification engine**, not a second notification system: it inherits BR-0016 (only durable events produce messages), the `(event, template, channel)` idempotency key, retry, dead-lettering and the delivery history an operator can read.

What is new is that the address is a token held by a phone, which behaves unlike a number or an address:

- it is capability-like, so it is never returned by any endpoint and never logged in full;
- it rotates and is re-registered on every app start, so registration is idempotent by token;
- it **moves** when a handset is signed into a second account — the previous binding is deleted, not kept, because a shared phone is a real situation in a dairy;
- it dies silently when an app is uninstalled, and a permanent failure makes the platform forget it rather than spend a gateway call learning the same thing forever.

`notification_device.customer_id` is what lets an invoice-issued event — which knows a customer and has never heard of a user account — find a handset, without the notification module reading an identity table. The API layer copies it from the authenticated principal.

Bodies carry **no figures**. A push renders on a lock screen, which is a public surface: the bill is announced, never quoted, and the amount is one tap away behind the sign-in.

### Configuration required before push does anything

No messaging vendor is chosen, wired or paid for. `LACTEVA_NOTIFICATION_PUSH_PROVIDER` therefore defaults to **`disabled`**, so a deployment that has not made that decision fails a push visibly instead of recording it as delivered — this platform's own rule about looking healthy while doing nothing.

To turn it on:

| Where | What |
| --- | --- |
| Server | `LACTEVA_NOTIFICATION_PUSH_PROVIDER=http`, `LACTEVA_PUSH_API_URL`, `LACTEVA_PUSH_API_KEY` |
| App | add `firebase_messaging`, add the `google-services.json` / `GoogleService-Info.plist` from that project, implement `PushTokenSource` over `getToken()` |

Nothing else changes: `registerForPush` already runs after every sign-in and `revokePush` on sign-out. The server credential is server-side configuration and is **never** shipped in the application — what the phone holds is its own delivery token, an address for one installation, useless for reading anything and revoked on sign-out.

## 7. What the app does not hold

No AWS credentials, no database credentials, no API secrets, no privileged service credentials, no signing keys. The API base URL is a compile-time define. The release keystore is supplied from outside the repository (`android/key.properties`, gitignored) and a release build **fails** rather than falling back to debug signing — a fallback is how a debug-signed APK reaches a farmer's phone.

## 8. Related

- [OFFLINE-SYNC](OFFLINE-SYNC.md) — the queue, the sync engine and the recorder-not-decider rule
- [NOTIFICATION-ENGINE](NOTIFICATION-ENGINE.md) — templates, channels, retry and the delivery history

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-13 | Engineering | Established by DEMO-012. |
