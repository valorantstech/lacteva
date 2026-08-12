---
id: DEMO-010-FINAL
title: DEMO-010 — Customer Demo Readiness & End-to-End Polish
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-13
last-updated: 2026-08-13
related: [DEMO-009-FINAL, DEMO-008-FINAL, DEMO-007-FINAL, CAP-0006, BR-REGISTER]
baseline: ARCH-BASELINE-V1
---

# DEMO-010 — Customer Demo Readiness & End-to-End Polish

Nine work orders built two halves of a dairy. This one makes them a single
product a dairy owner can be walked through without anybody explaining the
architecture.

It is deliberately not a feature module. Most of what follows is either
**making the two halves legible together**, or **fixing things that had been
quietly broken and were only findable by doing** — a seeder that could not
finish, a deployment that rolled itself back without taking a backup, and a
login screen that asked a farmer for a UUID.

**Deployed:** `main-5bad1c6` at <https://dev.phoenixsoft.in>
**AWS cost impact:** none recurring. No resource was created or resized.

---

## 1. The customer demo journey

Sign in, and the front page is the business:

```
LOGIN → DASHBOARD ─┬─ SALES:       customers → deliveries → daily report
                   │                → monthly bill → payment → receipt
                   └─ PROCUREMENT: suppliers → collections → pricing
                                    → settlement → payment → receipt
```

Every step is a real screen backed by a real endpoint. The two journeys are
verified end to end in §11; the specific claims a demonstration makes are
answered one by one in §16.

### The dashboard now shows both sides, labelled

Money flows the **opposite way** through procurement and sales, and the
dashboard used to report only procurement. Putting the sales figures into the
same undivided grid would have been worse than leaving them out: "value" above
"value" is genuinely ambiguous, and a dairy owner who reads a receivable as a
payable will mistrust the whole page.

So there are two labelled sections, and each says which direction its money
goes:

| Procurement — *milk bought from suppliers, and what the dairy owes for it* | Sales — *milk delivered to customers, and what they owe the dairy* |
| --- | --- |
| Collections, quantity, collection value | Deliveries, milk delivered, sales value |
| Average fat, active suppliers, active centres | Customer receivable, bills outstanding, delivered-not-billed |

Below them, **Who owes money** — the question a dairy owner asks first —
answered on the front page with the six largest balances and a total computed
across every debtor.

---

## 2. Who owes money

The most demo-critical question in the work order got a real report rather than
a screen that adds up rows.

`GET /v1/reports/receivables` joins invoices and payments per customer **inside
the database**, orders by the balance, and paginates. Three queries whatever
the page size. The obvious wrong implementation — list customers, call
`BillingService.balance()` for each — is correct and is N+1 against the
database for every page.

Two properties are asserted from several directions because both fail quietly:

**`total_outstanding` covers every match, never the page.** A page total is a
real number, correctly formatted, derived from real rows — and it under-reports
the debt of any dairy with more households than fit on one screen. The backend
test creates twelve debtors and a page of five and asserts the headline is the
twelve. The portal test ships a fixture whose page adds to 3,600 out of 84,300
and asserts the larger figure is what appears.

**The aggregate agrees with the parts.** `sales_summary().receivable`, the sum
of every `/customers/{id}/balance`, and `receivables().total_outstanding` are
one number, from three routes. On the deployed demo tenant: **211,961.00 KES
owed by 7 of 16 customers**, identical across all three.

### Period figures and balances are named differently on purpose

`*_in_period` is what happened between two dates. `receivable`, `invoiced` and
`received` are **balances**, as at now, and deliberately ignore the date range
— narrowing a debt to a window shows a manager less than they are owed. The
dashboard tile says so in words (`all time`), and a test asserts that asking
for one day does not shrink the debt.

---

## 3. The demo tenant

`Lacteva Demo Cooperative`, rebuilt deterministically. **16 customers** (was
six — six households is a fixture, not a dairy), 24 suppliers, 5 collection
centres, 30 days of both rounds.

| | |
| --- | --- |
| Customers | 16 — households, shops, hotels, a school, a hospital, distributors |
| Deliveries | 570 over 30 days, three customers taking a second evening round |
| Bills | 14 issued; 11 payments; 11 receipts |
| Suppliers / centres | 24 / 5 |
| Collections | 351 completed, priced through three fat bands |
| Settlements | 52 (49 finalized, 3 deliberately left open) |
| Supplier payments / receipts | 25 / 21 |

