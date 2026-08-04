---
id: PROJECTION-LIFECYCLE
title: Projection Lifecycle & Replay
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-04
last-updated: 2026-08-04
related: [BR-REGISTER, CLAUDE-CONTEXT]
baseline: ARCH-BASELINE-V1
---

# Projection Lifecycle & Replay

How Lacteva builds, operates, verifies, and evolves **projections** — derived read models maintained from the durable event log. Established by PLT-001 as permanent platform infrastructure, before the projection count grows (Notifications, Offline, Analytics, AI).

**The guarantee (BR-0015):** every projection can be reconstructed, exactly, from the event log alone. Nothing derived is precious; the log is.

## 1. What a projection is

A projection is an [event consumer](../../ai/CLAUDE_CONTEXT.md) that owns read-model tables. It inherits every consumer guarantee — durable-log cursor, idempotency ledger, per-consumer ordering, exponential backoff, dead-letter queue, and total producer isolation (BR-0013/BR-0014) — and adds a lifecycle: metadata, rebuild, verification, and versioning.

Declaring one is a single class:

```python
class ReportingProjection(Projection):
    name = "reporting-projection"       # stable identity: keys cursor + ledger + state
    version = 1                          # bump when the derived shape changes
    owner_module = "reporting"           # the module whose read models these are
    description = "Daily, per-center and per-supplier collection totals."
    event_types = ("collection.transaction-completed.v1",)
    rebuild_strategy = "full-replay"
    replay_order = 10                    # ascending; lower rebuilds first
    models = (DailyTotals, CenterTotals, SupplierTotals)   # tables it owns

    async def handle(self, envelope, session): ...
```

`register_projection()` registers it as a projection **and** as a consumer — one declaration, both roles. Discovery imports `platform_core.consumers` at startup; there is exactly one discovery path.

**Rule: projections read event payloads only.** A projection must never query transactional tables — if it needs a fact, that fact belongs in the event. This is what makes replay meaningful and what lets read models scale independently of the write path.

## 2. States

| State | Meaning |
| --- | --- |
| `live` | Maintained incrementally by the consumer loop |
| `rebuilding` | A replay is in progress (progress and ETA are published) |
| `cancelled` | A replay was stopped; data is partial until rebuilt again |
| `failed` | A replay raised; the error is recorded and data is partial |
| `reset` | Rows and position cleared; the consumer loop will rebuild naturally |

**Health** is computed, not stored: `ok`, `outdated` (built version < code version), `rebuilding`, `degraded` (failed, stale rebuild, or dead-lettered events), `never_built`.

**Status is derived, never duplicated.** Position comes from the consumer cursor, processed counts from the ledger, pending counts from the log, row counts from the tables. `projection_state` stores only what cannot be derived: the built version, the rebuild story, and the cancel flag. There is therefore no second source of truth to drift.

## 3. Operations

| Operation | Endpoint | Notes |
| --- | --- | --- |
| Registry | `GET /v1/_projections` | Every projection with metadata, position, counts, health |
| Detail | `GET /v1/_projections/{name}` | Same shape, one projection |
| Rebuild | `POST /v1/_projections/{name}/rebuild` | `?dry_run=true` for a plan + ETA; `?batch_size=` to tune |
| Rebuild all | `POST /v1/_projections/rebuild-all` | In `replay_order` |
| Cancel | `POST /v1/_projections/{name}/cancel` | Honoured after the current batch |
| Verify | `POST /v1/_projections/{name}/verify` | `?deep=true` adds drift detection |
| Reset | `DELETE /v1/_projections/{name}/reset` | Clears rows + cursor + ledger |

All are platform-operations endpoints (`platform.relay.manage`), never tenant-facing.

**Rebuild** = count work → delete owned rows → clear cursor and ledger → stream the log in `(created_at, id)` order in batches → apply the projection's **own handler** → repopulate the ledger and cursor → record version, duration, and progress. Because replay uses the same handler as live processing, a rebuilt projection cannot diverge from an incrementally-built one.

Progress is committed per batch, so a concurrent `GET` sees `{total, done, percent, elapsed_seconds, eta_seconds}` while the replay runs; the cancel flag is read between batches.

**Reset without rebuild is a valid operation:** clearing rows and position lets the ordinary consumer loop rebuild the projection in the background at its own pace.

## 4. Versioning

Each projection declares a `version`. When the derived shape changes, bump it:

1. The registry immediately reports `health: outdated` and `verify` fails its `version` check — the stored data was built by older code.
2. `rebuild` replays the log through the new handler and stamps the new version.
3. Only a **completed** rebuild claims a version; cancelled and failed replays never do.

Old→new migration therefore needs no migration script for derived data: the new shape is computed from the log. Schema changes to projection tables still need an Alembic migration; the *data* is always replayed, never transformed in place.

## 5. Integrity verification

`verify` runs six checks; `deep=true` adds a seventh:

| Check | Detects |
| --- | --- |
| `version` | Stored data built by an older projection version |
| `corrupted_replay` | A replay that failed or has been "running" beyond the stale threshold |
| `missing_events` | Matching events the cursor has passed with no ledger entry |
| `dead_events` | Events dead-lettered for this projection |
| `duplicate_rows` | Natural-key duplicates (key read from the model's own unique constraint) |
| `unexpected_gaps` | Ledger count that disagrees with the log behind the cursor |
| `projection_drift` *(deep)* | Stored rows that disagree with a full replay of the log |

**Drift detection is a shadow replay:** the framework resets and replays into a transaction, snapshots the result, compares it with the live rows, and **always rolls back**. It is fully generic (it uses the projection's own handler) and never mutates data — verification cannot break what it inspects.

## 6. Operating guidance

- **After changing a handler's semantics:** bump `version`, deploy, then `rebuild`.
- **After a bug that corrupted derived data:** `verify --deep` to confirm drift, then `rebuild`.
- **Before a large rebuild:** `rebuild?dry_run=true` reports how many events would replay and an ETA measured from the previous rebuild's actual rate.
- **A rebuild is platform-scoped**, spanning all tenants, because the event log is global. Tenant-scoped rebuilds are future work.
- **Rebuilds run inline on the ops request today.** For very large logs, run them off-peak; a background job runner is the recorded scale path.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-04 | Engineering (PLT-001) | Initial projection lifecycle documentation: model, states, operations, versioning, verification, operating guidance. |
