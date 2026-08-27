---
id: PILOT-001-FINAL
title: PILOT-001 — Controlled End-to-End Pilot Validation
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-10
last-updated: 2026-08-10
related: [ARCH-BASELINE-V1, STD-0007]
baseline: ARCH-BASELINE-V1
---

# PILOT-001 — Controlled End-to-End Pilot Validation

**Work order:** PILOT-001
**Date executed:** 2026-08-10
**Target:** https://dev.phoenixsoft.in (the live deployment, treated as a protected baseline)
**Executed by:** Claude Opus 5, under the constraints stated in the work order

---

## 1. Executive summary

The business flow was driven end to end through the deployed stack over the public
HTTPS path — authentication → collection → pricing → settlement → payment →
receipt → notification — using only legitimate test data and **manual measurements
only**. No mock scale and no mock analyzer were used anywhere in this work order.

**The chain works, and every number agrees.** A manual collection of 10.000 kg at
fat 4.2 / SNF 8.6 / CLR 28.5 resolved to the published rate card's band [4.0, 5.0)
at 45.0000 KES/kg, priced at 450.00 KES, settled at 450.00, paid at 450.00, and
appeared on a real 3,184-byte PDF receipt reading `450.00 KES`. The same 45.0000
was reproduced independently through the pricing playground path, which never sees
the transaction.

**The single most important finding is that the post-deployment smoke test — the
script whose entire job is to prove a deployment works — could never have passed.**
Its business path had three independent blocking defects and had, on the evidence,
never been executed against a real deployment. That is the repository's own rule
made flesh once more: a proof nobody runs is documentation. It is now fixed and
**passes in 5.1 seconds**, exercising collection, settlement, payment, receipt and
notification against the live host.

Nine of nine platform readiness checks report healthy. 1,101 backend tests pass,
the PostgreSQL proof pipeline passes on a real engine, and 57 portal tests pass.

**Verdict: the deployment is demo-ready. There are no pilot blockers.** There are
two findings a demo operator must be briefed on, and one genuine business gap
(late-arriving collections cannot be settled) that should be closed before a real
pilot with real suppliers — but not before a demonstration.

**No AWS resources were created, resized, replaced or deleted. AWS cost did not
increase.**

---

## 2. Environment

| Property | Value |
| --- | --- |
| Public URL | https://dev.phoenixsoft.in |
| Host | EC2 `i-01f37ba08fe01aa84`, c7i-flex.large, ap-south-1a |
| Elastic IP | 15.252.65.201 (unchanged) |
| Storage | 40 GB gp3 root (`/dev/sda1`) + 50 GB gp3 data (`/dev/xvdf`) — unchanged |
| Instance status | running, system ok, instance ok |
| TLS | Let's Encrypt, `CN = dev.phoenixsoft.in`, valid 2026-08-09 → 2026-11-07 |
| Datastores | PostgreSQL, Redis, RabbitMQ — all inside the Docker Compose stack, as required |
| Repository HEAD at start | `f94f672` |

Security posture confirmed from outside: HTTP redirects 301 → HTTPS;
`strict-transport-security: max-age=31536000; includeSubDomains`;
`x-content-type-options: nosniff`; `x-frame-options: DENY`;
`referrer-policy: strict-origin-when-cross-origin`. Errors render as RFC-9457
problem+json.

---

## 3. Deployed versions

| Component | Version |
| --- | --- |
| Platform core image | `lacteva/platform-core:d991dee-fix7` |
| Admin portal image | `lacteva/admin-portal:d991dee-fix7` |
| Database schema (alembic head) | `8c41f0a7b2d3` |
| PostgreSQL engine | 16.14 |
| API title / version | Lacteva Platform Core 0.1.0 |
| Containers | 11 healthy |

Image tags, schema revision and engine version were read directly from the host
earlier in this work order, before host access was lost (§12, PILOT-F09).

---

## 4. Authentication

All checks performed over the public HTTPS path against the deployed stack.

