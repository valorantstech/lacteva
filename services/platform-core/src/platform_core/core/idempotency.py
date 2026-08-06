"""Platform-wide idempotency (IDM-001).

A client on a poor network cannot tell a lost response from a lost request.
It retries, and without help the platform performs the operation twice — a
second payment, a second supplier, a second collection. This platform is
built explicitly for field use over intermittent connectivity, so that is not
an edge case; it is the normal case.

**One capability, not one per endpoint.** Three partial answers already
existed and each solved its own problem well:

| Mechanism | Scope | Dedups |
| --- | --- | --- |
| `payment.idempotency_key` | One endpoint | A business *intent* — this payment, ever |
| `sync_operation.operation_id` | The offline queue | One captured operation, across batches |
| `consumer_execution` | The event log | One consumer handling one event |

None of them dedups an **HTTP request**, which is what a retrying client
actually repeats. This module adds that layer, and deliberately does not
replace the others: they mean different things, and a payment key that
survives across two genuinely different requests is a guarantee worth
keeping.

## How it works

`Idempotency-Key` on any POST/PUT/PATCH activates it. No header, no cost —
the framework is available everywhere and charges nothing when unused.

1. **Reserve.** A row is inserted for `(tenant, key)` in the REQUEST'S OWN
   session, so the reservation and the business write commit together or not
   at all. A crash between them rolls back both, and the retry simply re-runs
   — where a separate transaction would leave a key claiming an effect that
   never happened, refusing the retry forever.
2. **Run.** The handler executes normally.
3. **Record.** The status and body are written onto the same row, still in
   the same transaction.

A repeat of a *completed* request replays the stored response verbatim,
including its status code. A repeat that arrives while the first is still in
flight gets `409` — the operation is happening, and returning a made-up
answer would be worse than asking the client to wait.

## Why the fingerprint

The key identifies a request; it does not describe one. A client that reuses
a key with a different body is either confused or malicious, and replaying
the first response would silently discard the second request. That is a `422`,
following the IETF idempotency-key draft.

The fingerprint is a hash of method, path and body. It is not stored in the
clear, because request bodies contain credentials and PII and this table has
a retention period measured in days.
"""

import hashlib
import json
import uuid
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    delete,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow
from platform_core.core.metrics import (
    IDEMPOTENCY_CONFLICTS,
    IDEMPOTENCY_MISMATCHES,
    IDEMPOTENCY_REPLAYS,
    IDEMPOTENCY_STORED,
    IDEMPOTENCY_SWEPT,
)

log = structlog.get_logger("idempotency")

HEADER = "Idempotency-Key"
MAX_KEY_LENGTH = 128

IN_PROGRESS = "in_progress"
COMPLETED = "completed"


class IdempotencyRecord(Base, IdMixin):
    """One HTTP request, remembered long enough to recognise its retry."""

    __tablename__ = "idempotency_record"
    __table_args__ = (
        # The uniqueness that does the work: two concurrent requests with the
        # same key race to insert, one wins, and the loser learns it lost from
        # the database rather than from a check-then-act that has a gap.
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_idempotency_tenant_key"),
        # The sweep reads this and nothing else.
        Index("ix_idempotency_expiry", "expires_at"),
    )

    # Nullable because a platform-level principal has no tenant. The standard
    # RLS policy treats NULL as globally visible, which is correct here: such
    # a request belongs to no tenant and its key cannot collide with one that
    # does, because the pair is what is unique.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(MAX_KEY_LENGTH))

    #: sha256 of method + path + body. Never the body itself — bodies carry
    #: credentials and PII, and this table is retained for days.
    fingerprint: Mapped[str] = mapped_column(String(64))

    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))

    status: Mapped[str] = mapped_column(String(12), default=IN_PROGRESS)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped["Any"] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped["Any | None"] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped["Any"] = mapped_column(DateTime(timezone=True))


