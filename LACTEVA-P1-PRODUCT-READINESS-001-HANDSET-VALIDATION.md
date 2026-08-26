---
id: LACTEVA-P1-PRODUCT-READINESS-001-HANDSET-VALIDATION
title: The Operator Journey on a Physical Handset
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-26
last-updated: 2026-08-26
related: [LACTEVA-P1-PRODUCT-READINESS-AUDIT, LACTEVA-P1-MOBILE-COUNTER-001, LACTEVA-P0-PRODUCT-008-FULL-PRODUCT-READINESS-AUDIT, LACTEVA-PILOT-READINESS-GATE, LACTEVA-MASTER-PRODUCT-ROADMAP]
baseline: ARCH-BASELINE-V1
---

# Lacteva — The Operator Journey on a Physical Handset (P1-PRODUCT-READINESS-001)

## 1. Executive summary

The complete milk collection journey was driven end to end on a real Android
handset against a real backend: **centre → open session → supplier → milk entry
→ fat/quality → pricing → accept → close session**. **Every step passed.** A
parchi was issued (`SLP-2026-000001`), the platform's own records agree with
what the phone displayed, and the session closed cleanly with the collection
intact.

**No production code was changed to run this.** The working tree is clean at
`7941331`; the one code change this journey needed — the missing `INTERNET`
permission in the release manifest — was found and fixed in the preceding
increment and is already on `main`.

Three findings, **none of them blockers**:

- **D-1 (P2, real defect).** Two screens show the operator a raw permission
  key — `reporting.read`, `pricing.ratecard.read` — where the platform sent a
  perfectly good sentence. Presentational, in the mobile client, one line.
- **D-2 (P2, UX).** Those two screens are offered to an operator whose role
  can never use them. The house pattern for this already exists elsewhere in
  the same app and was not applied to the centre toolbar.
- **F-1 (business question, not a defect).** Pricing could not be exercised,
  because the synthetic dairy has no published rate card. The platform
  correctly refused to invent a price and the parchi printed **"Rate pending"**.
  That is honest, and it is a question the business should answer before a
  pilot: is a rate-pending parchi acceptable at the counter?

**Verdict: the collection journey is pilot-ready on real hardware.** See §7 for
the qualification.

---

## 2. What was under test

The thing that matters about this exercise is that nothing was simulated. Not
the device, not the network, not the database, not the numbers.

| Layer | What ran |
|---|---|
| Handset | moto g57 power, `ZN5226CLBG`, Android 16 (API 36), 1080×2400 |
| App | `com.lacteva.lacteva_mobile`, debug build from this tree |
| Backend | FastAPI `platform-core` on `:8000`, real PostgreSQL |
| Data | Synthetic dairy seeded through the platform's own API |
| Driving | `adb shell input` taps; `adb exec-out screencap` read back as images |

Every assertion below was checked twice: once by reading what the phone
displayed, and once by asking the platform directly over HTTP. Where those two
disagree, the platform wins and the disagreement is the finding. They did not
disagree.

---

## 3. Exact handset setup (reproducible)

No code change is required. This is the whole procedure.

**3.1 — Network.** The phone reaches the developer's backend through the USB
cable, not the LAN. This avoids needing the host's IP, avoids the firewall, and
works on a phone with no Wi-Fi:

```bash
adb reverse tcp:8000 tcp:8000     # phone's localhost:8000 → host's :8000
adb shell curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/healthz
# expect: 200
```

**3.2 — Build and install.** The API address is compiled in:

```bash
cd apps/mobile
flutter build apk --debug --dart-define=LACTEVA_API_URL=http://localhost:8000
adb install -r build/app/outputs/flutter-apk/app-debug.apk
adb shell monkey -p com.lacteva.lacteva_mobile 1
```

**3.3 — A note on the release build.** A release APK merges only
`src/main/AndroidManifest.xml`, and until `7941331` that manifest carried no
`INTERNET` permission — debug builds worked because the debug manifest supplied
it. A release build could not open a socket at all. That is fixed and guarded
by `apps/mobile/test/manifest_test.dart`, which asserts the permission is
present **and** declared before `<application>`.

**3.4 — Credentials.** Synthetic only. No real farmer, supplier or customer
data was used at any point, in keeping with the work order.

---

## 4. The journey, step by step

Screens were read as images; the platform was queried independently. Both
columns had to agree for a PASS.

