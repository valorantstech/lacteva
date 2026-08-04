---
id: BR-REGISTER
title: Business Rules Register
type: reference
status: Approved
version: "1.9"
owner: Architecture Board
created: 2026-08-03
last-updated: 2026-08-05
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

## BR-0005 — Monetary calculation is Decimal-only under an explicit rounding policy.

**Clarification.** No float arithmetic may touch money: values enter the money domain via `Decimal(str(x))` (artifact-free), and arithmetic methods reject non-Decimal factors with `TypeError`. Every rounding step names a policy from the platform registry (`HALF_UP` default — commercial convention; `HALF_EVEN`; `DOWN`), resolved request-override → tenant configuration (`pricing.rounding_policy`) → platform default, and quantizes to the currency's minor units (`Money.precision`, default 2).

**Enforcement.** `core/types.py` — `Money.multiplied_by()` (TypeError guard, policy registry, quantize); `pricing/calculator.py` — `PricingCalculator`, `_rounding_policy()`.

**Verification.** `test_pricing_types.py::test_money_multiplied_by_rejects_float_factor`, `::test_money_multiplied_by_policies_differ_on_ties`; `test_pricing_calculator_domain.py` (precision/rounding suite); `test_pricing_calculation_api.py` policy-resolution tests.

**Status:** Active (since PRC-004).

---

## BR-0006 — Every calculation result carries a complete trace.

**Clarification.** A monetary result without its explanation is unauditable. Each calculation returns an ordered trace (`inputs → normalize → multiply → round`) with exact Decimal string values at every step, including the unrounded raw amount, the policy, and the precision applied — plus the resolution provenance (which rate card, matrix, and band produced the unit price).

**Enforcement.** `pricing/calculator.py` — `TraceStep`, `Calculation.trace`, `ResolutionTraceRef` (frozen value objects).

**Verification.** `test_pricing_calculator_domain.py::test_trace_*`; `test_pricing_calculation_api.py::test_trace_via_api`.

**Status:** Active (since PRC-004).

---

## BR-0007 — Pricing calculation is deterministic.

**Clarification.** The same input always produces the same monetary output and the same trace. The domain calculator is pure — no I/O, no clock, no randomness (timestamps and calculation ids are applied by the application layer and are explicitly *identity*, not money).

**Enforcement.** `pricing/calculator.py` — `PricingCalculator` (pure domain service).

**Verification.** `test_pricing_calculator_domain.py::test_same_input_same_output`; `test_pricing_calculation_api.py::test_deterministic_via_api`.

**Status:** Active (since PRC-004).

---

## BR-0008 — A Pricing Calculation can belong to only one Settlement.

**Clarification.** Among *live* (non-cancelled) settlements, a calculation id appears in at most one settlement line; cancelling a settlement releases its calculations for re-settlement. Lines are built from the server-verified calculation record (the durable `pricing.calculated.v1` event) — amounts are never client-supplied.

**Enforcement.** `settlement/service.py` — `_assert_calculation_unsettled()`, `_verified_calculation()`; DB unique `(settlement_id, calculation_id)`.

**Verification.** `test_settlements.py::test_calculation_settled_elsewhere_rejected`, `::test_same_calculation_twice_in_settlement_rejected`, `::test_cancel_releases_calculations`; `test_settlement_lifecycle.py::test_finalized_calculation_stays_settled`.

**Status:** Active (since SET-001).

---

## BR-0009 — Settlements cannot overlap for the same supplier and period.

**Clarification.** Periods are CLOSED date ranges (sharing a single day overlaps); the rule keys on the supplier alone — a different collection center does not permit an overlapping settlement. Cancelled settlements release their period.

**Enforcement.** `settlement/service.py` — `_assert_no_period_overlap()` at create.

**Verification.** `test_settlements.py::test_overlapping_period_same_supplier_rejected`, `::test_shared_boundary_day_overlaps`, `::test_adjacent_period_allowed`, `::test_overlap_rule_is_supplier_wide_across_centers`, `::test_cancelled_settlement_releases_period`.

