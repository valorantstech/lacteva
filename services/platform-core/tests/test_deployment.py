"""Deployment and operational safety (DEP-001).

Nothing here tests business behaviour. It tests the properties a deployment
depends on: that a SIGTERM finishes work instead of abandoning it, that
readiness answers from the same probes the alerts read, that the container's
configuration cannot silently be a development configuration, and that the
compose/nginx artefacts say what the runbook claims they say.

The last group looks unusual for a test suite and is deliberate: a deployment
file that drifts from its documentation is the failure mode that only shows up
during an incident, when nobody has time to read both.
"""

import asyncio
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]


# --- graceful shutdown -----------------------------------------------------


async def test_a_worker_finishes_its_unit_of_work_before_stopping():
    """The point of a cooperative stop.

    Cancelling would be *safe* — a rolled-back consumer transaction is
    retried — but every rolling deploy would leave work to redo. The loop
    must leave between units of work, never inside one.
    """
    from platform_core.core import workers

    workers.clear()
    completed: list[int] = []
    entered = asyncio.Event()

    async def loop():
        n = 0
        while not workers.stopping():
            entered.set()
            n += 1
            await asyncio.sleep(0.02)  # the "unit of work" — uninterruptible
            completed.append(n)
            await workers.sleep(60)  # would block for a minute without the flag

    task = asyncio.create_task(loop())
    workers.register("probe", task)
    await entered.wait()

    outcome = await workers.shutdown(grace_seconds=5)
    assert outcome == {"probe": "drained"}, outcome
    assert completed == [1], "the unit of work in flight was abandoned"
    assert task.done() and not task.cancelled()
    workers.clear()


async def test_shutdown_wakes_a_sleeping_worker_immediately():
    """`workers.sleep` must return when the flag is set, not when the timer
    expires — otherwise a 30-second poll interval becomes a 30-second
    shutdown, and the orchestrator kills the container mid-drain."""
    from platform_core.core import workers

    workers.clear()
    started = asyncio.Event()

    async def loop():
        while not workers.stopping():
            started.set()
            await workers.sleep(3600)

    task = asyncio.create_task(loop())
    workers.register("sleeper", task)
    await started.wait()

    async with asyncio.timeout(2):  # far below the 3600s sleep
        outcome = await workers.shutdown(grace_seconds=1)
    assert outcome == {"sleeper": "drained"}
    workers.clear()


async def test_a_worker_that_overruns_its_grace_is_cancelled_and_reported():
    """A shutdown that can hang is not a shutdown. The distinction between a
    clean drain and a forced one is reported, because it predicts whether the
    next start has work to redo."""
    from platform_core.core import workers

    workers.clear()

    async def stubborn():
        await asyncio.sleep(3600)  # ignores the flag entirely

    task = asyncio.create_task(stubborn())
    workers.register("stubborn", task)
    outcome = await workers.shutdown(grace_seconds=0.1)
    assert outcome == {"stubborn": "cancelled_after_grace"}
    workers.clear()


async def test_clearing_the_registry_resets_the_stop_flag():
    """A process (or a test) that starts workers after a shutdown must not
    inherit a set flag and stop immediately."""
    from platform_core.core import workers

    workers.request_stop()
    assert workers.stopping()
    workers.clear()
    assert not workers.stopping()


# --- readiness -------------------------------------------------------------


async def test_readiness_uses_the_same_probes_as_the_alerts(client):
    """Before DEP-001 readiness was a `SELECT 1`, so a load balancer was told
    an instance was ready while its consumer loop was dead and nothing
    downstream was happening — the platform's most dangerous failure shape."""
    from platform_core.core import health

    await health.evaluate()
    r = await client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"  # the original contract, unchanged
    for component in ("database", "redis", "consumers", "projections", "notifications"):
        assert component in body["checks"], component


async def test_a_degraded_platform_is_still_ready(client):
    """Only CRITICAL removes an instance from the pool. Taking a degraded
    instance out of rotation turns a partial problem into a total one, and
    there is nowhere better for the traffic to go."""
    from platform_core.core import health

    health._last = health.PlatformHealth(
        status=health.DEGRADED,
        components=[health.degraded("consumers", "lagging")],
        checked_at="2026-08-06T00:00:00Z",
    )
    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["platform_status"] == health.DEGRADED


async def test_a_critical_platform_is_not_ready(client):
    from platform_core.core import health

    health._last = health.PlatformHealth(
        status=health.CRITICAL,
        components=[health.critical("database", "unreachable")],
        checked_at="2026-08-06T00:00:00Z",
    )
    r = await client.get("/health/ready")
    assert r.status_code == 503


