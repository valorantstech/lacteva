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

**What happens when the limiter is unreachable — SEC-003 / F-06.**

The original answer was "allow the request": a dairy at 5 a.m. must not stop
accepting milk because a cache is down. FINAL-001 rated that an accidental
default rather than a decision, because it also meant a Redis blip silently
removed every brute-force limit from login, refresh, password reset and
invitation acceptance, and the only trace was a log line nobody reads.

The decision taken, and the default: **degrade, do not fail open.** A limiter
error falls back to the process-local counter. The operator can still log in,
so the availability that fail-open protected is protected; and an attacker gets
`limit x worker count` attempts per window instead of unlimited ones, so the
security fail-open gave away is mostly kept. If even the fallback fails, rules
marked `fail_closed=True` — every credential and one-time-token rule — deny,
and the rest allow, because those protect cost rather than credentials.

`LACTEVA_RATE_LIMIT_FAILURE_POLICY` can force `fail_open` or `fail_closed`
whole-platform. `fail_open` is REFUSED in prod. See SECURITY.md.

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
    #: SEC-003 / F-06: if the limiter cannot judge this request even after
    #: falling back to the process-local counter, deny it. True for the rules
    #: that stand between an attacker and a credential or a one-time token;
    #: False for the ones that only protect the platform's own compute, where
    #: refusing an authorised operator costs more than the extra load.
    fail_closed: bool = False

    def key(self, *, ip: str, user: str | None, endpoint: str, tenant: str | None = None) -> str:
        """The Redis key this request is charged against.

        MT-001: `tenant` is not cosmetic. Email is unique PER TENANT
        (`uq_user_tenant_email`), so `alice@dairy-a.example` and
        `alice@dairy-b.example` can be the same string in two different
        organizations. Keying a per-identifier budget on the email alone put
        two different people in two different tenants on ONE counter, which
        is a cross-tenant denial of service: an attacker with an account in
        any tenant could exhaust the login budget of that address in every
        other tenant, by failing to log in to their own.

        Identifiers that are already globally unique — a user id — need no
        tenant, and passing one changes nothing.
        """
        parts = [f"rl:{self.name}"]
        if tenant:
            parts.append(f"t={tenant}")
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
#: The fallback the `degrade` policy charges against when the configured
#: limiter raises. Process-local and deliberately never reset between
#: requests: a limiter outage is exactly when the counter needs to survive.
_fallback_limiter = MemoryRateLimiter()


def get_fallback_limiter() -> MemoryRateLimiter:
    return _fallback_limiter


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


async def _degraded_verdict(
    rule: RateLimitRule, key: str, exc: Exception, *, policy: str
) -> RateLimitVerdict | None:
    """Decide what an unreachable limiter means for this one request.

    Returns a verdict to apply, or `None` for "allow, unjudged". Raises when
    the policy is to deny. Never re-raises the limiter's own exception: a
    cache outage must not become a 500 (SEC-003 / F-06).
    """
    if policy == "fail_open":
        log.warning("rate_limiter_unavailable_failing_open", rule=rule.name, error=str(exc))
        return None
    if policy == "fail_closed":
        log.error("rate_limiter_unavailable_failing_closed", rule=rule.name, error=str(exc))
        raise RateLimitExceeded(
            rule.name, rule.window_seconds, rule.limit, rule.window_seconds
        ) from exc
    # `degrade`. Charge the process-local counter instead. The budget is now
    # per worker rather than per platform, which is worse than Redis and very
    # much better than nothing.
    try:
        verdict = await get_fallback_limiter().hit(key, rule)
    except Exception as fallback_exc:  # pragma: no cover - an in-process dict
        log.error(
            "rate_limiter_fallback_failed",
            rule=rule.name,
            error=str(fallback_exc),
            fail_closed=rule.fail_closed,
        )
        if rule.fail_closed:
            raise RateLimitExceeded(
                rule.name, rule.window_seconds, rule.limit, rule.window_seconds
            ) from fallback_exc
        return None
    log.warning(
        "rate_limiter_degraded",
        rule=rule.name,
        error=str(exc),
        allowed=verdict.allowed,
        scope="process-local",
    )
    return verdict


async def enforce(
    rule: RateLimitRule,
    *,
    ip: str,
    user: str | None,
    endpoint: str,
    tenant: str | None = None,
) -> None:
    """Charge one request against `rule`, raising 429 when the budget is spent.

    Pass `tenant` whenever `user` is an identifier that is only unique within
    a tenant — an email, a supplier code, a phone number. See `RateLimitRule.key`.
    """
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return
    key = rule.key(ip=ip, user=user, endpoint=endpoint, tenant=tenant)
    try:
        verdict = await get_rate_limiter().hit(key, rule)
    except Exception as exc:  # the limiter must never turn into a 500
        RATE_LIMITER_UNAVAILABLE.inc()
        verdict = await _degraded_verdict(rule, key, exc, policy=settings.rate_limit_failure_policy)
        if verdict is None:
            return
    if not verdict.allowed:
        RATE_LIMITED.labels(rule.name).inc()
        raise RateLimitExceeded(rule.name, verdict.retry_after, rule.limit, rule.window_seconds)


# --- the platform's rules ---------------------------------------------------
# Credential endpoints are keyed per-IP AND per-identifier so neither a single
# host hammering many accounts (credential stuffing) nor many hosts hammering
# one account (distributed brute force) slips through a purely per-IP limit.

#
# SEC-003 / F-06: `fail_closed=True` on every rule that stands between an
# attacker and a credential or a one-time token. It only takes effect if the
# process-local fallback ALSO fails, which is close to unreachable — the point
# is that the last resort for a credential endpoint is "no", not "yes".

LOGIN = RateLimitRule("login", limit=10, window_seconds=60, scope="ip", fail_closed=True)
LOGIN_PER_USER = RateLimitRule(
    "login-user", limit=10, window_seconds=300, scope="user", fail_closed=True
)
REFRESH = RateLimitRule("refresh", limit=30, window_seconds=60, scope="ip", fail_closed=True)
PASSWORD_RESET = RateLimitRule(
    "password-reset", limit=5, window_seconds=900, scope="ip", fail_closed=True
)
INVITATION_ACCEPT = RateLimitRule(
    "invitation-accept", limit=10, window_seconds=900, scope="ip", fail_closed=True
)
# The rest protect the platform's own compute, not a secret. Refusing an
# authorised operator here costs more than the extra load would.
NOTIFICATION_PREVIEW = RateLimitRule(
    "notification-preview", limit=60, window_seconds=60, scope="ip+user"
)
PROJECTION_REBUILD = RateLimitRule(
    "projection-rebuild", limit=5, window_seconds=300, scope="ip+user"
)
CONSUMER_REPLAY = RateLimitRule("consumer-replay", limit=20, window_seconds=300, scope="ip+user")
