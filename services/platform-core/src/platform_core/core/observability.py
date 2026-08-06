"""Observability: request context, Prometheus metrics, health checks, OTel hook."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import APIRouter, FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from platform_core.core.i18n import negotiate_locale, set_locale
from platform_core.core.metrics import LATENCY, REQUESTS

log = structlog.get_logger("http")

HealthCheck = Callable[[], Awaitable[bool]]
_readiness_checks: dict[str, HealthCheck] = {}


def register_readiness_check(name: str, check: HealthCheck) -> None:
    _readiness_checks[name] = check


async def _database_ready() -> bool:
    from platform_core.core.db import get_session_factory

    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _route_label(request: Request) -> str:
    """The templated FULL path, for bounded metric cardinality.

    `scope["route"].path` is relative to the router that matched, so it drops
    the `/v1` prefix — two API versions would then share one series. Rebuilding
    the template from the actual path and its resolved parameters gives the
    complete template (`/v1/payments/{payment_id}`) regardless of how routers
    are nested, and keeps ids out of labels either way.
    """
    path = request.url.path
    params = request.scope.get("path_params") or {}
    for name, value in params.items():
        path = path.replace(str(value), "{" + name + "}")
    if params:
        return path
    route = request.scope.get("route")
    # No parameters: the literal path IS the template. Unmatched requests
    # (404s) collapse to a single series rather than one per probed URL.
    return path if route is not None else "<unmatched>"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Request ID + locale + access log + metrics for every request."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        set_locale(negotiate_locale(request))
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        route_path = _route_label(request)
        REQUESTS.labels(request.method, route_path, response.status_code).inc()
        LATENCY.labels(request.method, route_path).observe(elapsed)
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed * 1000, 2),
        )
        response.headers["X-Request-ID"] = request_id
        return response


router = APIRouter(tags=["platform"])


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(response: Response) -> dict:
    """Should this instance receive traffic? (DEP-001)

    Readiness now answers from the SAME nine probes the ops health endpoint
    and every Prometheus alert use — database, redis, outbox, consumers,
    projections, notifications, jwt_keys, background_workers, backups —
    rather than from a `SELECT 1`. A load balancer was previously told an
    instance was ready while its consumer loop was dead and nothing
    downstream was happening.

    **Degraded is still ready.** Only CRITICAL removes an instance from the
    pool. A platform with a lagging consumer should keep serving requests;
    taking it out of rotation would turn a partial problem into a total one,
    and there is nowhere better for the traffic to go.

    The evaluation is the background sampler's most recent, not a fresh one:
    a probe run per poll would make the health check a load source. Before
    the first sample lands, this falls back to the cheap adapter checks so a
    just-started instance is not reported unready for the sampling interval.
    """
    from platform_core.core import health

    snapshot = health.last_evaluation()
    if snapshot is None:
        # Startup window: no sample yet. The adapter checks are cheap and
        # answer the only question that matters this early — can we reach
        # the database at all?
        results = {name: await check() for name, check in _readiness_checks.items()}
        ready = all(results.values())
        response.status_code = 200 if ready else 503
        return {"status": "ok" if ready else "degraded", "checks": results}

    response.status_code = 200 if snapshot.ready else 503
    # `status` keeps its original two-value vocabulary: this endpoint has
    # consumers (load balancers, the container HEALTHCHECK) and DEP-001 is not
    # allowed to move a contract. The four-level detail is added beside it.
    return {
        "status": "ok" if snapshot.ready else "degraded",
        "platform_status": snapshot.status,
        "checked_at": snapshot.checked_at,
        "checks": {c.name: c.status for c in snapshot.components},
    }


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def setup_observability(app: FastAPI) -> None:
    # The startup-window fallback only (see `readiness`). Once the health
    # sampler has run, readiness comes from the nine registered probes, which
    # already cover redis, consumers, projections and the rest.
    register_readiness_check("database", _database_ready)
    app.include_router(router)
    # OpenTelemetry hook: instrumentation is wired only when an exporter
    # endpoint is configured, keeping dev/test lightweight.
    from platform_core.core.config import get_settings

    if get_settings().otel_exporter_endpoint:
        # TODO(M1): opentelemetry-instrument FastAPI/SQLAlchemy/aio-pika here
        # (add opentelemetry-sdk + OTLP exporter to dependencies when enabled).
        log.info("otel_configured", endpoint=get_settings().otel_exporter_endpoint)
