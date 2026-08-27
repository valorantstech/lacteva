---
id: LACTEVA-RATE-CHART-QUESTIONNAIRE
title: Pilot Dairy Rate Chart & Collection Slip Questionnaire
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-PILOT-MASTER-ROADMAP, LACTEVA-COLLECTION-HARDWARE-AUDIT]
baseline: ARCH-BASELINE-V1
---

# Pilot Dairy Rate Chart & Collection Slip Questionnaire

**Why this document exists.** P0-BIZ-001 requires the platform to price milk
the way the pilot dairy actually prices it. No real rate chart has been
supplied to this repository, and **inventing one would poison the pilot** — the
first settlement would disagree with the dairy's own arithmetic and the trust
the pilot exists to build would be gone. So this document does two things:

1. records, honestly, what the platform can already do (so the conversation
   starts from capability, not from a blank page), and
2. asks the pilot dairy the specific questions whose answers configure — or
   redirect — the pricing engine.

**Who fills it in:** the dairy owner or accountant, with the pilot lead,
ideally sitting with a real paper rate chart and three real parchis on the
table. **One session, under an hour.**

---

## 1. What the platform already supports (no work needed)

Verified in code and tests on 2026-08-18:

| Capability | Where |
|---|---|
| Cow and buffalo priced from **separate charts** on one published rate card | `product_code_for()` → `RAW-COW-MILK` / `RAW-BUFFALO-MILK`, one matrix each; proven end-to-end in `test_cow_and_buffalo_price_differently_from_the_same_fat` |
| FAT-banded rates (half-open bands, e.g. `[3.5, 4.0) → ₹34.50`) | `PricingMatrixRow`; band arithmetic proven to the paisa on PostgreSQL |
| Draft → approve → publish lifecycle; published cards immutable; corrections are new versions | `RateCard` lifecycle (EPIC-001) |
| Effective-date windows (a card for the flush season, another after) | `effective_from` / `effective_until` |
| Per-centre scoping (different centres, different cards) | rate-card centre assignments |
| Morning/evening recorded on every collection | session label; shown on the slip |
| SNF and CLR **captured** on every collection | quality step; stored, shown on slip |
| Collection slip / parchi: numbered, printable, shareable text, bilingual (hi) | P0-BIZ-003, this milestone |

What the platform does **not** do today — the honest boundary:

* **SNF does not affect the price.** `PRICING_DIMENSION = "FAT"` (MVP-001):
  resolution is single-axis. A FAT × SNF grid or an SNF deduction rule is a
  known future increment, deliberately not guessed at.
* **No per-kg-FAT ("fat-kg") formula pricing.** Only banded rate-per-litre/kg.
* **No deductions or advances inside pricing.** BR-0011 currently pins
  settlement adjustments to zero-impact; advances/loans are a settlement
  feature, not a rate-chart feature.

---

## 2. The questionnaire

### A. The chart's shape (decides everything else)

1. **Show us the chart.** Photograph the actual board/paper chart(s) in use
   today, front and back. *(Attach to this document; nothing else in section A
   matters until this exists.)*
