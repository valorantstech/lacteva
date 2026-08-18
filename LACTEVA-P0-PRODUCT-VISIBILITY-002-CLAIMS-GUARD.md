---
id: LACTEVA-P0-PRODUCT-VISIBILITY-002-CLAIMS-GUARD
title: Executable Claims Guard for Portal and Mobile
type: reference
status: Approved
version: "1.0"
owner: Product
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-PRODUCT-CAPABILITY-VISIBILITY-AUDIT, LACTEVA-MASTER-PRODUCT-ROADMAP, LACTEVA-FIRST-DAIRY-SALES-AND-PILOT-PACKAGE]
baseline: ARCH-BASELINE-V1
---

# Lacteva — Executable Claims Guard for Portal + Mobile (P0-PRODUCT-VISIBILITY-002)

## 1. Objective

P0-PRODUCT-VISIBILITY-001 verified by inspection that no shipping UI overclaims
an unavailable capability. Inspection does not survive the next edit. This
milestone makes the honesty **executable**: automated tests in the admin portal
and the mobile app that fail the suite the moment future copy asserts a
capability the product does not have — the same pattern the marketing site has
enforced since launch. Hardening only: **no product functionality changed, no
copy rewritten, no fake anything created, no roadmap/commercial decision
touched.**

## 2. The existing marketing guard (the pattern extended)

`apps/marketing-site/src/app/claims.test.ts`: a `FORBIDDEN` list of
`{pattern, why}` regexes swept across every non-test `.ts/.tsx` source file;
one test per pattern; any offender fails with the file named. It bans
AI-powered/ML claims, SSO/API-gateway/on-prem, certifications (SOC2/ISO/GDPR/
HIPAA/PCI), superlatives, invented ROI numbers, unfinalized commercial terms,
and instant-provisioning promises. **Unchanged by this milestone; re-run green
(24/24).**

## 3. Portal implementation

`apps/admin-portal/src/app/claims.test.ts` — same sweep (all non-test
`.ts/.tsx` under `src/`), with one structural addition the portal needs and
marketing does not: **two tiers**.

- **FORBIDDEN (15 patterns)** — claim shapes that cannot be honest anywhere
  today: AI-powered / powered-by-AI / "machine learning predicts…" /
  predictive-prediction, bare `GPS`, location tracking, `IoT`, "automatically
  reads/captures/weighs/measures", "scale/analyzer is connected/integrated/
  online", "reads the scale/analyzer", QR-scanning claims ("scan the QR",
  "tap to scan"), "WhatsApp is connected/enabled/live", "sent via
  WhatsApp/SMS", government-integration claims, certifications
  (with `ISO 8601`/`ISO 4217` excluded as factual standards), and
  legally/fully-compliant or absolute-security claims.
- **ROADMAP_ONLY (10 patterns)** — vocabulary that is legitimate **only** on
  `/roadmap`, where every item is explicitly labelled Coming soon / Enterprise
  / Future and rendered inert (pinned by `roadmap-page.test.tsx`): bare `AI`,
  machine-learning, artificial intelligence, `SAP`, `SSO`/single sign-on,
  federation, global identity, forecast, farmer app, outlet portal. Anywhere
  else in the portal, naming these reads as having them — so anywhere else
  fails.

## 4. Mobile implementation

`apps/mobile/test/claims_test.dart` — the same principle in Dart: sweep every
`.dart` file under `lib/`, one test per pattern, offenders named in the failure
reason. The mobile app has **no labelled roadmap surface**, so there is no
allowed home for the vocabulary at all — **all 23 patterns are banned
outright**, including bare `AI`, `whatsapp`, `forecast`, `predict`, `SAP`,
`SSO`, federation, global identity, farmer app, outlet portal, GPS, IoT, the
hardware/QR/messaging claim shapes, and the compliance patterns.

## 5. Forbidden claim categories (both trees)

AI/ML beyond the statistical deviation flag · GPS/location intelligence ·
automated scale/device capture · analyzer integration · QR scanning ·
WhatsApp/SMS sending · forecasting/prediction · SAP/ERP · enterprise SSO ·
federation/global identity · farmer app · web outlet portal ·
government/compliance claims · IoT/hardware automation — every category the
milestone ordered, each traceable to a specific pattern with a `why` string.

## 6. Allowed roadmap wording (verified still passing)

The guards deliberately preserve every honest phrase the audit catalogued:
the portal's disclaimers ("nothing here pretends a device supplied a value",
"not that WhatsApp will reach it", "does not try to predict that"), the
notifications page's factual WhatsApp template-registry copy, the rendered
supplier QR (a real feature — only *scanning* is future), mobile's "mock
scale"/"mock analyzer" dev-only labels, "QR scanning arrives with device
integration", "no PDF engine yet", references to the real web portal, and the
`/roadmap` page's full Coming soon / Enterprise / Future vocabulary. Proof:
both guards pass on the unmodified tree.

