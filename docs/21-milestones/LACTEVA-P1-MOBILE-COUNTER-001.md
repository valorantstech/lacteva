---
id: LACTEVA-P1-MOBILE-COUNTER-001
title: Mobile Counter Transaction & Offline Reliability Hardening
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-19
last-updated: 2026-08-19
related: [LACTEVA-P0-PRODUCT-008-FULL-PRODUCT-READINESS-AUDIT, LACTEVA-P1-PORTAL-SCALE-001, LACTEVA-MASTER-PRODUCT-ROADMAP]
baseline: ARCH-BASELINE-V1
---

# Lacteva — Mobile Counter Transaction & Offline Reliability Hardening (P1-MOBILE-COUNTER-001)

## A. Executive verdict

The counter workflow is operationally honest end to end: the farmer's parchi
now exists where the farmer stands (the wizard's completion step and a new
per-centre history), offline capture refuses at the counter exactly what the
platform would refuse at sync, rejection carries the operator's own reason,
the durable queue provably survives an app restart while offline — with the
signed-out operator TOLD their work is safe — and connectivity or sign-in now
resumes sync automatically without ever risking a duplicate. All gates green;
one test-suite flake was found, diagnosed and eliminated during the milestone.
**Functional hardening only — no redesign, no future capability, no security
change.**

## B. Source-of-truth references

Audit register: P0-PRODUCT-008 §5/§9/§11 (mobile completion register; defects
D-7, D-8, D-9 partial, D-12, D-13; missing-parchi/history findings). Backend
contracts used as-is: `GET /milk-transactions/{id}/slip` (SlipView, P0-BIZ-003),
`GET /milk-transactions` (paged), `POST /collection-sessions/{id}/close`,
`RejectCommand.reason`, `MAX_GROSS_KG = 200.0` and `QUALITY_RANGES` in
`milk_collection/service.py`. **Discrepancies reported, not invented around:**
the referenced "LACTEVA-P0-PRODUCT-009-mobile implementation" document does
not exist (P0-PRODUCT-009 = code + CHANGELOG, commit `2687f12`);
`LACTEVA-P0-PILOT-006-DEV-ONBOARDING-REHEARSAL.md` does exist and was used.

## C. Defects addressed

| Ref | Defect | Fix |
|---|---|---|
| Parchi gap (audit §5 E) | The wizard's completion step never called the slip endpoint; the parchi's audience stands at the phone | Completion fetches the platform's slip (number + shareable bilingual text) with copy-to-clipboard; transport failure leaves an explicit "Get parchi" retry; an OFFLINE completion says "Saved on this phone — queued to sync" and **never invents a slip number** |
| History gap (audit §5 E) | No transaction history/detail on mobile — a farmer's dispute unanswerable at the counter | New read-only `TransactionHistoryScreen` + detail (paged 20/“Load more”, loading/empty/error+retry, centre-scoped request; detail shows the parchi, which carries farmer identity) |
| D-8 | No offline input bounds — garbage queued silently, surfacing hours later | The platform's own rules mirrored pre-queue: gross>0, tare≥0, tare<gross, gross≤200; fat/snf 0–15, clr 20–40 — wording matches the server's refusals; backend stays authoritative |
| D-7 | Rejection reason hardcoded `'Rejected at review'` on the farmer's official parchi | Reject now asks; empty reason refused; the operator's words travel in `RejectCommand.reason` and render on completion |
| §5 restart | Restart-while-offline unproven; signed-out operator blind to queued work | Proven by test (same ops, same ids, zero duplicates across a process restart); the sign-in screen shows "N captured records are safe on this phone and will sync after you sign in" (count only — no data before auth) |
| D-13 (part) | Sync waited for a manual tap after any transport blip | Sync-on-sign-in + sync-on-resume (`WidgetsBindingObserver`), fire-and-forget over the existing idempotent `syncNow` — bounded, auth-respecting, duplicate-safe |
| D-12 | `close` session endpoint had no caller on any client | "Close session" action on centre detail: finds the open session, confirms naming the shift, platform closes (its refusal renders verbatim) |

## D. Mobile behavior before / after

| Before | After |
|---|---|
| Completion: state + net weight, no document | The parchi itself, or the honest queued state |
| Past collections: aggregate today-card only | Paged history + detail with the slip |
| Offline garbage queued silently | Refused at the counter in the server's words |
| Farmer's parchi could read "Rejected at review" | It reads what was actually wrong |
| Restart offline → operator blind | Banner: work is safe, will sync after sign-in |
| Sync only on a manual tap | Also on sign-in and app resume |
| No end-of-shift close anywhere | Confirmed close on centre detail |

## E–J. (Parchi · History · Offline · Restart · Resume · Rejections)

Detailed in §C; every behavior is regression-pinned (§N). Rejection handling
distinguishes: 401 = auth-recoverable (queued work waits, drain stops — the
P0-PRODUCT-009 rule, re-verified with a restart in the middle); business
conflict = inspectable, platform's reason preserved, **never blindly
resubmitted**; transport = retryable with bounded backoff; 403 on direct
drains remains a considered refusal (pinned since P0-PRODUCT-009).

