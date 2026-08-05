"""The platform's health probes (OBS-001).

One probe per component an operator can act on. Each answers a question in
the operator's terms, not the implementation's:

| Component              | The question it answers                          |
| ---------------------- | ------------------------------------------------ |
| `database`             | Can we read and write at all?                    |
| `redis`                | Are rate limits actually enforced?               |
| `outbox`               | Are business events getting out?                 |
| `consumers`            | Is anything falling behind, or dead-lettering?   |
| `projections`          | Are the read models current and correct?         |
| `notifications`        | Are farmers being told what they need to know?   |
| `jwt_keys`             | Can we still sign and verify tokens tomorrow?    |
| `background_workers`   | Are the loops that do all of this actually alive?|

**Probes must be cheap.** Each is a bounded query or an in-memory read; none
of them scans a table. The whole endpoint budget is 50 ms, and an operator
polling every 10 seconds must not become a load source.

**Thresholds carry judgement, not arithmetic.** A consumer 100 events behind
during a morning collection peak is normal; 5000 behind means milk is being
recorded that nothing downstream has seen. The numbers below encode that
judgement and are documented in ALERTING.md so an operator can argue with
them.
"""

from datetime import timedelta

import structlog
from sqlalchemy import func, select, text

from platform_core.core import health
from platform_core.core.config import get_settings
from platform_core.core.db import as_utc, get_session_factory, utcnow

log = structlog.get_logger("health.probe")

# --- thresholds (documented in ALERTING.md) ---------------------------------
CONSUMER_LAG_WARNING = 500
CONSUMER_LAG_DEGRADED = 5_000
OUTBOX_PENDING_WARNING = 1_000
OUTBOX_PENDING_DEGRADED = 10_000
OUTBOX_STALE_MINUTES = 15  # oldest undelivered event
NOTIFICATION_DEAD_WARNING = 1
NOTIFICATION_FAILURE_RATIO_DEGRADED = 0.25
KEY_EXPIRY_WARNING_DAYS = 14


async def database() -> health.ComponentHealth:
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        return health.critical("database", f"unreachable: {type(exc).__name__}")
    return health.healthy("database")


async def redis() -> health.ComponentHealth:
    """Redis backs rate limiting. Its absence is DEGRADED, not critical:
    collection keeps working, but abuse protection is off (the limiter fails
    open by design — see SECURITY.md)."""
    settings = get_settings()
    if settings.rate_limit_backend != "redis":
        return health.healthy("redis", "not in use (memory rate limiter)", backend="memory")
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
    except Exception as exc:
        return health.degraded(
            "redis",
            "unreachable — rate limits are failing open",
            error=type(exc).__name__,
        )
    return health.healthy("redis")


async def outbox() -> health.ComponentHealth:
    """A growing outbox means business events are not reaching consumers —
    notifications, receipts, and projections all stall behind it."""
    from platform_core.modules.event_relay.models import DeadLetter, OutboxEvent

    async with get_session_factory()() as session:
        pending = (
            await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.status.in_(("pending", "claimed")))
            )
        ) or 0
        oldest = await session.scalar(
            select(func.min(OutboxEvent.created_at)).where(OutboxEvent.status == "pending")
        )
        dead = (await session.scalar(select(func.count()).select_from(DeadLetter))) or 0

    data = {"pending": pending, "dead_letters": dead}
    if oldest is not None:
        age = utcnow() - as_utc(oldest)
        data["oldest_pending_minutes"] = round(age.total_seconds() / 60, 1)
        if age > timedelta(minutes=OUTBOX_STALE_MINUTES):
            minutes = data["oldest_pending_minutes"]
            return health.degraded("outbox", f"oldest pending event is {minutes} min old", **data)
    if pending >= OUTBOX_PENDING_DEGRADED:
        return health.degraded("outbox", f"{pending} events awaiting delivery", **data)
    if pending >= OUTBOX_PENDING_WARNING or dead:
        return health.warning("outbox", f"{pending} pending, {dead} dead-lettered", **data)
    return health.healthy("outbox", **data)


async def consumers() -> health.ComponentHealth:
    """A consumer that is disabled, lagging, or dead-lettering is the single
    most common way this platform silently stops doing its job."""
    from platform_core.modules.event_relay.consumers import ConsumerRunner

    runner = ConsumerRunner(get_session_factory())
    report = await runner.health()
    statuses: list[str] = []
    lagging: list[str] = []
    dead: list[str] = []
    paused: list[str] = []
    for entry in report.consumers:
        if not entry.enabled:
            paused.append(entry.name)
            statuses.append(health.WARNING)  # deliberate, but worth surfacing
            continue
        if entry.dead:
            dead.append(f"{entry.name}({entry.dead})")
            statuses.append(health.DEGRADED)
        if entry.lag_events >= CONSUMER_LAG_DEGRADED:
            lagging.append(f"{entry.name}({entry.lag_events})")
            statuses.append(health.DEGRADED)
        elif entry.lag_events >= CONSUMER_LAG_WARNING:
            lagging.append(f"{entry.name}({entry.lag_events})")
            statuses.append(health.WARNING)
        else:
            statuses.append(health.HEALTHY)

    data = {
        "count": len(report.consumers),
        "paused": paused,
        "lagging": lagging,
        "dead_lettering": dead,
        "max_lag": max((c.lag_events for c in report.consumers), default=0),
    }
    status = health.worst(statuses)
    if status == health.HEALTHY:
        return health.healthy("consumers", **data)
    detail = "; ".join(
        part
        for part in (
            f"paused: {', '.join(paused)}" if paused else "",
            f"lagging: {', '.join(lagging)}" if lagging else "",
            f"dead letters: {', '.join(dead)}" if dead else "",
        )
        if part
    )
    return health.ComponentHealth("consumers", status, detail, data)


