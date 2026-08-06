"""Async SQLAlchemy 2.0 engine, session, and declarative base."""

import uuid
from collections.abc import AsyncIterator
from contextvars import ContextVar
from datetime import UTC, datetime

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


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        kwargs: dict = {"echo": settings.debug}
        if settings.database_url.startswith("sqlite"):
            from sqlalchemy.pool import StaticPool  # test/dev convenience

            kwargs |= {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
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
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            _request_session.reset(token)


async def reset_engine() -> None:
    """Dispose the cached engine (tests / graceful shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
