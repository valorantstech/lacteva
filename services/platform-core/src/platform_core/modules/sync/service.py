"""Sync module — application service (OFF-001: Offline Collection Sync).

This service is a TRANSPORT, not a second implementation of collection. Every
operation is applied by calling the very same `MilkCollectionService` method
the online API calls, with the same authenticated principal and the same
tenant context — so a rule cannot execute differently because the operator
happened to be offline (BR-0021). If this file ever contains a business
decision, the design has failed.

Three problems it does solve, all of them transport problems:

1. **Idempotent replay.** A device that loses its acknowledgement re-sends.
   The client-generated `operation_id` is the key; the second attempt returns
   the FIRST outcome rather than creating a second transaction.

2. **Local identifiers.** Offline, the device invents ids for things the
   server has not created yet. Operations carry `client_reference` (the local
   id this operation creates) and `target_ref` (what it acts on), and the
   resolver maps local to server across batches — which is what makes
   interrupted, partial synchronisation resumable.

3. **Conflicts.** The world moves while a device is dark. Every failure the
   business services raise is classified and returned as structured data;
   nothing is ever silently overwritten.
"""

import time
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.metrics import (
    SYNC_BATCH_SECONDS,
    SYNC_CONFLICTS,
    SYNC_OPERATIONS,
)
from platform_core.core.tenancy import require_current_tenant
from platform_core.modules.milk_collection.models import CollectionSession
from platform_core.modules.milk_collection.service import (
    IdentifySupplierCommand,
    MilkCollectionService,
    MilkInfoCommand,
    QualityCommand,
    RejectCommand,
    WeightCommand,
)
from platform_core.modules.sync.models import SyncOperation

# Operation kinds a device may replay. Each maps 1:1 onto an online endpoint —
# there is deliberately no kind that has no online equivalent.
OPERATION_KINDS = (
    "open_session",
    "close_session",
    "create_transaction",
    "identify_supplier",
    "receive_milk",
    "capture_weight",
    "capture_quality",
    "accept",
    "reject",
    "complete",
    "cancel",
)

# Kinds that create an entity the device gave a local id to.
CREATING_KINDS = ("open_session", "create_transaction")


# --- DTOs ------------------------------------------------------------------


class SyncOperationInput(BaseModel):
    operation_id: uuid.UUID  # client-generated idempotency key
    kind: str
    sequence: int = 0
    client_reference: str | None = None  # local id this operation creates
    target_ref: str | None = None  # local-or-server id it acts on
    payload: dict = {}
    recorded_at: datetime | None = None  # when the operator did it, on device


class SyncBatchInput(BaseModel):
    device_id: str = Field(default="", max_length=80)
    operations: list[SyncOperationInput] = Field(default_factory=list)


class ConflictInfo(BaseModel):
    reason: str
    detail: str


class SyncOperationResult(BaseModel):
    operation_id: uuid.UUID
    kind: str
    status: str  # applied | duplicate | conflict | failed
    applied: bool  # a conflict may still have landed (see rate_card_changed)
    client_reference: str | None = None
    server_id: uuid.UUID | None = None
    conflict: ConflictInfo | None = None
    error: str | None = None


class SyncBatchResult(BaseModel):
    accepted: int
    applied: int
    duplicates: int
    conflicts: int
    failed: int
    results: list[SyncOperationResult]
    server_time: datetime


class SyncOperationView(BaseModel):
    id: uuid.UUID
    operation_id: uuid.UUID
    device_id: str
    kind: str
    sequence: int
    client_reference: str | None
    target_ref: str | None
    status: str
    applied: bool
    server_id: uuid.UUID | None
    conflict_reason: str | None
    conflict_detail: str | None
    error: str | None
    attempts: int
    recorded_at: datetime | None
    created_at: datetime
    applied_at: datetime | None

    model_config = {"from_attributes": True}


class SyncOperationPage(BaseModel):
    items: list[SyncOperationView]
    total: int
    limit: int
    offset: int


class DeviceSyncView(BaseModel):
    device_id: str
    operations: int
    conflicts: int
    failed: int
    last_sync_at: datetime | None


class SyncStatsView(BaseModel):
    total: int
    by_status: dict[str, int]
    by_kind: dict[str, int]
    conflicts: int
    failed: int
    devices: list[DeviceSyncView]
    last_sync_at: datetime | None