| # | Step | What the operator did | Result | Verified against the platform |
|---|---|---|---|---|
| 0 | Sign in | Email + password, synthetic operator | **PASS** | Token issued, tenant bound |
| 1 | **Centre** | Centre list → `E2E Centre 1` (`E2EC14F5`) | **PASS** | Centre reachable, `active` |
| — | Centre detail | Status `active`, hours Mon–Sun 05:00–21:00 | **PASS** | Matches stored operating hours |
| 2 | **Open session** | Collect-milk action opened a session | **PASS** | Session `83e44f9e`, `label: mobile`, `opened_at 16:35:39Z` |
| 3 | **Supplier** | Identified supplier `S-88A723` | **PASS** | `supplier_id dd166cb0…` on the transaction |
| 4 | **Milk entry** | cow · can · `CAN-07` | **PASS** | `milk_type cow`, `container_identifier CAN-07` |
| 5 | **Weight** | gross 42.5 kg, tare 2.5 kg | **PASS** | **net 40.0 computed by the platform**, not the phone |
| 6 | **Fat / quality** | FAT 4.2, SNF 8.5, CLR 27.0 | **PASS** | `fat 4.2`, `snf 8.5`, `clr 27.0` stored exactly |
| 7 | **Pricing** | Review screen | **PASS (refusal)** | `pricing_status: pricing_unavailable` — see §6 |
| 8 | **Accept** | Completed the capture | **PASS** | Parchi `SLP-2026-000001`, state `COMPLETED` |
| 9 | History | Centre history screen | **PASS** | Centre-scoped; the collection is listed |
| 10 | **Close session** | Confirm dialog → Close session | **PASS** | `status: closed`, `closed_at 16:46:00Z`, **0 open sessions** |
| 11 | Post-close integrity | — | **PASS** | Transaction still `COMPLETED` and readable after close |

**11 of 11 steps passed.** Two additional observations, both good:

- **Operational readiness: READY, 6 of 6 checks passing** — read on the device.
- **Design System V1 renders correctly on real hardware** — cream ground, milk
  cards, dairy-green primary actions, at real density on a real panel.

### 4.1 The parchi

`SLP-2026-000001`, dated `2026-08-26T22:06:48+05:30` — the **organisation's**
timezone, not the phone's, which is the behaviour DEMO-013 established and the
right one for a dairy whose operator's phone may be set to anything. The
operator is named on it. The rate line reads **"Rate pending"**.

### 4.2 The close, in full

The confirmation dialog is worth quoting because it is exactly what a
confirmation dialog should say:

> Closing "mobile" ends this shift at the centre. Collections already captured
> are unaffected; a new shift opens a new session.

It names the session, states the consequence, states what is *not* affected,
and says what happens next. The operator is not being asked to guess.

The platform's record afterwards:

```json
{ "id": "83e44f9e-8de6-4e93-80f7-d97e5adfb3db",
  "status": "closed", "label": "mobile",
  "opened_at": "2026-08-26T16:35:39.412319Z",
  "closed_at": "2026-08-26T16:46:00.968011Z" }
```

Open sessions for the centre: **zero**. The captured transaction: still there,
still `COMPLETED`. Closing a shift does not disturb the shift's work — which is
the guarantee, and it is now executed rather than asserted.

---

## 5. Findings

### D-1 — The operator is shown a permission key instead of a sentence (P2)

**What happens.** Tapping "Today's collection" shows a bare red
`reporting.read`. Tapping "Pricing test" shows **No resolution ·
`pricing.ratecard.read`**. A dairy operator learns nothing from either.

**What the platform actually sent.** A correct RFC-9457 problem document:

```json
{ "title": "forbidden", "status": 403,
  "detail": "You do not have permission to perform this action.",
  "extra": "pricing.ratecard.read" }
```

The sentence was there. The app discarded it.

**Root cause,** in `apps/mobile/lib/src/api.dart`:

```dart
detail = (decoded['detail'] ?? decoded['title'] ?? detail).toString();
final rawExtra = decoded['extra'];
...
} else if (rawExtra is String && rawExtra.isNotEmpty) {
  detail = rawExtra;      // ← unconditional
}
```

