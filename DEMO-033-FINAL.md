---
id: DEMO-033-FINAL
title: DEMO-033 — WhatsApp Template Variants & Template Approval Lifecycle
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-17
last-updated: 2026-08-17
related: [DEMO-032-FINAL, DEMO-031-FINAL, DEMO-029-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-033 — WhatsApp Template Variants & Template Approval Lifecycle

DEMO-032 found that Lacteva's WhatsApp templates **could not be WhatsApp
templates**. This milestone fixes that, and adds the lifecycle that records what
a provider decided about each one. **No vendor was selected, contacted or
credentialed; no template was submitted anywhere; no real message was sent.**

---

## 1. What already existed

`modules/notification/templates.py` — **41 templates** across four languages
(`en`, `hi`, `ar`, `sw`) and three channels, each with a key, title, body,
declared variable order and, since DEMO-028, `[[optional segments]]`. Around it:
`get_template`, `render`, `catalog`, `languages_for`, `variables_for`,
`vendor_template_for()` (DEMO-031, reads deployment configuration), and DEMO-032's
registry view with `purpose` / `version` / `active` / `provider_mapping_status`.

Reused unchanged: channels, the provider port and registry, dispatch and retry,
delivery state, DEMO-029's webhook signature verification, tenant channel
configuration, reachability, and both business journeys — farmer settlement and
customer invoice.

**The optional segment lived in exactly one place** (§1's survey question): the
template *body*, as `[[…]]` markers, expanded or removed by `render()` according
to whether the variable was supplied. Nothing else in the platform modelled
optionality — not the dispatch path, not the registry, not the provider port.
That single location is why the fix could be contained.

## 2. The DEMO-032 finding

> A WhatsApp template message has a **fixed** parameter count, registered in
> advance and approved by the provider. Lacteva's `settlement_finalized` body
> carried an optional quantity segment, so the same template rendered with two
> parameters for one farmer and four for the next. Registered as a template, it
> would have been rejected — or worse, approved at one shape and then sent at
> another.

DEMO-032 reported this honestly and did not paper over it: the registry showed
**8 WhatsApp templates that could not be approved templates**, and the portal
said so in plain words.

## 3. The WhatsApp template problem, precisely

Three properties collide:

1. **WhatsApp** requires a template registered with a **fixed positional
   parameter list** — `{{1}}, {{2}}, …` — approved before any send.
2. **SMS and email** have no such requirement and never did. Their flexible
   rendering is a genuine product feature: a farmer whose settlement has no
   quantity data gets a shorter, truthful message rather than a blank field.
3. **The same business journey** feeds all three channels from one template key.

So the conflict is real and cannot be resolved by choosing a side.

## 4. Decision and rationale

Per §2's decision rules — all three preserved:

* **Not** "force every message to include every optional field." A farmer whose
  settlement genuinely has no quantity would receive an invented or blank number.
* **Not** "remove optional fields from SMS/email." That deletes a working
  feature to satisfy a channel that is not yet live.
* **Not** "change existing business meaning." No message says anything new.

**The decision:** *optionality is a channel property, not a message property.*
SMS and email keep flexible rendering, unchanged. WhatsApp gets **explicit
fixed-parameter variants** — one separate template per shape the business
actually produces — and dispatch chooses among them from the data it already has.

This is the only option that leaves both channels honest. It costs more
templates; that cost is real and is paid in §17.

## 5. Template variants

`FIXED_PARAMETER_CHANNELS = ("whatsapp",)`. Two journeys reach WhatsApp with
optional data, so two journeys have variants:

| Journey | Optional groups | Variants |
| --- | --- | --- |
| `settlement_finalized` | quantity | `_base`, `_with_quantity` |
| `invoice_issued` | quantity, balance | `_base`, `_with_quantity`, `_with_balance`, `_with_quantity_and_balance` |

Six variant keys × four languages = **24 WhatsApp templates**; the registry now
holds **57** in total. Per §3, these are the combinations the *existing journeys
actually emit* — the settlement journey never carries a previous balance, so
`settlement_finalized_with_balance` was not created. No mathematical
completeness for its own sake.

Optionality is grouped, because parameters that travel together must appear
together:

```python
VARIANT_GROUPS = {
    "quantity": ("quantity", "quantity_unit"),   # a number without its unit is not a fact
    "balance":  ("previous_balance",),
}
```

**The variant bodies were not written.** Each was produced mechanically from the
already-reviewed WhatsApp body by inlining or deleting the `[[…]]` segment. The
Hindi, Arabic and Swahili wording a farmer reads is the wording that was
reviewed for DEMO-028 — no translation was invented here.

## 6. Parameter model

A fixed-parameter template declares its parameters in order and has **no**
optional segments. `assert_fixed_parameters(template, variables)` enforces the
exact contract §5 asks for, and refuses in all three directions:

* an **unknown** parameter → refused (not silently dropped);
* a **missing** declared parameter → refused (not silently invented);
* a **remaining optional** parameter on a fixed-parameter channel → refused,
  because it means variant selection picked the wrong template.

`fixed_parameters(template, variables)` then returns the values as an ordered
tuple — `{{1}} … {{n}}` in the template's own declared order — and that tuple is
what `OutboundMessage.parameters` carries to a provider.

A guard is only a guard if it can refuse. Each of these was mutation-tested:
disabling the unknown-parameter check fails 9 tests, the missing-parameter check
1, the optional-remaining check 4, and the ordering guarantee 2.

## 7. Template selection

```python
select_template_key(key, channel, variables) -> str
```

Lives in `templates.py`, the domain layer. Given the journey key, the channel
and the variables the journey already computed, it returns the key to render:
the journey key unchanged for SMS and email, and the matching variant for a
fixed-parameter channel. Selection is by `present_groups(variables)` — a
`frozenset` of which optional groups have data — looked up in `VARIANTS`.

**No vendor identifier participates.** §4's requirement is met structurally: the
function's inputs are a business key, a channel name and business data, and
`grep` for a provider name in the selection path returns nothing. Vendor template
names enter only at the edge, in `OutboundMessage.vendor_template`, read from
deployment configuration.

An unregistered combination raises rather than falling back — a fallback here
would send the wrong shape to an approved template.

## 8. Approval lifecycle

`NotificationTemplateApproval` records **PENDING / APPROVED / REJECTED** for a
`(template_key, channel, language, provider)` combination, unique on exactly that
tuple.

The absence of a row is a fourth, distinct state: **`NOT_CONFIGURED`**. It is not
a judgement — nothing has been submitted and nothing is claimed. This is why §9's
"existing production templates must NOT automatically become APPROVED" holds by
construction: the migration creates an **empty** table and backfills nothing. All
57 templates read `NOT_CONFIGURED` on every deployment today.

**The lifecycle does not pretend Lacteva approves anything** (§7). Every label
names the decider: the portal reads "approved by provider", never "approved";
`record_approval` requires a `provider`; and the API is `POST
/v1/notification-templates/approval` — *record*, not *approve*.

Recording is guarded by a new permission, `notification.template.approve`, held
by `platform-admin` through its wildcard and by **no tenant role**. A dairy
cannot record an approval against Lacteva's messaging account.

Every transition writes an audit entry, `notification.template_approval_recorded`,
carrying previous state, new state, actor, timestamp, provider, provider template
id and note — §9's full list. A rejection reason is the thing an operator has to
act on, so it is stored verbatim.

## 9. Provider mapping

Mapping is separate from business identity, as §8 requires:

* **Business identity** is the template key — `settlement_finalized_with_quantity`.
* **Provider identity** is `provider_template_id`, the vendor's own name for it,
  which also arrives via `notification_vendor_templates` deployment configuration.

`provider_template_id` is a name, not a credential. The model holds **no** API
key, token, secret or account identifier, and a test asserts that no field name
or value in the approval model or registry response matches a credential shape.

## 10. Readiness

Per §11, a WhatsApp template is READY only when **all four** hold:

1. the structure is valid (positional parameters, no optional segments);
2. the language is supported;
3. approval state is `APPROVED`;
4. a provider template mapping exists.

Anything else is `ready = False` with `blockers` listing **every** failing
reason, not the first — an operator who fixes one blocker and discovers another
was told half the truth.

`ready_whatsapp` is **0** on every deployment today, and that is the honest
number: nothing has been submitted to any provider.

## 11. Portal

The existing registry panel was extended, not replaced (§10). It now shows, per
template: the **fixed parameter structure** as `{{1}} number {{2}} name …` in
declared order; the **approval state** in provider-attributed words with the
provider's name; the **provider mapping**; and **readiness**, with every blocker
listed. SMS and email rows show `—` in the approval and readiness columns —
adding a lifecycle column to a channel that has no lifecycle would be a claim.

A header badge reports `N WhatsApp ready to send`, currently `0`.

Three portal mutations were run and each is caught by exactly one test: reporting
only the first blocker, labelling approval "approved by Lacteva", and dropping
the positional numbering.

No credential appears on the page, and a test scans the rendered DOM for
credential-shaped strings to keep it that way.

## 12. Security and RLS

`notification_template_approval` is declared **PLATFORM_GLOBAL** in `core/rls.py`
with a written reason: the messaging account a template is approved against is
Lacteva's, not a dairy's. Five dairies separately tracking the same external
decision about the same account would leave four of them wrong. §13's ownership
question was answered deliberately, and the existing model was not changed —
templates were process-wide before and remain so.

Proven (§14):

* an unauthenticated approval attempt is **401**;
* an authenticated tenant user without the permission is **403**;
* no tenant role holds `notification.template.approve`;
* templates remain unmodifiable through the API — the registry and preview
  endpoints write nothing, asserted by a no-write test that exempts only
  `/preview` and `/approval`;
* two tenants read the identical platform-global registry, and neither can alter
  the other's messaging configuration;
* cross-tenant resource access remains **404**, never 403.

## 13. PostgreSQL proof

`tests/test_template_variants_postgres.py` covers all sixteen items §15 lists —
fixed parameter count and order, missing and unknown parameter rejection, variant
selection, SMS and email regression, the three states, transitions, audit,
provider mapping, readiness, tenant isolation, and concurrent approval recording
leaving exactly one coherent row.

It is wired into `infra/ci/postgres-proof.sh`'s explicit file list, so it runs in
the pipeline rather than existing beside it.

```
./infra/ci/verify-postgres.sh   →   215 passed
                                    POSTGRESQL PROOF PASSED
```

(199 before this milestone.) Real PostgreSQL, from the `pgserver` wheel, with no
Docker and no root.

## 13a. What running the full suite found — three defects DEMO-031 left behind

Running the complete backend suite to the end, rather than trusting a prior
"green", found three problems that were **already in `HEAD`** and had nothing to
do with this milestone's feature work. All three are the same lesson the
repository already states: a guarantee that is not executed is not a guarantee.

**1. Thirty-three delivery tests had been failing since DEMO-031.** Commit
`206e4d6` added the messaging-mode gate to the real SMS, email and push adapters
and did not update `test_sms_delivery.py`, `test_email_delivery.py` or
`test_push_devices.py`. Every test in those three files died on
`MessagingModeError` before reaching its subject. So the **production SMS, email
and push adapters were untested for two milestones** — retry classification,
stable idempotency keys, credential redaction, segment reporting, all of it.

*Fixed by making those tests opt into `sandbox` explicitly, out loud, the way a
sandbox deployment does — not by weakening the gate.* The gate was
mutation-checked afterwards: disabling it fails
`test_a_real_gateway_refuses_to_reach_the_network_in_test_mode`, so the refusal
is still proven.

One of the thirty-three deserves its own line.
`test_an_unconfigured_host_fails_permanently_rather_than_pretending` was
asserting the **mode gate**, not the missing SMTP host — both refusals are
permanent and their messages look alike, so the test passed for the wrong reason
right up until the gate started firing first. It now opts in before asserting,
and tests what its name claims.

**2. A lint violation the ruff cache was hiding.** `RUF012` on
`providers.py:371`, present at `HEAD`, invisible to a warm cache and fatal in
CI. Confirmed by linting `HEAD`'s own bytes through `--no-cache`. Fixed with a
`ClassVar` annotation. **`ruff check --no-cache` is the honest invocation**; the
cached one can report a clean tree that CI will reject.

**3. Stale pytest bytecode from a workspace that no longer exists.** Thirty-three
`__pycache__` directories held assertion-rewritten code objects whose
`co_filename` pointed at `/mnt/data/workspace_lacteva/...`, which is why the
first tracebacks printed `???` instead of source lines. Cleared.

Two further failures *were* this milestone's, and are recorded honestly here
rather than quietly fixed: the approval error message contained the fragment
`" in "`, which DEMO-031's vendor-name boundary test correctly reads as the
country code `in` — reworded rather than loosening the test; and
`test_no_endpoint_can_modify_a_template` needed `/approval` exempted alongside
`/preview`, an edit that had been lost when a multi-replacement script rolled
back mid-way and which was believed to have landed.

## 14. Production verification

Deployed `main-5afcd47` to **https://dev.phoenixsoft.in** through the existing
path. **The schema moved** — the deploy said so explicitly and printed the
rollback caveat — and landed on `a7c3e21f9b64`, matching the image. A
pre-deployment backup was taken first: `pre-demo033-20260816T184328Z.dump`,
3.1 MB.

Deploy checks, all green: PostgreSQL accepting connections, schema matching the
image, **every tenant-owned table has a policy**, **policies are FORCED**, the
API role `lacteva_app` is `NOSUPERUSER`/`NOBYPASSRLS`, the API and schema owner
are different roles, Redis responding, projections healthy, nginx serving, smoke
test passed.

**The registry on production:**

```
total 57  |  whatsapp 24  |  unmapped 24  |  ready 0
optional segments on whatsapp: 0
approval states: ['NOT_CONFIGURED']
languages: ['ar', 'en', 'hi', 'sw']
```

**The DEMO-032 finding is gone from production, not merely from a test.** Zero
WhatsApp templates carry an optional segment, where 8 of 8 could not be approved
templates before. `ready = 0` and every state `NOT_CONFIGURED`, which is the
honest reading: nothing has been submitted to any provider.

**Variant selection, live:**

```
select no-quantity   -> settlement_finalized_base
select with-quantity -> settlement_finalized_with_quantity
select on sms        -> settlement_finalized          (identity — unchanged)
```

**SMS and email regression, live** (§6): SMS omits the quantity segment when
absent, shows it when present, and is shorter without it. Email omits all three
optional variables when absent and renders them when present. Both channels
behave exactly as they did before this milestone.

**Refusals, live:** an unknown parameter and a missing parameter are each
refused with `TemplateRenderError` on the deployed code.

| Check | Result |
|---|---|
| `/health/live`, `/health/ready` | **200** |
| `GET /v1/notification-templates/registry` unauthenticated | **401** |
| `POST /v1/notification-templates/approval` unauthenticated | **401** |
| Writable template endpoints in the live schema | only `/preview` and `/approval` |
| Rows in `notification_template_approval` | **0** — nothing backfilled, nothing fabricated |
| RLS on that table | `f/f` — platform-global, deliberately |
| Tenant-owned tables without a policy | **0** |
| `messaging_mode` | `test` |
| Vendor templates configured | **0** |
| Notifications created in the last 2 hours | **0** |

**Financial safety, before and after the deploy — identical in every figure:**

| Table | Count | Sum |
| --- | --- | --- |
| `settlement` | 84 → 84 | 353,417.50 → 353,417.50 |
| `customer_invoice` | 31 → 31 | 809,038.00 → 809,038.00 |
| `customer_payment` | 24 → 24 | 444,105.00 → 444,105.00 |
| `customer_receipt` | 24 → 24 | 444,105.00 → 444,105.00 |
| `payment` | 42 → 42 | 168,675.50 → 168,675.50 |
| `receipt` | 36 → 36 | 138,903.00 → 138,903.00 |

**No external provider was contacted, no credential exists, and no real message
was sent.**

### The verification found one more defect — in this milestone's own code

Reading the live positional list showed:

```
fixed_parameters(template, partial_variables)
  -> ('S-1', 'Grace', '', '', '', '310', 'L', '', '', '')
```

`fixed_parameters` substituted an **empty string** for any absent variable. It
was never reachable in dispatch, which calls `assert_fixed_parameters` first and
refuses — so nothing was ever sent that way. But §5 says do not silently invent
a parameter, and a blank `{{3}}` is a farmer reading a message with a hole where
a figure belongs. A safety that depends on the caller remembering to call
something else is not a safety.

`fixed_parameters` now refuses a missing variable itself, mutation-checked:
removing the guard fails
`test_the_parameter_list_refuses_a_gap_rather_than_blanking_it` with a raw
`KeyError`. Shipped in the follow-up deploy recorded below.

**This is the fourth defect this milestone found by executing rather than
reading**, and the only one of the four that was DEMO-033's own.

## 15. Financial safety

DEMO-033 touches templates, approvals and the registry. It writes to exactly one
new table and modifies no financial table. Settlement, invoice, payment, receipt,
receivable, supplier-payment and customer-balance counts and values are compared
before and after deployment in §14, and no historical record was altered to make
the demo look clean.

## 16. REAL versus TEST versus NOT PROVEN

**REAL** — in the deployed product:

* the WhatsApp fixed-parameter variant model and all 24 WhatsApp templates;
* fixed parameter validation, refusing unknown, missing and leftover-optional;
* provider-independent template selection;
* the approval lifecycle, its permission, its audit and its API;
* provider mapping, kept separate from business identity;
* readiness evaluation and its blocker reporting;
* RLS classification and tenant isolation.

**TEST** — proven here, not in production traffic:

* local rendering of every variant in every language;
* in-process dispatch through the variant selection path;
* the approval workflow, including concurrent recording.

**NOT PROVEN** — and not claimed:

* that any external provider would approve any of these templates;
* real WhatsApp delivery;
* real SMS or email delivery to a live handset or inbox;
* any vendor's actual behaviour, parameter limits, or template review outcome.

## 17. Known limitations

1. **Variant count grows combinatorially.** Two optional groups produced four
   invoice variants; a third would produce eight. Six variant keys × four
   languages is already 24 templates a human must eventually read. A future
   journey with three optional groups should be reviewed before it is built.
2. **Approval is recorded, not fetched.** An operator types what a provider
   decided. If a provider later revokes a template, Lacteva will not know until
   somebody records it. Polling a provider's API is DEMO-034 territory.
3. **`ready_whatsapp` is 0 and will stay 0** until a real vendor account exists.
   Nothing in this milestone can move it.
4. **One provider per row.** The model keys approval by provider, so multiple
   providers are representable, but no code yet chooses between two approved
   providers for the same template.
5. **The optional-segment syntax still exists** for SMS and email, and is still
   the right thing there. A future channel with fixed parameters would need the
   same variant treatment; `FIXED_PARAMETER_CHANNELS` is the one place to add it.

## 18. Recommended DEMO-034

**Not started.** For consideration only:

* select a WhatsApp Business Solution Provider on commercial terms, with
  credentials held in the existing secret path and never in source control;
* submit the 24 WhatsApp templates for approval and record each outcome through
  the API this milestone built;
* implement the real provider adapter behind the existing `Notifier` port, with
  the sandbox mode gate DEMO-031 already enforces;
* first real send to an internal number, in sandbox, with the receipt path
  DEMO-029 built.

---

## Change Log

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-08-17 | DEMO-033 delivered — WhatsApp fixed-parameter variants, approval lifecycle, readiness. |
