---
id: DEMO-013-FINAL
title: DEMO-013 — Globalization, Country, Currency, Timezone & Language
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-14
last-updated: 2026-08-14
related: [LOCALIZATION, MOBILE-EXPERIENCES, NOTIFICATION-ENGINE, DEMO-012-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-013 — Globalization, Country, Currency, Timezone & Language

The platform's own context guide has carried this rule since the foundation:

> **9.6 Do not hardcode country- or market-specific rules.** No currency
> defaults in logic, no locale assumptions, no regulatory constants.

It was false. The sales chain defaulted to the literal `"KES"`, business dates
were UTC's dates, `user.locale` was a column nothing validated, and the demo
seeder posted `country_code: "ke"` outright. Lacteva was a Kenyan dairy
application that could be installed elsewhere.

An organization now resolves **country → currency + timezone + languages**
once, at onboarding, and everything else reads the organization. Nothing in
the application branches on which country a tenant is in.

**Three defects found, two of them only by running things.** **AWS cost: none.**

---

## 1. What was already present

More than expected, which shaped the whole design:

| Already there | Where |
| --- | --- |
| `organization.country_code` (ISO 3166-1 alpha-2) | since the foundation |
| `organization.default_locale` | since the foundation |
| `user_account.locale` | since the foundation — unused and unvalidated |
| `collection_center.timezone` (IANA) | per-centre, used by one readiness check |
| Backend message catalogs (en/sw/hi) + `translate()` | `core/i18n.py` |
| `currency` on **every** money row, ISO 4217 | since DEMO-009 and earlier |
| `Decimal` end to end, `Numeric` columns | BR-0005 |

So this milestone extended rather than replaced: no new i18n mechanism on the
backend, no new currency column anywhere, no change to the money model.

## 2. What was missing

- `organization.currency_code`, `timezone`, `supported_languages`.
- Any resolution from country to those — onboarding asked for a country and
  then ignored it.
- Any constraint on a user's language, or any way for a person to set one.
- **Any notion of a business day that was not UTC's.**
- i18n in the portal and the mobile app: **none at all**, English hard-coded in
  components.
- An organization settings screen.

## 3. Database changes

One migration, `f3a92d18c47b`, additive and reversible:

| Change | Note |
| --- | --- |
| `organization.currency_code` (ISO 4217, NOT NULL) | backfilled by country |
| `organization.timezone` (IANA, NOT NULL) | backfilled by country |
| `organization.supported_languages` (JSON, NOT NULL) | backfilled by country |
| `organization.default_locale` widened 8 → 16 | `en-IN` did not fit in 8 |
| `user_account.locale` widened 8 → 16 | same |

The backfill maps country → currency/timezone from a table **snapshotted in
the migration**, because a migration is a historical record and must not change
meaning when `core/locales.py` later does. A country the snapshot does not know
gets `XXX` — ISO 4217's own code for "no currency involved" — and `UTC`, so
such an organization cannot trade until an administrator says what it uses.
Every organization in existence is `KE`, so that branch is theoretical, which
is the point of writing it down rather than defaulting to Kenya.

Verified up → down → up on SQLite and applied on production PostgreSQL;
`alembic check` reports no drift.

## 4. API changes

| Endpoint | Purpose | Guard |
| --- | --- | --- |
| `GET /v1/locales/countries` | what each country implies, for onboarding | any session |
| `GET /v1/organizations/settings/locale` | this organization's locale context | `organization.read` |
| `PUT /v1/organizations/settings/locale` | change money, clock or languages | `organization.settings.manage` |
| `PUT /v1/auth/me/language` | a person's own language | any session |

Changed: `POST /v1/organizations` accepts optional currency/timezone/language
overrides and resolves the rest from the country. `GET /v1/auth/me` carries the
organization's locale context. `GET /v1/deliveries/report` dates became
**optional**, defaulting to the organization's today. Rate card, settlement and
payment currency became **optional**, defaulting to the organization's.

`organization.settings.manage` is a new registry entry, deliberately separate
from the platform's `organization.manage` (the authority to create
organizations at all) and from `configuration.write`.

