"""Application factory and ASGI entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_core import __version__
from platform_core.api.routes import router as api_router
from platform_core.core import health, health_probes, workers
from platform_core.core.config import get_settings
from platform_core.core.db import Base, get_engine, get_session_factory
from platform_core.core.errors import register_error_handlers
from platform_core.core.http_security import SecurityHeadersMiddleware
from platform_core.core.logging import configure_logging, get_logger
from platform_core.core.observability import RequestContextMiddleware, setup_observability
from platform_core.core.tenancy import TenantContextMiddleware
from platform_core.core.tracing import setup_tracing
from platform_core.modules.authz.service import AuthzService

log = get_logger("app")


async def _consumer_loop() -> None:
    """Background consumer runner (SPRINT-008B): processes the outbox log
    for every registered consumer, forever. Failures are isolated per event
    and per consumer — this loop only logs and continues."""
    import asyncio

    from platform_core.modules.event_relay.consumers import ConsumerRunner
    from platform_core.modules.notification.service import NotificationService

    settings = get_settings()
    runner = ConsumerRunner(get_session_factory())
    while True:
        try:
            await runner.run_once()
            # Delivery retries (NOT-001) ride the same loop: a failed send is
            # a notification-level concern, never an event-processing failure.
            async with get_session_factory()() as session:
                await NotificationService(session).retry_pending()
                await session.commit()
        except Exception:
            log.exception("consumer_loop_error")
        await asyncio.sleep(settings.consumer_poll_seconds)


async def _relay_loop() -> None:
    """Background dispatcher: delivers committed outbox events forever."""
    import asyncio

    from platform_core.infrastructure.events import get_event_bus
    from platform_core.modules.event_relay.service import RelayService

    settings = get_settings()
    while True:
        try:
            async with get_session_factory()() as session:
                relay = RelayService(session, get_event_bus())
                await relay.dispatch_pending()
                await session.commit()
        except Exception:
            log.exception("relay_loop_error")
        await asyncio.sleep(settings.outbox_poll_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Discovery FIRST: importing consumers/projections registers their models
    # in the metadata, so dev/test create_all cannot miss projection tables.
    from platform_core.modules.event_relay.consumers import discover_consumers
    from platform_core.modules.event_relay.projections import discover_projections

    discovered = discover_consumers()
    projections = discover_projections()
    log.info("consumers_discovered", consumers=discovered, projections=projections)
    if settings.env in ("dev", "test"):
        # Convenience only — real environments run Alembic migrations
        # (see migrations/env.py and the deploy pipeline, TODO M1).
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    async with get_session_factory()() as session:
        await AuthzService(session).ensure_system_roles()
        await session.commit()
    relay_task = None
    consumer_task = None
    if settings.outbox_mode == "background" and settings.env != "test":
        import asyncio

        relay_task = asyncio.create_task(_relay_loop())
        workers.register("relay", relay_task)
    if settings.consumers_enabled and settings.env != "test":
        import asyncio

        consumer_task = asyncio.create_task(_consumer_loop())
        workers.register("consumers", consumer_task)
    # OBS-001: health probes and tracing come up with the process, so the
    # first scrape after a restart already tells the truth.
    health_probes.register_all()
    tracing_active = setup_tracing()
    log.info(
        "startup_complete",
        env=settings.env,
        version=__version__,
        health_probes=list(health.registered_probes()),
        tracing=tracing_active,
    )
    yield
    if relay_task is not None:
        relay_task.cancel()
    if consumer_task is not None:
        consumer_task.cancel()
    workers.clear()
    # TODO(M1): graceful shutdown — drain event-bus connection, dispose engine.


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title="Lacteva Platform Core",
        version=__version__,
        description=(
            "Platform foundation: identity, organizations, authentication, "
            "authorization (RBAC), configuration, audit, and platform "
            "infrastructure. OpenAPI schema at /openapi.json."
        ),
        lifespan=lifespan,
        docs_url="/docs" if settings.env != "prod" else None,  # no swagger in prod
    )
    # CORS is an allow-list of exact origins — never a wildcard, and never
    # reflected from the request. `allow_credentials` with a wildcard is
    # rejected by browsers anyway, and reflecting an origin would defeat the
    # point of having a list (SEC-001).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        # Only the verbs and headers this API actually uses. A wildcard here
        # would also authorise anything a future vulnerability needs.
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(RequestContextMiddleware)  # outermost: request id + metrics
    register_error_handlers(app)
    setup_observability(app)
    app.include_router(api_router)
    return app


app = create_app()