## K. Idempotency verification

Pinned by test: operation ids are minted at capture, survive restart
byte-for-byte, travel unchanged on every retry, apply exactly once, and a
second sync sends nothing. Restart, dropped connection, retry, expired-then-
renewed authentication and reopening the app all leave exactly one effect.

## L. Security / RLS verification

No authorization moved into Flutter; every call rides the existing
authenticated path; 401/403 semantics unchanged; the history request is
centre-scoped and the platform decides what exists (RLS + centre scope,
backend-tested). The pre-auth banner reveals a COUNT only. No new local
persistence was introduced (the queue file predates this milestone; tokens
remain memory-only). The claims guard ran green — and **caught this
milestone's own draft comment** ("WhatsApp-pasteable") which was reworded
rather than the guard weakened.

## M. Files changed

**lib (5):** `api.dart` (+`transactionSlip`, `listMilkTransactions`,
`closeCollectionSession`), `collection_wizard.dart` (bounds, reject-reason,
parchi step), `transactions_history.dart` (new), `centers.dart` (history +
close-session actions, sign-in banner), `home.dart` (sync-on-resume/sign-in).
**test (6 new):** `counter_wizard_test.dart` (9), `history_screen_test.dart`
(4), `restart_offline_test.dart` (4), `offline_banner_test.dart` (1),
`auto_sync_test.dart` (4), `session_close_test.dart` (3). Backend, portal:
**untouched**.

## N. Exact tests and counts

| Gate | Result |
|---|---|
| Mobile `flutter test` (complete) | **205/205 passed — three consecutive runs** (180 prior + 25 new). A flake was found during validation: mixing `testWidgets` with real-file-IO `test`s in one file made the restart test time out intermittently (~1 in 3 full runs); the widget test was split into its own file and three consecutive full runs are green. Never reported green on the flaky state. |
| `flutter analyze` | **No issues** |
| Claims/product-honesty guards | Green (inside the suite; one own-comment violation caught and reworded) |
| Backend / portal suites | **Not run — those trees untouched** (backend last green at `83400c8`: 1,998/265/0) |
| Docs validation + xref | Green |
| Test letters A–S | A,B (wizard drive-through + parchi ×3) · C (history ×4) · D,F (restart capture) · E (bounds ×5) · G,H (restart survival) · I,J (resume ×4) · K,L,M (expired-restart-replay + P0-009 suite) · N (P0-009 403 pins) · O (conflict reason preserved, no blind retry) · P (transport retryable) · Q (original ids, exactly once) · R (session close ×3 + existing backend session contract) · S (centre-scoped request; RLS backend-tested) |

**On-glass status (honest):** the milestone APK (built against DEV) was
installed on the physical Motorola and its launch + sign-in surface verified;
**the new flows themselves were validated by automated tests only** — physical
walk-through was deferred by the owner mid-milestone. A DEV sign-in for
device-driving was attempted (SSH path; SG ingress added for the operator's
current IP) and abandoned on the owner's instruction; nothing on DEV was
changed and no credentials were used.

## O. Remaining P1/P2

Deferred with reasons: **token/session persistence** (full offline capture
after restart still needs an online sign-in first — persisting a token is a
security-posture decision, TO CONFIRM, out of scope per the milestone's own
offline-data-safety rule); connectivity-listener auto-sync (resume/sign-in
triggers only — a connectivity plugin is a new dependency, deferred);
driver quantity/notes on outcomes; operator-persona Hindi strings
(P1-LOCALE-I18N-001); remaining audit P2 polish (icons, decimal keyboards,
overflow tests, wizard back/cancel, live queue counts).

## P. UI/UX redesign deferral

Explicitly deferred: the Lacteva Design System V1 and the mobile UX redesign.
Every new surface here uses the current design system (Material defaults,
existing card/list/snackbar patterns); no animations, no visual language
change.

## Q. Preserved roadmap

Untouched and still labelled: AI/forecasting, SAP/ERP + SoR, enterprise SSO/
global identity/federation, GPS, WhatsApp/SMS providers (the parchi shares as
plain text), automated scale/analyzer capture, QR scanning (helper text
stands), chilling/BMC/plant/procurement transport, farmer app, web outlet
portal, payment gateway, advances/loans, advanced analytics. The claims guards
enforcing this passed inside this milestone's own runs.

## R. Recommended next milestone

**P1-LOCALE-I18N-001** per the established sequence (the counter surfaces
added here are prime candidates for the operator-persona catalog work).

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-19 | Engineering | Counter hardening: parchi on completion (+history screen with detail), platform-mirrored offline input bounds, operator-entered rejection reasons, restart-while-offline proven with pre-auth visibility banner, sync-on-sign-in/resume, end-of-shift session close (D-12 closed). 25 new tests; 205/205 ×3 consecutive runs after eliminating a mixed-binding test flake; analyze clean; claims guard green (and it caught this milestone's own draft wording). Backend/portal untouched; physical walk-through deferred by owner (P1-MOBILE-COUNTER-001). |
