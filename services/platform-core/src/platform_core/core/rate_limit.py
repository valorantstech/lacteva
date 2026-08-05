"""Rate limiting (SEC-001).

Protects the endpoints where an attacker gets the most value per request:
credential endpoints (brute force, credential stuffing), token endpoints
(refresh abuse), one-time-token endpoints (reset and invitation guessing), and
the expensive platform operations (projection rebuild, consumer replay,
template preview) where a single authorised caller can cost the platform far
more than it costs them.

**One Redis round trip per request.** A fixed window implemented as
`INCR` + `EXPIRE` in a pipeline: two commands, one trip, no Lua, no read-then-
write race. A sliding window would be more precise and would cost a sorted-set
operation plus a trim on every call; for abuse control the extra precision buys
nothing worth that.

**Fail-open by default, deliberately.** If Redis is unreachable the limiter
allows the request and logs it. A dairy at 5 a.m. must not stop accepting milk
because a cache is down — availability of the business function outranks the
marginal security of a rate limit. Deployments that disagree set
`LACTEVA_RATE_LIMIT_FAIL_OPEN=false`; the trade-off is documented in
SECURITY.md rather than decided silently here.

Scopes compose: a rule may be keyed per-IP, per-user, or per-endpoint, and the
key always includes the rule name so limits never collide.
"""

import time
from dataclasses import dataclass

import structlog

from platform_core.core.config import get_settings
from platform_core.core.errors import AppError
from platform_core.core.metrics import RATE_LIMITED, RATE_LIMITER_UNAVAILABLE

log = structlog.get_logger("security.rate_limit")


class RateLimitExceeded(AppError):
    """429 with structured retry information (RFC 9457 problem detail)."""

    status_code = 429
    code = "rate_limited"
    message_key = "error.rate_limited"

    def __init__(self, rule: str, retry_after: int, limit: int, window: int):
        # The platform convention: `detail` IS the structured payload that
        # surfaces as `extra` in the problem document (see pricing errors).
        super().__init__(
            {
                "rule": rule,
                "retry_after_seconds": retry_after,
                "limit": limit,
                "window_seconds": window,
            }
        )
        self.retry_after = retry_after


@dataclass(frozen=True)
class RateLimitRule:
    """A named budget: `limit` requests per `window` seconds, per scope."""

    name: str
    limit: int
    window_seconds: int
    scope: str = "ip"  # ip | user | endpoint | ip+user

    def key(self, *, ip: str, user: str | None, endpoint: str) -> str:
        parts = [f"rl:{self.name}"]
        if "ip" in self.scope:
            parts.append(f"ip={ip}")
        if "user" in self.scope:
            parts.append(f"user={user or 'anonymous'}")
        if "endpoint" in self.scope:
            parts.append(f"ep={endpoint}")
        return "|".join(parts)


@dataclass(frozen=True)
class RateLimitVerdict:
    allowed: bool
    remaining: int
    retry_after: int


class MemoryRateLimiter:
    """In-process fixed window — tests, and single-node dev.

    Explicitly NOT for production: it cannot see other workers, so the real
    limit becomes `limit x worker count`.
    """

    def __init__(self):
        self._counters: dict[str, tuple[int, float]] = {}

    async def hit(self, key: str, rule: RateLimitRule) -> RateLimitVerdict:
        now = time.monotonic()
        count, expires = self._counters.get(key, (0, now + rule.window_seconds))
        if now >= expires:
            count, expires = 0, now + rule.window_seconds
        count += 1
        self._counters[key] = (count, expires)
        remaining = max(rule.limit - count, 0)
        return RateLimitVerdict(
            allowed=count <= rule.limit,
            remaining=remaining,
            retry_after=max(int(expires - now), 1),
        )

    async def reset(self) -> None:
        self._counters.clear()


class RedisRateLimiter:
    """Redis fixed window: INCR + EXPIRE pipelined — one round trip."""

    def __init__(self, url: str):
        self._url = url
        self._client = None

    async def _redis(self):
        if self._client is None:
            import redis.asyncio as redis

            self._client = redis.from_url(self._url, encoding="utf-8", decode_responses=True)
        return self._client

    async def hit(self, key: str, rule: RateLimitRule) -> RateLimitVerdict:
        client = await self._redis()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, rule.window_seconds, nx=True)
        count, _ = await pipe.execute()
        count = int(count)
        ttl = await client.ttl(key)
        return RateLimitVerdict(
            allowed=count <= rule.limit,
            remaining=max(rule.limit - count, 0),
            retry_after=max(int(ttl), 1) if ttl and ttl > 0 else rule.window_seconds,
        )

    async def reset(self) -> None:  # pragma: no cover - operational tool
        client = await self._redis()
        async for key in client.scan_iter("rl:*"):
            await client.delete(key)


_limiter = None


def get_rate_limiter():
    global _limiter
    if _limiter is None:
        settings = get_settings()
        _limiter = (
            RedisRateLimiter(settings.redis_url)
            if settings.rate_limit_backend == "redis"
            else MemoryRateLimiter()
        )
    return _limiter


def set_rate_limiter(limiter) -> None:
    """Install a limiter (tests, and deployments with their own backend)."""
    global _limiter
    _limiter = limiter


async def enforce(rule: RateLimitRule, *, ip: str, user: str | None, endpoint: str) -> None:
    """Charge one request against `rule`, raising 429 when the budget is spent."""
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return
    key = rule.key(ip=ip, user=user, endpoint=endpoint)
    try:
        verdict = await get_rate_limiter().hit(key, rule)
    except Exception as exc:  # the limiter must never turn into a 500
        RATE_LIMITER_UNAVAILABLE.inc()
        if settings.rate_limit_fail_open:
            log.warning("rate_limiter_unavailable", rule=rule.name, error=str(exc))
            return
        log.error("rate_limiter_unavailable_failing_closed", rule=rule.name, error=str(exc))
        raise RateLimitExceeded(
            rule.name, rule.window_seconds, rule.limit, rule.window_seconds
        ) from exc
    if not verdict.allowed:
        RATE_LIMITED.labels(rule.name).inc()
        raise RateLimitExceeded(rule.name, verdict.retry_after, rule.limit, rule.window_seconds)


# --- the platform's rules ---------------------------------------------------
# Credential endpoints are keyed per-IP AND per-identifier so neither a single
# host hammering many accounts (credential stuffing) nor many hosts hammering
# one account (distributed brute force) slips through a purely per-IP limit.

LOGIN = RateLimitRule("login", limit=10, window_seconds=60, scope="ip")
LOGIN_PER_USER = RateLimitRule("login-user", limit=10, window_seconds=300, scope="user")
REFRESH = RateLimitRule("refresh", limit=30, window_seconds=60, scope="ip")
PASSWORD_RESET = RateLimitRule("password-reset", limit=5, window_seconds=900, scope="ip")
INVITATION_ACCEPT = RateLimitRule("invitation-accept", limit=10, window_seconds=900, scope="ip")
NOTIFICATION_PREVIEW = RateLimitRule(
    "notification-preview", limit=60, window_seconds=60, scope="ip+user"
)
PROJECTION_REBUILD = RateLimitRule(
    "projection-rebuild", limit=5, window_seconds=300, scope="ip+user"
)
CONSUMER_REPLAY = RateLimitRule("consumer-replay", limit=20, window_seconds=300, scope="ip+user")