Also added `ValidationError` (422): the error hierarchy had no home for a value
wrong in *domain* terms, so a bad IANA zone answered **500** — telling the
caller the platform broke when in fact they did.

## 5. Frontend changes

- `src/lib/messages.ts` — catalogs, English and Hindi, keys namespaced by area.
- `src/lib/i18n.tsx` — `LocaleProvider`, `useT()`, `translatorFor()`.
- Navigation holds **keys, not sentences**; the dashboard, settings page and
  shell render through the catalog.
- `/admin/settings` — country, currency, timezone, languages; organization-wide
  controls behind `organization.settings.manage`, a personal language chooser
  behind nothing.
- **No framework added.** react-intl, next-intl and lingui each solve problems
  this portal does not have and each would add a build step.

## 6. Mobile changes

- Session carries `locale` and the organization's locale context; the app holds
  **no country configuration of its own**.
- `lib/src/l10n.dart` — the same dictionary-and-lookup shape as the portal,
  English and Hindi.
- `money()` takes the symbol and code from the session and never parses the
  amount into a `double`.
- **The app asks the platform what day it is.** A handset cannot compute an
  IANA calendar date without shipping a timezone database, and its own clock is
  not the dairy's — so it omits the dates and uses the platform's echoed
  `date_from` as the date it records against.

## 7. i18n architecture

Three catalogs, one shape, keyed by **language** (`hi`) rather than locale
(`hi-IN`) — the region carries the money and the calendar, which live on the
organization; splitting per region would double the translation work to say the
same sentences. Fallback is language → English → the key: an English sentence a
person can act on, or a key an engineer can grep for, never a blank.

The language in force is the person's own, read from their account — never
`Accept-Language` or `navigator.language`, because a shared machine in a dairy
office would otherwise flip a supervisor's screen because of what the last
person's laptop was set to.

## 8. Country / currency / timezone architecture

`core/locales.py` is the one place that knows one country from another. A
registry **in code**, like permissions and `BUS_EVENTS`, because this is
reference data: it changes when the world changes, not when a tenant does, and
a typo should be a failing build rather than a row somebody has to notice.

Adding a country is a data entry. A country the registry has never met is still
onboardable, provided the caller supplies the currency and timezone — it is
never guessed, because a guess about somebody's money is wrong silently and
discovered on the first bill.

Settings are **columns, not lookups**: if they were derived from
`country_code`, a correction to the registry would silently change the meaning
of every historical report of every tenant in that country.

`core/business_time.py` makes storage UTC and *interpretation* the
organization's. Day bounds are half-open so midnight belongs to exactly one
day, and are built by localizing midnight rather than adding 24 hours — a day
is 23 or 25 hours across a DST transition, and Europe/London is in the registry.

## 9. Indian demo organization

**Lacteva India Demo** — IN, INR, Asia/Kolkata, en-IN + hi-IN. Built by the
same seeder code from a different `Market` profile; there is no branch in the
seeder that asks which country it is building.

| | Kenya | India |
| --- | --- | --- |
| Centres | 5 | 3 |
| Suppliers | 24 | 12 |
| Customers | 16 | 16 |
| Deliveries | 570 | 570 |
| Bills issued | 14 | 14 |
| Collection value (7d) | 110,320.00 KES | 45,168.00 INR |
| Sales value (7d) | 101,061.00 KES | 73,602.00 INR |
| Customer receivable | 211,961.00 KES | 152,104.00 INR |
| Customer login | `household@lacteva-demo.example.com` | `household@lacteva-india.example.com` |

Both markets carry the full chain: collection centres, farmers, collections
with FAT/quality, rate cards, a pricing matrix, settlements, payments,
receipts — and customers, deliveries, monthly bills, customer payments,
receipts and outstanding balances.

