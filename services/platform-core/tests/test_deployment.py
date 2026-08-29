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
import re

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
        # One-shot jobs are healthy by exiting zero; a health check on a
        # container that is meant to stop would report it as unhealthy for
        # doing its job. Both are gated by `service_completed_successfully`,
        # which is the real ordering guarantee.
        if name in ("migrate", "wal-archive-init"):
            continue
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
    inc = (REPO / "infra/nginx/conf.d/security-headers.inc").read_text()
    assert directive in conf + base + inc, f"nginx is missing {directive}"


# --- the headers have to REACH the browser (WO-42) -------------------------
#
# The test above passed for the whole life of the deployed platform while
# `curl -I https://dev.phoenixsoft.in/login` returned no HSTS, no nosniff and
# no X-Frame-Options at all. Presence in the file is not service on the wire:
# nginx inherits `add_header` from the enclosing level "if and only if there
# are no add_header directives defined on the current level", so any location
# that sets a header of its own silently discards every inherited one — which
# `location /`, the location that serves the entire portal, does.
#
# So this asserts the property that was actually broken, and it is the reason
# the headers now live in an included snippet: a location may add whatever it
# likes, as long as it re-states the security headers with it.

_HEADERS_INCLUDE = "include /etc/nginx/conf.d/security-headers.inc;"


