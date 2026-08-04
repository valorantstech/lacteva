"""Application settings (pydantic-settings, LACTEVA_ env prefix)."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-me"  # noqa: S105 - sentinel, refused in prod
DEV_MINIO_SECRET = "lacteva-secret"  # noqa: S105 - sentinel, refused in prod


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LACTEVA_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "staging", "prod"] = "dev"
    debug: bool = False
    log_level: str = "INFO"
    service_name: str = "platform-core"

    # --- Security (SEC-001) ------------------------------------------------
    # RS256 is the production signing algorithm; keys come from the registry
    # (see core/keys.py). HS256 remains ONLY as a documented rollback path and
    # is refused in prod.
    jwt_algorithm: Literal["RS256", "HS256"] = "RS256"
    # Shared secret for the HS256 rollback path only. Never used under RS256.
    jwt_secret: str = DEV_JWT_SECRET
    # JSON array of signing keys — the sole source of key material. Empty in
    # dev/test means "generate an ephemeral keypair"; empty in prod is fatal.
    jwt_keys: str = ""
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 14 * 24 * 3600
    jwt_leeway_seconds: int = 30  # clock skew tolerance between nodes

    # Rate limiting (per-IP / per-user / per-endpoint, Redis-backed).
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["redis", "memory"] = "redis"
    # Fail-open keeps milk collection working when Redis is down; a deployment
    # that prefers to fail closed sets this to False (see SECURITY.md).
    rate_limit_fail_open: bool = True

    # Security headers. HSTS is only meaningful behind TLS, so it is opt-in
    # and off by default in dev.
    security_headers_enabled: bool = True
    hsts_enabled: bool = False
    hsts_max_age_seconds: int = 31536000
    content_security_policy: str = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )

    # Row Level Security (PostgreSQL only; SQLite has no equivalent).
    rls_enabled: bool = True

    # Data stores
    database_url: str = "postgresql+asyncpg://lacteva:lacteva@localhost:5432/lacteva"
    redis_url: str = "redis://localhost:6379/0"

    # Messaging / storage / search
    event_bus: Literal["rabbitmq", "memory", "null"] = "memory"
    outbox_mode: Literal["inline", "background"] = "background"
    outbox_poll_seconds: float = 1.0
    consumers_enabled: bool = True  # background consumer loop (never runs in test env)
    consumer_poll_seconds: float = 1.0
    # Notification channel adapters (NOT-001): logging | placeholder. Real
    # gateways implement the same provider protocol at deployment time.
    notification_sms_provider: Literal["logging", "placeholder"] = "logging"
    notification_email_provider: Literal["logging", "placeholder"] = "logging"
    # RCP-001: no PDF engine ships with the platform; a deployment registers
    # its own renderer for the `pdf` format.
    receipt_pdf_renderer: Literal["placeholder"] = "placeholder"
    rabbitmq_url: str = "amqp://lacteva:lacteva@localhost:5672/"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "lacteva"
    minio_secret_key: str = DEV_MINIO_SECRET
    minio_secure: bool = False
    opensearch_url: str = "http://localhost:9200"

    # CORS — browser origins allowed to call the API (the admin portal).
    # Dev defaults cover the local portal; set LACTEVA_CORS_ORIGINS in
    # staging/prod (JSON list, e.g. '["https://admin.lacteva.example"]').
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")

    # Observability
    otel_exporter_endpoint: str = ""  # empty = OTel hook disabled

    # Localization
    default_locale: str = "en"
    supported_locales: tuple[str, ...] = ("en", "sw", "hi")

    @model_validator(mode="after")
    def _refuse_dev_secrets_in_prod(self) -> "Settings":
        """Production refuses to start on development credentials.

        Every one of these has a safe default that is convenient in dev and
        catastrophic in prod, so the check is a startup failure rather than a
        warning nobody reads.
        """
        if self.env != "prod":
            return self
        problems = []
        if self.jwt_algorithm == "HS256":
            if self.jwt_secret == DEV_JWT_SECRET:
                problems.append("LACTEVA_JWT_SECRET must be set when using the HS256 fallback")
        elif not self.jwt_keys:
            problems.append("LACTEVA_JWT_KEYS must be configured (RS256 signing keys)")
        if self.minio_secret_key == DEV_MINIO_SECRET:
            problems.append("LACTEVA_MINIO_SECRET_KEY must be set in prod")
        if self.debug:
            problems.append("LACTEVA_DEBUG must be false in prod")
        if any(origin in ("*", "") for origin in self.cors_origins):
            problems.append("LACTEVA_CORS_ORIGINS must name explicit origins in prod")
        if problems:
            raise ValueError("insecure production configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
