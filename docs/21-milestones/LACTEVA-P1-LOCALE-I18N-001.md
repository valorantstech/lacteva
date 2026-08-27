---
id: LACTEVA-P1-LOCALE-I18N-001
title: Localization & Internationalization Hardening
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-19
last-updated: 2026-08-19
related: [LACTEVA-P0-PRODUCT-008-FULL-PRODUCT-READINESS-AUDIT, LACTEVA-P1-PORTAL-SCALE-001, LACTEVA-P1-MOBILE-COUNTER-001, LACTEVA-MASTER-PRODUCT-ROADMAP]
baseline: ARCH-BASELINE-V1
---

# Lacteva — Localization & Internationalization Hardening (P1-LOCALE-I18N-001)

## A. Executive verdict

**PARTIAL — the operator's daily path is genuinely multilingual; the
back-office remainder is inventoried, not done.** The surfaces a Hindi-speaking
operator touches every shift — the mobile collection persona end to end, and
the portal's transactions family including the farmer-facing parchi — now read
from the catalogs in Hindi and Arabic, proven by rendering tests at the pilot's
real 320px geometry. The on-screen slip was aligned to the **platform's own
printed-parchi Hindi**, so the paper in a farmer's hand and the screen say the
same words. Two long-standing defect classes were closed permanently by
executable guards: the thrice-recurring "catalog without callers", and
"parity satisfied by copying English". A **complete string inventory of both
clients** (~1,450 portal + ~360 mobile, classified A–H) is the milestone's
second deliverable and the work-list for the remainder. Nothing was
mistranslated by invention: money-consequence sentences are keyed but carry
English pending business sign-off, listed and test-enforced as a visible debt.

**Honest scope statement:** the audit's "27 English-only portal pages" were
inventoried in full but only the highest-exposure cluster was converted. The
rest is §N, not a claim.

## B. Exact localization inventory

Read-only inventory of both clients, classified per the milestone's A–H scheme
(A must-localize · B developer/internal · C server-provided · D legal/commercial
needing confirmation · E technical identifier · F Coming-Soon informational ·
G test fixture · H documentation):

- **Portal: ~1,450–1,550 category-A strings** across 37 pages + 8 shared
  components. Highest-exposure ranking (used to sequence the work):
  transactions/new · transactions/[id] SlipCard · customers/[id] · dashboard ·
  settlements · payments · suppliers · receivables.
- **Mobile: ~360 category-A strings** across 17 files; ~250–280 distinct keys
  after de-duplication.
- **Cross-cutting findings recorded**: 13 local `stamp()` copies bypassing
  `datetime.tsx`; algorithmic English from identifiers (`humanise()`,
  `humanAction()`); hand-built plurals (`${n} rate card${n===1?"":"s"}`) that
  cannot survive translation; `formatAmount` using Western 3-digit grouping
  where an Indian dairy reads lakh grouping (**TO CONFIRM**, §O); RTL physical
  classes concentrated in notifications (34), deliveries (11), subscription (9),
  routes (7).

## C. Portal pages localized

| Page | Result |
|---|---|
| `login` | Fully catalogued |
| `transactions` (list) | Fully catalogued incl. filters/empty states |
| `transactions/[id]` | Catalogued incl. **SlipCard (the parchi)** — highest farmer-facing priority |
| `transactions/new` (capture wizard) | Catalogued incl. stepper, validation, accept-confirm |
| `suppliers`, `centers` | Locale-correctness fix only (§H) — strings deferred |
| **Catalog** | **361 → 544 keys × 3 languages (+183)** |

## D. Mobile strings audited / localized

| File | Result |
|---|---|
| `collection_wizard.dart` | Fully catalogued (48 lookups) incl. parchi block, reject-reason UI, milk-type labels |
| `centers.dart` | Fully catalogued (62) — login, list, form, detail, close-session dialog, readiness |
| `transactions_history.dart` | Fully catalogued (18) |
| `center_summary.dart` | Fully catalogued (11) |
| `home.dart`, `customer_portal.dart`, `deliveries.dart` | **23 dead catalog keys wired** to the English they retyped |
| `suppliers.dart`, `offline/sync_screen.dart`, `pricing_resolution.dart` | Session threaded; strings **deferred** (§N) |
| **Catalog** | **73 → 254 keys × 3 languages (+181)** |

Session threading: an **optional** `Session? session` was added down the
collection stack (`L10n.of(null)` → English), so no existing test constructor
changed and the default locale is unaffected.

## E. Locale / catalog matrix

| | en | hi | ar |
|---|---|---|---|
| Portal | 544 keys (source of truth) | 544, parity-tested | 544, parity-tested |
| Mobile | 254 keys | 254, parity-tested | 254, parity-tested |
| Fallback | — | missing key → en → key | same |
| Direction | LTR | LTR | RTL (`directionFor`, applied at the router) |