This is a **regression from a good fix**. P0-PILOT-004 found that on validation
refusals the platform localises `detail` generically ("The resource already
exists.") and carries the actionable specific in `extra` ("supplier is not
assigned to this collection center") — so `extra` was made to win. But on a
**403**, `extra` carries the permission *key* from the registry, which is a
machine identifier. One field, two meanings; the fix generalised the wrong one.

This is the same shape as the catalogue-without-callers lesson: the change was
right for the case in front of it and was never executed against the other case.

**Not a blocker.** It cannot occur anywhere on the collection path — every step
in §4 is inside the operator's grants. It is reachable in two taps from the
centre screen, so it should not ship to a pilot either.

**Fix (one line, not applied here — see §8):** prefer `detail` when the status
is 403, or when `extra` looks like a registry key rather than a sentence.

### D-2 — Screens offered to a role that cannot use them (P2)

`COLLECTION_OPERATOR` holds exactly six grants:

```
collection.center.read      operations.readiness.read
supplier.read               collection.session.manage
collection.transaction.record   collection.transaction.read
```

Neither `reporting.read` nor `pricing.ratecard.read` is among them, and neither
should be — **the platform's refusal is correct, and RBAC is working exactly as
designed.** The defect is that the centre toolbar shows six icons of which two
are dead for this persona, every time, for every operator.

The house pattern already exists in this same app —
`apps/mobile/lib/src/deliveries.dart` catches the refusal and degrades:

```dart
} on ApiException {
  report = null; // reporting is a separate grant; the round still works
}
```

The centre toolbar simply did not get it. The P1 audit named
"permission-aware toolbar (hide what `session.can()` refuses)" as a P2 item;
this is the physical-handset evidence for it.

### F-1 — "Rate pending" on the parchi (business question, not a defect)

Step 7 could not be exercised, because the seeded dairy has **no published rate
card** covering this centre, product and date. The platform said so precisely —
`pricing_unavailable`, *"no published rate card covers this center, product,
and date"* — and refused to invent a number. That is the correct engineering
behaviour and the review screen said it plainly.

Two things follow.

**For test coverage:** validating pricing end to end on hardware needs a
published rate card in the fixture. That is **test-data setup, not code**, and
it is the one part of §4 that is proven-by-refusal rather than
proven-by-computation.

**For the business:** the parchi printed **"Rate pending"**. Engineering cannot
answer whether that is acceptable at the counter. A farmer handing over 40 kg of
milk and receiving a slip with no rate on it is a real interaction with real
consequences, and somebody should decide deliberately whether the dairy is
allowed to be in that state — rather than discovering the answer during a
pilot. Flagged, not decided.

---

## 6. What this exercise proves that reading could not

Consistent with this repository's governing rule, the value is in what only
execution could surface:

- The **release manifest** defect (`7941331`) was invisible in every debug
  build and in every test, and would have made the first real release APK
  unable to open a socket.
- **D-1** is invisible from the code: the platform's contract is correct, the
  client's parsing is defensible, and only putting the two together on a screen
  shows an operator a registry key.
- The **timezone** behaviour on the parchi is only meaningful on a device whose
  own clock and locale are not the dairy's. This one's was not.
- **Post-close integrity** — that closing a shift leaves the shift's
  collections untouched — was asserted in a dialog and is now executed.

---

## 7. Pilot verdict

**The milk collection journey is ready for a pilot on real hardware,** with one
qualification and one decision outstanding.

**Ready:** every step from centre selection to session close works on a real
handset against a real backend, the platform's records agree with the phone at
every step, money-adjacent arithmetic (net weight) is computed by the platform
and not the device, quality readings survive round-trip exactly, the parchi
carries the dairy's own time, and closing a shift does not disturb its work.

**Qualification — pricing is proven only by refusal.** Step 7 has never been
executed on hardware with a real rate card. Before a pilot, publish a rate card
in the pilot dairy's data and re-run §4 steps 7–8. This needs no code.

**Decision outstanding — F-1.** Whether a "Rate pending" parchi is acceptable
at the counter is the business's call, and it should be made before a farmer
sees one.

**Recommended before pilot (neither is a blocker):** fix D-1, apply D-2. Both
are small, both are in the mobile client, and both are the difference between
an operator who understands what the app is telling them and one who does not.

---

## 8. Why nothing was changed

The work order was explicit: *"If the handset can run the existing app without
code changes, stop and give me the exact manual test procedure instead of
modifying anything."*

It could, so this stops here. The setup procedure is §3, the test procedure is
§4, and D-1 and D-2 are described precisely enough to be fixed on a word from
the owner. `git status` is clean apart from this document.

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-26 | Engineering | The complete operator journey — centre, open session, supplier, milk entry, fat/quality, pricing, accept, close session — executed on a physical moto g57 power (Android 16) against a real backend and real PostgreSQL, driven by `adb` and verified independently over HTTP at every step. Eleven of eleven steps passed; parchi `SLP-2026-000001` issued and session `83e44f9e` closed with the collection intact. No production code changed. Three findings, none blocking: D-1, the mobile client shows a raw permission key (`reporting.read`, `pricing.ratecard.read`) because a string `extra` unconditionally overrides `detail` — a regression from the P0-PILOT-004 fix, which is right for validation refusals and wrong for 403s; D-2, two centre-toolbar screens are offered to a `COLLECTION_OPERATOR` who holds neither grant, where the graceful pattern already exists in `deliveries.dart`; F-1, pricing is proven only by refusal because the fixture has no published rate card, and the parchi prints "Rate pending" — a business decision, flagged not decided (P1-PRODUCT-READINESS-001). |