def _location_blocks(conf: str) -> list[tuple[str, str]]:
    """Every `location …{ }` block in the file, as (header line, body)."""
    blocks, i = [], 0
    while (start := conf.find("location ", i)) != -1:
        brace = conf.find("{", start)
        depth, j = 0, brace
        while j < len(conf):
            if conf[j] == "{":
                depth += 1
            elif conf[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        blocks.append((conf[start:brace].strip(), conf[brace : j + 1]))
        i = brace + 1
    return blocks


def test_every_location_that_adds_a_header_restates_the_security_headers():
    conf = (REPO / "infra/nginx/conf.d/lacteva.conf").read_text()
    offenders = [
        name
        for name, body in _location_blocks(conf)
        if "add_header" in body and _HEADERS_INCLUDE not in body
    ]
    assert not offenders, (
        "these locations set a header of their own, which discards every "
        f"inherited security header, and do not re-state them: {offenders}"
    )


def test_the_server_level_still_sets_them_for_everything_else():
    conf = (REPO / "infra/nginx/conf.d/lacteva.conf").read_text()
    outside = conf
    for _, body in _location_blocks(conf):
        outside = outside.replace(body, "")
    assert _HEADERS_INCLUDE in outside, (
        "no location-free level includes the security headers, so a location "
        "that adds nothing of its own would inherit nothing"
    )


def test_the_credential_endpoints_are_rate_limited_more_tightly_than_the_rest():
    # The application's limiter is the precise one, but it needs Redis and it
    # needs a worker. This is the floor beneath it, and it is only a floor if
    # it is actually tighter than the budget every other route gets.
    conf = (REPO / "infra/nginx/conf.d/lacteva.conf").read_text()
    base = (REPO / "infra/nginx/nginx.conf").read_text()

    blocks = dict(_location_blocks(conf))
    assert "location /v1/auth/" in blocks, "the credential endpoints share the general budget"
    assert "limit_req zone=auth" in blocks["location /v1/auth/"]

    rates = {
        name: float(rate)
        for line in base.splitlines()
        if "limit_req_zone" in line and "zone=" in line
        for name, rate in [
            (
                line.split("zone=")[1].split(":")[0],
                line.split("rate=")[1].split("r/s")[0],
            )
        ]
    }
    assert rates["auth"] < rates["api"], f"auth is not the tighter budget: {rates}"


def test_the_longest_prefix_wins_so_the_auth_budget_is_the_one_that_applies():
    # nginx matches the LONGEST prefix, so /v1/auth/ must be a strictly longer
    # prefix of the same shape as /v1/ — not a regex, which would lose to it.
    conf = (REPO / "infra/nginx/conf.d/lacteva.conf").read_text()
    names = [name for name, _ in _location_blocks(conf)]
    assert "location /v1/auth/" in names and "location /v1/" in names
    assert len("/v1/auth/") > len("/v1/")


def test_the_snippet_is_not_loaded_twice_as_a_server_block():
    # `nginx.conf` includes `conf.d/*.conf`. A snippet named `.conf` would be
    # parsed as a second top-level context and nginx would refuse to start.
    base = (REPO / "infra/nginx/nginx.conf").read_text()
    assert "conf.d/*.conf" in base
    assert (REPO / "infra/nginx/conf.d/security-headers.inc").exists()


# --- infrastructure as code (INF-001) --------------------------------------
#
# Terraform cannot be executed here, so these assert the properties whose
# absence would be dangerous rather than merely wrong. They are cheap, and
# each one encodes a decision that is easy to undo by accident.

INFRA = REPO / "infra"


def _tf(*parts) -> str:
    return (INFRA / "terraform" / pathlib.Path(*parts)).read_text()


def _all_tf() -> str:
    return "\n".join(p.read_text() for p in (INFRA / "terraform").rglob("*.tf"))


@pytest.mark.parametrize("target", ["hetzner", "aws"])
def test_ssh_cannot_be_opened_to_the_whole_internet(target):
    """Exposing sshd to 0.0.0.0/0 is the most common way a small deployment is
    compromised. Key-only auth reduces that risk; it does not remove it,
    because the daemon still parses attacker-controlled input from anywhere.
    Both configurations refuse it at plan time."""
    variables = _tf(target, "variables.tf")
    assert 'contains(var.ssh_allowed_cidrs, "0.0.0.0/0")' in variables
    assert "refusing to open SSH" in variables


@pytest.mark.parametrize("target", ["hetzner", "aws"])
def test_only_three_ports_are_reachable(target):
    """80, 443, SSH. Everything else — PostgreSQL, Redis, Prometheus, Grafana,
    Loki — is internal, and the compose network already confines it."""
    source = _tf(target, "firewall.tf") if target == "hetzner" else _tf(target, "main.tf")
    opened = set(re.findall(r'(?:port\s*=\s*"(\d+)"|from_port\s*=\s*(\d+))', source))
    ports = {a or b for a, b in opened}
    assert ports <= {"80", "443", "22", "0"}, f"unexpected inbound ports: {ports}"


@pytest.mark.parametrize("target", ["hetzner", "aws"])
def test_the_data_volume_and_the_static_ip_cannot_be_destroyed(target):
    """They outlive the machine — that is the entire server-replacement story.
    A `terraform destroy` that takes the database with it is not a rebuild."""
    source = _tf(target, "main.tf")
    assert source.count("prevent_destroy = true") >= 2, (
        "the data volume and the static IP must both be protected"
    )


@pytest.mark.parametrize("target", ["hetzner", "aws"])
def test_the_volume_size_is_ignored_after_creation(target):
    """A volume can be grown online and never shrunk. Without `ignore_changes`,
    a smaller number in tfvars plans a destroy-and-recreate of the volume
    holding production data."""
    assert re.search(r"ignore_changes\s*=\s*\[size\]", _tf(target, "main.tf"))


def test_terraform_never_formats_the_data_volume():
    """Formatting belongs to cloud-init, which checks for an existing
    filesystem first. A `format` ATTRIBUTE in Terraform lets an apply after a
    state mishap reformat a volume holding production data."""
    attributes = re.findall(r"^\s*(\w+)\s*=", _tf("hetzner", "main.tf"), re.M)
    assert "format" not in attributes, "hcloud_volume must not declare `format`"


def test_cloud_init_refuses_to_reformat_a_volume_that_has_data():
    init = (INFRA / "cloud-init" / "lacteva.yaml").read_text()
    assert "if ! blkid" in init, "must check for an existing filesystem before mkfs"
    assert "already has a filesystem — leaving it alone" in init


def test_cloud_init_disables_password_and_root_login():
    init = (INFRA / "cloud-init" / "lacteva.yaml").read_text()
    for setting in ("ssh_pwauth: false", "disable_root: true", "lock_passwd: true"):
        assert setting in init, setting
    assert "PermitRootLogin no" in init and "PasswordAuthentication no" in init


def test_cloud_init_does_not_reboot_by_itself():
    """Security patches install automatically; the reboot is scheduled.
    Rebooting a single-host platform without warning is an unplanned outage."""
    init = (INFRA / "cloud-init" / "lacteva.yaml").read_text()
    assert 'Unattended-Upgrade::Automatic-Reboot "false"' in init


def test_no_secret_is_committed_in_any_terraform_file():
    """tfvars are git-ignored and the token is exported, never written."""
    source = _all_tf() + (INFRA / "terraform" / "hetzner" / "terraform.tfvars.example").read_text()
    for pattern in (r"hcloud_token\s*=\s*\"[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}"):
        assert not re.search(pattern, source), f"possible committed credential: {pattern}"


def test_aws_requires_imdsv2():
    """IMDSv1 turns any SSRF in the application into instance credentials —
    the single most valuable thing on the machine."""
    source = _tf("aws", "main.tf")
    assert (
        'http_tokens                 = "required"' in source or 'http_tokens = "required"' in source
    )
    assert "http_put_response_hop_limit = 1" in source, (
        "containers must not reach the metadata service"
    )


def test_aws_volumes_are_encrypted():
    """The data volume holds names, phone numbers, national IDs and bank
    account numbers, none of which are encrypted at the column level."""
    source = _tf("aws", "main.tf")
    encrypted = re.findall(r"^\s*encrypted\s*=\s*true", source, re.M)
    assert len(encrypted) >= 2, (
        f"both the root device and the data volume must be encrypted; found {len(encrypted)}"
    )


# --- systemd ---------------------------------------------------------------


def test_systemd_starts_the_platform_on_boot():
    unit = (INFRA / "systemd" / "lacteva.service").read_text()
    assert "WantedBy=multi-user.target" in unit
    assert "Requires=docker.service" in unit


def test_systemd_waits_for_the_data_volume():
    """Starting before the volume is mounted creates an empty PGDATA on the
    root disk — silently, and only discovered when the data is gone."""
    unit = (INFRA / "systemd" / "lacteva.service").read_text()
    assert "RequiresMountsFor=/var/lib/lacteva" in unit


def test_systemd_allows_the_full_graceful_shutdown():
    """The API's stop_grace_period is 90s (30s draining requests, 20s for
    workers, headroom). systemd must give at least that, or it kills the drain
    DEP-001 exists to make possible."""
    unit = (INFRA / "systemd" / "lacteva.service").read_text()
    stop_timeout = int(re.search(r"TimeoutStopSec=(\d+)", unit).group(1))
    compose_grace = int(_compose()["services"]["api"]["stop_grace_period"].rstrip("s"))
    assert stop_timeout > compose_grace, (
        f"systemd would kill the stack after {stop_timeout}s while the API "
        f"expects up to {compose_grace}s to drain"
    )


def test_every_backup_timer_survives_a_missed_run():
    """A host that was off at 02:15 must still back up when it returns.
    Without Persistent, an overnight reboot silently skips a night."""
    for timer in (INFRA / "systemd").glob("*.timer"):
        assert "Persistent=true" in timer.read_text(), timer.name


def test_the_backup_timers_cover_nightly_weekly_and_verification():
    names = {p.stem for p in (INFRA / "systemd").glob("*.timer")}
    assert {"lacteva-backup-nightly", "lacteva-backup-weekly", "lacteva-backup-verify"} <= names


# --- backup and deploy scripts ---------------------------------------------


def test_retention_prunes_only_after_a_verified_new_backup():
    """Pruning first means a failing backup job deletes its way through the
    retention window, and the day you need a restore there is nothing left."""
    script = (INFRA / "backup" / "run-logical-backup.sh").read_text()
    verify_at = script.index("cli verify")
    prune_at = script.index("pruning backups older")
    assert verify_at < prune_at, "retention must run after verification, never before"
    assert "Nothing pruned." in script


def test_backup_verification_actually_restores():
    """BR-0025: a backup is trusted only once a restore has been demonstrated."""
    script = (INFRA / "backup" / "verify-latest-backup.sh").read_text()
    assert "cli restore" in script
    assert "integrity --deep" in script
    assert "DROP DATABASE" in script, "verification must use a throwaway database"


def test_deploy_takes_a_backup_before_migrating():
    """The last cheap moment to get a way back, and it must come before the
    schema moves."""
    script = (INFRA / "deploy" / "deploy.sh").read_text()
    assert script.index("pre-deployment backup") < script.index("applying migrations")
    assert "refusing to deploy without a way back" in script


def test_deploy_rolls_back_on_verification_or_smoke_failure():
    script = (INFRA / "deploy" / "deploy.sh").read_text()
    assert "VERIFICATION FAILED" in script and "SMOKE TEST FAILED" in script
    assert script.count("rollback_to") >= 3


def test_deploy_never_rolls_the_schema_back_automatically():
    """A code rollback is safe after an expand-only migration and unsafe after
    a contract. No script can tell from the outside, so it must not try."""
    script = (INFRA / "deploy" / "deploy.sh").read_text()
    assert "alembic downgrade" not in script
    assert "SCHEMA MOVED" in script, "a schema change must at least be announced"


# --- the deployment contract, end to end (DEPLOY-001) -----------------------


def _interpolate(value: str, env: dict[str, str]) -> str:
    """Resolve `${VAR}`, `${VAR:-default}` and `${VAR:?message}` the way
    Compose does, so the test reads the same file the operator deploys."""
    import re

    def replace(match: re.Match) -> str:
        name, op, arg = match.group(1), match.group(2), match.group(3)
        present = env.get(name, "")
        if present:
            return present
        if op == ":-":
            return arg
        if op == ":?":
            raise AssertionError(
                f"docker-compose.production.yml requires {name}, which "
                f".env.production.example does not set: {arg}"
            )
        return ""

    return re.sub(r"\$\{([A-Z_][A-Z0-9_]*)(:-|:\?)?([^}]*)\}", replace, value)


def _example_env() -> dict[str, str]:
    env = {}
    for line in (REPO / ".env.production.example").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def test_the_documented_production_stack_can_actually_start():
    """The deployment contract, checked end to end rather than in pieces.

    Take `.env.production.example` — the file DEPLOYMENT.md tells an operator
    to copy — layer the compose `environment:` block over it exactly as the
    container would see it, and hand the result to the platform's OWN
    production validator.

    **This is the test DEPLOY-001 exists for.** Running it for the first time
    found that the documented stack could not start at all:

      * there was no RabbitMQ service and no way to configure one, while
        `prod` refuses `event_bus=memory` — so the API died at startup
      * `LACTEVA_BACKUP_OFFSITE_ENDPOINT` was empty, which `prod` also refuses
      * `LACTEVA_NOTIFICATION_EMAIL_PROVIDER=logging` is refused too
      * every `SMTP_*` variable was missing the `LACTEVA_` prefix, so none of
        them was ever read

    Each piece had a test. Nothing tested the pieces TOGETHER, which is where
    all four defects lived.
    """
    import os

    from platform_core.core.config import Settings

    compose = _compose()
    env = _example_env()
    api_environment = compose["x-api-base"]["environment"]

    resolved = dict(env)
    for key, value in api_environment.items():
        resolved[key] = _interpolate(str(value), env)

    # Build the environment from SCRATCH. `conftest.py` pins test values
    # (`outbox_mode=inline`, `rate_limit_backend=memory`) before any import, and
    # leaving them in place would let the test pass on settings the deployment
    # never supplies — the container starts with a clean environment, so the
    # test must too.
    saved = {k: v for k, v in os.environ.items() if k.startswith("LACTEVA_")}
    try:
        for key in saved:
            os.environ.pop(key, None)
        for key, value in resolved.items():
            if key.startswith("LACTEVA_"):
                os.environ[key] = value
        Settings()  # raises if production would refuse to start
    finally:
        for key in [k for k in os.environ if k.startswith("LACTEVA_")]:
            os.environ.pop(key, None)
        os.environ.update(saved)


def test_every_lacteva_variable_in_the_example_is_a_real_setting():
    """A variable nobody reads is worse than a missing one: it looks configured.

    `SMTP_HOST=` sat in the example through two work orders. The setting is
    `LACTEVA_SMTP_HOST`, so pydantic-settings never read it — an operator could
    fill in a relay and find email silently dead.
    """
    from platform_core.core.config import Settings

    known = {f"LACTEVA_{name.upper()}" for name in Settings.model_fields}
    # Compose-level variables: consumed by docker-compose interpolation to
    # build the image reference and create the database role. They are never
    # read by the application, so they are legitimately not settings.
    compose_only = {
        "LACTEVA_IMAGE",
        "LACTEVA_IMAGE_TAG",
        "LACTEVA_APP_USER",
        "LACTEVA_APP_PASSWORD",
        # DEMO-011: the bind-mount devices for the backup and WAL volumes.
        # Compose interpolates them into `volumes:`; the application never
        # reads either, because inside the container they are simply /backup
        # and /wal-archive.
        "LACTEVA_BACKUP_DIR",
        "LACTEVA_WAL_DIR",
    }
    # Read by the DEPLOYMENT SCRIPTS rather than by the application or by
    # compose. The distinction matters for the same reason the test exists: a
    # variable nobody reads looks configured. Each of these must be named by
    # something under infra/, which is asserted below rather than trusted.
    deploy_only = {
        "LACTEVA_PUBLIC_URL",  # deploy.sh: where verification and the smoke test point
    }
    # Same discipline as `deploy_only` below: a variable claimed to be
    # compose-level must actually appear in the compose file, or this set
    # becomes a place to hide a typo.
    compose_text = (_REPO_COMPOSE := REPO / "docker-compose.production.yml").read_text()
    for name in ("LACTEVA_BACKUP_DIR", "LACTEVA_WAL_DIR"):
        assert name in compose_text, f"{name} is declared compose-only but compose does not use it"

    for name in deploy_only:
        assert any(
            name in path.read_text()
            for path in (REPO / "infra").rglob("*")
            if path.is_file() and path.suffix in {".sh", ".py"}
        ), f"{name} is declared deploy-only but nothing under infra/ reads it"
    unknown = sorted(
        key
        for key in _example_env()
        if key.startswith("LACTEVA_")
        and key not in known
        and key not in compose_only
        and key not in deploy_only
    )
    assert unknown == [], f"example sets LACTEVA_ variables that are not settings: {unknown}"


def test_the_stack_provides_every_service_the_configuration_demands():
    """Configuration and stack must agree.

    `prod` refuses an in-memory event bus, so the compose file has to contain a
    broker for the API to reach. It did not, and no test compared the two.
    """
    compose = _compose()
    services = compose["services"]
    api_env = compose["x-api-base"]["environment"]

    assert api_env.get("LACTEVA_EVENT_BUS") == "rabbitmq", (
        "the API is not configured for a real event transport"
    )
    assert "rabbitmq" in services, (
        "LACTEVA_EVENT_BUS=rabbitmq but the stack defines no broker to connect to"
    )
    assert "rabbitmq" in str(api_env.get("LACTEVA_RABBITMQ_URL", "")), (
        "the API has no RabbitMQ URL pointing at the broker service"
    )
    assert services["rabbitmq"].get("healthcheck"), "the broker has no health check"
    assert services["api"]["depends_on"]["rabbitmq"]["condition"] == "service_healthy", (
        "the API may start before the broker is ready"
    )
    assert "ports" not in services["rabbitmq"], "the broker must not be published to the host"
