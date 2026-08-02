# Lacteva development entry points.
# `make dev` is THE one command: full local environment (infra + backend + portal).
# Flutter needs a device/emulator, so it runs on the host: `make mobile`.

COMPOSE := docker compose
BACKEND_DIR := services/platform-core
PORTAL_DIR := apps/admin-portal
MOBILE_DIR := apps/mobile
# Prefer uv; fall back to the checked-in venv workflow when uv is absent.
UV := $(shell command -v uv 2>/dev/null)
PY := $(if $(UV),uv run,$(BACKEND_DIR)/.venv/bin/python -m)

.PHONY: help dev infra backend portal mobile stop test test-backend test-portal test-mobile \
        lint fmt migrate migration docs-validate clean

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

dev: ## Start the complete dev environment (infra + backend + admin portal)
	$(COMPOSE) --profile apps up --build -d
	@echo ""
	@echo "  Backend      http://localhost:8000  (/docs /health/ready /metrics)"
	@echo "  Admin portal http://localhost:3000  (first start installs npm deps — allow a minute)"
	@echo "  RabbitMQ UI  http://localhost:15672 (lacteva/lacteva)"
	@echo "  MinIO UI     http://localhost:9001  (lacteva/lacteva-secret)"
	@echo "  Mobile app:  make mobile            (runs on host — needs a device/emulator)"
	@echo "  Logs:        docker compose logs -f platform-core"

infra: ## Start infrastructure only (postgres redis rabbitmq minio)
	$(COMPOSE) up -d postgres redis rabbitmq minio

backend: infra ## Run the backend locally with reload (outside docker)
	cd $(BACKEND_DIR) && \
	LACTEVA_DATABASE_URL=postgresql+asyncpg://lacteva:lacteva@localhost:5432/lacteva \
	$(if $(UV),uv run,./.venv/bin/)uvicorn platform_core.main:app --reload

portal: ## Run the admin portal locally with reload
	cd $(PORTAL_DIR) && npm install && npm run dev

mobile: ## Run the Flutter app (pass DEVICE=<id>; API defaults to host emulator address)
	cd $(MOBILE_DIR) && flutter run $(if $(DEVICE),-d $(DEVICE),) \
		--dart-define=LACTEVA_API_URL=$(or $(LACTEVA_API_URL),http://10.0.2.2:8000)

stop: ## Stop everything
	$(COMPOSE) --profile apps --profile search down

test: test-backend test-mobile ## Run all test suites available on this machine

test-backend: ## Backend tests (no infrastructure needed)
	cd $(BACKEND_DIR) && $(if $(UV),uv run pytest,./.venv/bin/python -m pytest)

test-portal: ## Portal production build + lint (its test suite arrives in M2)
	cd $(PORTAL_DIR) && npm run build && npx eslint src --max-warnings 0

test-mobile: ## Flutter analyze + widget tests (skipped if flutter is absent)
	@command -v flutter >/dev/null && (cd $(MOBILE_DIR) && flutter analyze && flutter test) \
		|| echo "flutter not installed — skipping mobile tests"

lint: ## Ruff checks (backend)
	cd $(BACKEND_DIR) && $(if $(UV),uv run,./.venv/bin/)ruff check . && \
		$(if $(UV),uv run,./.venv/bin/)ruff format --check .

fmt: ## Auto-format backend
	cd $(BACKEND_DIR) && $(if $(UV),uv run,./.venv/bin/)ruff check . --fix && \
		$(if $(UV),uv run,./.venv/bin/)ruff format .

migrate: ## Apply database migrations (needs postgres from `make infra`)
	cd $(BACKEND_DIR) && \
	LACTEVA_DATABASE_URL=postgresql+asyncpg://lacteva:lacteva@localhost:5432/lacteva \
	$(if $(UV),uv run,./.venv/bin/)alembic upgrade head

migration: ## Autogenerate a migration: make migration m="add xyz"
	cd $(BACKEND_DIR) && \
	LACTEVA_DATABASE_URL=postgresql+asyncpg://lacteva:lacteva@localhost:5432/lacteva \
	$(if $(UV),uv run,./.venv/bin/)alembic revision --autogenerate -m "$(m)"

docs-validate: ## Documentation standards + cross-reference freshness
	python3 tools/validate/validate_docs.py && python3 tools/xref/generate_xref.py --check

clean: ## Stop containers and remove volumes (DESTROYS local data)
	$(COMPOSE) --profile apps --profile search down -v
