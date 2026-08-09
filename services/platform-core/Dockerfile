# Lacteva platform-core — production image
# Build:  docker build -t lacteva/platform-core .
# Run:    docker run -p 8000:8000 --env-file .env lacteva/platform-core

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Install dependencies first (layer-cached), then the project.
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev || uv sync --no-install-project --no-dev
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv uv sync --no-dev

FROM python:3.13-slim-bookworm AS runtime
WORKDIR /app
# Never run as root in production.
RUN groupadd -r app && useradd -r -g app app
COPY --from=builder --chown=app:app /app /app
# AWS-001: the backup target must exist IN THE IMAGE and be owned by the
# container user, so a named volume mounted here inherits that ownership.
# Docker creates a missing mount point root-owned, and the container runs as
# uid 999 — which is why `backup /backup/logical/...` died with
# "PermissionError: /backup" on the first real deployment.
RUN install -d -o app -g app /backup/logical
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health/live')"
CMD ["uvicorn", "platform_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
