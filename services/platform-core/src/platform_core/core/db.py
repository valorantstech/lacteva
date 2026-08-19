"""Async SQLAlchemy 2.0 engine, session, and declarative base."""

import uuid
from collections.abc import AsyncIterator
from contextvars import ContextVar
from datetime import UTC, datetime

import structlog
from sqlalchemy import Uuid
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from platform_core.core.config import get_settings


class Base(DeclarativeBase):
    pass


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime) -> datetime:
    """Normalize a stored datetime for comparison: SQLite returns naive
    datetimes even for timezone-aware columns; all stored values are UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

_diag_log = structlog.get_logger("security.session_diagnostic")


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        kwargs: dict = {"echo": settings.debug}
        if settings.database_url.startswith("sqlite"):
            from sqlalchemy.pool import StaticPool  # test/dev convenience

            kwargs |= {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
        else:
            # ARCH-001. Until now the engine took SQLAlchemy's defaults —
            # pool_size=5, max_overflow=10, no pre-ping, no recycle, no
            # statement or lock timeout. ABR-002 rated that the highest
            # probability cause of the first production incident and it
            # survived four work orders unfixed.
            #
            # Each setting answers a specific failure:
            #
            #   pool_pre_ping   a connection killed by a load balancer, a
            #                   firewall idle timeout or a database failover
            #                   is handed to a request and fails it. This is
            #                   the "mystery 500s after a network blip" that
            #                   every Python service eventually reports.
            #   pool_recycle    the same, pre-emptively, before an idle
            #                   connection can be reaped by something else.
            #   pool_timeout    fail fast when the pool is exhausted rather
            #                   than queueing invisibly behind it.
            #   statement_timeout  an unbounded query holds its snapshot and
            #                   blocks VACUUM across the WHOLE database, which
            #                   turns one slow query into a cluster-wide
            #                   problem (ABR-002 §9).
            #   lock_timeout    a migration needing ACCESS EXCLUSIVE queues
            #                   behind a long read, and every subsequent query
            #                   queues behind the migration — the classic
            #                   PostgreSQL lock pileup that takes an
            #                   application down during a "safe" deploy.
            #
            # Sizing is deliberate rather than inherited: the runbook rule is
            # replicas x (pool_size + max_overflow) + workers + operator
            # headroom < max_connections. Exhausting max_connections makes NEW
            # connections fail, including the operator's during the incident.
            kwargs |= {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_timeout": settings.db_pool_timeout_seconds,
                "pool_pre_ping": True,
                "pool_recycle": settings.db_pool_recycle_seconds,
                "connect_args": {
                    "timeout": settings.db_connect_timeout_seconds,
                    "server_settings": {
                        "application_name": settings.service_name,
                        "statement_timeout": str(settings.db_statement_timeout_ms),
                        "lock_timeout": str(settings.db_lock_timeout_ms),
                        # A transaction left open holds its locks and its
                        # snapshot indefinitely. This is the backstop for a
                        # client that disappears mid-transaction.
                        "idle_in_transaction_session_timeout": str(
                            settings.db_idle_in_transaction_timeout_ms
                        ),
                    },
                },
            }
        _engine = create_async_engine(settings.database_url, **kwargs)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


# IDM-001: the request's session, reachable from outside the dependency graph.
#
# The idempotency framework has to write its record in the SAME transaction as
# the business change it is protecting — otherwise a crash between the two
# leaves a key claiming an effect that never happened, and the retry is
# refused forever. The route wrapper that owns that record runs outside
# FastAPI's dependency injection, so the session reaches it the same way the
# tenant already does: a context variable, set for the life of the request.
_request_session: ContextVar["AsyncSession | None"] = ContextVar("request_session", default=None)


def current_request_session() -> "AsyncSession | None":
    """The session this request is using, or None outside a request."""
    return _request_session.get()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, commit on success.

    SEC-001: the request's tenant is bound to the transaction so PostgreSQL
    row-level security can enforce isolation in the database. Authentication
    re-binds once it establishes the authoritative tenant from the token —
    the header-derived value is only a starting point.
    """
    from platform_core.core.rls import bind_tenant
    from platform_core.core.tenancy import get_current_tenant

    async with get_session_factory()() as session:
        token = _request_session.set(session)
        try:
            await bind_tenant(session, get_current_tenant())
            yield session
            await _diagnose_commit(session)
            await session.commit()
        except Exception as exc:
            # BEFORE the rollback, which destroys the evidence: what did this
            # transaction actually have bound? See `_diagnose_failure`.
            await _diagnose_failure(session, exc)
            await session.rollback()
            raise
        finally:
            _request_session.reset(token)


