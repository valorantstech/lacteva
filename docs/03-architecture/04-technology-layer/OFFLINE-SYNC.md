---
id: OFFLINE-SYNC
title: Offline Collection Sync
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-05
last-updated: 2026-08-05
related: [BR-REGISTER, PROJECTION-LIFECYCLE, CLAUDE-CONTEXT]
baseline: ARCH-BASELINE-V1
---

# Offline Collection Sync

How the Lacteva operator app collects milk with no connectivity and reconciles when it returns. Established by OFF-001.

**The guarantee (BR-0021):** offline changes how work *reaches* the platform, never what the platform *decides*.

## 1. The shape of the problem

Collection happens at 5 a.m. in a village with a queue of farmers and no signal. Three constraints follow, and they conflict:

1. The operator must never be blocked. Milk is perishable and the queue is real.
2. The business rules must not fork. A second implementation on the device would drift, and the two would disagree about what a farmer is owed.
3. Nothing may be lost or doubled. A device that dies mid-morning still holds the only record of what was poured.

The resolution is to treat the device as a **recorder, not a decider**. It captures what the operator did, durably, and replays it later; the platform judges it exactly as it would have judged it live.

## 2. What the device does — and does not

| Does | Does not |
| --- | --- |
| Append each step to a durable queue | Price milk |
| Give local ids to things not yet created | Validate a supplier's status |
| Show an echo of captured values (net weight) | Compute a payable amount |
| Advance a local projection so the wizard flows | Decide a state the engine would refuse |
| Rethrow business errors unchanged | Queue a 409 as if it were a network failure |

That last row matters more than it looks: a rejection from the platform is an *answer*. Only transport failures fall back to the queue, so a rule violation surfaces identically online and offline.

Values the platform owns are reported as `pending_sync`, never guessed. The operator sees "priced when this device syncs" rather than a number that might be wrong.

## 3. Storage and the queue

`OfflineStore` is a port with two adapters: an in-memory one (tests, and the fallback when no writable directory exists) and a **file store that writes to a temporary file and renames it over the target**. Rename is atomic, so a crash leaves either the previous complete queue or the new one — never a half-written file that loses a morning.

The queue holds pending requests, completed requests, the sync queue itself, the last sync timestamp, conflict metadata, local identifiers, and per-operation status — durable across app restart, device reboot, and crash. On load, operations stranded in `SYNCING` by a process death are returned to `PENDING`: replay is idempotent, so recovering them is safe and stranding them is not.

| State | Meaning |
| --- | --- |
| `PENDING` | Captured, waiting for connectivity |
| `SYNCING` | Handed to the server, outcome unknown |
| `SYNCED` | The platform applied it |
| `FAILED` | Transient failure; retried on exponential backoff (2s → 300s cap) |
| `CONFLICT` | The world moved on; needs a human |

Backoff deliberately mirrors the platform's own consumer retry schedule, so an operator and an engineer are looking at the same behaviour on both sides of the connection.

## 4. Identity across the gap

Offline, the device invents ids for things the server has not created. Each operation carries:

- `operation_id` — client-generated, the **idempotency key**
- `client_reference` — the local id this operation *creates*
- `target_ref` — the local-or-server id it *acts on*

The server records the mapping when an operation applies, so a later batch saying "weigh the transaction I created while offline" is understood. That mapping is what makes an interrupted sync **resumable** rather than restartable, and it is persisted server-side — so it survives the device losing its own state too.

## 5. Sync lifecycle

```
capture (offline)  →  PENDING
      │
      ▼
push batch  ──────►  POST /v1/sync/collection      (batched, ordered by sequence)
      │                    │
      │                    ├─ applied    → SYNCED
      │                    ├─ duplicate  → SYNCED   (the original outcome stands)
      │                    ├─ conflict   → CONFLICT (structured reason, human decides)
      │                    └─ failed     → FAILED   (backoff, automatic retry)
      ▼
network died  ────►  whole batch back to FAILED, nothing lost
```

Cancellation is honoured **between** batches: work already handed to the server has its outcome applied first, and anything not yet sent returns to `PENDING`. A cancel requested before a run starts is deliberately cleared — a stale flag must not silently abort the next sync.

## 6. Conflict resolution

The device is a single writer per shift (REVIEW-NOTES A7), so conflicts are not concurrent-edit races; they are the world having moved while the device was dark. Every one is returned as structured data and shown to a human.

| Reason | What happened | Applied? |
| --- | --- | --- |
| `already_accepted` | The transaction reached a terminal state elsewhere | no |
| `supplier_unavailable` | The supplier was archived since capture | no |
| `session_closed` | The collection session closed or expired | no |
| `unresolved_reference` | A predecessor operation never landed | no |
| `invalid_state` | The state machine refuses this step now | no |
| `rate_card_changed` | Pricing did not resolve as the device assumed | **yes** |

`rate_card_changed` is the interesting one. Milk is perishable and MVP-001 forbids blocking a collection on pricing, so the collection **stands** and the divergence is flagged instead of discarded. A conflict that applied is still a conflict: it needs a human, but the data is in.

Conflicts are never retried automatically — a retry would just re-derive the same answer. Only `failed` operations retry, on the device automatically and from the portal manually.

## 7. Authorization

The sync endpoint requires `collection.transaction.record` — the same permission as the online write. Offline is not a privilege escalation path: a principal who cannot record a collection online cannot record one by capturing it on a device first. The read-only monitor has its own `sync.read`.

## 8. Known limits

- **Single device per shift.** Concurrent offline writers on one center are out of scope (A7); two devices collecting the same session would produce conflicts rather than a merge.
- **No cached login.** The app reuses an existing authenticated session; it cannot perform a *first* login while offline, because that requires the platform.
- **Reference data is not pre-cached.** Supplier lookup by QR works offline only in the sense that the payload is captured and validated on sync — the operator cannot browse suppliers with no signal.
- **The queue is a work list, not an archive.** Synced history is pruned; the platform holds the record of truth.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Engineering | Established by OFF-001. |