## 10. Kenya demo preserved

Untouched and verified after the change: 24 suppliers, 5 centres, 110
collections, every figure in KES, English, Africa/Nairobi. **Nothing was
converted** — converting the existing records would have destroyed the evidence
that the platform runs two countries at once, which is the whole claim.

## 11. Daily report verification

`GET /v1/deliveries/report` with no dates returns the **organization's** today
and echoes it. Asserted in tests for both zones, and exercised by the mobile
round, which now records against the platform's date rather than the handset's.

The defect this prevents: 05:00 in Bengaluru is 23:30 UTC *the day before*, so
a UTC-dated round is filed under yesterday. Nairobi is UTC+3, which is exactly
why the Kenyan demo never showed it.

## 12. Monthly billing verification

A test bills an Indian household for July — three deliveries on the 1st, 15th
and 31st — and asserts the period comes back `2026-07-01 → 2026-07-31`, the
currency `INR`, and the subtotal exactly `168.00` (3 × 1.000 L × 56.0000). In
the browser, the Indian dairy shows 14 bills and 152,104.00 INR receivable.

`month_bounds()` computes a billing month in the organization's calendar. The
billing system itself was **not** redesigned (§9 of the work order).

## 13. Tests executed

| Suite | Result |
| --- | --- |
| Backend, full | **1,385 passed**, 0 failed |
| Backend, new for DEMO-013 | 40 (localization 38, payment currency 1, RLS 1) |
| Portal | **208 passed** (11 new) |
| Mobile | **107 passed** (13 new) |
| Analyzer / lint | `dart analyze`, `eslint --max-warnings 0`, `ruff` all clean |
| Migration | up → down → up, `alembic check` no drift |
| Docs | validator + XREF regenerated |

Covered explicitly: India and Kenya; INR and KES; Asia/Kolkata and
Africa/Nairobi; English and Hindi; a user choosing a supported language and
being **refused** an unsupported one; India's defaults; Kenya's defaults;
daily report and monthly billing in the organization's timezone; tenant
isolation both directions; and money still arriving as exact decimal **strings**
rather than JSON numbers.

The cross-tenant claim about locale settings is asserted in the **PostgreSQL**
suite, not the SQLite one: `organization` is isolated by RLS, which SQLite does
not have, and a green where a guarantee cannot fail is not a test.

## 14. Browser verification

Real Chrome, the built portal against the two-market database:

1. Signed in to **Lacteva India Demo** — dashboard shows collection value
   **45,168.00 INR**, sales value **73,602.00 INR**, receivable **152,104.00 INR**.
2. Settings — **India / ₹ INR / Asia/Kolkata / en-IN**, languages English and
   हिन्दी.
3. Switched **my language to Hindi** — the entire navigation and the dashboard
   became Hindi (डैशबोर्ड, खरीद, संग्रह मूल्य, बिक्री, ग्राहक बकाया) while every
   amount stayed **INR**: money and timezone are data, not vocabulary.
4. The preference **survived a re-login** after a server restart, proving it is
   stored on the account rather than in the browser.
5. Switched back to English — restored.
6. Signed in to **Kenya** — 110,320.00 KES, 101,061.00 KES, 211,961.00 KES, in
   English, with its original 24 suppliers and 5 centres.
7. Kenya settings — **Kenya / KSh KES / Africa/Nairobi / en-KE**, offering
   English and Kiswahili. **Hindi is not offered**, because that dairy has not
   enabled it.
8. Tenant isolation — each dairy's customer by id from the other returns
   **404**.

## 15. Deployment

See §18 below.

## 16. AWS resources and cost

None created, changed or deleted. **$0 recurring cost added.**

## 17. Defects discovered

### D1 — Procurement was priced in Kenyan shillings (found in the browser)

The Indian dashboard showed sales in rupees and, on the same screen for the
same dairy, **"45,168.00 KES"** for procurement.

