"""Application settings (pydantic-settings, LACTEVA_ env prefix)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-me"  # noqa: S105 - sentinel, refused in prod
DEV_MINIO_SECRET = "lacteva-secret"  # noqa: S105 - sentinel, refused in prod


class Settings(BaseSettings):
    # DEP-001: `secrets_dir` is how Docker Secrets reach the process — each
    # secret is a file at /run/secrets/<name>, read once at startup and never
    # present in the environment, so it cannot leak through `docker inspect`,
    # a crash dump, or a child process's `environ`. Conditional because the
    # directory only exists where secrets are actually mounted, and
    # pydantic-settings warns about a path that is not there.
    model_config = SettingsConfigDict(
        env_prefix="LACTEVA_",
        env_file=".env",
        extra="ignore",
        secrets_dir="/run/secrets" if Path("/run/secrets").is_dir() else None,
    )

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
    #: What happens when the limiter itself is unreachable (SEC-003 / F-06).
    #:
    #: `degrade` — the recorded decision. Charge the request against the
    #: process-local limiter instead. A dairy at 5 a.m. can still log in and
    #: keep accepting milk, and an attacker gets `limit x workers` attempts
    #: per window rather than unlimited ones. If even that fails, rules marked
    #: `fail_closed` deny and the rest allow.
    #: `fail_open` — allow everything the limiter could not judge. REFUSED in
    #: prod: a Redis blip must not silently remove brute-force protection from
    #: the credential endpoints, and `degrade` already protects the
    #: availability that fail-open existed to protect.
    #: `fail_closed` — deny everything the limiter could not judge. A
    #: deployment that would rather stop than be probed sets this knowing it
    #: also stops its own operators logging in.
    rate_limit_failure_policy: Literal["degrade", "fail_open", "fail_closed"] = "degrade"

    # Security headers. HSTS is only meaningful behind TLS, so it is opt-in
    # and off by default in dev.
    security_headers_enabled: bool = True
    hsts_enabled: bool = False
    hsts_max_age_seconds: int = 31536000
    content_security_policy: str = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )

    # OBS-001: how often the platform samples its own component health into
    # the `component_health` gauge. Every Prometheus alert rule reads that
    # gauge, so a platform that never samples is a platform that never alerts.
    health_sample_seconds: float = 30.0
    # DEP-001: how long background workers get to finish the unit of work they
    # are in when SIGTERM arrives. Must be comfortably below the orchestrator's
    # kill timeout (compose `stop_grace_period`, Kubernetes
    # `terminationGracePeriodSeconds`), or the container is killed mid-drain
    # and the drain was pointless.
    shutdown_grace_seconds: float = 20.0

    # --- Idempotency (IDM-001) ---------------------------------------------
    # How long a completed request stays replayable. Long enough to cover any
    # realistic client retry — a mobile device that reconnects the next
    # morning still gets the original answer rather than a duplicate — and
    # short enough that the table stays a working set rather than a log.
    idempotency_retention_hours: int = 24
    # Seconds between expiry sweeps. Frequent and small beats rare and large:
    # an unbounded DELETE takes a long lock on the table the request path
    # depends on.
    idempotency_sweep_seconds: float = 300.0

    # --- the delivery scheduler (DEMO-017) --------------------------------
    #: Off in tests, on everywhere else. A test suite that generated a dairy's
    #: round in the background would race every delivery test it has.
    scheduler_enabled: bool = True
    #: How often the loop asks each tenant whether its day is due. A minute is
    #: chosen so that a round appears within a minute of the generation hour
    #: rather than up to an hour late, and the question is two cheap indexed
    #: reads per tenant — not the generation itself, which happens once.
    scheduler_poll_seconds: float = 60.0
    #: LOCAL hour, in each tenant's own timezone. Five in the morning, because
    #: a dairy's first round leaves around six and the deliveries have to be on
    #: the operator's phone before the van does. NOT a UTC hour — see
    #: `modules/delivery/scheduler.py`.
    scheduler_generation_hour: int = 5

    # Row Level Security (PostgreSQL only; SQLite has no equivalent).
    rls_enabled: bool = True

    # Data stores
    database_url: str = "postgresql+asyncpg://lacteva:lacteva@localhost:5432/lacteva"
    redis_url: str = "redis://localhost:6379/0"

    # --- Connection pool (ARCH-001) ----------------------------------------
    # PostgreSQL only; SQLite uses StaticPool. See core/db.py for what each
    # of these prevents — none of them are tuning, they are all a specific
    # production failure that has a name.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: float = 10.0
    #: Recycle before anything else reaps an idle connection.
    db_pool_recycle_seconds: int = 1800
    db_connect_timeout_seconds: float = 10.0
    #: Request-path ceiling. Background work that legitimately runs longer
    #: raises it per session; nothing runs unbounded.
    db_statement_timeout_ms: int = 30_000
    #: A contended DDL statement fails fast instead of queueing every query
    #: in the platform behind itself.
    db_lock_timeout_ms: int = 5_000
    db_idle_in_transaction_timeout_ms: int = 60_000
    #: Cross-tenant work — projection rebuilds, backups, deep integrity —
    #: legitimately runs longer than a request. Raised, never removed.
    db_background_statement_timeout_ms: int = 900_000  # 15 minutes

    # Messaging / storage / search
    event_bus: Literal["rabbitmq", "memory", "null"] = "memory"
    outbox_mode: Literal["inline", "background"] = "background"
    outbox_poll_seconds: float = 1.0
    consumers_enabled: bool = True  # background consumer loop (never runs in test env)
    consumer_poll_seconds: float = 1.0
    # Notification channel adapters (NOT-001): logging | placeholder. Real
    # gateways implement the same provider protocol at deployment time.
    # MSG-001. `logging`/`placeholder` keep the pre-production behaviour;
    # `http` is the real gateway; `dry_run` renders and logs a real message
    # against production-shaped configuration WITHOUT sending it (staging);
    # `disabled` refuses permanently, for a market that is not live yet.
    notification_sms_provider: Literal["logging", "placeholder", "http", "dry_run", "disabled"] = (
        "logging"
    )
    notification_email_provider: Literal[
        "logging", "placeholder", "smtp", "dry_run", "disabled"
    ] = "logging"
    #: DEMO-012 §10. Defaults to `disabled`, not `logging`, and that is the
    #: point: no push vendor has been chosen or paid for, so a deployment
    #: that has not made that decision must FAIL a push visibly rather than
    #: record it as delivered. `http` speaks the vendor-neutral contract in
    #: `HttpPushProvider`.
    notification_push_provider: Literal["logging", "placeholder", "http", "dry_run", "disabled"] = (
        "disabled"
    )

    # --- Email gateway (PROD-001) ------------------------------------------
    # SMTP is the provider-neutral choice deliberately: every transactional
    # email service (SES, SendGrid, Postmark, Mailgun, a co-op's own relay)
    # speaks it, so one adapter reaches all of them without a vendor SDK, and a
    # market that must keep mail on its own infrastructure is served by the
    # same code path. A vendor API adapter implements the same protocol.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    #: STARTTLS on the submission port (587) is the default; `ssl` is implicit
    #: TLS (465); `none` exists only for a relay on localhost and is refused
    #: over a network host in prod.
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = 15.0
    #: Envelope sender. A wrong or unverified value is a PERMANENT failure at
    #: every gateway, which is why it is worth setting in staging.
    smtp_from_address: str = ""
    smtp_from_name: str = "Lacteva"

    # --- SMS gateway (MSG-001) ---------------------------------------------
    # Vendor-neutral: the adapter speaks a small documented JSON contract and
    # classifies outcomes by HTTP status, which every gateway agrees on.
    # Credentials live in the environment or a Docker secret, never in code.
    sms_api_url: str = ""
    sms_api_key: str = ""
    #: The alphanumeric or short-code sender a supplier sees. Registration is
    #: per-market and per-operator; a wrong value is rejected by the gateway
    #: as a PERMANENT failure, which is why it is worth getting right in
    #: staging rather than discovering in the field.
    sms_sender_id: str = "LACTEVA"

    # --- Push gateway (DEMO-012 §10) ---------------------------------------
    # Vendor-neutral for the same reason as SMS. The credential is a SERVER
    # credential and lives here, in the environment or a Docker secret — it
    # is never shipped in the mobile application, which holds only its own
    # per-installation delivery token.
    push_api_url: str = ""
    push_api_key: str = ""
    push_timeout_seconds: float = 10.0
    #: Below a farmer's patience and above a gateway's p99. Too short and
    #: every message retries; too long and the consumer loop stalls behind
    #: one unresponsive gateway.
    sms_timeout_seconds: float = 10.0
    # PROD-001: `builtin` is a real, dependency-free PDF writer (see
    # receipt/pdf.py). `placeholder` is kept only so the pre-PROD-001
    # behaviour remains reachable in dev; prod refuses it.
    receipt_pdf_renderer: Literal["builtin", "placeholder"] = "builtin"
    #: SEC-003 / F-01: may `mock_scale` and `mock_analyzer` fabricate a
    #: measurement?
    #:
    #: `None` means "derive it from the environment" — allowed everywhere
    #: except `prod`. That is the safe default: an operator who has never
    #: heard of this setting still cannot invent milk in production, and a
    #: developer who has never heard of it still gets working mocks.
    #: Setting it to `true` in prod is REFUSED at startup rather than
    #: honoured, because a fabricated weight is priced, settled, paid and
    #: receipted like any other — there is no downstream check that can tell
    #: an invented reading from a weighed one.
    allow_mock_hardware: bool | None = None
    rabbitmq_url: str = "amqp://lacteva:lacteva@localhost:5672/"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "lacteva"
    minio_secret_key: str = DEV_MINIO_SECRET
    minio_secure: bool = False
    opensearch_url: str = "http://localhost:9200"

    # --- Off-site backup replication (BKP-003) -----------------------------
    # A backup on the database's own volume is not a backup: losing the volume
    # loses both. These point replication at an INDEPENDENT S3-compatible
    # endpoint — deliberately separate from `minio_*`, because the
    # application's object storage lives on the same host and would die with
    # it. Empty endpoint = replication disabled, which `prod` refuses.
    backup_offsite_endpoint: str = ""
    backup_offsite_access_key: str = ""
    backup_offsite_secret_key: str = ""
    backup_offsite_bucket: str = "lacteva-backups"
    #: TLS to the object store — encryption IN TRANSIT. Default on; prod
    #: refuses it off, because a backup in flight carries every farmer's record.
    backup_offsite_secure: bool = True
    #: How many complete off-site backups to retain. Never below 1, and the
    #: newest is excluded from deletion regardless (see offsite.prune).
    backup_offsite_retain: int = 30

    # CORS — browser origins allowed to call the API (the admin portal).
    # Dev defaults cover the local portal; set LACTEVA_CORS_ORIGINS in
    # staging/prod (JSON list, e.g. '["https://admin.lacteva.example"]').
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")

    # Observability
    otel_exporter_endpoint: str = ""  # empty = OTel hook disabled

    # Localization
    default_locale: str = "en"
    supported_locales: tuple[str, ...] = ("en", "sw", "hi")

    @property
    def mock_hardware_enabled(self) -> bool:
        """The single authority on whether a fabricated reading is permitted.

        Everything that could invent a measurement asks this — the service that
        accepts the source and the adapter that produces the number. One
        predicate, so there is no second opinion to get wrong (SEC-003 / F-01).
        """
        if self.allow_mock_hardware is None:
            return self.env != "prod"
        return self.allow_mock_hardware

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
        # ARCH-FINAL-001: `rls_enabled=False` is not a tuning knob in
        # production — it is the tenant boundary.
        #
        # It short-circuits `bind_tenant`, `bind_platform_context` AND
        # `assert_rls_is_enforceable`, so the one startup check that catches a
        # SUPERUSER connection (the defect VER-001 found, where every policy
        # was inert while looking correct) stops running too. One environment
        # variable therefore both removes the guarantee and silences the alarm
        # that would report its absence. Refused in prod for the same reason a
        # development JWT secret is.
        if not self.rls_enabled:
            problems.append(
                "LACTEVA_RLS_ENABLED must be true in prod — it is the tenant "
                "boundary, and disabling it also disables the check that "
                "detects a database role which bypasses row-level security"
            )
        # ARCH-FINAL-001: the default channel providers report success and
        # send nothing.
        #
        # `logging` and `placeholder` both return ACCEPTED, so the notification
        # is rendered, the delivery row says it was accepted, the metrics are
        # green and the supplier is never told anything. Both are the DEFAULT,
        # which means a production deployment that changes nothing gets a
        # messaging platform that silently discards every message — the exact
        # "looks healthy while doing nothing" failure this platform's own
        # observability doctrine calls its most dangerous.
        #
        # Refused in prod so the choice has to be made out loud. `disabled`
        # (raises, so the delivery visibly fails) and `dry_run` (a real
        # message against real config, deliberately not sent) both remain
        # available — email has no transport yet and must say so.
        for channel, configured in (
            ("SMS", self.notification_sms_provider),
            ("EMAIL", self.notification_email_provider),
            ("PUSH", self.notification_push_provider),
        ):
            if configured in ("logging", "placeholder"):
                problems.append(
                    f"LACTEVA_NOTIFICATION_{channel}_PROVIDER is {configured!r}, which marks "
                    "every message delivered and sends nothing — use a real provider, "
                    "'dry_run' to rehearse, or 'disabled' to fail visibly"
                )
        if self.debug:
            problems.append("LACTEVA_DEBUG must be false in prod")
        if any(origin in ("*", "") for origin in self.cors_origins):
            problems.append("LACTEVA_CORS_ORIGINS must name explicit origins in prod")

        # --- PROD-001: every remaining way to look healthy while doing nothing.
        #
        # The audit behind this block asked one question of each setting: if a
        # deployment left it at its default, would the platform REPORT success
        # for work it never did? Everything below answered yes.

        # The database. A default credential is the oldest production incident
        # there is, and `lacteva:lacteva@localhost` is in this repository's own
        # compose files, so it is what a copied .env contains.
        url = self.database_url
        if not url.startswith("postgresql"):
            problems.append(
                f"LACTEVA_DATABASE_URL must be PostgreSQL in prod (got {url.split(':')[0]!r}) — "
                "RLS, exact aggregation and the backup format all depend on it"
            )
        if "lacteva:lacteva@" in url or "postgres:postgres@" in url:
            problems.append(
                "LACTEVA_DATABASE_URL still carries development credentials — production "
                "connects as an unprivileged, NOSUPERUSER NOBYPASSRLS role (DEPLOYMENT.md)"
            )

        # The event transport. `memory` and `null` both ACCEPT a publish and
        # drop it: the outbox row is written and marked delivered, so the relay
        # drains, the metrics are green, and no consumer on any other process
        # ever sees the event.
        if self.event_bus in ("memory", "null"):
            problems.append(
                f"LACTEVA_EVENT_BUS is {self.event_bus!r}, which accepts every publish and "
                "delivers nothing — production needs 'rabbitmq'"
            )

        # Inline dispatch runs delivery inside the request transaction, so a
        # slow broker becomes slow milk collection and the retry/DLQ machinery
        # never runs. It is a development convenience.
        if self.outbox_mode == "inline":
            problems.append(
                "LACTEVA_OUTBOX_MODE must be 'background' in prod — 'inline' dispatches "
                "inside the request transaction and bypasses retry and the dead-letter queue"
            )

        # A per-process limiter gives every replica its own full budget and
        # cannot see the others, so the configured limit is silently multiplied
        # by the replica count.
        if self.rate_limit_backend == "memory":
            problems.append(
                "LACTEVA_RATE_LIMIT_BACKEND must be 'redis' in prod — the memory backend is "
                "per-process, so each replica grants the full budget again"
            )

        # SEC-003 / F-06. Fail-open means a Redis blip silently removes every
        # brute-force limit from login, refresh, password reset and invitation
        # acceptance — the four endpoints where an attacker gets the most value
        # per request — and nothing in the request path reports it. `degrade`
        # keeps the availability that fail-open was protecting (the operator
        # can still log in at 5 a.m.) while leaving an attacker a bounded
        # budget instead of an unlimited one, so there is nothing left for
        # fail-open to buy.
        if self.rate_limit_failure_policy == "fail_open":
            problems.append(
                "LACTEVA_RATE_LIMIT_FAILURE_POLICY must not be 'fail_open' in prod — an "
                "unreachable limiter would silently allow unlimited credential attempts; "
                "use 'degrade' (process-local fallback) or 'fail_closed'"
            )

        # SEC-003 / F-01. A fabricated weight or quality reading is priced,
        # settled, paid and receipted exactly like a measured one, and no
        # downstream check can tell them apart.
        if self.allow_mock_hardware:
            problems.append(
                "LACTEVA_ALLOW_MOCK_HARDWARE must not be true in prod — mock_scale and "
                "mock_analyzer fabricate measurements that become real money"
            )

        # A gateway selected but not configured fails every send at runtime,
        # one message at a time, instead of failing the deployment once.
        if self.notification_push_provider == "http" and not (
            self.push_api_url and self.push_api_key
        ):
            problems.append(
                "LACTEVA_NOTIFICATION_PUSH_PROVIDER is 'http' but LACTEVA_PUSH_API_URL / "
                "LACTEVA_PUSH_API_KEY are not both set"
            )
        if self.notification_sms_provider == "http" and not (self.sms_api_url and self.sms_api_key):
            problems.append(
                "LACTEVA_NOTIFICATION_SMS_PROVIDER is 'http' but LACTEVA_SMS_API_URL / "
                "LACTEVA_SMS_API_KEY are not both set"
            )
        if self.notification_email_provider == "smtp" and not self.smtp_host:
            problems.append(
                "LACTEVA_NOTIFICATION_EMAIL_PROVIDER is 'smtp' but LACTEVA_SMTP_HOST is not set"
            )

        # PROD-001 §4: the placeholder renderer emits a text file named .pdf.txt
        # and marks itself `placeholder=True`. A dairy handing a farmer proof of
        # payment cannot use it, and a deployment should not discover that from
        # a supplier.
        # BKP-003: a deployment with no off-site destination has backups that
        # die with the volume they protect.
        if not self.backup_offsite_endpoint:
            problems.append(
                "LACTEVA_BACKUP_OFFSITE_ENDPOINT is not set — backups would live only on "
                "the database's own volume, which is not a backup"
            )
        elif not (self.backup_offsite_access_key and self.backup_offsite_secret_key):
            problems.append(
                "LACTEVA_BACKUP_OFFSITE_ENDPOINT is set but its access key / secret key "
                "are not both configured"
            )
        if self.backup_offsite_endpoint and not self.backup_offsite_secure:
            problems.append(
                "LACTEVA_BACKUP_OFFSITE_SECURE must be true in prod — a backup in flight "
                "carries every farmer's records"
            )
        if self.backup_offsite_retain < 1:
            problems.append("LACTEVA_BACKUP_OFFSITE_RETAIN must be at least 1")

        if self.receipt_pdf_renderer == "placeholder":
            problems.append(
                "LACTEVA_RECEIPT_PDF_RENDERER is 'placeholder', which cannot produce a "
                "printable receipt — use 'builtin'"
            )

        if problems:
            raise ValueError("insecure production configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