| Check | Result | Status |
| --- | --- | --- |
| Unauthenticated request through the portal proxy | 401 | PASS |
| Unauthenticated request direct to `/v1` | 401 | PASS |
| Wrong password | 401 `invalid_credentials` | PASS |
| Correct login (platform admin) | 204, cookies set | PASS |
| Correct login (tenant manager, with `tenant_id`) | 204 | PASS |
| Session probe reports identity | `authenticated=true`, tenant `cb4c562b…`, 41 permissions | PASS |
| Authenticated business request | 200 | PASS |
| Logout | 204 | PASS |
| Request after logout | 401 | PASS |
| Re-login | 204 | PASS |
| Direct backend token grant `/v1/auth/token` | 200, token works against `/v1` | PASS |

Tokens are never exposed to page script: the browser holds only HttpOnly cookies
and every call goes through the portal's `/api/proxy` BFF, which attaches the
bearer server-side.

**Finding PILOT-F02 (MEDIUM):** a tenant-scoped user cannot sign in with email and
password alone — `get_by_email` filters `User.tenant_id == tenant_id` exactly, so a
login without a `tenant_id` matches only platform users. The login page does expose
an "Organization ID (tenant)" field, so this is not a blocker, but it requires a
dairy manager to type a UUID to sign in. This cost me a failed login during this
work order and will cost a demo operator the same if unbriefed.

---

## 5. Tenant isolation

The deployment held one organization, so a second was created **as a database row**
(not AWS infrastructure) purely to make the cross-tenant test possible:
"Isolation Probe Dairy" `e9e42b8c-c77b-43b8-a331-1fbaeed9cb25`.

| Check | Result | Status |
| --- | --- | --- |
| Manager reads the other organization | **404**, never 403 | PASS |
| Forged `X-Tenant-ID` header at the portal proxy | Same 1 supplier — token remains authoritative | PASS |
| Forged `X-Tenant-ID` direct to the backend | Same 1 supplier | PASS |
| RLS policies present | 53 | PASS |
| Policies `FORCE`d | 53 of 53; 0 enabled-but-not-forced | PASS |
| Tenant tables without a policy | 0 | PASS |
| Application role `lacteva_app` | `superuser=false`, `bypassrls=false` | PASS |
| API connects as | `lacteva_app` (not the owner) | PASS |

Row-level security is genuinely enforced in the deployed database, by a role that
cannot bypass it. Another tenant's resource answers 404, as the architecture
requires.

---

## 6. Portal page validation

All eighteen pages served HTML 200 and their underlying API calls succeeded as the
signed-in manager. No page displayed fabricated or static data — every row shown is
backed by a real record, and counts below are live payload totals.

| # | Page | HTML | API | Payload | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | Centers | 200 | 200 | 1 centre | PASS |
| 2 | Suppliers | 200 | 200 | live count | PASS |
| 3 | Transactions | 200 | 200 | live count | PASS |
| 4 | Rate cards | 200 | 200 | 1 published card | PASS |
| 5 | Matrices | 200 | 200 | 1 matrix | PASS |
| 6 | Playground | 200 | 200 | `/v1/quality-dimensions` | PASS |
| 7 | Settlements | 200 | 200 | live count | PASS |
| 8 | Payments | 200 | 200 | live count | PASS |
| 9 | Receipts | 200 | 200 | live count | PASS |
| 10 | Reports | 200 | 200 | daily collection report | PASS |
| 11 | Notifications | 200 | 200 | 15 records | PASS |
| 12 | Sync | 200 | 200 | 0 operations (honest empty) | PASS |
| 13 | Users | 200 | 200 | 1 member | PASS |
| 14 | Roles | 200 | 200 | permission registry | PASS |
| 15 | Organizations | 200 | 200 | org detail | PASS |
| 16 | Audit | 200 | 200 | audit trail | PASS |
| 17 | Configuration | 200 | 200 | missing key → 404, handled | PASS |
| 18 | Operations | 200 | 200 | backup status (admin) | PASS |

Error handling was checked deliberately, not assumed: an unknown configuration key
returns 404 and the page treats it as an answer rather than a crash — the class of
defect that produced the earlier dashboard `Object.entries(undefined)` failure.

Navigation is permission-driven: entries render only for permissions the session
actually holds, so no menu item leads to a 403.

---

## 7. Collection flow

Two complete collections were recorded through the public HTTPS path. **Every
measurement was entered manually** (`source: "manual"` on both weight and quality).
Mock hardware was not used.

