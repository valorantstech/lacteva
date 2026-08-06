"""The platform metric registry (OBS-001).

**Every Prometheus metric the platform exposes is defined here, once.**

Scattering `Counter(...)` across modules is how a metrics surface becomes
unreviewable: nobody can answer "what do we expose?" without grepping, and
nobody notices when a label starts carrying a tenant id and multiplies the
series count by the customer count. A single registry makes the surface
enumerable, lets `METRICS.md` be generated from reality rather than memory,
and lets a test enforce the cardinality rules below.

## The cardinality rule

A Prometheus time series exists for every distinct combination of label
values. Labels must therefore be drawn from a **small, bounded, known-ahead**
set. These are forbidden as label values, and a test enforces it:

- tenant id, user id, supplier id, or any other UUID
- an e-mail address, phone number, or receipt/payment number
- a raw URL path (route templates are fine; `/v1/payments/{id}` is bounded,
  `/v1/payments/9f2c...` is not)
- an error message

Per-tenant *breakdown* is a dashboard question, answered by querying the
business data — not by exploding every counter by customer.

## Naming

`<subsystem>_<thing>_<unit>` following Prometheus convention: counters end
`_total`, durations end `_seconds`, point-in-time values are gauges with a
plain noun. Units are always base units (seconds, bytes) — never milliseconds.
"""

from prometheus_client import Counter, Gauge, Histogram

# Latency buckets tuned to this platform: most calls are single-digit
# milliseconds, and the interesting tail is "did an operator wait?".
_API_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
# Background work is allowed to be slower; a rebuild can legitimately take
# minutes, and bucketing it like an API call would lose all resolution.
_JOB_BUCKETS = (0.01, 0.1, 0.5, 1.0, 5.0, 15.0, 60.0, 300.0, 900.0)


# --- HTTP -------------------------------------------------------------------

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=_API_BUCKETS,
)
IN_FLIGHT = Gauge("http_requests_in_flight", "Requests currently being served")

# --- security ---------------------------------------------------------------
# `reason` is a fixed vocabulary (see security_audit), never a message.

AUTH_FAILURES = Counter("auth_failures_total", "Authentication failures", ["reason"])
AUTHZ_DENIALS = Counter("authz_denials_total", "Authorization denials", ["permission"])
RATE_LIMITED = Counter("rate_limited_total", "Requests refused by a rate limit", ["rule"])
RATE_LIMITER_UNAVAILABLE = Counter(
    "rate_limiter_unavailable_total", "Rate-limit checks that could not reach their backend"
)
JWT_VERIFICATION_FAILURES = Counter(
    "jwt_verification_failures_total", "Tokens rejected during verification", ["reason"]
)
RLS_DENIALS = Counter("rls_denials_total", "Statements refused by row-level security")

# --- Idempotency (IDM-001) --------------------------------------------------
# `method` is a fixed vocabulary of three values; the key itself is NEVER a
# label — it is client-supplied and unbounded, which is the cardinality rule
# in this module's header.
IDEMPOTENCY_REPLAYS = Counter(
    "idempotency_replays_total", "Requests answered from a stored response", ["method"]
)
IDEMPOTENCY_STORED = Counter(
    "idempotency_stored_total", "Responses recorded against an idempotency key"
)
IDEMPOTENCY_CONFLICTS = Counter(
    "idempotency_conflicts_total", "Retries that arrived while the first attempt was in flight"
)
IDEMPOTENCY_MISMATCHES = Counter(
    "idempotency_mismatches_total", "Keys reused for a DIFFERENT request (a client bug)"
)
IDEMPOTENCY_SWEPT = Counter("idempotency_swept_total", "Expired idempotency records deleted")

# --- SMS / channel delivery (MSG-001) ---------------------------------------
# `kind` is a THREE-value vocabulary — permanent | transient | timeout — not
# the provider's error string, which is unbounded and attacker-influenced.
# Knowing which kind is what tells an operator whether to page the gateway or
# fix a phone number.
NOTIFICATION_PROVIDER_ERRORS = Counter(
    "notification_provider_errors_total",
    "Delivery failures, by whether a retry can help",
    ["channel", "provider", "kind"],
)

# --- relay (outbox) ---------------------------------------------------------

RELAY_DELIVERED = Counter("relay_delivered_total", "Events delivered by the relay")
RELAY_RETRIES = Counter("relay_retries_total", "Delivery attempts that failed and were retried")
RELAY_DEAD = Counter("relay_dead_total", "Events moved to the dead letter queue")
RELAY_PENDING = Gauge("relay_pending_events", "Outbox events awaiting delivery")
RELAY_LATENCY = Histogram(
    "relay_delivery_seconds", "Time from publish to successful delivery", buckets=_JOB_BUCKETS
)

# --- consumers --------------------------------------------------------------

CONSUMER_PROCESSED = Counter(
    "consumer_processed_total", "Events successfully processed", ["consumer"]
)
CONSUMER_FAILED = Counter("consumer_failed_total", "Handler failures", ["consumer"])
CONSUMER_RETRIED = Counter("consumer_retried_total", "Retries scheduled", ["consumer"])
CONSUMER_DEAD = Counter("consumer_dead_total", "Events dead-lettered", ["consumer"])
CONSUMER_LAG = Gauge("consumer_lag_events", "Events behind the log head", ["consumer"])
CONSUMER_LATENCY = Histogram(
    "consumer_latency_seconds",
    "Time from event creation to processing",
    ["consumer"],
    buckets=_JOB_BUCKETS,
)
CONSUMER_ENABLED = Gauge(
    "consumer_enabled", "1 when a consumer is enabled, 0 when paused", ["consumer"]
)