## F. Hindi validation — **PROVEN (automated), NOT device-verified**

`hindi_render_test.dart` renders the capture wizard (weight and quality steps)
and the history screen with a `hi-IN` session at **320×568, DPR 1.0** — the
pilot's real cheap-Android geometry — and treats a RenderFlex overflow as a
failure. It asserts Devanagari is actually on screen (not the English
fallback), that units and instrument tokens (**kg, FAT, SNF, CLR**) stay Latin
because a meter reads them in every language, and — the check that catches a
rushed catalog — that Hindi/Arabic values are **real script, not copied
English**. UTF-8 decoding was already fixed and pinned in P0-PILOT-004
(`bodyBytes`), so mojibake is structurally excluded.
**Not claimed:** on-glass visual verification. That is a P0-PILOT-004-class
exercise and is not asserted here.

## G. Arabic / RTL — **PARTIAL, remainder DEFERRED**

Proven: catalog parity and real Arabic script; `directionFor` drives
`Directionality` at the router so the whole experience mirrors together; the
wizard renders RTL at 320px without overflow. Portal files touched had physical
direction classes converted to logical (`text-left`→`text-start`, `pl-`→`ps-`).
**Deferred, honestly:** full RTL layout correctness across the untouched
portal (notifications/subscription/routes carry the bulk of physical classes),
and "A → B" arrow constructs which need a direction-safe treatment. No RTL
visual redesign was attempted — that belongs to the Design System milestone.

## H. Numbers / dates / currency