**Transaction A** — supplier Amina Njoroge, 42.500 kg gross / 2.500 kg tare:

| Step | Resulting state |
| --- | --- |
| create | NEW |
| identify (manual, supplier id) | SUPPLIER_IDENTIFIED |
| milk (cow, can, 4.5 °C) | MILK_RECEIVED |
| weight (manual, 42.500 / 2.500 kg) | QUALITY_PENDING |
| quality (manual, fat 4.2 / SNF 8.6 / CLR 28.5) | PRICED |
| accept | ACCEPTED |
| complete | COMPLETED |

Net weight 40.0 kg, unit price 45.0000 KES, gross 1,800.00 KES.

**Transaction B** — 12.000 kg gross / 2.000 kg tare → 10.0 kg net, 450.00 KES.
This is the one carried through to a receipt (§9, §10).

**Event trail** for transaction A, read back from the platform — nine events, in
order: `TransactionCreated`, `SupplierIdentified`, `MilkReceived`,
`WeightCaptured`, `QualityCaptured`, `PricingRequested`, `PricingCompleted`,
`TransactionAccepted`, `TransactionCompleted`.

**State machine refusals proven, not assumed.** Out-of-order steps are rejected
with the expected state named — e.g. `expected state SUPPLIER_IDENTIFIED,
transaction is NEW`; `cannot complete a transaction in state NEW`. A draft supplier
is refused at identification (`supplier is draft, not active`), and the platform
refuses to activate a supplier with no collection centre assignment.

---

## 8. Pricing

| Check | Value | Status |
| --- | --- | --- |
| Rate card | `RC-2B30BC` v1, status **published**, currency KES | PASS |
| Dimension resolved | fat = 4.2 → matrix "FAT bands", row sequence 2 | PASS |
| Matching range | `[4.0, 5.0)` | PASS |
| Unit price | **45.0000 KES**, precision 2 | PASS |
| Quantity | 40.000 kg (A) / 10.000 kg (B) | PASS |
| Gross amount | 1,800.00 (A) / 450.00 (B) | PASS |
| Rounding policy on the amount | `HALF_UP` | PASS |
| Calculator version | 1.0.0 | PASS |

**Verified manually against expected values:** 40.000 × 45.0000 = 1,800.00 and
10.000 × 45.0000 = 450.00. Both agree exactly with what the platform recorded.

**Verified independently:** the same 45.0000 was obtained through
`POST /v1/pricing/resolve` followed by `POST /v1/pricing/calculate` — a path that
takes a row id and quantity and never sees the transaction. The transaction's own
`pricing_detail` reads `RC-2B30BC v1 band [4.0, 5.0)`, matching.

The client-sends-row-ids-never-prices rule is enforced: `/v1/pricing/calculate`
rejects a request without `row_id`.

---

## 9. Settlement and payment

The smallest safe transaction was used throughout: a single 10.000 kg collection
worth 450.00 KES.

| Step | Result | Status |
| --- | --- | --- |
| Collect completed transaction into settlement | `{"added": 1, "skipped": 0}` | PASS |
| **Collect again (idempotency)** | `{"added": 0, "skipped": 1}` | PASS |
| Calculate | status `calculated`, gross 450.00 | PASS |
| Finalize | status `finalized`, gross 450.00, adjustments 0.00, **net 450.00** | PASS |
| Create payment (MOBILE_MONEY) | PAY-2026-000002, 450.00 KES, `draft` | PASS |
| **Replay with same `idempotency_key`** | Same payment id, count unchanged at 2 | PASS |
| submit → execute → complete | `pending` → `processing` → `completed` | PASS |
| Balance after payment | payable 450.00, allocated 450.00, paid 450.00, **outstanding 0.00**, fully paid | PASS |

**Guards proven to refuse — and to create nothing when they do:**

| Guard | Response |
| --- | --- |
| Mutating a finalized settlement (`collect`, `calculate`) | 409 `finalized settlements are immutable` |
| Finalizing an uncalculated settlement | 409 `only calculated settlements can be finalized` |
| Finalizing a settlement with no lines | 409 `cannot finalize a settlement with no lines` |
| Over-allocating a fully-paid settlement | 409 `settlement STL-2026-000001 is already fully paid or allocated` |
| Paying in the wrong currency | 409 `settlement STL-2026-000001 is in KES, not USD — currency conversion is not a payment operation` |
| Overlapping settlement period | 409 `period overlaps settlement STL-2026-000001` |