**Status:** Active (since SET-001).

---

## BR-0010 — Finalized Settlements are immutable.

**Clarification.** Finalization (CAS-protected, requires calculated status and ≥1 line) permanently freezes the settlement: no line changes, no recalculation, no cancellation. Cancelled preserves history (lines remain visible) but is equally terminal.

**Enforcement.** `settlement/service.py` — `_require_open()` on every mutation; CAS `finalize()`.

**Verification.** `test_settlement_lifecycle.py::test_finalized_settlement_is_immutable`, `::test_cancel_preserves_history`, `::test_cancel_twice_rejected`.

**Status:** Active (since SET-001).

---

## BR-0011 — Settlement totals must equal the sum of Settlement Lines.

**Clarification.** Totals are exact Decimal sums (BR-0005 applies — `Money.plus`, no rounding step); any line change reverts the settlement to draft so stale totals cannot be finalized; `finalize()` re-verifies the equality as an integrity gate; the detail view surfaces `totals_match_lines` for review screens. Net = gross + adjustments (adjustments fixed at 0 until the bonus/penalty/tax engines).

**Enforcement.** `settlement/service.py` — `calculate_totals()`, `_sum_lines()`, the draft-revert in `add_calculation()`/`remove_line()`, the finalize integrity gate.

**Verification.** `test_settlement_lifecycle.py::test_calculate_totals_sums_lines_exactly`, `::test_line_change_reverts_to_draft`, `::test_finalize_integrity_gate_detects_tampered_lines`, `::test_detail_flags_totals_mismatch_after_tamper`.

**Status:** Active (since SET-001).

---

## BR-0012 — Duplicate transaction references are not allowed.

**Clarification.** A collection-transaction id may be referenced by at most one line among live settlements (double settlement = double payment); lines without a transaction reference may coexist freely. DB uniqueness backs the in-settlement case; the cross-settlement case is service-enforced.

**Enforcement.** `settlement/service.py` — `_assert_transaction_unsettled()`; DB unique `(settlement_id, transaction_id)`.

**Verification.** `test_settlements.py::test_duplicate_transaction_reference_rejected`, `::test_duplicate_transaction_across_settlements_rejected`, `::test_lines_without_transaction_ids_can_coexist`.

**Status:** Active (since SET-001).

---

## BR-0013 — Consumers never affect business transactions.

**Clarification.** Event consumers process the durable outbox log AFTER business transactions commit, in their own isolated per-event transactions. No consumer failure, retry, or dead-letter can roll back, block, or slow a business write. Producers never know consumers exist (consumers live in the separate `platform_core.consumers` package; business modules import nothing from it).

**Enforcement.** `event_relay/consumers.py` — `ConsumerRunner` (own session factory, per-event commit, failure recorded out-of-band); package separation.

**Verification.** `test_event_consumers.py::test_consumer_failure_never_affects_business_flow`, `::test_handler_writes_roll_back_on_failure`, `::test_multiple_consumers_isolated`.

**Status:** Active (since SPRINT-008B).

---

## BR-0014 — An event is processed at most once per consumer.

**Clarification.** The idempotency ledger (`consumer_execution`, unique per consumer+event) guarantees exactly-once effects per consumer even under duplicate delivery, cursor rewinds, replays, or crash-recovery reruns. Handler writes commit atomically with the ledger entry: an event is either fully processed with its record, or not at all. Dead-lettered events (after 5 attempts with exponential backoff) advance the cursor to unblock ordering and remain replayable forever.

**Enforcement.** `event_relay/consumers.py` — `_process()` ledger check, atomic outcome recording, `replay_execution()`; DB unique `(consumer_name, event_id)`.

**Verification.** `test_event_consumers.py::test_idempotency_run_twice_no_double_counting`, `::test_duplicate_delivery_of_same_event_id_skipped`, `::test_crash_recovery_resumes_from_cursor`, `::test_replay_dead_execution`.

**Status:** Active (since SPRINT-008B).

---

## BR-0015 — Every projection must be fully rebuildable from the event log.