# --- projections ------------------------------------------------------------

PROJECTION_REBUILDS = Counter(
    "projection_rebuilds_total", "Projection rebuilds started", ["projection"]
)
PROJECTION_REPLAYED = Counter(
    "projection_events_replayed_total", "Events replayed into projections", ["projection"]
)
PROJECTION_ROWS = Gauge("projection_rows", "Rows held by a projection", ["projection"])
PROJECTION_OUTDATED = Gauge(
    "projection_outdated", "1 when the built version is behind the code version", ["projection"]
)
PROJECTION_LAG = Gauge(
    "projection_lag_events", "Events the projection has not yet applied", ["projection"]
)
PROJECTION_REBUILD_SECONDS = Histogram(
    "projection_rebuild_duration_seconds",
    "Wall time of a projection rebuild",
    ["projection"],
    buckets=_JOB_BUCKETS,
)
PROJECTION_DRIFT = Gauge(
    "projection_drift_rows", "Rows that differ from a shadow replay", ["projection"]
)

# --- notifications ----------------------------------------------------------

NOTIFICATIONS_SENT = Counter(
    "notifications_sent_total", "Notifications delivered", ["channel", "template"]
)
NOTIFICATIONS_FAILED = Counter(
    "notifications_failed_total", "Notification delivery failures", ["channel", "template"]
)
NOTIFICATIONS_DEAD = Counter(
    "notifications_dead_total", "Notifications that exhausted retries", ["channel", "template"]
)
NOTIFICATION_RETRIES = Counter(
    "notification_retries_total", "Delivery attempts after the first", ["channel"]
)
NOTIFICATION_PROVIDER_SECONDS = Histogram(
    "notification_provider_duration_seconds",
    "Time spent inside a channel provider",
    ["channel", "provider"],
    buckets=_API_BUCKETS,
)

# --- payments ---------------------------------------------------------------

PAYMENTS_CREATED = Counter("payments_created_total", "Payments created", ["method"])
PAYMENTS_COMPLETED = Counter("payments_completed_total", "Payments completed", ["method"])
PAYMENTS_FAILED = Counter("payments_failed_total", "Payment attempts that failed", ["method"])
PAYMENTS_CANCELLED = Counter("payments_cancelled_total", "Payments cancelled", ["method"])

# --- receipts ---------------------------------------------------------------

RECEIPTS_GENERATED = Counter("receipts_generated_total", "Receipts generated")
RECEIPT_RENDER_SECONDS = Histogram(
    "receipt_render_duration_seconds",
    "Time to render a receipt artifact",
    ["format"],
    buckets=_API_BUCKETS,
)

# --- offline sync -----------------------------------------------------------

SYNC_OPERATIONS = Counter("sync_operations_total", "Device operations replayed", ["kind", "status"])
SYNC_CONFLICTS = Counter("sync_conflicts_total", "Replayed operations that conflicted", ["reason"])
SYNC_BATCH_SECONDS = Histogram(
    "sync_batch_duration_seconds", "Time to apply one device batch", buckets=_API_BUCKETS
)
SYNC_QUEUE_DEPTH = Gauge(
    "sync_pending_operations", "Device operations recorded but not yet applied"
)

# --- pricing ----------------------------------------------------------------

PRICING_RESOLUTION_SECONDS = Histogram(
    "pricing_resolution_duration_seconds", "Rate-card resolution latency", buckets=_API_BUCKETS
)
PRICING_FAILURES = Counter(
    "pricing_failures_total", "Resolutions or calculations that produced no price", ["stage"]
)

# --- settlements ------------------------------------------------------------

SETTLEMENTS_CREATED = Counter("settlements_created_total", "Settlements created")
SETTLEMENTS_FINALIZED = Counter("settlements_finalized_total", "Settlements finalized")
SETTLEMENTS_CANCELLED = Counter("settlements_cancelled_total", "Settlements cancelled")

# --- platform health --------------------------------------------------------
# `component` and `status` are both fixed vocabularies (see core/health.py).

COMPONENT_HEALTH = Gauge(
    "component_health",
    "Component health as a number: 3 healthy, 2 warning, 1 degraded, 0 critical",
    ["component"],
)
ALERTS_FIRING = Gauge("alerts_firing", "Alert rules currently firing", ["severity"])


# --- cardinality guardrail --------------------------------------------------

# Label names that may never appear on a metric: each would multiply the
# series count by an unbounded, customer-driven factor.
FORBIDDEN_LABELS = frozenset(
    {
        "tenant",
        "tenant_id",
        "user",
        "user_id",
        "actor",
        "actor_id",
        "supplier",
        "supplier_id",
        "email",
        "phone",
        "id",
        "uuid",
        "path",
        "url",
        "message",
        "error",
        "reference",
        "receipt_number",
        "payment_number",
    }
)


def declared_metrics() -> dict[str, tuple[str, ...]]:
    """Every metric this module defines, with its label names.

    Used by the cardinality test and by the metrics documentation, so both
    describe what actually exists rather than what someone remembered.
    """
    import sys

    module = sys.modules[__name__]
    found: dict[str, tuple[str, ...]] = {}
    for value in vars(module).values():
        name = getattr(value, "_name", None)
        if name and hasattr(value, "_labelnames"):
            found[name] = tuple(value._labelnames)
    return found