The payment record count was re-read after the refusals and was **unchanged**, so
the guards refuse without leaving debris.

---

## 10. Receipt

| Check | Result | Status |
| --- | --- | --- |
| Generated by | a **consumer**, from `payment.completed.v1` — not by the payment call | PASS |
| Latency | appeared **1 second** after completion | PASS |
| Number | RCP-2026-000002 | PASS |
| Download | HTTP 200, `content-type: application/pdf`, `content-disposition: attachment; filename="RCP-2026-000002.pdf"` | PASS |
| File | genuine `%PDF-1.4`, 1 page, 3,184 bytes | PASS |

The PDF was parsed and its text extracted to prove it is a real document rather
than a stub. It contains, among other fields: supplier `Smoke Supplier`, supplier
code `S-5604B3`, `PAY-2026-000002 (Mobile Money)`, reference `PILOT-001-MPESA`,
settlement `STL-2026-000002`, period `2026-08-10 - 2026-08-11`, quantity
`10.000 kg`, average rate `45.0000`, `Gross 450.00`, `Adjustments 0.00`, and
`PAID 450.00 KES`.

**The values agree end to end:** 10.000 kg × 45.0000 KES = 450.00 KES, identical at
collection, pricing, settlement, payment and on the printed receipt.

The pre-existing seeded receipt RCP-2026-000001 was verified the same way and is
internally consistent too (125.500 kg × 45.0000 = 5,647.50).

This also proves the Relay is alive in production: the event was written to the
outbox inside the business transaction, published, and consumed — the failure mode
that "looks healthy" is demonstrably absent.

---

## 11. Notification

Notifications are generated correctly and **nothing was sent to any external
recipient**.

- 15 notification records exist, produced by five distinct event types:
  `supplier.supplier-registered.v1`, `settlement.finalized.v1`,
  `payment.completed.v1`, `receipt.generated.v1`,
  `collection.transaction-rejected.v1`.
- Payloads are correct — the receipt notification carries
  `{"number": "RCP-2026-000001", "amount": "5647.50", "currency": "KES"}`.
- Recipients are test numbers only (`+254700000001` and similar).
- **Every record is `status=dead` with `error: "sms delivery is disabled by
  configuration"`.** Delivery is deliberately switched off in this environment, and
  the platform dead-letters cleanly with the reason recorded rather than pretending
  to send.

So the **generation half is proven; the dispatch half is disabled by design** and
therefore untested here. See PILOT-F04.

---

## 12. Observability

| Signal | Result |
| --- | --- |
| `/health/live` | 200 |
| `/health/ready` | `status: ok`, `platform_status: healthy` |
| Readiness checks | **9 of 9 healthy** — background_workers, backups, consumers, database, jwt_keys, notifications, outbox, projections, redis |
| Backups | last successful 2026-08-10T17:56:28Z, 53 tables, 818 rows, 394,636 bytes, **`verified: true`** |
| Containers | 11 healthy (read from the host earlier in this work order) |
| nginx | serving, 301 HTTP→HTTPS, security headers present |
| Error shape | RFC-9457 problem+json throughout |

Backup and recovery tooling remains available and was **not** exercised
destructively: `infra/ci/verify-postgres.sh`, `dr-proof.sh`, `pitr-proof.sh` and
`postgres-proof.sh` are all present, and the first was run against a *local*
throwaway engine (§13), never against the live database.

**PILOT-F09 (ENVIRONMENT BLOCKED):** host-level log inspection could not be
completed. My first SSH invocation omitted `IdentitiesOnly=yes`, so the agent
offered every key it held; fail2ban is configured `maxretry = 4, bantime = 1h` and
REJECTed the source address, which is **the hardening working exactly as designed**.
This is my own operator error, not a platform defect, and it is self-clearing. The
application was unaffected throughout — the site stayed up and instance status
remained ok/ok. Container-level health was obtained instead from the platform's own
readiness and backup-status endpoints, above.

---