async def projections() -> health.ComponentHealth:
    """Projections feed reporting and notification recipients. Outdated or
    drifting read models produce confidently wrong answers, which is worse
    than no answer."""
    from platform_core.modules.event_relay.projections import ProjectionRebuilder

    rebuilder = ProjectionRebuilder(get_session_factory())
    statuses = await rebuilder.status_all()
    outdated = [s.name for s in statuses if s.status == "outdated"]
    rebuilding = [s.name for s in statuses if s.status == "rebuilding"]
    failed = [s.name for s in statuses if s.status == "failed"]
    behind = [s.name for s in statuses if s.pending > CONSUMER_LAG_WARNING]

    data = {
        "count": len(statuses),
        "outdated": outdated,
        "rebuilding": rebuilding,
        "failed": failed,
        "behind": behind,
    }
    if failed:
        return health.degraded("projections", f"rebuild failed: {', '.join(failed)}", **data)
    if outdated or behind:
        return health.warning(
            "projections",
            f"outdated: {', '.join(outdated) or 'none'}; behind: {', '.join(behind) or 'none'}",
            **data,
        )
    return health.healthy("projections", **data)


async def notifications() -> health.ComponentHealth:
    """Dead notifications mean a farmer was never told about their money."""
    from platform_core.modules.notification.models import Notification

    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(Notification.status, func.count()).group_by(Notification.status)
            )
        ).all()
    counts = {status: count for status, count in rows}
    total = sum(counts.values())
    dead = counts.get("dead", 0)
    failed = counts.get("failed", 0)
    data = {"total": total, **{f"{k}": v for k, v in counts.items()}}

    if total and (failed + dead) / total >= NOTIFICATION_FAILURE_RATIO_DEGRADED:
        return health.degraded(
            "notifications", f"{failed + dead} of {total} deliveries are failing", **data
        )
    if dead >= NOTIFICATION_DEAD_WARNING:
        return health.warning("notifications", f"{dead} notification(s) gave up", **data)
    return health.healthy("notifications", **data)


async def jwt_keys() -> health.ComponentHealth:
    """A signing key that expires unnoticed takes authentication down for
    everyone at once — this is the check that buys the warning window."""
    from platform_core.core.keys import KeyRegistryError, get_key_registry

    try:
        registry = get_key_registry()
        current = registry.current()
    except KeyRegistryError as exc:
        return health.critical("jwt_keys", str(exc))

    data = {"keys": len(registry.keys), "signing_kid": current.kid}
    if current.expires_at is not None:
        remaining = as_utc(current.expires_at) - utcnow()
        data["signing_key_expires_in_days"] = round(remaining.total_seconds() / 86400, 1)
        if remaining <= timedelta(0):
            return health.critical("jwt_keys", "the signing key has expired", **data)
        if remaining <= timedelta(days=KEY_EXPIRY_WARNING_DAYS):
            return health.warning(
                "jwt_keys",
                f"signing key expires in {data['signing_key_expires_in_days']} days — rotate",
                **data,
            )
    if get_settings().env == "prod" and not get_settings().jwt_keys:
        return health.critical("jwt_keys", "running on an ephemeral key in production", **data)
    return health.healthy("jwt_keys", **data)


async def background_workers() -> health.ComponentHealth:
    """The relay and consumer loops do the platform's asynchronous work. If
    they are not running, everything above them looks fine while nothing
    actually happens — the most dangerous failure shape there is."""
    from platform_core.core import workers

    report = workers.status()
    stopped = [name for name, alive in report.items() if not alive]
    data = {"workers": report}
    if not report:
        return health.warning("background_workers", "no workers registered", **data)
    if stopped:
        return health.degraded("background_workers", f"stopped: {', '.join(stopped)}", **data)
    return health.healthy("background_workers", **data)


def register_all() -> None:
    """Install every probe. Called once at startup."""
    for name, probe in (
        ("database", database),
        ("redis", redis),
        ("outbox", outbox),
        ("consumers", consumers),
        ("projections", projections),
        ("notifications", notifications),
        ("jwt_keys", jwt_keys),
        ("background_workers", background_workers),
    ):
        health.register_probe(name, probe)