**Clarification.** Derived read models are never precious: the durable outbox log is the source of truth, and any projection can be reconstructed from it exactly. Projections therefore read event payloads ONLY — never transactional tables — and replay uses the projection's own handler, so a rebuilt projection cannot diverge from an incrementally-built one. A version bump marks stored data outdated until a *completed* rebuild claims the new version; cancelled and failed replays claim nothing. Verification proves the rule by shadow-replaying the log and comparing (always rolled back).

**Enforcement.** `event_relay/projections.py` — `Projection` (declares owned models + version), `ProjectionRebuilder.rebuild()/reset()/verify()`; registration rejects projections that declare no models.

**Verification.** `test_projections.py::test_rebuild_reconstructs_from_the_log`, `::test_rebuild_from_empty_state_is_identical`, `::test_deep_verify_detects_drift`, `::test_version_bump_marks_projection_outdated`, `::test_rebuild_repopulates_ledger_and_cursor`.

**Status:** Active (since PLT-001).

---

## BR-0016 — A business module never sends a message; notifications originate only from durable domain events.

**Clarification.** No business module may call an SMS, email, or push provider — directly or through a helper. A module's only obligation is to emit its domain event through the outbox with enough payload for a message to be composed later. The notification consumer reads that durable log and decides what to send. This makes messaging a consequence of committed business facts rather than a side effect of a request: a rolled-back transaction can never produce a message, an unsent message can always be replayed from the log, and a provider outage can never fail a milk collection. Recipients are resolved from a rebuildable directory projection (BR-0015), never by calling back into a business module.

**Enforcement.** `consumers/notification_dispatch.py` (the sole dispatch path); `notification/service.py` — `NotificationRequest` accepts a template key, never a message; producers (`auth`, `organization`, `supplier`, `settlement`, `milk_collection`) hold no notifier dependency; `consumers/supplier_directory.py` resolves recipients from projected data.

**Verification.** `test_notifications.py::test_business_modules_never_send_directly`, `::test_supplier_registration_sends_a_welcome_sms`, `::test_password_reset_notification_from_the_event`, `::test_settlement_finalized_notification`, `::test_recipient_directory_is_rebuildable`.

**Status:** Active (since NOT-001).

---

## BR-0017 — Every outbound message is rendered from a registered template and delivered at most once.

**Clarification.** No message text exists outside the template registry: a template is identified by (key, channel, language), declares the variables it needs, and refuses to render when any are missing — a farmer never receives a half-substituted message. Language resolves to the requested locale or falls back to the platform default, so a market can ship one locale at a time without breaking delivery. Delivery is idempotent on (event, template, channel): duplicate consumption, cursor rewinds, and consumer replays re-examine an existing notification rather than sending a second message. Delivery failure is a property of the notification, not of the event — the event was processed correctly — so a failed send retries on the consumer framework's backoff schedule and dies after the same attempt budget, leaving its history intact.

**Enforcement.** `notification/templates.py` — `get_template()` fallback, `render()` missing-variable error; `notification/models.py` — unique `(event_id, template_key, channel)`; `notification/service.py` — `dispatch()` idempotency check, `_record_failure()` using `backoff_delay` and `MAX_CONSUMER_ATTEMPTS`.

**Verification.** `test_notifications.py::test_missing_variables_are_an_error_not_a_broken_message`, `::test_language_resolution_and_fallback`, `::test_duplicate_event_processing_does_not_resend`, `::test_consumer_replay_does_not_resend`, `::test_failed_delivery_retries_and_succeeds`, `::test_delivery_dies_after_max_attempts`, `::test_backoff_grows_between_attempts`.

**Status:** Active (since NOT-001).

---

## BR-0018 — Payments consume finalized settlements and never exceed the payable.

**Clarification.** Only a FINALIZED settlement can be paid: a draft or calculated settlement is still changing, and paying a moving number is how disputes start. A payment allocates against one or more settlements of ONE supplier in ONE currency — currency conversion is not a payment operation. The sum of LIVE allocations (draft, pending, processing, completed) against a settlement must never exceed its net payable, which is what makes the outstanding balance computable and what prevents the same money being paid twice. A draft allocation reserves: it is an intent that must stop a second payment being built for money the first already claims. Failure and cancellation release the reservation, so the settlement becomes payable again. Payments never write to settlements — the payable is read, the allocation lives on the payment side.