## 13. Tests

| Suite | Result | Status |
| --- | --- | --- |
| Backend (`pytest tests/`) | **1,101 passed, 74 skipped, 0 failed** (exit 0) | PASS |
| PostgreSQL proof (`infra/ci/verify-postgres.sh`, real engine via `pgserver`) | **PASSED** (exit 0) | PASS |
| — migrations from empty | proven | PASS |
| — RLS enabled + forced | proven | PASS |
| — RLS enforcement tests | **proven (not skipped)** | PASS |
| — logical backup + checksums | proven | PASS |
| — restore into a fresh database | proven | PASS |
| — business integrity (deep) | proven | PASS |
| — source vs restored | identical | PASS |
| Admin portal (`vitest`) | **57 passed / 6 files** | PASS |
| Docs validation | 160 files, 65 IDs, 86 capabilities — all checks passed | PASS |
| Xref freshness | `XREF.md` is current | PASS |
| Deployment smoke test (live host) | **PASSED in 5.1 s** after fixes | PASS |
| Mobile (Flutter) | not run — no mobile code was touched | NOT APPLICABLE |

The 74 backend skips are the PostgreSQL-only suites, which skip without a database
URL. Rather than let that stand as a silent green, they were **executed for real**
through the proof pipeline above, which reports "RLS enforcement tests … proven
(not skipped)".

---

## 14. Defects discovered

| ID | Finding | Classification |
| --- | --- | --- |
| PILOT-F01 | **The post-deployment smoke test's business path could never pass.** Three independent blocking defects: (a) it asserted "a settlement with no lines finalizes to zero" while the platform refuses exactly that; (b) it created a supplier and left it `draft`, which cannot be identified at a collection point; (c) it assumed an idle centre, but a centre permits only one open session. It had, on the evidence, never been run against a real deployment. | **CLOSED** (fixed, §15) |
| PILOT-F02 | A tenant-scoped user cannot log in with email + password alone; the organization UUID must be supplied. The field exists on the login page, so it is usable but unfriendly, and it is a demo trip-hazard. | MEDIUM |
| PILOT-F03 | **A collection completed after its period's settlement is finalized can never be settled.** The finalized settlement is immutable, overlapping periods are refused, `collect_period` filters candidates by `created_at`, and `adjustments_amount` is a hard-coded `Decimal("0.00")` placeholder with no API. Transaction A (1,800.00 KES) is in exactly this state and is unsettleable. | MEDIUM |
| PILOT-F04 | All 15 notifications are `dead` (`sms delivery is disabled by configuration`), yet the readiness probe reports `notifications: healthy`. Generation is proven; dispatch is untested and a demo cannot show a delivered message. | MEDIUM |
| PILOT-F05 | `/openapi.json` is served unauthenticated on the public host, disclosing all 159 API paths. `/docs` is correctly disabled. | MEDIUM |
| PILOT-F06 | Domain validation errors render as HTTP 409 with the generic detail **"The resource already exists."**; the real reason appears only in the non-standard `extra` field. E.g. an invalid `milk_type` reports "already exists". Misleading to any client that shows `detail`. | MEDIUM |
| PILOT-F07 | `collect_period` selects transactions by `created_at` (a system timestamp) rather than the business transaction date, comparing against naive datetimes. Back-dated or late-entered collections land in the wrong period. | LOW |
| PILOT-F08 | Rate-card unit prices carry `rounding_policy: "unspecified"`. The computed amount correctly uses `HALF_UP`, so nothing is wrong today, but an unspecified policy on money is a latent ambiguity. | LOW |
| PILOT-F09 | Host-level log inspection blocked by a self-inflicted fail2ban ban (operator error; hardening working as designed, self-clearing within one hour). Application unaffected. | **ENVIRONMENT BLOCKED** |
| PILOT-F10 | No `Content-Security-Policy` header on portal responses (HSTS, nosniff, frame-DENY and referrer-policy are present). | LOW |

---

## 15. Defects fixed in this work order

**PILOT-F01 — `infra/deploy/smoke-test.py`** (the only file changed).

The smoke test now exercises the chain it claims to prove:

1. It assigns the new supplier to a collection centre **and then** activates it —
   in that order, because the platform refuses to activate a supplier with nowhere
   to deliver.
