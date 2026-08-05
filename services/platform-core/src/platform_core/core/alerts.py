"""Alert rules (OBS-001).

An alert is a **promise that a human will act**. Every rule here therefore
carries the one thing most alerting systems omit: what to do about it. A rule
with no action is a notification, and notifications train operators to ignore
alerts.

Two deliberate choices:

**Rules are data, evaluated in one place.** They are declared as objects with
a severity, a condition, and a runbook link, so the same definitions drive
the operator API here *and* the exported Prometheus rules — a single source
that cannot drift into two different opinions about what "lagging" means.

**Evaluation reads health and metrics, never business tables.** Alert
evaluation must not become a load source, and it must keep working when the
thing it is alerting about is the database.

Severity means response time, not importance:

| Severity   | Response          | Example                                   |
| ---------- | ----------------- | ----------------------------------------- |
| `critical` | Page now          | Database unreachable; signing key expired |
| `warning`  | Look within a day | Consumer lag climbing; key expiring soon  |
| `info`     | Review at leisure | A consumer is deliberately paused         |
"""

from collections.abc import Callable
from dataclasses import dataclass

import structlog

from platform_core.core import health
from platform_core.core.metrics import ALERTS_FIRING

log = structlog.get_logger("alerts")

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class AlertRule:
    """One condition an operator has agreed to be woken for."""

    name: str
    severity: str
    summary: str
    # What the operator should DO. A rule without this is a notification.
    action: str
    # Evaluated against the platform health snapshot.
    condition: Callable[[health.PlatformHealth], bool]
    runbook: str = "docs/03-architecture/06-operations/RUNBOOK.md"


@dataclass(frozen=True)
class FiringAlert:
    name: str
    severity: str
    summary: str
    action: str
    runbook: str
    detail: str


def _component(snapshot: health.PlatformHealth, name: str) -> health.ComponentHealth | None:
    return next((c for c in snapshot.components if c.name == name), None)


def _status_at_least(snapshot: health.PlatformHealth, name: str, *statuses: str) -> bool:
    component = _component(snapshot, name)
    return component is not None and component.status in statuses


def _data(snapshot: health.PlatformHealth, name: str, key: str, default=0):
    component = _component(snapshot, name)
    return component.data.get(key, default) if component else default


# --- the platform's rules ---------------------------------------------------

