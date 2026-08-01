"""Application factory and ASGI entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from platform_core import __version__
from platform_core.api.routes import router as api_router
from platform_core.core.config import get_settings
from platform_core.core.db import Base, get_engine, get_session_factory
from platform_core.core.errors import register_error_handlers
from platform_core.core.logging import configure_logging, get_logger
from platform_core.core.observability import RequestContextMiddleware, setup_observability
from platform_core.core.tenancy import TenantContextMiddleware
from platform_core.modules.authz.service import AuthzService

log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.env in ("dev", "test"):
        # Convenience only — real environments run Alembic migrations
        # (see migrations/env.py and the deploy pipeline, TODO M1).
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    async with get_session_factory()() as session:
        await AuthzService(session).ensure_system_roles()
        await session.commit()
    log.info("startup_complete", env=settings.env, version=__version__)
    yield
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
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(RequestContextMiddleware)  # outermost: request id + metrics
    register_error_handlers(app)
    setup_observability(app)
    app.include_router(api_router)
    return app


app = create_app()