2. It records a **real collection with manual measurements** (identify → milk →
   weight → quality → accept → complete) and asserts the transaction reached
   `COMPLETED` with a calculation id, so the settlement has a line to finalize.
3. It **collects** that transaction into the settlement and fails loudly if nothing
   was collected, rather than finalizing an empty settlement.
4. It **joins an already-open collection session** instead of demanding an idle
   centre, and leaves it open afterwards — closing another operator's shift is not a
   smoke test's business.

The incorrect comment claiming an empty settlement "finalizes to zero, which is a
legitimate business state" was replaced with the platform's actual rule.

**Verified by execution, not by review:** the script now passes against the live
deployment in 5.1 seconds, creating supplier `6f7b97ec…`, transaction `21927668…`,
settlement `STL-2026-000003`, payment `PAY-2026-000003` and receipt
`RCP-2026-000003`, including the consumer-generated receipt and notification steps.

No platform, infrastructure or security code was modified.

---

## 16. Defects deferred

| ID | Reason for deferral |
| --- | --- |
| PILOT-F02 | Login works today via the organization field. Fixing it properly means letting a user log in by email alone and resolving their tenant — a real design decision about cross-tenant email uniqueness, not a pilot patch. **DEFERRED.** Brief the demo operator instead. |
| PILOT-F03 | Closing this needs an adjustment or carry-forward mechanism — the `adjustments_amount` placeholder made real. That is a feature, not a fix, and it is outside a validation work order. **DEFERRED**, and recommended before any pilot with real suppliers. |
| PILOT-F04 | SMS dispatch is switched off deliberately in this environment, and the work order forbids sending real messages. **DEFERRED BY DESIGN.** The readiness probe reporting `notifications: healthy` while every record is dead is worth a separate look. |
| PILOT-F05 | A one-line change, but it touches the deployed nginx/API configuration, which the work order protects. **DEFERRED** to a deployment-config work order. |
| PILOT-F06 | The fix is in `core/errors.py`, shared by every module, and would change response bodies platform-wide. Too broad to land inside a validation work order without a full regression pass. **DEFERRED.** |
| PILOT-F07 | Changing the collection predicate alters which transactions land in which settlement — a money-affecting change needing its own tests and review. **DEFERRED.** |
| PILOT-F08, PILOT-F10 | Low severity, no present incorrect behaviour. **DEFERRED.** |
| PILOT-F09 | Self-clearing environment condition. **ENVIRONMENT BLOCKED**, no action. |

---

## 17. AWS resources touched

**None were created, resized, replaced or deleted.**

| Resource | Action |
| --- | --- |
| EC2 `i-01f37ba08fe01aa84` (c7i-flex.large) | **Read only.** Not resized, not replaced, not restarted. |
| EBS `vol-053a9611e0895f9f7` (40 GB gp3, root) | **Read only.** Capacity unchanged. |
| EBS `vol-07cedd427934137ca` (50 GB gp3, data) | **Read only.** Capacity unchanged. |
| Elastic IP 15.252.65.201 | **Untouched.** DNS unchanged. |
| EC2 Instance Connect | `send-ssh-public-key` called to attempt host access. Creates no billable resource; the pushed key is valid for 60 seconds. |
| Security groups | **Read only**, to diagnose SSH reachability. Not modified. |

Confirmed absent, as the cost-control directive requires: **no RDS, no ElastiCache,
no Amazon MQ, no ECS, no EKS, no load balancer, and no NAT gateway.** PostgreSQL,
Redis and RabbitMQ all remain inside the Docker Compose stack.

A second instance, `i-03756ce11f387b370` (`ibs-prod`, t3.small, launched
2026-07-19), and its Elastic IP 43.204.125.243 exist in this account. It is
**pre-existing and unrelated to Lacteva** — not created, touched or affected by this
work order. It is listed here only so the inventory is honest.

---

## 18. AWS cost impact

**No increase.** Daily unblended cost, 2026-08-04 through 2026-08-10:

| Date | Cost (USD) |
| --- | --- |
| 2026-08-04 … 2026-08-08 | 0.00 |
| 2026-08-09 | 0.00 (EC2-Other 0.01) |
| 2026-08-10 (this work order) | **0.00** |