async def test_liveness_never_touches_a_dependency(client):
    """Liveness answers "is this process alive", not "is the platform well".
    If it consulted the database, a database outage would make every
    orchestrator restart every container — turning an outage into an outage
    plus a thundering herd."""
    r = await client.get("/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


# --- deployment artefacts --------------------------------------------------


def _compose() -> dict:
    import yaml

    return yaml.safe_load((REPO / "docker-compose.production.yml").read_text())


def test_the_production_stack_defines_every_documented_service():
    services = set(_compose()["services"])
    for required in ("api", "migrate", "postgres", "redis", "nginx", "prometheus", "grafana"):
        assert required in services, f"{required} missing from the production stack"


def test_nothing_in_production_waits_on_a_sleep():
    """Ordering is by health check. `sleep 10` is a guess that is either too
    short (and fails under load) or too long (and wastes every deploy)."""
    raw = (REPO / "docker-compose.production.yml").read_text()
    offenders = [
        line.strip()
        for line in raw.splitlines()
        if "sleep" in line and not line.strip().startswith("#")
    ]
    assert offenders == [], f"startup ordering must use health checks, not sleeps: {offenders}"


def test_the_api_starts_only_after_its_dependencies_are_healthy():
    api = _compose()["services"]["api"]
    depends = api["depends_on"]
    assert depends["postgres"]["condition"] == "service_healthy"
    assert depends["redis"]["condition"] == "service_healthy"
    # Migrations are not a dependency to be started alongside — they must have
    # COMPLETED, or the API can boot against a schema that is not there yet.
    assert depends["migrate"]["condition"] == "service_completed_successfully"


def test_migrations_run_as_their_own_service_and_can_fail_the_deploy():
    migrate = _compose()["services"]["migrate"]
    assert "alembic upgrade head" in " ".join(
        migrate["command"] if isinstance(migrate["command"], list) else [migrate["command"]]
    )
    assert migrate.get("restart", "no") == "no", (
        "a failing migration must abort the deployment, not retry forever"
    )


def test_no_development_mounts_or_debug_flags_in_production():
    compose = _compose()
    for name, service in compose["services"].items():
        for volume in service.get("volumes", []):
            spec = volume if isinstance(volume, str) else volume.get("source", "")
            # Bind-mounting the source tree is how a "production" stack quietly
            # runs whatever is on the operator's laptop.
            assert not spec.startswith("./services"), f"{name} bind-mounts source: {volume}"
            assert not spec.startswith("./src"), f"{name} bind-mounts source: {volume}"
        env = service.get("environment", {})
        values = env.values() if isinstance(env, dict) else env
        for value in values:
            assert "--reload" not in str(value), f"{name} runs with reload"


def test_every_service_has_a_healthcheck_or_says_why_not():
    compose = _compose()
    for name, service in compose["services"].items():
        if name == "migrate":
            continue  # a one-shot job is healthy by exiting zero
        assert "healthcheck" in service, f"{name} has no healthcheck"


def test_the_api_container_gets_longer_to_stop_than_its_workers_get_to_drain():
    """If the orchestrator's kill timeout is shorter than the drain grace, the
    container is killed mid-drain and the drain was pointless."""
    from platform_core.core.config import Settings

    api = _compose()["services"]["api"]
    grace = api.get("stop_grace_period", "")
    assert grace.endswith("s"), f"expected an explicit stop_grace_period, got {grace!r}"
    assert int(grace.rstrip("s")) > Settings().shutdown_grace_seconds


def test_the_example_environment_documents_every_variable_it_sets():
    """A variable without a comment is a variable nobody can set correctly."""
    lines = (REPO / ".env.production.example").read_text().splitlines()
    undocumented = []
    for i, line in enumerate(lines):
        if "=" not in line or line.strip().startswith("#") or not line.strip():
            continue
        preceding = [x for x in lines[max(0, i - 6) : i] if x.strip().startswith("#")]
        if not preceding:
            undocumented.append(line.split("=")[0])
    assert undocumented == [], f"undocumented variables: {undocumented}"


def test_the_example_environment_contains_no_real_secret():
    """It is committed, so every value in it must be obviously a placeholder."""
    raw = (REPO / ".env.production.example").read_text()
    for line in raw.splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition("=")
        if any(t in key.upper() for t in ("SECRET", "PASSWORD", "KEY", "TOKEN", "DSN")):
            assert value.strip() in ("", "CHANGEME") or "CHANGEME" in value or "<" in value, (
                f"{key} looks like it carries a real value: {value!r}"
            )


@pytest.mark.parametrize(
    "directive",
    [
        "gzip on",  # compression
        "proxy_set_header Upgrade",  # websockets
        "client_max_body_size",  # large uploads
        "Strict-Transport-Security",  # HTTPS security headers
        "X-Content-Type-Options",
        "proxy_read_timeout",
    ],
)
def test_nginx_configures_what_the_runbook_promises(directive):
    conf = (REPO / "infra/nginx/conf.d/lacteva.conf").read_text()
    base = (REPO / "infra/nginx/nginx.conf").read_text()
    assert directive in conf + base, f"nginx is missing {directive}"