**Enforcement.** `payment/service.py` — `_payable_settlement()` (finalized, same supplier, same currency), `_resolve_allocation()` (outstanding check, positive amount), `_allocations_for()` (LIVE_STATUSES sum); `payment/models.py` — `LIVE_STATUSES`, unique `(payment_id, settlement_id)`.

**Verification.** `test_payments.py::test_only_finalized_settlements_can_be_paid`, `::test_over_allocation_is_rejected`, `::test_second_payment_for_a_fully_allocated_settlement_is_rejected`, `::test_partial_over_allocation_across_two_payments_is_rejected`, `::test_cancelled_payment_releases_the_allocation`, `::test_failed_payment_releases_the_allocation`, `::test_payment_never_modifies_the_settlement`, `::test_currency_mismatch_is_rejected`.

**Status:** Active (since PAY-001).

---

## BR-0019 — A completed payment is immutable, and every execution attempt is recorded.

**Clarification.** Money that has moved cannot be un-moved by editing a record: once a payment completes it accepts no transition — not submit, not fail, not cancel — and corrections are new payments, never edits. Before completion the lifecycle is draft → pending → processing → completed | failed, with cancellation available from every pre-processing state; cancelling a *processing* payment is deliberately impossible because the money may already be in flight, and the truthful sequence is to record the failure first. Every execution opens a NEW attempt row carrying its number, provider, reference, operator, timestamps, and failure reason — a retry never reuses an attempt, so the failure history of a payment survives its eventual success. Every transition is CAS-guarded: two callers racing the same transition, exactly one wins.

**Enforcement.** `payment/service.py` — `_transition()` (immutability guards + `UPDATE … WHERE status IN (expected)` rowcount check), `_open_attempt()` / `_close_attempt()`, `retry()`; `payment/models.py` — unique `(payment_id, attempt_number)`.

**Verification.** `test_payments.py::test_completed_payment_is_immutable`, `::test_cancelled_payment_is_terminal`, `::test_processing_payment_cannot_be_cancelled`, `::test_retry_opens_a_new_attempt_and_can_succeed`, `::test_repeated_failures_accumulate_attempts`, `::test_concurrent_completion_only_succeeds_once`, `::test_concurrent_submit_only_succeeds_once`.

**Status:** Active (since PAY-001).

---

## BR-0020 — A receipt is generated only from a completed payment, and its content never changes.

**Clarification.** A receipt is evidence, and evidence that can be authored on demand or edited afterwards is not evidence. It is therefore produced ONLY by consuming `payment.completed.v1` off the durable log — never requested by a business module, and never issued for a draft, failed, or cancelled payment, which prove nothing. One completed payment generates exactly one receipt, enforced by a unique `(tenant, payment)` constraint rather than by convention, so consumer replay and duplicate delivery re-find the existing artifact instead of handing a farmer a second one. Because the content is frozen, the receipt COPIES everything it shows — supplier name, payment reference, settlement numbers, centers, periods, amounts — at generation time: re-deriving them later could show a different world, and a receipt must show the world as it was when the money moved. Receipts never write to payments or settlements. The only permitted mutation is the lifecycle marker (generated → delivered → archived); archived receipts remain fully queryable and renderable, and no update or delete path exists anywhere in the module.

**Enforcement.** `consumers/receipt_generation.py` (the sole generation path, subscribed to `payment.completed.v1`); `receipt/service.py` — `generate()` idempotency check, `_transition()` CAS with archived-is-terminal guard, no update/delete methods; `receipt/models.py` — unique `(tenant_id, payment_id)` and `(tenant_id, receipt_number)`, copied content columns.