The settlement state is written on each roster row rather than derived from an
index, so the seeded ledger can be read in the source and matched against the
screen: **7 paid, 4 part paid, 3 unpaid, 2 delivered-but-unbilled**. A dairy
whose customers are all settled cannot demonstrate a collection round.

Five accounts, one per role (§5), and `DEMO_PASSWORD` overrides the default.

**What was preserved.** The purge is keyed on the two Lacteva demo tenant ids
and touched nothing else: `Phoenix Demo Dairy` and `Isolation Probe Dairy` are
untouched, and a pre-deployment backup was taken minutes before (§9). The
rebuild also removed the one artefact DEMO-008 left behind — a settlement its
permission probe finalized by accident.

**A judgement call, stated plainly.** Rebuilding the demo tenant deletes and
regenerates its financial records. They are seeded, deterministic and
reproducible — not a record of real business — and rebuilding was the only way
to satisfy "remove confusing artefacts from the demo tenant". Record identifiers
quoted in DEMO-006 through DEMO-009 no longer resolve. Nothing outside the two
demo organizations was affected.

---

## 4. Signing in

**The first screen of the demonstration asked a dairy owner to paste
"Organization ID (tenant)" — a raw UUID — into a text box.**

It was there for a real reason: `get_by_email` matched on `(email, tenant_id)`,
so a member of an organization was invisible without their organization's id.
Nobody knows their tenant UUID.

The tenant is now resolved from the credentials. The password is verified
against each candidate account and the answer follows from how many verified:

- **none** — `invalid_credentials`, byte for byte what an unknown address gets.
  Asking reveals nothing.
- **one** — sign in as that account. Every real case.
- **more than one** — the same password really does open accounts in several
  organizations, and only then is the caller asked which. They have already
  proven the password, so naming the organizations reveals nothing that trying
  each in turn would not have.

The cross-tenant read this needs is the only one in the authentication path:
narrow, deliberate, logged through `bind_platform_context`, and bounded at five
candidates so one request cannot be made expensive.

**What did not loosen** has ten tests of its own — the issued token is scoped
to that user's own tenant and never platform-level, an inactive account is
still refused, naming a tenant you do not belong to is still refused, a
resolved session still cannot read another organization's rows, and a failed
sign-in never names an organization.

`test_invitation_is_single_use_and_tenant_isolated` asserted the old ergonomics
("platform-level login fails"). It now asserts the stronger property that
replaced it — the resolved token is scoped to that tenant — rather than being
deleted.

The portal drops the field entirely and shows it only on `ambiguous_tenant`,
and signing in now lands on the dashboard rather than the centres list.

---

## 5. Roles, verified against the deployed platform

Five accounts, five roles from DEMO-008's registry, seeded as real members.
Nothing is special-cased anywhere: they are rows.

| Account | Role | Permissions |
| --- | --- | --- |
| `manager@…` | tenant-admin (organization administrator) | 51 |
| `operations@…` | `ORGANIZATION_MANAGER` | 24 |
| `sales@…` | `SALES_OFFICER` | 10 |
| `viewer@…` | tenant-viewer (read-only) | 23 |
| `operator@…` | `COLLECTION_OPERATOR` | 6 |

**78 checks, all passing**, run against <https://dev.phoenixsoft.in>. The
matrix is the interesting part — it is genuinely role-driven:

| | suppliers | customers | deliveries | invoices | settlements | payments | reports | audit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tenant-admin | 200 | 200 | 200 | 200 | 200 | 200 | 200 | 200 |
| ORGANIZATION_MANAGER | 200 | 200 | 200 | 200 | 200 | 200 | 200 | **403** |
| SALES_OFFICER | **403** | 200 | 200 | 200 | **403** | **403** | 200 | **403** |
| tenant-viewer | 200 | 200 | 200 | 200 | 200 | 200 | 200 | 200 |
| COLLECTION_OPERATOR | 200 | **403** | **403** | **403** | **403** | **403** | **403** | **403** |

A sales officer cannot see suppliers or settlements. A collection operator sees
suppliers and nothing else. Neither is hidden only in the navigation — these
are the API's answers.

### Nothing was consumed to prove a refusal