2. Is the rate decided by **FAT alone**, or by **FAT and SNF together**
   (a two-way grid), or by a **formula** (e.g. ₹ per kg of fat, "fat rate ×
   fat %")? Circle one — or describe the hybrid.
3. If FAT-banded: what is the band width (0.1? 0.5?), the lowest FAT you buy,
   and the highest on the chart?
4. If SNF matters: is it a second full grid, or a **deduction** (e.g. "−₹0.50
   per 0.1 SNF below 8.5")?
5. Do you buy by **litre or by kilogram**? If litres, do you convert weight →
   volume, and at what density?

### B. Cow, buffalo, mixed

6. Separate charts for cow and buffalo? *(The platform is ready for yes.)*
7. Is **mixed** milk bought at its own chart, at the cow chart, or refused?
8. Any other milk (goat)? At what chart?

### C. Time and season

9. Do morning and evening pay **the same rate** from the same chart?
   *(The platform records the shift either way.)*
10. How often does the chart change (seasonally? monthly? when the union
    circular arrives?), and who decides? *(Maps to card versions + effective
    dates; the approver becomes the card's approver.)*
11. When a new chart arrives mid-day, does it apply from the next shift, the
    next day, or retroactively?

### D. Rejection and edge cases

12. Below what FAT / above what adulteration signal do you **refuse** milk?
13. Is refused milk recorded anywhere today? *(The platform issues a numbered
    REJECTED parchi — is that acceptable to your farmers?)*
14. What happens when the analyzer is down — flat rate, yesterday's reading,
    or hold the sample?

### E. Deductions, advances, rounding

15. Any standing deductions at collection time (feed, advance recovery,
    society commission)? Per-litre or per-settlement?
16. How do you round: the **rate** (paise?), the **line amount**, the
    **settlement total**? Half-up?
17. Settlement cycle: 10 days? Fortnight? Month? From which day?

### F. The parchi (validates P0-BIZ-003 against reality)

18. Compare the platform's slip to your current parchi (samples below in §4).
    What is **missing**? What is on ours that you never print?
19. Language: Hindi + English acceptable? Any local-language need?
20. Does the farmer get the parchi **on paper** today, and must that continue?
    (Thermal printer? Handwritten book? SMS/WhatsApp acceptable as the copy?)

### G. Equipment at the centre (hardware boundary, PSP-0007)

21. What weighs the milk (electronic scale — make/model? beam balance?) and
    what analyzes it (Ekomilk/Lactoscan/other — make/model, connection ports)?
22. Who types/reads the values today, and who would operate Lacteva at the
    centre?
23. Is there a printer at the centre? Power reliability? Network (4G? WiFi?
    dead zones)?

---

## 3. The hardware integration boundary (documented, NOT implemented)

P0-BIZ-001/003 deliberately implement **no device integration**. The seam the
platform already holds, end to end:

```
HARDWARE (scale / analyzer)          — pilot: operator reads the display
   ↓ future CONNECTOR                — adapter behind the hardware port;
                                       mocks exist and are production-refused
TRANSACTION (weight_source /         — TODAY: "manual"; a device sets its own
             quality_source)           source name; schema needs NO change
   ↓
RATE (published card → matrix →      — resolution never knows or cares where
      band)                            the reading came from
   ↓
SETTLEMENT (period aggregation,      — sums stored amounts; source-agnostic
            BR-0011)
   ↓
PARCHI (slip, P0-BIZ-003)            — prints the reading AND its source
```

The single rule: **a device changes only the `*_source` value and who types
the number. Nothing downstream of the transaction knows the difference.** That
is why answering §G is discovery, not engineering — per the hardware audit,
the pilot runs on the Basic/Standard profile (operator-entered readings) with
zero integration work.

---

## 4. Data sheets to collect alongside the chart

* **Farmer list** — name, code (if any), phone, village, cow/buffalo, usual
  morning/evening litres. (The supplier import exists; this fills it.)
* **Three real parchis** — one accepted cow, one accepted buffalo, one
  rejected/edge case. These validate the slip field-for-field.
* **One completed settlement** — a real 10-day/fortnight statement, so the
  first Lacteva settlement can be reconciled against the dairy's own
  arithmetic to the paisa.
* **The current chart(s)** — photographed (§A.1), and the date each came into
  force.

---

## 5. What happens with the answers

| Answer pattern | Action | Size |
|---|---|---|
| FAT-banded, per milk type | **Configuration only**: create card + two matrices, publish | Hours |
| FAT bands + SNF deduction | Small pricing increment (deduction step after band resolution) | Work order |
| Full FAT × SNF grid | The multi-dimension increment MVP-001 already names | Work order |
| Per-kg-fat formula | New calculator strategy beside the band resolver | Work order |
| Deductions/advances at collection | Settlement-side feature; BR-0011 revision with its own proofs | Work order |

Nothing in this milestone pre-implements any row of that table. The chart the
dairy hands over decides which row runs — that is the point of asking.

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Initial questionnaire: platform capability register, dairy questions A–G, hardware boundary, data sheets, answer→action map (P0-BIZ-001). |