## 7. Test evidence — the guards genuinely detect

Controlled negative examples (temporary files, deleted before commit, verified
absent via `git status`):

- **Portal**: `src/lib/__claims_negative__.ts` containing "AI-powered insights
  with GPS tracking, connected to SAP, sent via WhatsApp" → **5 tests failed**
  (both tiers fired: `AI-powered`, `GPS`, `sent via WhatsApp` in FORBIDDEN;
  `SAP`, bare `AI` in ROADMAP_ONLY). File removed → **27/27 green**.
- **Mobile**: `lib/__claims_negative__.dart` containing "AI-powered forecast,
  GPS tracking, share via WhatsApp" → **4 tests failed** (`AI`, `forecast`,
  `GPS`, `whatsapp`). File removed → **24/24 green**.
- **False positive caught and fixed during development**: the compliance
  pattern initially flagged mobile's factual "Currency (ISO 4217)" field label;
  the pattern now excludes `ISO 8601`/`ISO 4217` explicitly. No product copy
  was changed.

## 8. Files changed

| File | Change |
|---|---|
| `apps/admin-portal/src/app/claims.test.ts` | **New** — portal guard (27 tests) |
| `apps/mobile/test/claims_test.dart` | **New** — mobile guard (24 tests) |
| `LACTEVA-P0-PRODUCT-VISIBILITY-002-CLAIMS-GUARD.md` | **New** — this record |
| `CHANGELOG.md` | Entry |

No product source file, copy string, configuration, or canonical document was
modified.

## 9. Limitations

- The guards match **patterns, not meaning**: a determined euphemism ("smart
  insights engine") can slip past, and a future *legitimate* feature (e.g. a
  contracted WhatsApp provider) will require consciously editing the guard —
  which is the point: the edit is the review.
- They sweep source text (including comments); a claim rendered from
  **backend-supplied strings** at runtime is out of their reach (the backend's
  own honesty — e.g. mock-source refusal — covers that layer).
- Images/assets are not scanned; neither is the backend tree (its "copy" is
  API data, governed by its own tests).
- The portal's ROADMAP_ONLY allowlist is the single directory `app/roadmap/`;
  if a second labelled surface ever exists, the guard must be consciously
  extended.

## 10. Exact validation results

| Gate | Result |
|---|---|
| Portal vitest (full) | **25 files, 345/345 passed** (318 prior + 27 new guard tests) |
| Portal eslint `--max-warnings 0` | **Clean** |
| Portal build | Not re-run — no non-test source changed (last build green at 7f0d8cd) |
| Mobile `flutter analyze` | **No issues found** |
| Mobile `flutter test` (full) | **170/170 passed** (146 prior + 24 new guard tests) |
| Marketing claims test | **24/24 passed** (untouched) |
| Negative-example detection | Portal **5 failures** planted/**0** after removal; mobile **4**/**0** |
| Pre-existing failures | **None encountered** |
| `validate_docs.py` / xref | Green |

## 11. Security / integrity considerations

- The guards are **read-only tests**: they execute no network calls, mutate no
  state, and cannot leak data — they read the repository's own source.
- They are themselves excluded from their own sweep (the `.test.` filter /
  `test/` directory), so the forbidden patterns listed inside them do not
  self-trigger.
- No intentional false-positive fixture remains in the repository (verified:
  the only new files are the two guards and this document).
- The guard raises the cost of *accidental* dishonesty to a failing CI run,
  and of *deliberate* dishonesty to a reviewed edit of a file whose every
  entry carries its own justification string.

## 12. Next action

None required by this milestone — **STOP**. The pilot's critical path remains
business-gated (onboarding pack → four artifacts + licences + signed agreement
→ P0-PILOT-008 runbook). When a roadmap capability genuinely ships (messaging
provider contracted, hardware connector built), its guard entry is removed in
the same commit that ships the capability — the test edit *is* the honesty
review.

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product | Executable claims guards for portal (two-tier: 15 forbidden + 10 roadmap-only patterns, 27 tests) and mobile (23 patterns banned outright, 24 tests), mirroring the marketing claims.test.ts pattern; negative-example detection proven (5/4 planted failures, clean after removal); all honest existing wording preserved and verified passing; ISO 8601/4217 excluded as factual standards; full suites green (portal 345, mobile 170, marketing 24). Hardening only — no product change (P0-PRODUCT-VISIBILITY-002). |