RULES: tuple[AlertRule, ...] = (
    AlertRule(
        name="database_unavailable",
        severity=CRITICAL,
        summary="The database is unreachable — the platform cannot serve requests.",
        action=(
            "Check the database host and connection pool. Until it returns the platform "
            "is down; there is no degraded mode for this."
        ),
        condition=lambda s: _status_at_least(s, "database", health.CRITICAL),
    ),
    AlertRule(
        name="redis_unavailable",
        severity=WARNING,
        summary="Redis is unreachable — rate limits are failing open.",
        action=(
            "Collection is unaffected by design. Restore Redis; until then the platform "
            "has no abuse protection, so watch auth_failures_total."
        ),
        condition=lambda s: _status_at_least(s, "redis", health.DEGRADED, health.CRITICAL),
    ),
    AlertRule(
        name="background_worker_stopped",
        severity=CRITICAL,
        summary="A background worker has stopped — asynchronous work is not happening.",
        action=(
            "The API will look healthy while notifications, receipts, and projections "
            "silently stall. Check the logs for the worker's exception and restart the "
            "process; work is durable and resumes from the log."
        ),
        condition=lambda s: _status_at_least(
            s, "background_workers", health.DEGRADED, health.CRITICAL
        ),
    ),
    AlertRule(
        name="consumer_stopped",
        severity=WARNING,
        summary="A consumer is paused.",
        action=(
            "If this was deliberate (an incident, a deploy), no action. If not, resume it "
            "with POST /v1/_consumers/{name}/resume — the cursor means nothing is lost."
        ),
        condition=lambda s: bool(_data(s, "consumers", "paused", [])),
    ),
    AlertRule(
        name="consumer_lag",
        severity=WARNING,
        summary="A consumer is falling behind the event log.",
        action=(
            "Check whether the consumer is failing (dead letters) or merely slow. During a "
            "collection peak some lag is normal; sustained growth is not."
        ),
        condition=lambda s: bool(_data(s, "consumers", "lagging", [])),
    ),
    AlertRule(
        name="dead_letter_growth",
        severity=CRITICAL,
        summary="Events are being dead-lettered — some business effect is not happening.",
        action=(
            "Inspect GET /v1/_consumers/dead-letters. Fix the handler, then replay; dead "
            "events remain replayable forever, so nothing is lost while you investigate."
        ),
        condition=lambda s: bool(_data(s, "consumers", "dead_lettering", [])),
    ),
    AlertRule(
        name="outbox_backlog",
        severity=WARNING,
        summary="Business events are not leaving the outbox.",
        action=(
            "Check the relay dispatcher and the transport. Events are durable — this is a "
            "delay, not a loss — but everything downstream is stalled behind it."
        ),
        condition=lambda s: _status_at_least(s, "outbox", health.WARNING, health.DEGRADED),
    ),
    AlertRule(
        name="projection_rebuild_failed",
        severity=CRITICAL,
        summary="A projection rebuild failed — its read model may be incomplete.",
        action=(
            "Reports and notification recipients read from projections; a partial rebuild "
            "gives confidently wrong answers. Re-run the rebuild, then verify with "
            "POST /v1/_projections/{name}/verify?deep=true."
        ),
        condition=lambda s: bool(_data(s, "projections", "failed", [])),
    ),
    AlertRule(
        name="projection_drift",
        severity=CRITICAL,
        summary="A projection disagrees with a replay of the event log.",
        action=(
            "The read model has diverged from the source of truth. Rebuild it; the log is "
            "authoritative and the rebuild is safe by BR-0015."
        ),
        condition=lambda s: bool(_data(s, "projections", "outdated", [])),
    ),
    AlertRule(
        name="notification_failure_spike",
        severity=WARNING,
        summary="Notification deliveries are failing.",
        action=(
            "Check the channel provider. Notifications retry on a backoff and dead-letter "
            "after five attempts; retry survivors with POST /v1/notifications/retry-pending."
        ),
        condition=lambda s: _status_at_least(s, "notifications", health.WARNING, health.DEGRADED),
    ),
    AlertRule(
        name="jwt_key_expiring",
        severity=WARNING,
        summary="The signing key is close to expiry.",
        action=(
            "Rotate now — JWT-ROTATION.md §2. Rotation is additive and invalidates nothing, "
            "so there is no reason to wait for a window."
        ),
        condition=lambda s: _status_at_least(s, "jwt_keys", health.WARNING),
    ),
    AlertRule(
        name="jwt_keys_unusable",
        severity=CRITICAL,
        summary="No usable signing key — authentication is failing or about to.",
        action=(
            "Every login and token refresh fails. Install a valid key immediately "
            "(JWT-ROTATION.md §5) — this is an outage, not a warning."
        ),
        condition=lambda s: _status_at_least(s, "jwt_keys", health.CRITICAL),
    ),
)


def evaluate(snapshot: health.PlatformHealth) -> list[FiringAlert]:
    """Which rules are firing right now, worst first."""
    firing: list[FiringAlert] = []
    for rule in RULES:
        try:
            if not rule.condition(snapshot):
                continue
        except Exception as exc:  # a broken rule must not hide the others
            log.warning("alert_rule_failed", rule=rule.name, error=str(exc))
            continue
        component = next(
            (c for c in snapshot.components if c.name in rule.name or rule.name in c.name), None
        )
        firing.append(
            FiringAlert(
                name=rule.name,
                severity=rule.severity,
                summary=rule.summary,
                action=rule.action,
                runbook=rule.runbook,
                detail=component.detail if component else "",
            )
        )

    order = {CRITICAL: 0, WARNING: 1, INFO: 2}
    firing.sort(key=lambda a: order.get(a.severity, 9))
    for severity in (CRITICAL, WARNING, INFO):
        ALERTS_FIRING.labels(severity).set(sum(1 for a in firing if a.severity == severity))
    return firing