**Verification.** `test_receipts.py::test_completed_payment_generates_a_receipt`, `::test_an_incomplete_payment_generates_nothing`, `::test_cancelled_payment_generates_nothing`, `::test_one_payment_generates_exactly_one_receipt`, `::test_consumer_replay_does_not_mint_a_second_receipt`, `::test_receipt_content_is_frozen_after_generation`, `::test_receipt_never_modifies_the_payment_or_settlement`, `::test_archived_receipts_are_terminal_but_queryable`, `::test_no_delete_or_edit_endpoint_exists`.

**Status:** Active (since RCP-001).

---

## BR-0021 — Offline changes how work reaches the platform, never what the platform decides.

**Clarification.** A device that collects milk without connectivity is a TRANSPORT problem, not a business one. Every operation captured offline is applied, on sync, by calling the same application service the online API calls, with the same authenticated principal, the same tenant context, and the same state machine — so a step the engine would refuse online is refused offline, a supplier who is archived is still archived, and a session that closed is still closed. The device therefore decides NOTHING it would not decide online: it never prices milk, never validates identity, never advances a state on its own authority; values the platform owns are reported as pending until sync resolves them. Replay is idempotent on a client-generated operation id, so a lost acknowledgement re-sends without duplicating a collection, and local identifiers are mapped to server ids across batches so an interrupted sync resumes rather than restarts. Every divergence discovered at sync time is returned as a structured conflict and surfaced to a human; nothing is ever silently overwritten. Offline never relaxes authorization: the sync endpoint requires the same permission as the online write.

**Enforcement.** `sync/service.py` — `_dispatch()` routes every kind to the online `MilkCollectionService` method (no business decision lives in the sync module), `push()` idempotency check on `(tenant, operation_id)`, `_resolve_target()` local-to-server mapping, `_classify()` structured conflicts; `api/routes.py` — the sync router reuses `collection.transaction.record`; `sync/models.py` — unique `(tenant_id, operation_id)`. On the device: `offline/offline_client.dart` records and projects but never computes a payable, and rethrows business errors instead of queueing them.

**Verification.** `test_offline_sync.py::test_a_whole_collection_captured_offline_lands_intact`, `::test_business_rules_are_identical_offline`, `::test_replaying_the_same_batch_creates_nothing_twice`, `::test_partial_batches_resume_across_pushes`, `::test_an_operation_whose_predecessor_never_landed_is_a_conflict`, `::test_archived_supplier_conflicts`, `::test_closed_session_conflicts`, `::test_changed_rate_card_is_flagged_but_the_collection_stands`, `::test_offline_never_bypasses_authorization`; `offline_test.dart` "a full collection can be captured with no connectivity", "the device never prices milk", "a business error from the platform is not swallowed by the queue".

**Status:** Active (since OFF-001).

---

## BR-0022 — Tenant isolation is enforced by the database, not only by the application.

**Clarification.** Every tenant-owned table carries a PostgreSQL row-level security policy comparing its `tenant_id` against a transaction-scoped session setting, so a query that forgets its filter returns NOTHING rather than another tenant's data. The application's own `tenant_id` predicates remain in place and become defense-in-depth: correctness no longer depends on every future query remembering them. The policy covers reads, updates, and deletes through `USING`, and writes through `WITH CHECK` — without the latter a caller could move a row INTO another tenant, succeeding silently. `FORCE` is mandatory because the application connects as the table owner, which would otherwise bypass its own policies. An unbound session matches nothing and therefore fails CLOSED. Cross-tenant machinery (relay dispatch, consumers, projection rebuilds, platform administration) may set an explicit, transaction-scoped, logged bypass — never a superuser connection. A new tenant-owned table without a policy is a build failure, not a latent leak.

**Enforcement.** `core/rls.py` — `bind_tenant()` (`SET LOCAL`, so a pooled connection cannot carry a tenant across requests), `bind_platform_context()`, `policy_statements()`; `core/db.py` — per-request binding; `api/deps.py` — re-binding once the token's tenant is proven; migration `a1c7f3b90e22` — the policy set.