Every write the probe attempts is aimed at an id that **cannot exist**, so a
role that is permitted gets `404` and a role that is not gets `403` — the exact
distinction under test, without creating, issuing, paying or finalizing
anything. `ORGANIZATION_MANAGER` was refused all five: `settlement.finalize`,
`payment.manage`, `sales.invoice.issue`, `sales.customer.manage`,
`sales.payment.record`.

This is the direct lesson of DEMO-008, where a permission probe finalized a
real settlement.

---

## 6. Tenant isolation

- The demo manager sees **16** customers; the other organization's manager sees
  **none of them**.
- Fetching one of them by id answers **404, not 403** — 403 would confirm the
  row exists.
- **`X-Tenant-ID` is ignored for a tenant-scoped token.** Asserting the other
  organization's id returns the caller's own 24 suppliers, not the other
  organization's 3. The header is the platform-admin bootstrap path; a member's
  token decides their tenant.
- No token → 401. A token that is not a token → 401. Right user, wrong password
  → 401.
- The login rate limiter (10/minute) refused the probe when it ran twice in a
  minute. That is the control working; the probe now paces itself.

At the database level, on the deployed PostgreSQL: **every tenant-owned table
has a policy, and every one of them is FORCED** — checks 13 and 14 in §7.

---

## 7. Financial reconciliation

Fifteen queries against the deployed database, each re-deriving a figure the
product displays from the rows underneath it. **All fifteen return zero rows.**

| # | Check | Rows |
| --- | --- | --- |
| 1 | delivery amount ≠ quantity × rate | 0 |
| 2 | a non-delivered delivery worth money | 0 |
| 3 | invoice subtotal ≠ sum of its lines | 0 |
| 4 | amount due ≠ total + brought forward | 0 |
| 5 | an invoice line that is not a copy of its delivery | 0 |
| 6 | the same delivery billed twice | 0 |
| 7 | a billed delivery not stamped with its invoice | 0 |
| 8 | receipt amount ≠ its payment | 0 |
| 9 | a recorded payment with no receipt | 0 |
| 10 | allocations exceeding their payment | 0 |
| 11 | a customer whose balance is negative | 0 |
| 12 | settlement gross ≠ sum of its lines | 0 |
| 13 | a tenant-owned table with no RLS policy | 0 |
| 14 | a tenant-owned table whose RLS is not FORCED | 0 |
| 15 | a sales row referencing another tenant's parent | 0 |

The seeder's own `verify` reports **0 problems** across 16 customers, 570
deliveries, 14 invoices, 11 payments, 11 receipts, 351 collections and 52
settlements.

---

## 8. Host stability — builds moved off the serving machine

DEMO-009 could not build the portal image on the production host, and the disk
reached 100% twice in a week. Both are one mistake: a 2 vCPU / 4 GB instance
doing a compiler's job and a server's job at the same time.

```
git → GitHub Actions → docker build → ECR → the EC2 pulls
```

`.github/workflows/images.yml` builds both images on a GitHub runner and pushes
them to the two ECR repositories that already existed. The host only pulls.
**Verified working**: `main-5bad1c6` was built by CI and is what is serving.

**No AWS key is stored in GitHub.** The runner exchanges its OIDC token for a
session on `lacteva-github-actions-ecr`, restricted to this repository's
branches and tags — never a pull request, which must not be able to publish an
image, and which matters because this repository is public.

### The subject to trust is not the documented one

`AssumeRoleWithWebIdentity` was refused three times. Job logs need admin rights
on the repository, so the diagnostic step printing the subject was useless.
**CloudTrail answered it** — a refused attempt records the offered subject in
`userIdentity.principalId`:

```
repo:valorantstech@164855793/lacteva@1319582534:ref:refs/heads/main
```

This organization has GitHub's immutable identifiers enabled, so the subject
carries numeric owner and repository IDs rather than the documented
`repo:owner/name:ref:…`. The trust policy matches that form **exactly** rather
than being loosened to a wildcard on the name: the IDs are the stronger
identifier, because a repository deleted and recreated under the same name gets
new ones and cannot inherit this role's access.

### The disk guard

`infra/deploy/disk-guard.sh`, every six hours, 01:45 deliberately before the
02:15 backup — a backup that fails for want of space is how a bad night becomes
an unrecoverable one.

It does nothing below 75%. Above it, it reclaims in order of least regret and
stops at 60% rather than churning the cache to nothing:

1. build cache (pure recomputable waste, and the largest consumer)
2. dangling images
3. stopped containers
4. release directories beyond the newest three, never the current one
5. tagged images older than seven days
6. the journal, above 200 MB

It is a guard, not a scheduled `prune -a`: that would delete the previous
release's image, which is exactly what `deploy.sh --rollback` needs at 3am.
Still above 90% after everything safe has been tried is a non-zero exit — a
real alert, not a cleanup job.

**First run on the host: 86% → 54%**, 18 GB free, the current release and the
rollback target both intact.

Alongside it: container log retention dropped from 50 MB × 5 to 20 MB × 3 —
3.25 GB of standing entitlement across thirteen services down to 780 MB, losing
nothing, because promtail ships every line to Loki as it is written. And an ECR
lifecycle policy keeping the 15 most recent images per repository.

---

## 9. Defects found

Eleven, every one found by executing rather than reading.

### The demo seeder could not finish

1. **A settlement period collision aborted every run.** `demonstrate_br_0027`
   settled `today-7 … today-7` for supplier 0, who is also one of three
   suppliers deliberately left holding an open settlement over
   `today-7 … today-1`. The platform correctly refused the overlap and the
   whole seed died — on any day, on every run.
2. **The admin's access token expired mid-run.** Sixteen customers and ~570
   deliveries push the seed past fifteen minutes, so building the second
   organization failed with a bare 401 after twenty minutes of correct work.
   Both the admin and the tenant manager now re-authenticate in place.
3. **A refused delivery was silently not counted.** `if status == 201` meant a
   run where every delivery failed still reported success with a smaller number
   nobody would question.

### A healthy deployment rolled itself back, without a backup

4. **The pre-deployment backup silently did not happen.** `COMPOSE_FILE` was a
   bare filename, so every compose call before step 3 depended on the caller's
   working directory — and `cd "${CURRENT}"` is *in* step 3. Running the script
   by absolute path made `compose ps` fail, which the check read as "no API is
   running" and announced as

   > no running API (first deployment) — skipping pre-deployment backup

   on a platform serving every request. The one thing that makes an
   unrecoverable migration recoverable was quietly absent, in a line that reads
   like a decision. "Compose could not run at all" is now a third outcome that
   stops the deploy.
5. **The verifier and the smoke test failed against a working platform.** Both
   default to `http://localhost`; nginx correctly answers 301 to HTTPS, the
   redirect is followed to `https://localhost`, and the certificate is for the
   real hostname. Both declared the deployment broken, the automatic rollback
   ran, failed the same way, and reported an incident. AWS-001 fixed the
   redirect and left the hostname. `LACTEVA_PUBLIC_URL` now points both at what
   a browser types.
6. **ECR credentials on the host expired into a failed deploy.** A static
   twelve-hour token in `config.json` with nothing to refresh it. The
   credential helper is now installed and the instance role carries a
   pull-only policy for the two Lacteva repositories.
7. **The seeder was documented at a path that has never existed.** The image
   holds the application, not the repository, so `/app/infra/demo/seed_demo.py`
   is not there.

### The demo journey

8. **The login screen asked for a tenant UUID** (§4).
9. **The dashboard's links did not arrive filtered.** `/billing` and
   `/deliveries` ignored their query strings, so "54 deliveries made but not
   yet billed → review" landed on the unfiltered list — which reads, in front
   of a customer, as a filter that does not work.
10. **Four different timestamp formats.** Most pages sliced sixteen characters,
    two sliced nineteen, and Operations used `toLocaleString`, which renders in
    the viewer's locale — the same instant read `2026-08-12 09:30` on one
    screen and `8/12/2026, 9:30:00 AM` on the next.

### Pre-existing, and not caused by this work order

11. **The disaster-recovery proofs had not run in CI for at least five
    commits.** Both jobs failed at `astral-sh/setup-uv`, before a single line
    of the proof executed: the action has no dependency file at the repository
    root to key its cache on, and without an explicit `cache-dependency-glob`
    it errors rather than skipping the cache. The DR and PITR proofs exist
    because DR-001 found that recovery did not work at all. `postgres.yml`
    already passed the glob and has been green throughout, which is what made
    the difference findable.

### One defect I introduced and caught

`base.subquery()` called twice in `receivables()` builds two derived tables and
joins them — a cartesian product reporting the **square** of the customer
count. Found while writing the query; the test asserts 12 rather than 144.

---

## 10. Performance

