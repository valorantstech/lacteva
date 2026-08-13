---
id: DEMO-012-FINAL
title: DEMO-012 — Mobile Applications & Field Operations
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-14
last-updated: 2026-08-14
related: [MOBILE-EXPERIENCES, NOTIFICATION-ENGINE, OFFLINE-SYNC, DEMO-011-FINAL, DEMO-010-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-012 — Mobile Applications & Field Operations

The mobile app already existed. It authenticated, it held a durable offline
queue, it recorded collections, it built. What it did not do was **know who
had signed in**: every account, whoever they were, landed on the collection
centre list. A household signing in met a screen about the dairy's centres
and then a wall of 403s.

The platform was refusing correctly. The app had promised something it could
not deliver, and a menu is a promise.

DEMO-012 is mostly about closing that gap — one application, three
experiences, chosen by what the platform says a principal may do — and about
the boundary underneath it: **the phone is a client**. It renders what the
platform decided and captures what a person did. It prices nothing, bills
nothing, and never recomputes a figure the platform has already produced.

**Five defects were found, four of them by running things rather than reading
them.** One is a platform-wide login outage that had nothing to do with
mobile.

**AWS cost impact: none.** No new resources; no push vendor was created or
paid for.

---

## 1. One application, not three

Three field users: a **collection operator** at a centre, a **delivery rider**
on a household round, and a **customer** looking at their own account.

They differ in their screens and agree in everything underneath — the same
authentication, tenancy, offline queue, API client and release pipeline.
Three applications would triplicate all of that so each could hold one folder
the others do not, and the offline engine is the last thing in this codebase
that should exist in three slightly diverging copies.

The decision is recorded in `lib/src/home.dart`, next to the code it explains,
rather than left as a preference.

## 2. Routing by capability, never by role name

DEMO-008 made roles editable database rows. A client that switched on
`role == 'COLLECTION_OPERATOR'` would be wrong the moment an administrator
created a role doing the same job under another name — which is precisely what
the registry exists to allow.

So `experienceFor()` asks what the principal **can do**, from `/v1/auth/me`:

| Signal | Experience |
| --- | --- |
| `customer_id` is set | the customer's own account |
| `sales.delivery.record` / `sales.delivery.read` | the delivery round |
| `collection.session.manage` / `supplier.read` | the collection centre |
| none of the above | an honest dead end, pointing at the web portal |

Frontend hiding is never the control: every screen is enforced by
`require_permission` on the route and, for a customer, by
`enforce_customer_scope` in the service. The app hides what the platform would
refuse so that it does not make promises it cannot keep.

## 3. A login that speaks for one customer

Tenancy answers "which organization". It cannot answer "which household inside
it" — every `sales.*` permission is tenant-wide, so a customer granted
`sales.invoice.read` to read its own bill would read every household's bill in
the dairy.

`user_account.customer_id` answers that, and the scope only ever **removes**
rows:

- a query that omits the filter gets the scope applied anyway;
- asking for somebody else's id is **not found**, never forbidden — 403 would
  confirm the row exists, which is exactly what one household must not learn
  about another;
- it is NULL on every staff account, so a scope that fails to apply cannot
  widen anyone's access. It can only show a customer nothing.

`CUSTOMER_PORTAL` grants five read permissions and nothing that writes.

## 4. What the phone must never compute

Not "avoid arithmetic" — **never recompute a figure the platform issued**,
because whichever number the app shows is the number the customer believes.

- The bill renders the platform's own `totals_match_lines` verdict instead of
  re-adding the lines in Dart. A second billing engine's only possible
  contribution is to disagree with the first in front of the person being
  billed.
- The balance shows `outstanding` as issued, not invoiced-minus-paid.
- A queued delivery carries **no amount**: the rate lives on the customer's
  plan and the arithmetic is the platform's.
- The round's day totals are the server's aggregate.

`test/screens_test.dart` asserts this by making the platform's answer
**disagree** with the obvious local arithmetic and requiring the platform's.

## 5. Offline

Inherited from OFF-001, with two things specific to deliveries.

**One request, not a batch.** A delivery is a single idempotent POST, replayed
with the key it was captured with rather than through the collection batch
protocol, which exists for a multi-step state machine. `delivery_router` is an
`IdempotentRoute`, so a delivery recorded before the phone lost the reply is
recognised, not written twice.

**A refusal is an answer.** A 4xx is the platform's verdict — "this slot is
already recorded" — and it reaches the rider. Hiding it in a queue that
replays it nightly turns one clear error into a haunting. Only transport
failures fall back to the queue.

The round always shows what is waiting on the phone.

## 6. Push notifications

Push is a **channel on the existing engine**, not a second notification
system: it inherits BR-0016, the `(event, template, channel)` idempotency key,
retry, dead-lettering and the delivery history. Two events are wired —
`sales.invoice-issued.v1` and `sales.customer-payment-recorded.v1` — both to
the household's own handset.

What is new is that the address is a token held by a phone:

- capability-like, so never returned by any endpoint (a six-character suffix
  is), never logged in full, and **deleted** on revocation;
- re-registered on every app start, so registration is idempotent by token;
- **movable** — a token already held by another user moves, because a shared
  handset is real in a dairy and rejecting would leave the old binding in
  place, which is the outcome that leaks;
- silently mortal — a permanent failure makes the platform forget the token.

Bodies carry **no figures**: a lock screen is a public surface, so the bill is
announced and never quoted.

### Configuration required (§10)

No messaging vendor is chosen or paid for, so
`LACTEVA_NOTIFICATION_PUSH_PROVIDER` defaults to **`disabled`** — not
`logging`, which would mark every push delivered and send nothing.

| Where | What |
| --- | --- |
| Server | `LACTEVA_NOTIFICATION_PUSH_PROVIDER=http`, `LACTEVA_PUSH_API_URL`, `LACTEVA_PUSH_API_KEY` |
| App | add `firebase_messaging`, add `google-services.json` / `GoogleService-Info.plist`, implement `PushTokenSource` over `getToken()` |

`registerForPush` already runs after sign-in and `revokePush` on sign-out. The
server credential never ships in the application; the phone holds only its own
delivery token.

**Not proven:** `HttpPushProvider` has never delivered a real push. Its
contract, classification and idempotency key are exercised against a stub
gateway; no vendor has accepted a message from it.

---

## 7. Defects found

### D1 — The mobile signing guard refused *every* build (§23.2)

`flutter build apk --debug` failed with *"Release build requested with no
signing configuration"*. Nothing was requesting a release build.

PORTAL-001 put the check inside `buildTypes.release { }`, which is a
**configuration** block Gradle evaluates on every invocation. So on any machine
without `android/key.properties` — every developer's machine, and every CI job
that only runs tests — the app could not be built at all. The guard was right
to exist and was looking in a place that could not see the question it was
asking.

Moved to `gradle.taskGraph.whenReady`. Verified **both** directions: `--debug`
now produces `app-debug.apk` (137 MB) and `--release` still refuses, naming the
task that triggered it.

### D2 — Two `RegisterDeviceCommand`s, one OpenAPI component

`operational_readiness` already exported `RegisterDeviceCommand` and
`DeviceView` for weighing scales. The second import in `routes.py` silently
shadowed the first, so the new push endpoint validated request bodies against
the **hardware** schema, and both endpoints collapsed to a single OpenAPI
component — a generated client would have had one of them wrong. Renamed to
`RegisterPushDeviceCommand` / `PushDeviceView`.

### D3 — The RLS drift guard caught an unreadable policy

`test_every_tenant_owned_table_is_covered_by_a_policy` failed on
`notification_device`. The migration *did* install the policy — but inline,
rather than from a snapshotted list, so nothing the build could read said so.
Now snapshotted like every other policy migration. The guard has now earned
its keep five times.

### D4 — Summed quantities were published at ten decimal places

Found by running the app against real data: the customer's monthly card read
**"23.0000000000 L"**.

Aggregation casts to unconstrained `NUMERIC` — deliberately, so the sum is
exact — and every **money** figure was quantised on the way out while the
**quantities** were not. The platform was publishing ten decimal places of a
figure it stores to three, and both clients rendered it faithfully.

Fixed in `delivery/service.py` (`litres()`), not in the app: a client that
formats a number has decided how many decimals a litre has, and the two
clients would eventually disagree. The scale belongs to the column.

### D5 — One row could lock every user out of the platform

The worst of the five, and unrelated to mobile.

`login` inserts the session row before it can hash the refresh secret, so the
row needs a placeholder in `refresh_token_hash`. **That column is UNIQUE**, and
the placeholder was the literal string `"pending"`. A single row that reached
the database still holding it — one interrupted request is enough — made
**every subsequent login fail with a 500, for every user, permanently**,
because the next insert collided with it. Nothing in the system ever cleans
such a row up.

Found by accident: a local API process was killed mid-login, and afterwards no
account could sign in at all until the row was deleted by hand.

A placeholder is a value the code does not care about; a unique index cares
about every value. The two must not meet. The placeholder is now unique per
row (`unissued:<random>`), so a stranded row is inert — and obvious to whoever
finds it. `test_a_stranded_session_row_does_not_lock_everyone_out` strands one
deliberately and then asks whether anyone can still sign in; it fails against
the old code with the original `IntegrityError`.

---

## 8. Verification

Every claim below was executed, not read.

| What | How | Result |
| --- | --- | --- |
| Backend suite | `pytest tests/ -q` | **1,347 passed**, 0 failed |
| Mobile suite | `flutter test` | **94 passed** (was 56) |
| Mobile analyzer | `dart analyze` | no issues |
| Lint | `ruff check` + `ruff format --check` | clean |
| Migration | `alembic upgrade head` → `downgrade -1` → `upgrade head`, `alembic check` | reversible, no drift |
| Debug build | `flutter build apk --debug` | `app-debug.apk`, 137 MB |
| Release build refuses | `flutter build apk --release` | refuses, names `packageRelease` |
| Demo seed | `seed_demo.py seed` end to end on a scratch database | exit 0, customer login produced |
| Customer scope | signed in as the seeded household against the seeded data | 1 customer, 30 deliveries, 1 bill, 1 receipt; another household by id → **404**; create a customer → **403** |
| Push contract | stub gateway | accepted / 410 permanent / 503 retried / stable idempotency key |
| Push end to end | real consumer over the real event log | the bill reached the handset that registered; the household with no handset resolved to no device |

### Real-app verification (§16)

No Android emulator images and no attached device on this machine
(`flutter emulators` → none; `adb devices` → empty). **Chrome is a real run
target**, so the app was built for web, served, and driven in a browser at a
phone viewport (412×915) against a real backend on the seeded database:

1. **Sign-in** — no tenant-UUID field (DEMO-010 removed the need); the
   household lands on its own account, not the collection centres.
2. **Customer account** — "What I owe **1829.00 KES**", billed 3658.00, paid
   1829.00; "This month **23.000 L**, 11 deliveries"; bill INV-2026-000001;
   receipt CRC-2026-000001; delivery history. Every figure matches the API
   exactly.
3. **A bill** — deliveries 28, subtotal 3658.00, adjustments 0.00, brought
   forward 0.00, amount due 3658.00 KES, paid 1829.00, outstanding 1829.00,
   and the platform's own verdict: *"Checked by the dairy: this bill matches
   the deliveries below."*
4. **The round** — signed in as the sales officer: today's round, the sync
   banner, day totals, all 16 customers with "not yet recorded".
5. **Recording a delivery** — one tap on DELIVERED. The row became "delivered
   1.500 L" and the day totals became 1 · 1 · 1.500 L · **93.00**. The app
   sent neither the quantity nor the amount: the standing order supplied
   1.500 L and the platform priced it at 62.0000/L. Confirmed server-side.

D4 was found at step 2 and re-verified there after the fix.

---

## 9. Security

- **No credential of any kind ships in the app.** The API base URL is a
  compile-time define; the release keystore comes from `android/key.properties`
  (gitignored, and a test asserts the real file is absent); the push server
  credential is server-side configuration.
- **Role information is never trusted from the client.** Every capability comes
  from `/v1/auth/me`, resolved from the database per request.
- **Cross-tenant access** is unchanged and still enforced by RLS in the
  database; `notification_device` is tenant-owned and carries the standard
  policy, installed by migration.
- **Nothing sensitive is logged.** A push token appears in no log line and no
  API response; a failed registration is swallowed without logging, because an
  HTTP error string is exactly where a request body ends up.
- Another tenant's — and another household's — resource is a 404.

## 10. AWS

No resources created, changed or deleted. No deployment was required for the
verification above, which ran entirely against a local scratch database. **$0
recurring cost added.**

## 11. Known limitations

- **`customer_id` has no API.** Binding a login to a customer is a direct
  database write (the demo seeder does it, as would an operator). This is
  deliberate: a scope an administrator could set from a request body is a scope
  they could set wrong, and the failure mode is one household reading
  another's bills. A safe path — an explicit, audited, permission-guarded
  binding — is worth building before customer logins are handed out widely.
- **Push has never been delivered.** See §6. The adapter is proven against a
  stub only.
- **No emulator or device.** Verified in Chrome at a phone viewport, which
  exercises the same Dart and the same platform, but not the Android runtime,
  notification permissions, or a real FCM token.
- **The collection-centre experience is untouched.** It was already built and
  DEMO-012 only changed how one reaches it.
- **No sign-out in the app.** `revokePush` exists and is called by nothing yet,
  because there is no sign-out button to call it from.
- **"Today" is UTC everywhere, and nothing owns that decision.** The app asks
  the platform for today's round using the UTC date, which is what the rest of
  the platform does. For the demo dairy (UTC+3) a 5 a.m. round falls on the
  same UTC day and nothing is wrong. For a dairy at UTC+5:30 it does not: a
  5 a.m. local round is 23:30 UTC the day before, and the round would be filed
  under yesterday.

  Surfaced by a test of mine that computed the date in LOCAL time and so
  passed for eighteen and a half hours a day and failed for the other five and
  a half. The test was wrong and is fixed. The underlying question is a
  PLATFORM decision — the portal, the daily report and the billing period all
  depend on the same answer — and a client that picked its own would be
  exactly the divergence this milestone exists to avoid. Recorded rather than
  decided.

## 12. Recommended next

1. An audited API for binding a customer login, so customer accounts can be
   issued without database access.
2. Sign-out, which is also what makes `revokePush` reachable.
3. Choose a push vendor, or decide explicitly that SMS remains the channel for
   customers — the platform is ready for either and currently does neither.
4. An Android emulator image in CI, so §16 can be answered by a real Android
   runtime rather than by a browser.
5. A per-tenant timezone, so "today" means the dairy's today. Today it means
   UTC's, which is right for East Africa and wrong for India by one day on
   every morning round.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-14 | Platform Engineering | DEMO-012 delivered: three mobile experiences routed by capability, customer-scoped logins, push as a channel, five defects. |
