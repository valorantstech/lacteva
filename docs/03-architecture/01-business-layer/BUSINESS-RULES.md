---
id: BR-REGISTER
title: Business Rules Register
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-03
last-updated: 2026-08-03
related: [STD-0003, CAP-0001]
baseline: ARCH-BASELINE-V1
---

# Business Rules Register

**This register is the source of truth for platform business rules.** Each rule has a permanent identifier `BR-NNNN` (scheme registered in [STD-0003 §5](../../00-standards/STD-0003-document-numbering.md)). Code enforces rules; tests verify them; documents cite them — but the rule itself is *defined here*. On conflict, this register wins over any restatement (per the [baseline](../../../ARCHITECTURE_BASELINE_V1.md) precedence rules); divergence between register and code is a defect, never silently resolved in either direction.

**Rule lifecycle.** Rules are appended with the next free number (never reused, never renumbered); changing a rule's meaning requires Architecture Board approval and a changelog entry; retired rules keep their ID with status `Retired`. Every rule entry names its **enforcement points** (code) and **verification** (tests) so the register stays checkable against reality.

**Entry format:** statement (normative, one sentence) · clarification (precise semantics) · enforcement · verification · status.

---

## BR-0001 — A published Rate Card is immutable.

**Clarification.** Publication freezes a rate card version forever: fields, center/product scope, and its pricing matrices and bands can never change again. Corrections happen on a *new version* created from the published card ([BR-0001] is why the new-version operation exists). Implementation is deliberately stricter than the minimum: editability ends at *submission* (draft-only editing), so reviewers approve exactly what publishes; publication then makes the freeze permanent. Archiving a published card preserves all of its history.

**Enforcement.** `pricing/service.py` — `_require_draft()` guard on every mutation (update, scope assignment), explicit 409 "published rate cards are immutable — create a new version"; `pricing/matrix.py` — `_require_card_draft()` on every matrix/row mutation.

**Verification.** `test_rate_card_publishing.py::test_published_card_is_immutable`, `::test_new_version_leaves_history_untouched`; `test_pricing_matrix.py::test_matrix_immutable_once_card_submitted`; `test_pricing_matrix_rows.py::test_rows_immutable_once_card_published`.

**Status:** Active (since Increment-001).

---

## BR-0002 — Only one published Rate Card may be active for the same scope.

**Clarification.** *Scope* = (collection center, product); *active* = published with an effective-date range covering the date in question (`effective_until = null` is open-ended). Therefore: for any (center, product, date) triple, at most one published rate card exists. Enforced preventively at publish time (overlap check) and defensively at resolution time (an observed violation is a `pricing_integrity` exception, never a silent choice — see [BR-0003]).

**Enforcement.** `pricing/service.py` — `_assert_no_published_overlap()` inside the CAS-protected `publish()`; `pricing/resolution.py` — `PricingIntegrityError` when `applicable_cards()` returns more than one.

**Verification.** `test_rate_card_publishing.py::test_overlap_same_scope_rejected`, `::test_non_overlapping_ranges_both_publish`, `::test_open_ended_card_blocks_future_ranges`, `::test_new_version_overlap_resolved_by_archiving_predecessor`; `test_pricing_resolution.py::test_duplicate_published_cards_raise_integrity`.

**Status:** Active (since Increment-001).

---

## BR-0003 — Resolution must return exactly one Pricing Matrix Row.

**Clarification.** For a valid pricing question (center, product, transaction date, quality dimension, reading), the Resolution Engine returns exactly one band. Zero matches yield a **structured business exception** (`pricing_no_match`, 422) naming the failing stage (`dimension` | `rate_card` | `matrix` | `band`), the reason, and the echoed inputs. More than one match at any stage yields a **business integrity exception** (`pricing_integrity`, 409) listing the candidates. The engine never silently chooses and never guesses.

**Enforcement.** `pricing/resolution.py` — `PricingResolutionService.resolve()` (staged exactly-one pipeline), `PricingResolutionError`, `PricingIntegrityError`.

**Verification.** `test_pricing_resolution.py` — the full suite: correct-resolution cases, every no-match stage, both integrity paths, determinism.

**Status:** Active (since PRC-003).

---

## BR-0004 — A Pricing Matrix Row range must never overlap.

**Clarification.** Among the *active* rows of one matrix, ranges are half-open `[from, to)` and pairwise disjoint. Adjacent bands sharing a boundary value (`[3,4)` + `[4,5)`) do **not** overlap — the shared value belongs to the upper band. Inactive rows are parked data and do not participate. Duplicates are total overlaps and therefore rejected. This rule is what makes [BR-0003]'s band stage deterministic.

**Enforcement.** `pricing/matrix.py` — `_require_no_overlap()` on row create/update (service-level, half-open predicate `_ranges_overlap`); DB check constraint `ck_matrix_row_range` (`to > from`); `pricing/resolution.py` — integrity exception if an overlap ever reaches resolution.

**Verification.** `test_pricing_matrix_rows.py::test_duplicate_range_rejected`, `::test_partial_and_containing_overlaps_rejected`, `::test_adjacent_ranges_allowed_half_open`, `::test_inactive_rows_do_not_block`, `::test_update_row_overlap_rejected_but_self_ok`; `test_pricing_resolution.py::test_overlapping_bands_raise_integrity`.

**Status:** Active (since Increment-002).

---

## Adding a Rule

1. Take the next free `BR-NNNN` (this register is the reservation; see STD-0003 §4).
2. Write the entry: normative statement, clarification, enforcement points, verification, status.
3. Land the enforcing code and tests in the same change set when the rule is new — a rule without enforcement is `Proposed`, not `Active`.
4. Cite the ID from code (`# BR-NNNN` beside the guard) and from documents (`[BR-NNNN]`).

**Backfill queue.** The platform enforces many pre-register rules that are not yet catalogued here (supplier lifecycle, center activation, readiness gating, milk-transaction state machine, matrix scope rules, …). They remain authoritative in code + tests until backfilled; backfilling them is an open documentation task and MUST NOT change their behavior.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-03 | Architecture Board | Register established with BR-0001…BR-0004 (rate card immutability, single-active-card scope, exactly-one resolution, non-overlapping bands). |