The cause was not a stray literal. Rate cards, settlements and payments all
**required** a currency from the caller — and requiring it *is* the defect:
every caller then has to know, and one of them will be wrong. The seeder had
been stating `"KES"` since there was only one country, so an Indian tenant got
Kenyan rate cards and everything derived from them inherited it.

Now optional everywhere, defaulting to the organization's currency.

### D2 — The payment currency guard compared against `None`

Making currency optional was half the change. `_payable_settlement` compares a
payment's currency against the settlement's — correctly, because converting
between them is not something a payment does — and was still handed the
*request's* value. With the caller omitting it, every settlement looked like a
mismatch and **every payment was refused**.

Caught by the demo seeder on the **Kenyan** market, one commit after the change
that introduced it: my localization test covered the rate card and stopped
there. A test now creates a payment with no currency stated, verified to fail
against the previous commit with the original 409.

### D3 — The mobile session read the person from the wrong place (DEMO-012)

`Session.fromJson` read `id`, `email` and `full_name` from the top level of
`/v1/auth/me`, where they are not — they are nested under `user`. The signed-in
address had been rendering blank on the dead-end screen and in the push-device
label since DEMO-012. Both shapes are now accepted, and a test asserts against
the real payload.

### Also worth recording

- **The rate limiter stopped the seeder**, correctly: two markets pushed
  invitation-accept past ten in fifteen minutes. The seeder now reads
  `retry_after_seconds` and waits, rather than being exempted from a control
  that protects a real endpoint.
- **A bad IANA zone answered 500** because the error hierarchy had no 422.

## 18. Remaining limitations

- **Hindi coverage is partial by design.** Navigation, the dashboard, the
  settings screen and the common vocabulary are translated. Deep pages
  (transaction wizard, settlement detail, rate-card editor) still render
  English through the fallback — a partly-English screen, never a broken one.
  Extending is a catalog entry plus swapping literals for keys, with no
  architectural work left.
- **No Arabic yet.** `LANGUAGES` carries `rtl` for it and the registry lists AE
  and SA, but no catalog exists and no right-to-left layout work has been done.
- **The backend catalog covers errors and notification subjects only** — it was
  never a full UI catalog and DEMO-013 did not make it one.
- **No FX conversion**, deliberately: this milestone determines an
  organization's currency. A tenant whose customers pay in two currencies is
  supported only in the sense that each row carries its own.
- **Country is not changeable** after onboarding. Moving an organization
  between countries changes what its historical money means; it needs a
  migration, not a settings form.
- **`collection_center.timezone` still exists** alongside the new organization
  timezone. It predates DEMO-013 and is used by one readiness check. A centre
  in a different zone from its organization is a real possibility that nothing
  yet resolves; today the organization's zone is authoritative for business
  dates and the centre's for that one check.
- **Mobile localization is verified by unit tests, not on a device.** The
  Flutter changes have 13 tests and a clean analyzer; the browser verification
  above is the portal. No emulator image is available on this machine
  (unchanged since DEMO-012).
- **Money scale is still a constant.** `Currency.minor_units` exists and is
  correct, but every supported currency has two decimals, so nothing reads it
  yet. A zero-decimal currency (UGX is already in the registry) would need
  `core/db.py`'s money scale to become a lookup.

## 19. Recommended next milestone

1. **Finish the Hindi catalog** across the deep pages, and add Arabic with the
   right-to-left layout work — the architecture is done, the vocabulary is not.
2. **Resolve centre-vs-organization timezone** into one documented rule.
3. **Per-currency money scale**, before a zero-decimal currency is onboarded
   rather than after.
4. **An audited API for binding a customer login** (carried over from
   DEMO-012, still the largest gap in the customer experience).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-14 | Platform Engineering | DEMO-013 delivered: country-resolved locale context, organization business time, portal and mobile i18n, an Indian demo tenant, three defects. |
