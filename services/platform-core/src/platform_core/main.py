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
from platform_core.core.rls import platform_factory, platform_session
from platform_core.core.tenancy import TenantContextMiddleware
from platform_core.core.tracing import setup_tracing
from platform_core.modules.authz.service import AuthzService

log = get_logger("app")


async def _consumer_loop() -> None:
    """Background consumer runner (SPRINT-008B): processes the outbox log
    for every registered consumer, forever. Failures are isolated per event
    and per consumer — this loop only logs and continues."""

    from platform_core.modules.event_relay.consumers import ConsumerRunner
    from platform_core.modules.notification.service import NotificationService

    settings = get_settings()
    # MT-001: consumers are definitionally cross-tenant — one loop drains the
    # log for every tenant. Without the platform binding the policy hides
    # every tenant-owned event and the loop finds nothing to do, silently.
    runner = ConsumerRunner(platform_factory("consumer runner: drains the log for all tenants"))
    # DEP-001: cooperative. The loop leaves between units of work, never
    # inside one, so a SIGTERM cannot land between a handler's write and the
    # ledger row that records it.
    while not workers.stopping():
        try:
            await runner.run_once()
            # Delivery retries (NOT-001) ride the same loop: a failed send is
            # a notification-level concern, never an event-processing failure.
            async with get_session_factory()() as session:
                await NotificationService(session).retry_pending()
                await session.commit()
        except Exception:
            log.exception("consumer_loop_error")
        await workers.sleep(settings.consumer_poll_seconds)


async def _relay_loop() -> None:
    """Background dispatcher: delivers committed outbox events forever."""

    from platform_core.infrastructure.events import get_event_bus
    from platform_core.modules.event_relay.service import RelayService

    settings = get_settings()
    while not workers.stopping():
        try:
            async with platform_session(
                "relay dispatcher: delivers events for all tenants"
            ) as session:
                relay = RelayService(session, get_event_bus())
                await relay.dispatch_pending()
                await session.commit()
        except Exception:
            log.exception("relay_loop_error")
        await workers.sleep(settings.outbox_poll_seconds)


async def _idempotency_sweep_loop() -> None:
    """Delete expired idempotency records (IDM-001).

    Retention is the whole cleanup strategy: a record is useful for as long as
    a client might retry, and dead weight after. Sweeping on a timer keeps the
    table a working set rather than a log — and small, frequent deletes beat
    one large one, which would take a long lock on a table the request path
    reads on every keyed mutation.
    """
    from platform_core.core import idempotency

    settings = get_settings()
    while not workers.stopping():
        try:
            async with platform_session("idempotency sweep: expiry spans tenants") as session:
                await idempotency.sweep(session)
        except Exception as exc:  # a failed sweep must never stop the loop
            log.warning("idempotency_sweep_failed", error=str(exc))
        await workers.sleep(settings.idempotency_sweep_seconds)


async def _health_loop() -> None:
    """Sample component health on a schedule (OBS-001).

    The `component_health` gauge is what every Prometheus alert rule reads.
    Populating it only when an operator opens the ops API would mean the
    alerts never fire — the platform would look quiet precisely because
    nobody was watching. Sampling on a timer makes the gauge true at scrape
    time whether or not a human is present.
    """
    settings = get_settings()
    while not workers.stopping():
        try:
            await health.evaluate()
        except Exception:
            log.exception("health_loop_error")
        await workers.sleep(settings.health_sample_seconds)


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
        # VER-001: before anything else touches data, prove the database will
        # actually enforce the isolation the platform claims. A superuser
        # ignores every policy, silently.
        from platform_core.core.rls import assert_rls_is_enforceable

        await assert_rls_is_enforceable(session)
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
    sweep_task = None
    if settings.env != "test":
        import asyncio

        sweep_task = asyncio.create_task(_idempotency_sweep_loop())
        workers.register("idempotency-sweep", sweep_task)
    health_task = None
    if settings.env != "test":
        import asyncio

        health_task = asyncio.create_task(_health_loop())
        workers.register("health", health_task)
    tracing_active = setup_tracing()
    log.info(
        "startup_complete",
        env=settings.env,
        version=__version__,
        health_probes=list(health.registered_probes()),
        tracing=tracing_active,
    )
    yield

    # --- shutdown (DEP-001) ------------------------------------------------
    # Uvicorn has already stopped accepting connections and drained in-flight
    # requests by the time this runs (`--timeout-graceful-shutdown`), so what
    # is left is the work the platform started on its own: the relay
    # dispatcher, the consumer runner, the health sampler.
    #
    # They are asked to finish the unit of work they are in and then stop.
    # Cancelling them instead would be safe — a rolled-back consumer
    # transaction is retried — but it would mean every rolling deploy left
    # work to redo, and on a busy platform that is a lot of redoing.
    outcome = await workers.shutdown(grace_seconds=settings.shutdown_grace_seconds)
    workers.clear()
    # The engine last, and only after the loops are done: disposing it while a
    # consumer still holds a session turns a clean shutdown into a stack trace.
    await get_engine().dispose()
    log.info("shutdown_complete", workers=outcome)


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
    _publish_error_contract(app)
    return app


def _publish_error_contract(app: FastAPI) -> None:
    """Declare the problem-detail responses on every operation (API-001).

    Done here, once, rather than as a `responses=` argument repeated on 177
    routes — a per-route list is a list that drifts, and the drift is invisible
    because nothing fails when a route forgets.

    The rules are mechanical and therefore checkable:

      * every `/v1` operation can return 401, 403, 422 and 429;
      * an operation with a PATH PARAMETER can return 404 — it addresses a
        specific resource, and a resource belonging to another tenant is a 404
        rather than a 403, because the API must not reveal that it exists;
      * an operation that MUTATES can return 409 — a duplicate unique value or
        a transition the lifecycle refuses.

    Unauthenticated endpoints keep 401 deliberately: `/v1/auth/token` returns
    it for bad credentials, which is exactly the documented meaning.
    """
    from fastapi.openapi.utils import get_openapi

    from platform_core.core.errors import (
        CONFLICT_PROBLEM,
        NOT_FOUND_PROBLEM,
        UNIVERSAL_PROBLEMS,
        ProblemDetail,
    )

    def openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema.setdefault("components", {}).setdefault("schemas", {})["ProblemDetail"] = (
            ProblemDetail.model_json_schema()
        )
        mutating = {"post", "put", "patch", "delete"}
        for path, operations in schema.get("paths", {}).items():
            if not path.startswith("/v1"):
                continue
            for method, operation in operations.items():
                extra = dict(UNIVERSAL_PROBLEMS)
                if "{" in path:
                    extra |= NOT_FOUND_PROBLEM
                if method in mutating:
                    extra |= CONFLICT_PROBLEM
                for code, body in extra.items():
                    # A route that documents a code itself wins — the central
                    # rule is a floor, not a ceiling.
                    operation.setdefault("responses", {}).setdefault(str(code), body)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi


app = create_app()
