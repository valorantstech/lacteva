"""Making every mutation retry-safe (IDM-001).

Two pieces that only work together, because neither half can see what the
other needs:

* **`idempotency_guard`** is a router-level dependency. It runs inside the
  dependency graph, so it has the request's session — but it never sees the
  response, so it cannot store one.
* **`IdempotentRoute`** wraps the handler. It has the response — and, because
  FastAPI closes dependency teardown *after* the route handler returns, the
  session is **still open** when it regains control. Verified rather than
  assumed; `test_idempotency.py` pins it.

That ordering is the whole design. It means the reservation, the business
write and the stored response all land in ONE transaction:

    reserve ──┐
    handler ──┼── one transaction, committed by get_session
    record  ──┘

A crash anywhere inside rolls back all three, and the retry simply re-runs.
The alternative — a separate transaction for the reservation — leaves a key
claiming an effect that never happened, and refuses the retry until it
expires. That failure is silent, and it strands exactly the client the
framework exists to help.

The framework activates ONLY when `Idempotency-Key` is present, so every
existing caller is unaffected and the capability costs nothing until used.
"""

import uuid
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Annotated, Any

import structlog
from fastapi import Depends, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from platform_core.core import idempotency
from platform_core.core.config import get_settings
from platform_core.core.db import get_session
from platform_core.core.errors import ConflictError, InvalidTokenError
from platform_core.core.tenancy import get_current_tenant

log = structlog.get_logger("idempotency")

#: A retry can only duplicate these. GET and DELETE are idempotent by
#: definition and adding bookkeeping to them would be ceremony.
GUARDED_METHODS = {"POST", "PUT", "PATCH"}

_STATE = "idempotency_record_id"


class _Replay(Exception):
    """Raised by the guard when this request already has an answer.

    An exception rather than a return value because the guard is a
    dependency: raising is the only way it can stop the handler from running
    a second time.
    """

    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self.body = body


def _tenant_of(request: Request) -> uuid.UUID | None:
    """The tenant this request belongs to, at guard time.

    IDM-001: router-level dependencies run BEFORE the route's own, so
    authentication has not happened yet and `get_current_tenant()` reflects
    only the `X-Tenant-ID` header — which a token-authenticated client does
    not send. Keys would then all be reserved with a NULL tenant, putting
    every tenant on one namespace: exactly the class of defect MT-001 found
    in the rate limiter.

    The token's claim is authoritative and verifying it is pure crypto, so
    reading it here costs no database work. A token that does not verify is
    ignored — the real authentication that follows will reject the request
    anyway, and refusing here would turn an auth failure into a confusing
    idempotency error.
    """
    from platform_core.core.security import decode_token

    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        try:
            claims = decode_token(header.split(" ", 1)[1], expected_type="access")
        except Exception:
            claims = {}
        if claims.get("tenant_id"):
            return uuid.UUID(claims["tenant_id"])
    return get_current_tenant()


def retention() -> timedelta:
    return timedelta(hours=get_settings().idempotency_retention_hours)


async def idempotency_guard(
    request: Request,
    session: Annotated[Any, Depends(get_session)],
) -> None:
    """Claim the key, or stop the request because it already has an answer.

    Depends on `get_session` deliberately: FastAPI caches dependencies per
    request, so this is the SAME session the handler will use — which is what
    lets the reservation share the business transaction.
    """
    raw = request.headers.get(idempotency.HEADER)
    if raw is None or request.method not in GUARDED_METHODS:
        return
    # An EMPTY header is refused rather than treated as absent. A client that
    # sends one believes it is protected and is not, and silent
    # non-protection is the failure this framework exists to remove.
    key = raw.strip()
    if not key or len(key) > idempotency.MAX_KEY_LENGTH:
        raise InvalidTokenError("error.idempotency_key_invalid")

    # Starlette caches the body, so reading it here does not consume it — the
    # handler's own parsing still works.
    body = await request.body()
    fingerprint = idempotency.fingerprint_of(request.method, request.url.path, body)

    # P0-MOB defect fix, pre-existing since IDM-001 and latent until the first
    # keyed request from a token-authenticated client hit real PostgreSQL:
    # `get_session` bound RLS from the X-Tenant-ID header (authentication has
    # not run yet), token clients send no header, so the session sat on a NULL
    # tenant while the reservation row carried the token's tenant — and the
    # WITH CHECK half of the policy refused the INSERT with a 500. SQLite
    # tests could never see it, and no keyed request had ever reached a live
    # deployment before the driver's round did.
    #
    # The claim is VERIFIED crypto (`decode_token` checks signature, issuer,
    # expiry and type), so rebinding on it here is exactly as trustworthy as
    # authentication, which re-binds to the same value moments later.
    tenant_id = _tenant_of(request)
    if tenant_id is not None:
        from platform_core.core.rls import rebind_tenant

        await rebind_tenant(session, tenant_id)

    try:
        record = await idempotency.reserve(
            session,
            tenant_id=tenant_id,
            key=key,
            fingerprint=fingerprint,
            method=request.method,
            path=request.url.path,
            retention=retention(),
        )
    except idempotency.IdempotencyMismatch as exc:
        # The same key, a different request. Replaying the first response
        # would silently discard this one, which is worse than refusing it.
        log.warning("idempotency_mismatch", key_length=len(key), path=request.url.path)
        raise InvalidTokenError("error.idempotency_key_reused") from exc
    except idempotency.IdempotencyConflict as exc:
        # The first attempt is still running. Inventing an answer would be
        # worse than asking the caller to wait for the real one.
        raise ConflictError("error.idempotency_in_progress") from exc

    if record.status == idempotency.COMPLETED:
        log.info("idempotency_replay", path=request.url.path, method=request.method)
        raise _Replay(record.response_status or 200, record.response_body)

    # The wrapper picks this up once the response exists.
    setattr(request.state, _STATE, record.id)


class IdempotentRoute(APIRoute):
    """Records the response against the key, in the handler's transaction."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            from platform_core.core.db import current_request_session

            try:
                response = await original(request)
            except _Replay as replay:
                # The stored answer, verbatim — same status, same body.
                return JSONResponse(
                    content=replay.body,
                    status_code=replay.status_code,
                    headers={"Idempotent-Replay": "true"},
                )

            record_id: uuid.UUID | None = getattr(request.state, _STATE, None)
            if record_id is None:
                return response

            session = current_request_session()
            if session is None:  # pragma: no cover - defensive
                return response

            if 200 <= response.status_code < 300:
                await idempotency.record_response(
                    session,
                    record_id,
                    status_code=response.status_code,
                    body=idempotency.serialisable(response.body),
                )
            else:
                # A failed operation must not hold the key. The client's retry
                # is a fresh attempt at something that did not happen, and
                # answering it with the failure forever would be wrong.
                await idempotency.release(session, record_id)
            return response

        return handler