async def commit_request_session() -> None:
    """Commit the request's transaction while the response can still change.

    E2E-001: the platform answered before it committed. `get_session` commits
    in FastAPI's dependency teardown, and because the middleware stack is built
    on `BaseHTTPMiddleware` — whose `call_next` returns as soon as the response
    *starts* — the bytes reached the client while that teardown was still
    pending. Measured in the harness, the commit landed 0.3-1.1 ms AFTER the
    response was logged as sent, every single time.

    Two things follow, and the second is the serious one:

    1. A client acting on its own answer could miss its own write. That is the
       "a row created moments earlier is not found" defect, and it was never
       about row-level security: the row simply did not exist yet.
    2. A commit that FAILS after the response is gone cannot change it. The
       platform would have reported 201 for a write that never happened —
       which for a transaction, a settlement or a receipt is the one failure
       this codebase refuses to tolerate.

    Committing here, inside the route handler, puts the commit back on the
    request's critical path: the write is durable before the answer exists, and
    a failed commit becomes a 500 the caller can act on rather than a lie.
    """
    session = _request_session.get()
    if session is None or not session.in_transaction():
        return
    await _diagnose_commit(session)
    await session.commit()


async def _diagnose_commit(session: AsyncSession) -> None:
    """Record what this request is about to commit, and what it holds.

    The counterpart to `_diagnose_failure`: a request answered 2xx and its row
    was not in the database afterwards, so the question moved from "who could
    see it" to "was it ever written". A transaction that has written has a
    PostgreSQL transaction id; one that has not, has none. Logging that id next
    to the objects still pending tells us which half of the sentence is false.
    """
    if not get_settings().session_diagnostics:
        return
    try:
        from sqlalchemy import text

        from platform_core.core.rls import is_postgres

        if not is_postgres():
            return
        pending = [
            f"{type(o).__name__}:{getattr(o, 'id', None)}"
            for o in list(session.new) + list(session.dirty)
        ]
        row = (
            await session.execute(
                text("SELECT txid_current_if_assigned() AS txid, pg_backend_pid() AS pid")
            )
        ).one()
        if row.txid is None and not pending:
            return  # a pure read; nothing to say
        _diag_log.warning(
            "session_commit_diagnostic",
            txid=row.txid,
            backend_pid=row.pid,
            pending=pending[:8],
            pending_count=len(pending),
            in_transaction=session.in_transaction(),
        )
    except Exception as diag_exc:  # diagnosis never masks the request
        _diag_log.warning("session_commit_diagnostic_failed", reason=type(diag_exc).__name__)


async def _diagnose_failure(session: AsyncSession, exc: BaseException) -> None:
    """Record the transaction's real tenant binding when a request refuses.

    "The row was written, and the very next request could not see it" cannot be
    answered from outside the process. The row is there; the question is what
    `lacteva.tenant_id` held inside the transaction that failed to find it, and
    only the transaction itself can say. This asks it, while the transaction is
    still alive — one statement, then the caller's rollback proceeds.

    Diagnosis must never change an outcome: any failure here is swallowed, so
    a broken probe cannot turn a 404 into a 500.
    """
    if not get_settings().session_diagnostics:
        return
    try:
        from sqlalchemy import text

        from platform_core.core.errors import ForbiddenError, NotFoundError, UnauthorizedError

        # isinstance, not a name match: `InvalidCredentialsError` is an
        # `UnauthorizedError`, and matching on the exact class name silently
        # skipped exactly the refusal that mattered.
        if not isinstance(exc, NotFoundError | UnauthorizedError | ForbiddenError):
            return

        from platform_core.core.rls import BYPASS_SETTING, TENANT_SETTING, is_postgres
        from platform_core.core.tenancy import get_current_tenant

        if not is_postgres():
            return  # these settings exist only where RLS does

        row = (
            await session.execute(
                text(
                    f"SELECT current_setting('{TENANT_SETTING}', true) AS bound, "
                    f"current_setting('{BYPASS_SETTING}', true) AS bypass, "
                    "pg_backend_pid() AS pid, "
                    "txid_current_if_assigned() AS txid"
                )
            )
        ).one()
        context_tenant = get_current_tenant()
        bound = row.bound or None
        _diag_log.warning(
            "session_diagnostic",
            error=type(exc).__name__,
            detail=str(exc)[:200],
            bound_tenant=bound,
            context_tenant=str(context_tenant) if context_tenant else None,
            # The single fact the whole investigation turns on.
            binding_matches_context=(bound == (str(context_tenant) if context_tenant else None)),
            bypass=row.bypass,
            backend_pid=row.pid,
            txid=row.txid,
        )
    except Exception as diag_exc:  # diagnosis never masks the failure it observes
        _diag_log.warning("session_diagnostic_failed", reason=type(diag_exc).__name__)


async def reset_engine() -> None:
    """Dispose the cached engine (tests / graceful shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