class SyncService:
    def __init__(self, session: AsyncSession, collection: MilkCollectionService):
        self._session = session
        self._collection = collection

    # --- replay -----------------------------------------------------------

    async def push(self, batch: SyncBatchInput, *, actor_id: uuid.UUID) -> SyncBatchResult:
        """Replay a batch of device operations, in order, idempotently."""
        tenant_id = require_current_tenant()
        # Local -> server ids learned in THIS batch, seeded from earlier ones
        # on demand. Ordering matters: a transaction is created before it is
        # weighed, so the resolver is filled as the batch progresses.
        resolved: dict[str, uuid.UUID] = {}
        results: list[SyncOperationResult] = []

        started = time.perf_counter()
        for op in sorted(batch.operations, key=lambda o: o.sequence):
            existing = await self._session.scalar(
                select(SyncOperation).where(
                    SyncOperation.tenant_id == tenant_id,
                    SyncOperation.operation_id == op.operation_id,
                )
            )
            if existing is not None and existing.status != "failed":
                # Idempotent replay: hand back the original outcome.
                existing.attempts += 1
                if existing.client_reference and existing.server_id:
                    resolved[existing.client_reference] = existing.server_id
                results.append(self._result(existing, duplicate=True))
                continue

            result = await self._apply(
                op,
                tenant_id=tenant_id,
                device_id=batch.device_id,
                actor_id=actor_id,
                resolved=resolved,
                record=existing,
            )
            if result.client_reference and result.server_id:
                resolved[result.client_reference] = result.server_id
            results.append(result)

        SYNC_BATCH_SECONDS.observe(time.perf_counter() - started)
        for result in results:
            SYNC_OPERATIONS.labels(result.kind, result.status).inc()
            if result.conflict is not None:
                SYNC_CONFLICTS.labels(result.conflict.reason).inc()
        return SyncBatchResult(
            accepted=len(results),
            applied=sum(1 for r in results if r.status == "applied"),
            duplicates=sum(1 for r in results if r.status == "duplicate"),
            conflicts=sum(1 for r in results if r.status == "conflict"),
            failed=sum(1 for r in results if r.status == "failed"),
            results=results,
            server_time=utcnow(),
        )

    async def retry(self, operation_id: uuid.UUID, *, actor_id: uuid.UUID) -> SyncOperationView:
        """Re-apply a failed operation from its stored payload (portal action).

        Only failures are retryable — a conflict needs a human decision, and
        an applied operation must never run twice.
        """
        tenant_id = require_current_tenant()
        record = await self._session.scalar(
            select(SyncOperation).where(
                SyncOperation.tenant_id == tenant_id,
                SyncOperation.operation_id == operation_id,
            )
        )
        if record is None:
            raise NotFoundError("sync operation not found")
        if record.status != "failed":
            raise ConflictError(
                f"only failed operations can be retried — this one is {record.status}"
            )
        op = SyncOperationInput(
            operation_id=record.operation_id,
            kind=record.kind,
            sequence=record.sequence,
            client_reference=record.client_reference,
            target_ref=record.target_ref,
            payload=record.payload or {},
            recorded_at=record.recorded_at,
        )
        await self._apply(
            op,
            tenant_id=tenant_id,
            device_id=record.device_id,
            actor_id=actor_id,
            resolved={},
            record=record,
        )
        await self._session.flush()
        return SyncOperationView.model_validate(record)

    # --- the single application path --------------------------------------

    async def _apply(
        self,
        op: SyncOperationInput,
        *,
        tenant_id: uuid.UUID,
        device_id: str,
        actor_id: uuid.UUID,
        resolved: dict[str, uuid.UUID],
        record: SyncOperation | None,
    ) -> SyncOperationResult:
        if record is None:
            record = SyncOperation(
                tenant_id=tenant_id,
                operation_id=op.operation_id,
                device_id=device_id,
                operator_id=actor_id,
                kind=op.kind,
                sequence=op.sequence,
                client_reference=op.client_reference,
                target_ref=op.target_ref,
                payload=op.payload,
                recorded_at=op.recorded_at,
            )
            self._session.add(record)
        else:
            record.attempts += 1

        if op.kind not in OPERATION_KINDS:
            return self._fail(record, f"unknown operation kind {op.kind!r}")

        try:
            target = await self._resolve_target(op, tenant_id, resolved)
        except _UnresolvedReference as exc:
            return self._conflict(record, "unresolved_reference", str(exc))

        try:
            entity = await self._dispatch(op, target, actor_id=actor_id)
        except NotFoundError as exc:
            return self._conflict(record, self._classify(op.kind, str(exc)), str(exc))
        except ConflictError as exc:
            return self._conflict(record, self._classify(op.kind, str(exc)), str(exc))

        record.status = "applied"
        record.applied = True
        record.server_id = entity.id
        record.applied_at = utcnow()
        record.conflict_reason = None
        record.conflict_detail = None
        record.error = None
        await self._session.flush()

        # A completed collection that could not be priced means the applicable
        # rate card is not what the device assumed. The collection STANDS —
        # milk is perishable and MVP-001 forbids blocking on pricing — but the
        # divergence is surfaced rather than swallowed.
        if op.kind == "complete" and getattr(entity, "pricing_status", None) not in (
            None,
            "priced",
        ):
            record.status = "conflict"
            record.conflict_reason = "rate_card_changed"
            record.conflict_detail = (
                "collection recorded, but pricing did not resolve at sync time "
                f"({getattr(entity, 'pricing_status', 'unknown')}) — the applicable "
                "rate card differs from what the device assumed"
            )
            await self._session.flush()

        return self._result(record)

    async def _dispatch(self, op: SyncOperationInput, target: Any, *, actor_id: uuid.UUID):
        """Route to the online service method. No business logic lives here."""
        payload = op.payload or {}
        service = self._collection
        match op.kind:
            case "open_session":
                center_id = uuid.UUID(str(payload["center_id"]))
                try:
                    return await service.open_session(
                        center_id,
                        payload.get("label", "mobile-offline"),
                        actor_id=actor_id,
                    )
                except ConflictError:
                    # P0-PILOT-004, found in a real airplane-mode drill on the
                    # first physical handset: a device that could not SEE the
                    # centre's open session opened its own local one. Refusing
                    # the replay stranded the entire offline capture behind an
                    # unmappable local session id — a whole morning of
                    # collections in "conflict" because yesterday's session was
                    # still open. The operator's intent is "an open session at
                    # this centre"; if one exists, it IS the answer, and every
                    # queued step lands on it. Any other conflict (inactive
                    # centre, NOT_READY) still refuses.
                    existing = await self._session.scalar(
                        select(CollectionSession).where(
                            CollectionSession.center_id == center_id,
                            CollectionSession.status == "open",
                        )
                    )
                    if existing is not None:
                        return existing
                    raise
            case "close_session":
                return await service.close_session(target, actor_id=actor_id)
            case "create_transaction":
                return await service.create_transaction(target, actor_id=actor_id)
            case "identify_supplier":
                return await service.identify_supplier(
                    target, IdentifySupplierCommand(**payload), actor_id=actor_id
                )
            case "receive_milk":
                return await service.receive_milk(
                    target, MilkInfoCommand(**payload), actor_id=actor_id
                )
            case "capture_weight":
                return await service.capture_weight(
                    target, WeightCommand(**payload), actor_id=actor_id
                )
            case "capture_quality":
                return await service.capture_quality(
                    target, QualityCommand(**payload), actor_id=actor_id
                )
            case "accept":
                return await service.accept(target, actor_id=actor_id)
            case "reject":
                return await service.reject(target, RejectCommand(**payload), actor_id=actor_id)
            case "complete":
                return await service.complete(target, actor_id=actor_id)
            case _:  # cancel
                return await service.cancel(
                    target, payload.get("reason", "cancelled offline"), actor_id=actor_id
                )

    async def _resolve_target(
        self, op: SyncOperationInput, tenant_id: uuid.UUID, resolved: dict[str, uuid.UUID]
    ) -> uuid.UUID | None:
        """Turn the device's reference into a server id.

        A reference is either already a server UUID, a local id learned in
        this batch, or a local id an EARLIER batch created — which is what
        makes an interrupted sync resumable.
        """
        if op.kind == "open_session":
            return None
        reference = op.target_ref
        if not reference:
            raise _UnresolvedReference(f"{op.kind} needs a target reference")
        if reference in resolved:
            return resolved[reference]
        try:
            return uuid.UUID(reference)  # already a server id
        except ValueError:
            pass
        earlier = await self._session.scalar(
            select(SyncOperation).where(
                SyncOperation.tenant_id == tenant_id,
                SyncOperation.client_reference == reference,
                SyncOperation.applied.is_(True),
            )
        )
        if earlier is None or earlier.server_id is None:
            raise _UnresolvedReference(
                f"local reference {reference!r} has not been synchronised yet — "
                "the operation that creates it must land first"
            )
        resolved[reference] = earlier.server_id
        return earlier.server_id

    @staticmethod
    def _classify(kind: str, message: str) -> str:
        """Map a business exception onto a reason a device can explain."""
        text = message.lower()
        if "supplier" in text and ("not found" in text or "not active" in text):
            return "supplier_unavailable"
        if "session" in text and ("not open" in text or "closed" in text or "not found" in text):
            return "session_closed"
        if "state" in text or "expected" in text or "cannot" in text:
            decision = kind in ("accept", "reject", "complete")
            return "already_accepted" if decision else "invalid_state"
        return "invalid_state"

    # --- result helpers ----------------------------------------------------

    def _conflict(self, record: SyncOperation, reason: str, detail: str) -> SyncOperationResult:
        record.status = "conflict"
        record.applied = False
        record.conflict_reason = reason
        record.conflict_detail = detail
        record.error = None
        return self._result(record)

    def _fail(self, record: SyncOperation, error: str) -> SyncOperationResult:
        record.status = "failed"
        record.applied = False
        record.error = error
        return self._result(record)

    def _result(self, record: SyncOperation, *, duplicate: bool = False) -> SyncOperationResult:
        return SyncOperationResult(
            operation_id=record.operation_id,
            kind=record.kind,
            status="duplicate" if duplicate else record.status,
            applied=record.applied,
            client_reference=record.client_reference,
            server_id=record.server_id,
            conflict=(
                ConflictInfo(reason=record.conflict_reason, detail=record.conflict_detail or "")
                if record.conflict_reason
                else None
            ),
            error=record.error,
        )

    # --- monitor (read-only, for the portal) -------------------------------

    async def search(
        self,
        *,
        status: str | None = None,
        kind: str | None = None,
        device_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SyncOperationPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        stmt = select(SyncOperation).where(SyncOperation.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(SyncOperation.status == status)
        if kind:
            stmt = stmt.where(SyncOperation.kind == kind)
        if device_id:
            stmt = stmt.where(SyncOperation.device_id == device_id)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.scalars(
            stmt.order_by(SyncOperation.created_at.desc()).limit(limit).offset(offset)
        )
        return SyncOperationPage(
            items=[SyncOperationView.model_validate(r) for r in rows.all()],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    async def stats(self) -> SyncStatsView:
        tenant_id = require_current_tenant()
        by_status = dict(
            (
                await self._session.execute(
                    select(SyncOperation.status, func.count())
                    .where(SyncOperation.tenant_id == tenant_id)
                    .group_by(SyncOperation.status)
                )
            ).all()
        )
        by_kind = dict(
            (
                await self._session.execute(
                    select(SyncOperation.kind, func.count())
                    .where(SyncOperation.tenant_id == tenant_id)
                    .group_by(SyncOperation.kind)
                )
            ).all()
        )
        device_rows = (
            await self._session.execute(
                select(
                    SyncOperation.device_id,
                    func.count(),
                    # case(), not SQLite's iif() — production is PostgreSQL.
                    func.sum(case((SyncOperation.status == "conflict", 1), else_=0)),
                    func.sum(case((SyncOperation.status == "failed", 1), else_=0)),
                    func.max(SyncOperation.created_at),
                )
                .where(SyncOperation.tenant_id == tenant_id)
                .group_by(SyncOperation.device_id)
            )
        ).all()
        devices = [
            DeviceSyncView(
                device_id=device_id or "(unnamed)",
                operations=count,
                conflicts=int(conflicts or 0),
                failed=int(failed or 0),
                last_sync_at=last,
            )
            for device_id, count, conflicts, failed, last in device_rows
        ]
        last_sync = await self._session.scalar(
            select(func.max(SyncOperation.created_at)).where(SyncOperation.tenant_id == tenant_id)
        )
        return SyncStatsView(
            total=sum(by_status.values()),
            by_status=by_status,
            by_kind=by_kind,
            conflicts=by_status.get("conflict", 0),
            failed=by_status.get("failed", 0),
            devices=sorted(devices, key=lambda d: d.device_id),
            last_sync_at=last_sync,
        )


class _UnresolvedReference(Exception):
    """A device reference points at something that has not synchronised."""