def fingerprint_of(method: str, path: str, body: bytes) -> str:
    """A stable identity for the request this key claims to be.

    Hashed rather than stored: the point is to detect a DIFFERENT request
    reusing a key, which equality of hashes answers, and keeping the body
    would put credentials in a table with a retention period.
    """
    digest = hashlib.sha256()
    digest.update(method.upper().encode())
    digest.update(b"\0")
    digest.update(path.encode())
    digest.update(b"\0")
    digest.update(body)
    return digest.hexdigest()


class IdempotencyConflict(Exception):
    """The same key is in flight right now."""


class IdempotencyMismatch(Exception):
    """The same key, a different request."""


async def reserve(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None,
    key: str,
    fingerprint: str,
    method: str,
    path: str,
    retention: timedelta,
) -> IdempotencyRecord:
    """Claim the key, or return what the previous claim produced.

    The returned record is `COMPLETED` when this is a replay and
    `IN_PROGRESS` when the caller now owns the key and should run the
    operation — the caller reads `.status` rather than being handed two
    different types.

    Raises `IdempotencyMismatch` when the key was used for a different
    request, and `IdempotencyConflict` when the first attempt is still
    running.
    """
    existing = await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == tenant_id,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    if existing is not None:
        if existing.fingerprint != fingerprint:
            IDEMPOTENCY_MISMATCHES.inc()
            raise IdempotencyMismatch
        if existing.status == COMPLETED:
            IDEMPOTENCY_REPLAYS.labels(method).inc()
            return existing
        IDEMPOTENCY_CONFLICTS.inc()
        raise IdempotencyConflict

    record = IdempotencyRecord(
        tenant_id=tenant_id,
        idempotency_key=key,
        fingerprint=fingerprint,
        method=method,
        path=path,
        status=IN_PROGRESS,
        expires_at=utcnow() + retention,
    )
    session.add(record)
    try:
        # Flush, not commit: the reservation belongs to the caller's
        # transaction. Flushing is what makes the unique constraint decide the
        # race — two concurrent requests both reach here and exactly one gets
        # past it, without a check-then-act gap in between.
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        IDEMPOTENCY_CONFLICTS.inc()
        raise IdempotencyConflict from exc
    return record


async def record_response(
    session: AsyncSession,
    record_id: uuid.UUID,
    *,
    status_code: int,
    body: Any,
) -> None:
    """Attach the outcome, in the same transaction that produced it."""
    record = await session.get(IdempotencyRecord, record_id)
    if record is None:  # pragma: no cover - the row was just inserted
        return
    record.status = COMPLETED
    record.response_status = status_code
    record.response_body = body
    record.completed_at = utcnow()
    await session.flush()
    IDEMPOTENCY_STORED.inc()


async def release(session: AsyncSession, record_id: uuid.UUID) -> None:
    """Give the key back, because the operation did not happen.

    A request that failed holds no effect worth deduplicating, and keeping the
    reservation would answer every future retry with the same failure — for a
    problem that may since have been fixed.
    """
    await session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.id == record_id))
    await session.flush()


async def sweep(session: AsyncSession, *, limit: int = 5000) -> int:
    """Delete expired records. Returns how many.

    Bounded per run: an unbounded DELETE on a table this size takes a long
    lock and competes with the request path it exists to serve. Running often
    and deleting a little is strictly better than the reverse.
    """
    expired = (
        await session.scalars(
            select(IdempotencyRecord.id).where(IdempotencyRecord.expires_at < utcnow()).limit(limit)
        )
    ).all()
    if not expired:
        return 0
    await session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.id.in_(list(expired))))
    await session.commit()
    IDEMPOTENCY_SWEPT.inc(len(expired))
    log.info("idempotency_swept", removed=len(expired))
    return len(expired)


def serialisable(body: bytes) -> Any:
    """The response body, as something JSON can hold."""
    if not body:
        return None
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError):  # pragma: no cover - defensive
        return None
