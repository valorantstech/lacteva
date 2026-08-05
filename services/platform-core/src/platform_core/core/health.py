"""Component health model (OBS-001).

The old readiness check answered one question — "is the database up?" — with
one bit. That is enough for a load balancer and useless for an operator, who
needs to know *which* part is unwell, *how* unwell, and whether it is their
problem right now.

Health is therefore reported per component on a four-level scale:

| Status     | Meaning                                              | Operator action |
| ---------- | ---------------------------------------------------- | --------------- |
| `healthy`  | Working as intended                                  | none |
| `warning`  | Working, but a trend will become a problem           | look today |
| `degraded` | Partially working; some capability is lost           | act now |
| `critical` | Not working; the platform cannot do its job          | page someone |

Two rules keep the scale meaningful:

1. **Overall status is the worst component.** Averaging hides the outage.
2. **A check never raises.** An exception in a health check becomes
   `critical` for that component with the reason attached, because a health
   endpoint that 500s tells an operator nothing except that health is broken.

Readiness (`/health/ready`) stays a bit — load balancers need a bit — and is
derived: `critical` means not ready, everything else means ready. That keeps
a degraded platform *serving* rather than being pulled out of rotation for a
problem that removing it would not fix.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import structlog

from platform_core.core.metrics import COMPONENT_HEALTH

log = structlog.get_logger("health")

HEALTHY = "healthy"
WARNING = "warning"
DEGRADED = "degraded"
CRITICAL = "critical"

# Ordered worst-first so `min` picks the worst status without a lookup table.
_SEVERITY = {CRITICAL: 0, DEGRADED: 1, WARNING: 2, HEALTHY: 3}


@dataclass(frozen=True)
class ComponentHealth:
    name: str
    status: str
    detail: str = ""
    # Facts an operator can act on — never a stack trace, never a secret.
    data: dict = field(default_factory=dict)
    duration_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == HEALTHY


@dataclass(frozen=True)
class PlatformHealth:
    status: str
    components: list[ComponentHealth]
    checked_at: str

    @property
    def ready(self) -> bool:
        """Ready unless something is CRITICAL: a degraded platform still
        serves, and removing it from rotation would not fix the degradation."""
        return self.status != CRITICAL


HealthProbe = Callable[[], Awaitable[ComponentHealth]]
_probes: dict[str, HealthProbe] = {}


def register_probe(name: str, probe: HealthProbe) -> None:
    _probes[name] = probe


def registered_probes() -> tuple[str, ...]:
    return tuple(sorted(_probes))


def healthy(name: str, detail: str = "", **data) -> ComponentHealth:
    return ComponentHealth(name=name, status=HEALTHY, detail=detail, data=data)


def warning(name: str, detail: str, **data) -> ComponentHealth:
    return ComponentHealth(name=name, status=WARNING, detail=detail, data=data)


def degraded(name: str, detail: str, **data) -> ComponentHealth:
    return ComponentHealth(name=name, status=DEGRADED, detail=detail, data=data)


def critical(name: str, detail: str, **data) -> ComponentHealth:
    return ComponentHealth(name=name, status=CRITICAL, detail=detail, data=data)


def worst(statuses: list[str]) -> str:
    """The overall status is the worst component — averaging hides outages."""
    if not statuses:
        return HEALTHY
    return min(statuses, key=lambda s: _SEVERITY.get(s, 0))


async def evaluate(only: tuple[str, ...] | None = None) -> PlatformHealth:
    """Run every registered probe. Probes run sequentially and are expected
    to be cheap: a health endpoint that takes a second is one nobody polls."""
    from platform_core.core.db import utcnow

    results: list[ComponentHealth] = []
    for name, probe in sorted(_probes.items()):
        if only and name not in only:
            continue
        started = time.perf_counter()
        try:
            result = await probe()
        except Exception as exc:  # a broken probe is a critical component
            result = critical(name, f"health probe failed: {type(exc).__name__}")
            log.warning("health_probe_failed", component=name, error=str(exc))
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        result = ComponentHealth(
            name=result.name,
            status=result.status,
            detail=result.detail,
            data=result.data,
            duration_ms=elapsed_ms,
        )
        COMPONENT_HEALTH.labels(result.name).set(_SEVERITY.get(result.status, 0))
        results.append(result)
    return PlatformHealth(
        status=worst([r.status for r in results]),
        components=results,
        checked_at=utcnow().isoformat(),
    )
