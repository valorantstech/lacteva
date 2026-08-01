"""Observability: request context, Prometheus metrics, health checks, OTel hook."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import APIRouter, FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from platform_core.core.i18n import negotiate_locale, set_locale

log = structlog.get_logger("http")

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "route"])

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
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
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
    results = {name: await check() for name, check in _readiness_checks.items()}
    healthy = all(results.values())
    response.status_code = 200 if healthy else 503
    return {"status": "ok" if healthy else "degraded", "checks": results}


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def setup_observability(app: FastAPI) -> None:
    register_readiness_check("database", _database_ready)
    # TODO(M1): readiness checks for rabbitmq, redis, minio, opensearch —
    # each adapter registers its own check on startup when enabled.
    app.include_router(router)
    # OpenTelemetry hook: instrumentation is wired only when an exporter
    # endpoint is configured, keeping dev/test lightweight.
    from platform_core.core.config import get_settings

    if get_settings().otel_exporter_endpoint:
        # TODO(M1): opentelemetry-instrument FastAPI/SQLAlchemy/aio-pika here
        # (add opentelemetry-sdk + OTLP exporter to dependencies when enabled).
        log.info("otel_configured", endpoint=get_settings().otel_exporter_endpoint)