The account remains within free-plan allowances. PILOT-001 created no billable
resource and generated no measurable spend. The only AWS API calls made were
read-only `describe-*` queries plus one EC2 Instance Connect key push, none of which
are billable.

---

## 19. Pilot readiness verdict

**READY FOR DEMONSTRATION. NOT YET READY FOR A PRODUCTION PILOT WITH REAL
SUPPLIERS.**

The complete business chain executes correctly through the public stack, the money
arithmetic is exact at every hop, tenant isolation is enforced in the database by a
role that cannot bypass it, immutability and idempotency hold under direct attack,
and the event-driven half of the platform demonstrably works in production. Nothing
found in this work order prevents a demonstration.

What stands between this and a real pilot is not stability — it is two capability
gaps: collections that arrive after their period closes have nowhere to go
(PILOT-F03), and notification delivery has never been exercised (PILOT-F04).

### The five questions

**1. Is the platform demo-ready?**
**Yes.** Authentication, all eighteen portal pages, collection with manual
measurements, pricing against a published rate card, settlement, payment, a real
PDF receipt and notification generation were all executed successfully against the
live deployment today. Nine of nine readiness checks are healthy and the smoke test
passes end to end in 5.1 seconds.

**2. What are the blockers?**
**There are no pilot blockers.** No finding in this work order is classified as a
PILOT BLOCKER. Two MEDIUM findings need briefing rather than fixing before a demo:
a tenant user must enter their organization UUID to sign in (PILOT-F02), and no
notification will actually be delivered because SMS dispatch is disabled
(PILOT-F04).

**3. What is the smallest change set needed?**
For the demo: **nothing more.** The one change this work order made — repairing the
smoke test — is already in place and proven by execution.

Before a pilot with real suppliers, in priority order:
1. **PILOT-F03** — an adjustment or carry-forward path, so a late collection can be
   paid. This is the only gap that can cost a real supplier real money.
2. **PILOT-F04** — enable and prove a real notification provider end to end, and
   stop readiness reporting `notifications: healthy` when every record is dead.
3. **PILOT-F05** — stop serving `/openapi.json` unauthenticated (one line).
4. **PILOT-F02** — let a user log in without knowing a UUID.

**4. What can wait?**
PILOT-F06 (validation errors mis-rendered as 409 "already exists" — cosmetic to the
business, but touches every module), PILOT-F07 (`created_at` versus business date in
period collection — no wrong behaviour observed today), PILOT-F08 (unspecified
rounding policy on the unit price, where the computed amount is correctly
`HALF_UP`), and PILOT-F10 (no CSP header). PILOT-F09 is an environment condition
that clears itself.

**5. Did AWS cost increase?**
**No.** No AWS resource was created, resized, replaced or deleted; the instance type,
both EBS volumes, the Elastic IP and DNS are all exactly as they were. Measured
daily spend for 2026-08-10 is 0.00 USD, unchanged from the preceding week, and the
account remains inside free-plan allowances.

---

## Data created during this work order

Legitimate test data only, in the existing demo tenant, all of it the by-product of
proving the flow. Nothing existing was destroyed, and no records were generated
beyond those needed for the proofs.

- 1 organization ("Isolation Probe Dairy") — required by the cross-tenant test
- 2 collection transactions (manual measurements) — 1,800.00 and 450.00 KES
- 1 settlement finalized (STL-2026-000002, 450.00 KES) and 1 payment completed
  (PAY-2026-000002) with receipt RCP-2026-000002
- 1 smoke-test run: supplier, transaction, STL-2026-000003, PAY-2026-000003,
  RCP-2026-000003

The pre-existing seeded demo data (STL-2026-000001, PAY-2026-000001,
RCP-2026-000001, supplier Amina Njoroge, centre Kilima Center) was left intact and
unmodified.

**One honest caveat:** transaction A (1,800.00 KES) cannot be settled, for the
reason described in PILOT-F03. It is left in place as evidence of that finding
rather than hidden.

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-10 | Platform Engineering | PILOT-001 executed against the live deployment; end-to-end business flow validated with manual measurements, ten findings recorded, the post-deployment smoke test repaired and proven by execution. |
