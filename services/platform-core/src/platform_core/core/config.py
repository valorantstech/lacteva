"""Application settings (pydantic-settings, LACTEVA_ env prefix)."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-me"  # noqa: S105 - sentinel, refused in prod


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LACTEVA_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "staging", "prod"] = "dev"
    debug: bool = False
    log_level: str = "INFO"
    service_name: str = "platform-core"

    # Security
    jwt_secret: str = DEV_JWT_SECRET
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 14 * 24 * 3600
    jwt_algorithm: str = "HS256"  # TODO(M1): move to RS256 with key rotation (platform ADR)

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
    minio_secret_key: str = "lacteva-secret"  # noqa: S105 - dev default
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
        if self.env == "prod" and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("LACTEVA_JWT_SECRET must be set in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