**Verification.** `test_security.py::test_every_tenant_owned_table_is_covered_by_a_policy`, `::test_the_rls_policy_denies_by_default_and_checks_writes`, `::test_application_level_tenant_isolation_holds`; `test_rls_postgres.py::test_a_query_that_forgets_its_filter_still_cannot_leak`, `::test_cross_tenant_update_affects_nothing`, `::test_cross_tenant_delete_affects_nothing`, `::test_a_row_cannot_be_written_into_another_tenant`, `::test_no_tenant_bound_means_no_rows` (PostgreSQL job — a skip fails CI).

**Status:** Active (since SEC-001).

---

## BR-0023 — A token is trusted only when a named, live key verifies it.

**Clarification.** Tokens are signed RS256 and carry the `kid` of the key that signed them. Verification resolves exactly that key from the registry — an unknown, retired, or expired `kid` is a rejection, never a fallback to another key, and never an algorithm chosen from the token's own header (which is how `alg: none` and HS256-with-the-public-key downgrades succeed elsewhere). Rotation is additive: a new key signs while every unexpired predecessor still verifies, so no live session is invalidated by routine rotation; retirement is the emergency lever that kills every token a key signed, at once. Access tokens remain bound to a server-side session, so revocation is immediate rather than waiting out expiry, and a refresh token is single-use — presenting a spent one revokes the whole family, because the platform cannot distinguish the legitimate holder from a thief and must assume theft. Private key material never appears in source, in the JWKS document, or in the operations API.

**Enforcement.** `core/keys.py` — `KeyRegistry.current()/verification_key()/jwks()`; `core/security.py` — `decode_token()` (fixed algorithm list, issuer check, required claims, explicit skew leeway); `api/routes.py` — `/.well-known/jwks.json`, `/v1/_security/keys`.

**Verification.** `test_security.py::test_a_forged_token_signed_with_an_attacker_key_is_rejected`, `::test_algorithm_confusion_is_rejected`, `::test_an_unknown_kid_is_rejected`, `::test_rotation_keeps_existing_sessions_alive`, `::test_a_retired_key_stops_verifying_immediately`, `::test_refresh_replay_is_treated_as_theft`, `::test_jwks_publishes_only_public_material`.

**Status:** Active (since SEC-001).

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
| 1.9 | 2026-08-05 | Architecture Board | SEC-001 rules: BR-0022 (database-enforced tenant isolation), BR-0023 (tokens trusted only via a named live key). |
| 1.8 | 2026-08-05 | Architecture Board | OFF-001 rule: BR-0021 (offline changes transport, never business decisions). |
| 1.7 | 2026-08-05 | Architecture Board | RCP-001 rule: BR-0020 (receipts are generated only from completed payments and never change). |
| 1.6 | 2026-08-05 | Architecture Board | PAY-001 rules: BR-0018 (payments consume finalized settlements, never exceeding the payable), BR-0019 (completed payments are immutable; every attempt recorded). |
| 1.5 | 2026-08-05 | Architecture Board | NOT-001 rules: BR-0016 (business modules never send messages; notifications originate only from durable domain events), BR-0017 (every message rendered from a registered template, delivered at most once). |
| 1.4 | 2026-08-04 | Architecture Board | PLT-001 rule: BR-0015 (every projection is fully rebuildable from the event log). |
| 1.3 | 2026-08-04 | Architecture Board | SPRINT-008B rules: BR-0013 (consumers never affect business transactions), BR-0014 (at-most-once processing per consumer). |
| 1.2 | 2026-08-04 | Architecture Board | SET-001 rules: BR-0008 (one settlement per calculation), BR-0009 (no supplier-period overlap), BR-0010 (finalized immutable), BR-0011 (totals equal line sum), BR-0012 (no duplicate transaction references). |
| 1.1 | 2026-08-03 | Architecture Board | PRC-004 rules: BR-0005 (Decimal-only money with explicit rounding policy), BR-0006 (complete calculation trace), BR-0007 (deterministic calculation). |
| 1.0 | 2026-08-03 | Architecture Board | Register established with BR-0001…BR-0004 (rate card immutability, single-active-card scope, exactly-one resolution, non-overlapping bands). |