- **No duplicate requests.** DEMO-007's regression (a differently-shaped tree
  while the session probe was in flight, remounting every page) has a mount-
  counting test, and the new `/receivables` page has its own.
- **Nothing is aggregated in the browser.** Every total on every screen is the
  platform's. `receivables` is three queries; `sales_summary` is six; the
  dashboard composes existing aggregates rather than re-implementing them.
- **Every list is paginated and every filter is a query parameter.** The
  receivables page asks for `limit=25` and pages by `offset`; a test asserts
  twelve debtors are paged without repeating or dropping one.
- **No unbounded list.** `receivables` caps at 100 per page; the login
  candidate scan caps at five.

---

## 11. Verification

### The demo journey, through the portal

**59/59 checks passed** against <https://dev.phoenixsoft.in>, signing in at
`/api/auth/login` and making every call through `/api/proxy/…` — the same BFF
and the same HttpOnly cookie a browser uses.

Sixteen pages return 200. Both workflows reconcile end to end:

```
sales        Wanjala Distributors → 60 deliveries → 30.000 × 52.0000 = 1,560.00
             → INV-2026-000005, 54 lines, 126,360.00 due, totals_match_lines ✓
             → balance: invoiced 126,360.00 − paid 0.00 = 126,360.00 ✓
procurement  12.0 kg at 4.6% fat → 45.5000 → 546.00
             → STL-2026-000052 → PAY-2026-000025 → RCP-2026-000021
             → receipt 1,176.00 = settlement net 1,176.00 ✓
```

All five "needs attention" links arrive at a filtered page.

### Real Chrome — not done, and not claimed

**The Chrome extension was not connected for the duration of this work order**
(`list_connected_browsers` returned empty; repeated attempts failed). DEMO-009's
24/24 browser verification was performed earlier in the same day, so this is an
environment change rather than a product change.

What §11 above proves is that every page in the journey serves, and that every
figure a screen will render is correct and mutually consistent, through the
browser's own session path. What it does **not** prove is layout, styling,
client-side rendering or interaction. Those claims are not made here. This is
the first item of §14.

### Tests

```
backend      1,314 tests — 1,240 passed, 74 skipped (PostgreSQL-only), 0 failed
portal         195 tests — 195 passed (15 files)
ruff check + ruff format --check      clean (227 files)
eslint src --max-warnings 0           clean
tsc --noEmit                          clean
npm run build                         clean
validate_docs.py                      172 files, all checks passed
```

New this work order: 14 backend tests for the sales aggregates, 10 for
tenant-resolving login, 9 for the receivables page, 4 for the login form,
3 for deep links, 3 for the dashboard's two sides.

**No test was weakened.** Two changed, both to assert something stronger:
`test_invitation_is_single_use_and_tenant_isolated` (§4), and
`test_every_lacteva_variable_in_the_example_is_a_real_setting`, which gained a
`deploy_only` category that must itself be justified — the test now asserts
that something under `infra/` actually reads the variable.

---

## 12. AWS changes and cost

**No resource was created, resized or deleted. No recurring cost was added.**

| Change | What | Recurring cost |
| --- | --- | --- |
| IAM OIDC provider | `token.actions.githubusercontent.com` | **$0** — free |
| IAM role | `lacteva-github-actions-ecr`, push to two repositories only, branches and tags only | **$0** — free |
| IAM inline policy | pull-only ECR on the existing `lacteva-ssm-role` | **$0** — free |
| ECR lifecycle policy | keep the 15 most recent images per repository | **$0** — reduces storage |
| GitHub Actions | both image builds | **$0** — GitHub's runners |
| ECR storage | two images per release, capped at 15 | ~**$0.15/month**, and lower than before the lifecycle policy |
| ECR → EC2 transfer | pulls | **$0** — same region |

The EC2 instance is unchanged: still `c7i-flex.large`, still running
PostgreSQL, Redis and RabbitMQ under Docker Compose. Nothing was resized, and
`vm.overcommit_memory=2` was not weakened — that hardening exists so the
database is never the process the OOM killer chooses.

Installed on the host (apt, no cost): `amazon-ecr-credential-helper`.

---

## 13. Documentation

- `DEPLOYMENT.md` §3 — where images are built, and why not here.
- `INFRASTRUCTURE.md` §7 — the disk guard and the build cadence.
- `infra/README.md` — the OIDC subject this organization presents, and the
  CloudTrail query that reveals it.