- **Fixed (real defect):** the 30-day activity windows on `suppliers` and
  `centers` computed from `new Date().toISOString()` — browser UTC — so an
  Indian dairy's "last 30 days" was wrong for 5.5 hours daily. Both now derive
  from `useBusinessToday()` (the dairy's clock). This was the last of the
  DEMO-019 bug family.
- **Unchanged by design:** money keeps the backend's exact decimal string
  end to end (no float introduced for formatting); business dates are the
  platform's own `YYYY-MM-DD`, rendered verbatim; the mobile app performs no
  timezone arithmetic.
- **TO CONFIRM:** Indian lakh/crore digit grouping (`formatAmount` currently
  groups in threes); relative-time strings in the portal's `sync` page.

## I. Error / offline / sync localization

Mobile: `common.couldNotReach` replaces every hardcoded transport-failure
string on the converted screens; the session-expiry notice, queued-work banner
and retry affordances are catalogued. **Server-provided content stays
verbatim** — `ApiError.detail`/`extra` are the platform's own words and are
never overwritten by a client translation. **Deliberate exception, recorded:**
the offline capture-bounds messages in the wizard remain English because they
**mirror the server's own refusal wording** so an operator sees the same
sentence online and offline; localizing both ends needs machine codes from the
platform (**TO CONFIRM**, §O). Queue-stored strings (`'session expired — sign
in to sync'`, `'offline'`) were left alone: they are persisted in the queue
file and surface in no UI today, so translating at render requires storing a
code — recorded, not silently changed.

## J. Accessibility

`aria-label`/`sr-only` strings on converted portal pages were keyed alongside
their visible copy (e.g. the wizard's `Progress` stepper label), so a
screen-reader user in Hindi hears Hindi. No cosmetic accessibility work was
added beyond the milestone's scope.

## K. Files changed

**Portal (7):** `lib/messages.ts`; `app/login/page.tsx`;
`app/transactions/{page,[id]/page,new/page}.tsx`; `app/{suppliers,centers}/page.tsx`
(UTC fix). **New test:** `app/locale-quality.test.tsx`.
**Mobile (12):** `l10n.dart`; `collection_wizard.dart`; `centers.dart`;
`transactions_history.dart`; `center_summary.dart`; `home.dart`;
`customer_portal.dart`; `deliveries.dart`; `suppliers.dart`;
`offline/sync_screen.dart`; `pricing_resolution.dart`; plus
`test/{offline,restart_offline}_test.dart` (flake fix, §L). **New tests:**
`test/catalog_callers_test.dart`, `test/hindi_render_test.dart`.

## L. Exact tests and counts

| Gate | Result |
|---|---|
| Portal vitest | **29 files, 367/367 passed** (360 prior + 7 new locale-quality) |
| Portal eslint `--max-warnings 0` | **Clean** · `next build` **green** · `tsc` no new errors |
| Mobile `flutter test` | **212/212 — three consecutive runs** (205 prior + 7 new: 2 catalog-callers, 5 Hindi/Arabic render) |
| Mobile `flutter analyze` | **No issues** |
| Backend | **Not run — untouched** (last green `83400c8`: 1,998/265/0) |
| Docs validation + xref | Green |

**Flake found and fixed (not hidden):** two full-suite runs failed
intermittently (204-1, 201-4) while others passed. Diagnosis: failures
correlated with *slower* runs — the default 30-second per-test timeout is a
machine-speed assertion, and the real-file-IO offline tests tripped it under
load. Fixed by widening the timeout on those files only (`_ioTimeout`,
2 minutes); **no assertion was weakened**. Verified with three consecutive
green runs *while the portal suite ran concurrently* — the exact load that
triggered it.

**New guard tests, and what they defend**
- `catalog_callers_test.dart` — every catalog key must be looked up somewhere
  in `lib/`. The "catalog without callers" defect had been found **three
  times**: a translated key sitting beside the English the screen retyped.
  Parity proves a key is translated; this proves it is *shown*.
- `locale-quality.test.tsx` — operator-critical keys carry real Devanagari and
  Arabic (a catalog can pass parity while holding English in every slot);
  every `{var}` survives translation; **the parchi labels equal the platform's
  own printed Hindi**; the untranslated-money list stays honest and small.
- `hindi_render_test.dart` — session locale → catalog → widget at 320px, with
  overflow as a failure, for the newly translated collection persona.

## M. Security / RLS verification

No authentication, authorization, RLS, tenancy, centre-scope or token change.
Localization is presentation only: the session's `locale` was already carried
by the platform and is read, never written. Server-provided content is
rendered verbatim, so no translation layer can alter what the platform
decided. The claims guards passed unchanged.

## N. Remaining localization gaps (honest work-list)

**Portal (~24 pages, ~1,100 category-A strings):** dashboard remainder,
customers list/detail/import, suppliers, centers(+detail), routes, billing,
invoices/[id], receivables, rate-cards(+detail), matrices, resolve,
settlements(+detail), payments(+detail), receipts, reports, sync, notifications
(largest single page, ~90), admin/* (users, roles, organizations, audit,
calendar, configuration, operations, subscription), and shared `csv-import`,
`entity-picker`, `app-shell` remainders. Recommendation for `roadmap`: catalog
the skeleton and badges only, leaving the capability paragraphs in English —
they are quoted verbatim from the canonical roadmap and a paraphrase would
create a second, unreviewed source of truth.
**Mobile (~150 strings):** `suppliers`, `sync_screen` (incl. the `queue.kind.*`
/ `conflict.*` code-to-word maps), `rate_cards`, `pricing_matrices`,
`pricing_resolution`, `settlements`, `payments`, `receipts`, `notifications` —
the phone's back-office wave, deliberately after the counter.

## O. TO CONFIRM

| # | Item | Owner |
|---|---|---|
| 1 | Hindi/Arabic wording for the 5 money-consequence sentences (keyed, English today, test-listed) | Business + legal |
| 2 | Server-side refusal **codes** so offline bounds messages can be localized on both ends without diverging from the server | Architecture |
| 3 | Indian lakh/crore digit grouping in `formatAmount` | Product |
| 4 | Locale source for the signed-out login screen (device locale vs last-known) | Product |
| 5 | Whether queue-stored error sentences become codes (invisible today) | Engineering |
| 6 | Whether server-provided `ApiError.detail` should be localized platform-side | Architecture |
| 7 | Portal relative-time (`ago()`) localization approach | Product |

## P. UI/UX redesign deferral

Explicitly deferred: **Lacteva Design System V1**, portal redesign, mobile
redesign, colour/typography systems, animations, imagery, navigation redesign.
Every change here used the existing design system; the only visual deltas are
translated words, logical direction classes, and one keyed stepper label.

## Q. Preserved roadmap

Untouched and still labelled: AI/forecasting, SAP/ERP, enterprise SSO, global
identity, federation, org-to-org, GPS, WhatsApp/SMS providers, automated
scale/analyzer, QR scanning, PDF generation, GST/FSSAI fields, chilling/BMC,
plant, procurement transport, farmer app, web outlet portal, advances/loans,
advanced analytics, payment gateway, enterprise integrations. No Coming-Soon or
Enterprise label was removed; the claims guards passed.

## R. Recommended next milestone

**P1-LOCALE-I18N-002 — back-office localization wave** (the §N work-list,
using this milestone's conventions and guard tests), *or* **P1-E2E-HARNESS-001**
if crossing a real client↔server boundary is judged the higher risk. Both are
ahead of Design System V1 in the agreed sequence.

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-19 | Engineering | Localization hardening: complete A–H string inventory of both clients (~1,810 strings); portal transactions family + login localized (361→544 keys ×3) with the SlipCard aligned to the platform's printed-parchi Hindi; mobile collection persona localized (73→254 keys ×3) with optional session threading and 23 dead keys wired; UTC 30-day-window defect fixed (last of the DEMO-019 family); three new guard suites (catalog-callers, locale-quality, Hindi/Arabic render at 320px); a real test flake diagnosed as a load-dependent timeout and fixed without weakening assertions. Portal 367/367 + lint + build; mobile 212/212 ×3. Remainder inventoried honestly, money wording left to business (P1-LOCALE-I18N-001). |