- `infra/demo/README.md` — the `docker cp` the seeder actually requires.
- `.env.production.example` — `LACTEVA_PUBLIC_URL`, with the failure it
  prevents.
- `CHANGELOG.md` — the increment.

---

## 14. Known limitations

1. **No rendering-engine verification.** §11 states exactly what was and was
   not checked. Re-run the browser pass when the extension reconnects.
2. **No automated backups on this host.** `lacteva-backup-nightly.timer`,
   `-verify` and `-weekly` exist in `infra/systemd/` and are **not installed**
   on the deployment. Backups happen only as a side effect of `deploy.sh`. This
   was found while looking for a safety net before rebuilding the demo tenant.
   It is the highest-priority item in §15 and is not fixed here.
3. **The ambiguous-login picker takes a UUID.** When one password opens
   accounts in two organizations the portal asks for an organization id rather
   than offering a list. It is correct and rare; a list needs an endpoint that
   returns the organizations for an already-authenticated principal.
4. **Adjustments are still fixed at zero** (BR-0011, unchanged from DEMO-009).
5. **The demo tenant is single-currency.** Every figure is KES. The platform
   handles more; the demonstration does not exercise it.
6. **Timestamps are UTC everywhere**, deliberately — parsing and re-rendering
   in the browser's timezone would disagree with the audit trail and the
   receipt. A dairy operating away from UTC will want a per-organization
   display timezone.
7. **`docker compose` remains the runtime.** One host, no failover.

---

## 15. Recommended next

1. **Install the backup timers.** Highest priority by a distance. The engine,
   the verification and the units all exist; nothing runs them. A platform that
   moves money and cannot restore itself is one bad night from an incident with
   no floor. Then run `dr-proof.sh` against the real deployment now that CI can
   execute it again.
2. **Bulk month-end billing.** A hundred households at one API call each is the
   first thing a real dairy hits. `generate_invoice` is per-customer by design;
   a batch endpoint over a period, reporting per-customer outcomes, is the
   natural next increment.
3. **Customer statements as documents.** The bill reconciles on screen; a dairy
   hands a household a piece of paper. Receipts have the same gap.
4. **SMS on delivery and on bill issue.** The notification module and the
   recipient directory already exist; the sales events do not use them.
5. **A per-organization display timezone** (§14.6).
6. **Mobile applications** — DEMO-011 on the roadmap.

---

## 16. The thirty-minute test

Could I sit with a real dairy owner and demonstrate each of these?

| # | Question | Where | ✓ |
| --- | --- | --- | --- |
| 1 | How are suppliers managed? | `/suppliers` — 24, searchable, with profiles | ✓ |
| 2 | How is milk collected? | `/transactions`, and `/transactions/new` walks the capture | ✓ |
| 3 | How does quality affect pricing? | `/rate-cards`, `/matrices`, `/resolve` — three fat bands, 42.00/45.50/49.00 | ✓ |
| 4 | How are suppliers settled? | `/settlements` — 52, three left open to finalize live | ✓ |
| 5 | How are suppliers paid? | `/payments` — 25, including a failed one to retry | ✓ |
| 6 | How are customers managed? | `/customers` — 16, each with an agreed rate | ✓ |
| 7 | How is a delivery recorded? | Customer page — quantity only; the rate is the platform's | ✓ |
| 8 | Today's delivery report? | `/deliveries` — aggregated in SQL, per-day breakdown | ✓ |
| 9 | How does monthly billing work? | Customer page → bill → `/invoices/{id}`, reconciled | ✓ |
| 10 | How are customer payments recorded? | Customer page → payment, allocated oldest-first | ✓ |
| 11 | How are receipts generated? | By a consumer from the payment event, never by hand | ✓ |
| 12 | How does management see the business? | `/` — both sides, labelled, and who owes money | ✓ |
| 13 | How do users differ by permission? | Sign in as five accounts; §5's matrix is what they get | ✓ |
| 14 | How is one customer's data isolated? | Sign in as the second organization; §6 | ✓ |

Fourteen of fourteen, each demonstrable on the deployed platform with the
seeded data.

---

## Change Log

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-08-13 | DEMO-010 complete: both sides on one dashboard, receivables, a 16-customer demo tenant, login without a UUID, builds moved off the serving host, a disk guard, and eleven defects fixed. |
