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
import os
import pathlib
import re

import pytest
import yaml

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


# --- WO-93: the api can see the operator-placed secrets -------------------------


SECRETS_MOUNT = "/etc/lacteva/secrets:/run/lacteva-secrets:ro"


def test_the_api_mounts_the_host_secrets_directory_read_only():
    """WO-77 told the operator to place the Firebase key on the host; nothing
    mounted the host into the container, so the key could never be seen and
    the switch-on could only make the API refuse to start."""
    services = _compose()["services"]
    for name in ("api", "migrate"):
        volumes = [
            v if isinstance(v, str) else v.get("source", "")
            for v in services[name].get("volumes", [])
        ]
        assert SECRETS_MOUNT in volumes, f"{name} does not mount the secrets directory: {volumes}"
    # A directory, never a single file (a missing bind source becomes a directory).
    assert not SECRETS_MOUNT.split(":")[0].endswith(".json")


def test_the_container_user_has_a_fixed_uid():
    """The operator's `chown root:999` means nothing unless 999 is the API's uid
    on EVERY build; `useradd -r` without `-u` picks the next free number."""
    dockerfile = (REPO / "services/platform-core/Dockerfile").read_text()
    assert "groupadd -r -g 999 app" in dockerfile
    assert "useradd -r -u 999 -g app app" in dockerfile


def test_the_deploy_creates_the_secrets_directory_for_the_api():
    script = (REPO / "infra/deploy/deploy.sh").read_text()
    assert "install -d -m 0750 -o root -g 999 /etc/lacteva/secrets" in script


def test_the_docs_and_the_example_say_how_to_switch_push_on():
    """The three lines and the ownership, exactly — an operator copies them."""
    three = (
        "LACTEVA_NOTIFICATION_PUSH_PROVIDER=fcm",
        "LACTEVA_NOTIFICATION_FCM_PROJECT_ID=lacteva-2987d",
        "LACTEVA_NOTIFICATION_FCM_CREDENTIALS_PATH=/run/lacteva-secrets/fcm-service-account.json",
    )
    example = (REPO / ".env.production.example").read_text()
    docs = (REPO / "DEPLOYMENT.md").read_text()
    for line in three:
        assert line in example, line
        assert line in docs, line
    assert "-o root -g 999" in docs and "0640" in docs
    assert "root:999" in example and "0640" in example
    # The old host path is gone: it named a file the container could not see.
    assert "PATH=/etc/lacteva/fcm-service-account.json" not in example


# --- WO-101: the log pipeline can actually deliver -------------------------------


def test_the_docker_socket_proxy_lets_promtail_discover_targets():
    """promtail's docker discovery lists /networks as well as /containers; a
    proxy that refuses it fails the whole refresh, and a pipeline with zero
    targets reports healthy while shipping nothing (found on production)."""
    env = _compose()["services"]["dockerproxy"]["environment"]
    assert str(env["CONTAINERS"]) == "1"
    assert str(env["NETWORKS"]) == "1", "promtail cannot refresh its targets without /networks"
    # Still read-only: nothing can be created, changed or executed through it.
    for key in ("POST", "EXEC"):
        assert str(env[key]) == "0", key


def test_the_deploy_verification_fails_on_an_empty_log_store():
    script = (REPO / "infra/deploy/verify-log-pipeline.sh").read_text()
    assert "promtail_sent_entries_total" in script
    assert "query_range" in script and "request_id" in script.lower()
    assert 'fail "promtail has shipped NOTHING' in script
    assert 'fail "a request made' in script and "cannot be found in Loki" in script
    # verify-deployment.sh runs it and counts its failure.
    runner = (REPO / "infra/deploy/verify-deployment.sh").read_text()
    assert "verify-log-pipeline.sh" in runner
    assert runner.index("verify-log-pipeline.sh") < runner.index('if [ "${FAILURES}" -eq 0 ]')


# --- WO-102: the log-pipeline check waits for promtail; the rollback is whole

# A `COMPOSE` command that plays api, promtail and Loki. promtail's counter is
# zero until FAKE_SHIPS_AFTER seconds have passed since first use; Loki finds
# the probe only once promtail has shipped, and only if FAKE_QUERYABLE=1.
_FAKE_COMPOSE = """#!/usr/bin/env bash
[ -f "$FAKE_STARTED" ] || date +%s > "$FAKE_STARTED"
age=$(( $(date +%s) - $(cat "$FAKE_STARTED") ))
shipped=0; [ "$age" -ge "$FAKE_SHIPS_AFTER" ] && shipped=1
# $1=exec $2=-T $3=service, the rest is the command
case "$3" in
  api) exit 0 ;;
  promtail)
    if [ "$shipped" = 1 ]; then echo 'promtail_sent_entries_total{host="x"} 142'
    else echo 'promtail_sent_entries_total{host="x"} 0'; fi ;;
  loki)
    if [ "$shipped" = 1 ] && [ "$FAKE_QUERYABLE" = 1 ]; then
      echo "${@: -1}" | sed -n 's/.*%22\\(verify-[^%]*\\)%22.*/{"line":"\\1"}/p'
    else echo '{}'; fi ;;
esac
"""


def _run_log_pipeline(tmp_path, *, ships_after: int, timeout: str, queryable: bool = True):
    import os
    import subprocess

    fake = tmp_path / "compose"
    fake.write_text(_FAKE_COMPOSE)
    fake.chmod(0o755)
    env = {
        **os.environ,
        "COMPOSE": str(fake),
        "FAKE_STARTED": str(tmp_path / "started"),
        "FAKE_SHIPS_AFTER": str(ships_after),
        "FAKE_QUERYABLE": "1" if queryable else "0",
        "LOG_PIPELINE_POLL": "1",
        "LOG_PIPELINE_TIMEOUT": timeout,
    }
    return subprocess.run(
        [str(REPO / "infra/deploy/verify-log-pipeline.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_log_pipeline_check_waits_for_a_promtail_that_starts_at_zero(tmp_path):
    """The b7d75d3 deploy was rolled back because this check fired seconds
    after promtail was recreated, saw promtail_sent_entries_total=0 and
    failed; a minute later the rollback's own run saw 142 lines. A promtail
    that starts at zero and ships after 20 s must PASS, not fail."""
    result = _run_log_pipeline(tmp_path, ships_after=20, timeout="90")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "promtail has shipped 142 lines to Loki" in result.stdout
    assert "queryable in Loki by its request_id" in result.stdout
    # It says how long it waited, and it did wait: not 0 s, not the whole timeout.
    waited = [int(m) for m in re.findall(r"after (\d+)s", result.stdout)]
    assert waited and 18 <= waited[-1] < 60, result.stdout


def test_the_log_pipeline_check_fails_the_same_promtail_without_the_wait(tmp_path):
    """The proof can refuse: the same 20-second promtail with no wait is the
    old behaviour, and it fails — so the wait is what changed."""
    result = _run_log_pipeline(tmp_path, ships_after=20, timeout="0")
    assert result.returncode == 1
    assert "promtail has shipped NOTHING to Loki after waiting 0s" in result.stderr


def test_the_log_pipeline_check_still_fails_when_nothing_ever_ships(tmp_path):
    """A wait is not a pass: a promtail that never ships fails after the
    timeout, and the message names the wait so the reader knows it was
    given every chance."""
    result = _run_log_pipeline(tmp_path, ships_after=10_000, timeout="3")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "promtail has shipped NOTHING to Loki after waiting" in result.stderr
    assert re.search(r"after waiting [3-9]s", result.stderr), result.stderr


def test_the_log_pipeline_check_fails_when_loki_cannot_find_the_request(tmp_path):
    """Shipped is not delivered: a counter that moves while the query finds
    nothing is still a failure."""
    result = _run_log_pipeline(tmp_path, ships_after=0, timeout="3", queryable=False)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "promtail has shipped 142 lines" in result.stdout
    assert "cannot be found in Loki by its request_id" in result.stderr


def test_rollback_restores_every_app_service_and_repoints_current():
    """A rollback that restores api and nginx only leaves portal and
    marketing on the failed release, and `current` naming it (found after
    the b7d75d3 rollback: api on 9e68ce0, the rest on b7d75d3)."""
    script = (INFRA / "deploy" / "deploy.sh").read_text()
    body = script[script.index("rollback_to() {") : script.index("# --- arguments")]
    assert "compose up -d --no-deps api portal marketing nginx" in body
    assert 'ln -sfn "${RELEASES}/${tag}" "${CURRENT}"' in body
    assert "verify-release.sh" in body, "the rollback must prove every container's tag"
    assert "ROLLBACK LEFT A CONTAINER ON THE WRONG RELEASE" in body
    # Every app service the compose file tags with the release is covered.
    services = _compose()["services"]
    tagged = {n for n, svc in services.items() if "LACTEVA_IMAGE_TAG" in str(svc.get("image", ""))}
    assert tagged == {"api", "portal", "marketing", "migrate"}, tagged
    checker = (INFRA / "deploy" / "verify-release.sh").read_text()
    for name in tagged - {"migrate"}:
        assert re.search(rf"for svc in [^;]*\b{name}\b", checker), name
    # And `migrate` stays out — a code rollback never touches the schema.
    assert "migrate" not in body.split("compose up -d")[1].split("||")[0]
    # The release check also guards the deploy itself, before verification.
    assert script.index("verify-release.sh") < script.index("./infra/deploy/verify-deployment.sh")


# `docker compose … ps -q <svc>` and `docker inspect <id>` over a stack whose
# containers run the images listed in FAKE_RUNNING as "svc=image" lines.
_FAKE_DOCKER_PS = """#!/usr/bin/env bash
if [ "$1" = inspect ]; then id="${@: -1}"; sed -n "s/^${id#id-}=//p" "$FAKE_RUNNING"; exit 0; fi
while [ "$1" != ps ]; do shift; done
grep -q "^$3=" "$FAKE_RUNNING" && echo "id-$3"
exit 0
"""


def _run_verify_release(tmp_path, running: dict[str, str], tag: str):
    import os
    import subprocess

    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "docker").write_text(_FAKE_DOCKER_PS)
    (bindir / "docker").chmod(0o755)
    listing = tmp_path / "running"
    listing.write_text("".join(f"{svc}={image}\n" for svc, image in running.items()))
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "COMPOSE": "docker compose",
        "FAKE_RUNNING": str(listing),
    }
    return subprocess.run(
        [str(REPO / "infra/deploy/verify-release.sh"), tag],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_verify_release_passes_when_every_app_container_is_on_the_tag(tmp_path):
    running = {
        "api": "lacteva/platform-core:main-abc1234",
        "portal": "lacteva/admin-portal:main-abc1234",
        "marketing": "lacteva/admin-portal:marketing-main-abc1234",
    }
    result = _run_verify_release(tmp_path, running, "main-abc1234")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("is on") == 3


def test_verify_release_fails_loudly_on_a_half_rollback(tmp_path):
    """Exactly production after the b7d75d3 rollback: api restored, the
    other two still on the failed release."""
    running = {
        "api": "lacteva/platform-core:main-9e68ce0",
        "portal": "lacteva/admin-portal:main-b7d75d3",
        "marketing": "lacteva/admin-portal:marketing-main-b7d75d3",
    }
    result = _run_verify_release(tmp_path, running, "main-9e68ce0")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "portal is on lacteva/admin-portal:main-b7d75d3, not :main-9e68ce0" in result.stderr
    assert (
        "marketing is on lacteva/admin-portal:marketing-main-b7d75d3, not :marketing-main-9e68ce0"
        in result.stderr
    )
    assert "api is on lacteva/platform-core:main-9e68ce0" in result.stdout


def test_verify_release_fails_when_an_app_container_is_missing(tmp_path):
    running = {
        "api": "lacteva/platform-core:main-abc1234",
        "portal": "lacteva/admin-portal:main-abc1234",
    }
    result = _run_verify_release(tmp_path, running, "main-abc1234")
    assert result.returncode == 1
    assert "marketing: no running container" in result.stderr


# A whole fake docker for the rollback path: `compose up` moves the named app
# services to the tag in the env file, `ps -q`/`inspect` report what each is
# on, and everything else is a no-op that succeeds.
_FAKE_DOCKER_STACK = """#!/usr/bin/env bash
tag="$(sed -n s/^LACTEVA_IMAGE_TAG=//p "$FAKE_ENV")"
if [ "$1" = inspect ]; then
  id="${@: -1}"; svc="${id#id-}"; img="$(sed -n "s/^$svc=//p" "$FAKE_SVCS")"
  [ "$svc" = marketing ] && echo "lacteva/portal:marketing-$img" || echo "lacteva/x:$img"
  exit 0
fi
shift
while [ $# -gt 0 ]; do
  case "$1" in up|ps|restart|run|exec|pull|config|images) break ;; *) shift ;; esac
done
cmd="${1:-}"; shift || true
case "$cmd" in
  up) for s in "$@"; do
        case "$s" in api|portal|marketing) sed -i "s/^$s=.*/$s=$tag/" "$FAKE_SVCS" ;; esac
      done ;;
  ps) echo "id-${@: -1}" ;;
  images) echo "$tag" ;;
esac
exit 0
"""

# Everything in deploy.sh above the argument parser (settings and functions),
# then the failed-verification branch exactly as step 5 takes it.
_ROLLBACK_HARNESS = """#!/usr/bin/env bash
eval "$(sed -n '1,/^# --- arguments/p' "$DEPLOY_SCRIPT" | grep -v "^set -")"
if "$CURRENT_LINK/infra/deploy/verify-deployment.sh"; then
  echo "expected the new release to fail"; exit 9
fi
rollback_to "$PREVIOUS_TAG"
"""


# A fake docker for staging: `pull` of a release image fails unless
# FAKE_RELEASE_TREE is set, in which case `create` succeeds and `cp` copies
# that tree into the destination; `ps -q`/`inspect` describe one running
# container whose bind mount is FAKE_MOUNT_SOURCE.
_FAKE_DOCKER_STAGING = """#!/usr/bin/env bash
case "$1" in
  pull)   [ -n "${FAKE_RELEASE_TREE:-}" ] || exit 1 ;;
  create) exit 0 ;;
  cp)     dest="${@: -1}"; cp -a "$FAKE_RELEASE_TREE/." "${dest%/}/" ;;
  rm)     exit 0 ;;
  ps)     [ -n "${FAKE_MOUNT_SOURCE:-}" ] && echo id-nginx ;;
  inspect) echo "$FAKE_MOUNT_SOURCE" ;;
esac
exit 0
"""

_STAGING_HARNESS = """#!/usr/bin/env bash
eval "$(sed -n '1,/^# --- arguments/p' "$DEPLOY_SCRIPT" | grep -v "^set -")"
IMAGE=lacteva/platform-core; PREVIOUS=main-0000000
stage_release "$TAG"
"""


def _staging_world(tmp_path, *, live_tag: str, fake_env: dict[str, str]):
    """A releases/ dir holding `live_tag` with the files production mounts,
    `current` pointing at it, and the fake docker on PATH."""
    import os

    releases, current = tmp_path / "releases", tmp_path / "current"
    live = releases / live_tag
    (live / "infra" / "nginx" / "conf.d").mkdir(parents=True)
    (live / "infra" / "nginx" / "nginx.conf").write_text("# the running nginx config\n")
    (live / "infra" / "nginx" / "conf.d" / "api.conf").write_text("server {}\n")
    (live / "docker-compose.production.yml").write_text("services: {}\n")
    (live / ".deployed-tag").write_text("main-0000000\n")
    current.symlink_to(live)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "docker").write_text(_FAKE_DOCKER_STAGING)
    (bindir / "docker").chmod(0o755)
    harness = tmp_path / "harness.sh"
    harness.write_text(_STAGING_HARNESS)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "RELEASES_DIR": str(releases),
        "CURRENT_LINK": str(current),
        "ENV_FILE": str(tmp_path / ".env.production"),
        "DEPLOY_LOG": str(tmp_path / "deploy.log"),
        "DEPLOY_SCRIPT": str(REPO / "infra/deploy/deploy.sh"),
        **fake_env,
    }
    (tmp_path / ".env.production").write_text("LACTEVA_IMAGE_TAG=main-1111111\n")
    return releases, current, harness, env


def _run_staging(harness, env, tag):
    import subprocess

    return subprocess.run(
        ["bash", str(harness)],
        env={**env, "TAG": tag},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_a_failed_restage_of_the_live_release_leaves_it_intact(tmp_path):
    """The incident: `current` named main-b7d75d3 (the half-rollback never
    moved it back), a deploy of that same tag began with `rm -rf` of its
    directory, and the attempt died before refilling it — while nginx,
    promtail, Loki, Grafana, Prometheus and postgres were all bind-mounted
    out of it. A pull that fails must leave every file where it was."""
    releases, current, harness, env = _staging_world(tmp_path, live_tag="main-1111111", fake_env={})
    result = _run_staging(harness, env, "main-1111111")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Refusing to deploy from the host tree" in result.stderr
    live = releases / "main-1111111"
    assert (live / "infra/nginx/nginx.conf").read_text() == "# the running nginx config\n"
    assert (live / "infra/nginx/conf.d/api.conf").exists()
    assert (live / "docker-compose.production.yml").exists()
    assert os.readlink(current) == str(live)
    assert not list(releases.glob(".staging-*")), "no staging leftovers"


def test_restaging_the_live_release_retires_it_by_rename_and_swaps_in_a_complete_tree(tmp_path):
    """When the re-deploy succeeds, the live tree is renamed aside (running
    containers keep their mounted inodes) and the new tree appears whole at
    the same path; nothing is deleted while a container mounts it."""
    import os

    tree = tmp_path / "tree"
    for rel in ("infra/nginx/conf.d", "infra/deploy"):
        (tree / rel).mkdir(parents=True)
    (tree / "infra/nginx/nginx.conf").write_text("# the NEW nginx config\n")
    (tree / "docker-compose.production.yml").write_text("services: {api: {}}\n")
    (tree / "infra/deploy/verify-deployment.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    releases, current, harness, env = _staging_world(
        tmp_path,
        live_tag="main-1111111",
        fake_env={
            "FAKE_RELEASE_TREE": str(tree),
            "FAKE_MOUNT_SOURCE": str(tmp_path / "releases/main-1111111/infra/nginx/nginx.conf"),
        },
    )
    result = _run_staging(harness, env, "main-1111111")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "is LIVE" in result.stdout and "retiring it to" in result.stdout
    live = releases / "main-1111111"
    assert (live / "infra/nginx/nginx.conf").read_text() == "# the NEW nginx config\n"
    assert (live / ".deployed-tag").read_text().strip() == "main-0000000"
    retired = list(releases.glob(".retired-main-1111111-*"))
    assert len(retired) == 1, retired
    assert (retired[0] / "infra/nginx/nginx.conf").read_text() == "# the running nginx config\n"
    assert os.readlink(current) == str(live)  # the caller re-points it; the path is unchanged
    assert not list(releases.glob(".staging-*"))


def test_restaging_an_unreferenced_release_replaces_it_outright(tmp_path):
    """A tag that neither `current` nor any container references is just a
    directory: no retirement, no clutter."""
    tree = tmp_path / "tree"
    (tree / "infra/nginx/conf.d").mkdir(parents=True)
    (tree / "infra/deploy").mkdir(parents=True)
    (tree / "infra/nginx/nginx.conf").write_text("new\n")
    (tree / "docker-compose.production.yml").write_text("services: {}\n")
    (tree / "infra/deploy/verify-deployment.sh").write_text("exit 0\n")
    releases, _current, harness, env = _staging_world(
        tmp_path, live_tag="main-1111111", fake_env={"FAKE_RELEASE_TREE": str(tree)}
    )
    (releases / "main-2222222").mkdir()
    (releases / "main-2222222" / "stale").write_text("x")
    result = _run_staging(harness, env, "main-2222222")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (releases / "main-2222222" / "stale").exists()
    assert (releases / "main-2222222" / "infra/nginx/nginx.conf").read_text() == "new\n"
    assert not list(releases.glob(".retired-*"))


def test_no_path_in_the_deploy_removes_a_release_tree_without_the_live_check():
    """The rule, pinned: every `rm -rf` in deploy.sh is of a staging
    directory this run owns, or is guarded by release_is_live()."""
    script = (INFRA / "deploy" / "deploy.sh").read_text()
    code = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
    assert 'rm -rf "${RELEASE}"' not in "\n".join(code)
    for line in code:
        if "rm -rf" not in line:
            continue
        if ".staging-" in line or 'rm -rf "${stage}"' in line:
            continue
        assert 'rm -rf "${release}"' in line or 'rm -rf "${d}"' in line, line
    guarded = script[script.index("stage_release() {") : script.index("# --- arguments")]
    for target in ('rm -rf "${release}"', 'rm -rf "${d}"'):
        assert guarded.index("release_is_live") < guarded.index(target)
    # The live check looks at BOTH what `current` names and what containers mount.
    check = script[script.index("release_is_live() {") : script.index("stage_release() {")]
    assert '"${CURRENT}"' in check and ".Mounts" in check


def test_a_failed_verification_leaves_nothing_on_the_failed_release(tmp_path):
    """deploy.sh's rollback against a fake docker, with the new release's
    verification made to fail: afterwards no container runs the failed tag,
    `current` points at the previous release, and the env file names it."""
    import os
    import subprocess

    releases, current = tmp_path / "releases", tmp_path / "current"
    prev, new = "main-0000000", "main-1111111"
    env_file = tmp_path / ".env.production"
    env_file.write_text(f"LACTEVA_IMAGE_TAG={prev}\n")
    svcs = tmp_path / "svcs"
    svcs.write_text(f"api={prev}\nportal={prev}\nmarketing={prev}\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "docker").write_text(_FAKE_DOCKER_STACK)
    (bindir / "docker").chmod(0o755)
    for tag in (prev, new):
        d = releases / tag / "infra" / "deploy"
        d.mkdir(parents=True)
        for name in ("verify-release.sh", "verify-log-pipeline.sh"):
            (d / name).write_bytes((REPO / "infra/deploy" / name).read_bytes())
            (d / name).chmod(0o755)
        outcome = "echo 'deliberate failure' >&2; exit 1" if tag == new else "exit 0"
        (d / "verify-deployment.sh").write_text(f"#!/usr/bin/env bash\n{outcome}\n")
        (d / "verify-deployment.sh").chmod(0o755)
        (releases / tag / "docker-compose.production.yml").write_text("services: {}\n")
    current.symlink_to(releases / new)  # step 3 has staged and re-pointed
    harness = tmp_path / "harness.sh"
    harness.write_text(_ROLLBACK_HARNESS)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "RELEASES_DIR": str(releases),
        "CURRENT_LINK": str(current),
        "ENV_FILE": str(env_file),
        "DEPLOY_LOG": str(tmp_path / "deploy.log"),
        "DEPLOY_SCRIPT": str(REPO / "infra/deploy/deploy.sh"),
        "PREVIOUS_TAG": prev,
        "FAKE_ENV": str(env_file),
        "FAKE_SVCS": str(svcs),
    }
    result = subprocess.run(
        ["bash", str(harness)], env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # No container on the failed release, and no symlink on it either.
    running = dict(line.split("=") for line in svcs.read_text().split())
    assert running == {"api": prev, "portal": prev, "marketing": prev}, running
    assert os.readlink(current) == str(releases / prev)
    assert f"LACTEVA_IMAGE_TAG={prev}" in env_file.read_text()
    assert f"rollback verified: running {prev}" in result.stdout
    assert f"marketing is on lacteva/portal:marketing-{prev}" in result.stdout


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
    conf = _vhost_conf()
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
_API_HEADERS_INCLUDE = "include /etc/nginx/conf.d/security-headers-api.inc;"


def _vhost_conf() -> str:
    """Every line nginx loads for the public vhosts, as one string.

    WO-63 split the locations out of `lacteva.conf` into includes, because the
    same locations now serve more than one hostname and two copies of a proxy
    configuration are two things that drift apart. Reading only `lacteva.conf`
    after that split would have left four of the checks below iterating over
    an EMPTY list of locations and passing vacuously — a green test asserting
    nothing, which is worse than the defect it was written for.
    """
    conf_dir = REPO / "infra/nginx/conf.d"
    return "\n".join(
        path.read_text()
        for path in sorted(conf_dir.iterdir())
        # The header snippets are what the locations INCLUDE; folding them in
        # would let a location satisfy the "re-states the headers" check by
        # standing next to the file that defines them.
        if path.suffix in (".conf", ".inc") and not path.name.startswith("security-headers")
    )


def _location_blocks(conf: str) -> list[tuple[str, str]]:
    """Every `location …{ }` block in the file, as (header line, body).

    Anchored to the start of a line, because the word "location" also appears
    in the prose of this config's comments — and matching one of those
    swallowed the real block that followed it, which quietly excused three
    API locations from a check they were failing.
    """
    blocks = []
    for match in re.finditer(r"^[ \t]*location\s", conf, re.MULTILINE):
        start = match.start()
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
    return blocks


def test_every_location_that_adds_a_header_restates_the_security_headers():
    conf = _vhost_conf()
    # The API variant includes the shared snippet, so either satisfies this.
    offenders = [
        name
        for name, body in _location_blocks(conf)
        if "add_header" in body
        and _HEADERS_INCLUDE not in body
        and _API_HEADERS_INCLUDE not in body
    ]
    assert not offenders, (
        "these locations set a header of their own, which discards every "
        f"inherited security header, and do not re-state them: {offenders}"
    )


def test_the_server_level_still_sets_them_for_everything_else():
    conf = _vhost_conf()
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
    conf = _vhost_conf()
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
    conf = _vhost_conf()
    names = [name for name, _ in _location_blocks(conf)]
    assert "location /v1/auth/" in names and "location /v1/" in names
    assert len("/v1/auth/") > len("/v1/")


def test_the_snippet_is_not_loaded_twice_as_a_server_block():
    # `nginx.conf` includes `conf.d/*.conf`. A snippet named `.conf` would be
    # parsed as a second top-level context and nginx would refuse to start.
    base = (REPO / "infra/nginx/nginx.conf").read_text()
    assert "conf.d/*.conf" in base
    assert (REPO / "infra/nginx/conf.d/security-headers.inc").exists()


# --- one owner for the transport headers (WO-46) ---------------------------
#
# The live platform served `Referrer-Policy` and `Permissions-Policy` TWICE on
# every API response, with different values, because the application and the
# edge both set them — while the portal served neither, because `location /`
# discards inherited headers. These assert the ruling: the edge owns them, it
# is the only owner, and every surface gets the same set.

_EDGE_OWNED = (
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
)


def test_the_application_no_longer_sets_any_edge_owned_header():
    source = (REPO / "services/platform-core/src/platform_core/core/http_security.py").read_text()
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(("#", "-", "*"))
    )
    code = code.split('"""')[-1]  # past the module docstring, which names them
    for header in (*_EDGE_OWNED, "Content-Security-Policy"):
        assert header not in code, f"the application still sets {header}"


def test_the_edge_defines_each_header_exactly_once():
    inc = (REPO / "infra/nginx/conf.d/security-headers.inc").read_text()
    for header in _EDGE_OWNED:
        assert inc.count(f"add_header {header} ") == 1, f"{header} is not defined exactly once"


def test_api_and_portal_receive_the_same_set():
    # Portal responses inherit the snippet; API responses include the API
    # variant, which includes the same snippet and adds only CSP. So the five
    # are identical on both surfaces by construction — this asserts the
    # construction, since nothing else can.
    api = (REPO / "infra/nginx/conf.d/security-headers-api.inc").read_text()
    assert "include /etc/nginx/conf.d/security-headers.inc;" in api, (
        "the API set does not derive from the shared one, so the two can drift"
    )
    for header in _EDGE_OWNED:
        assert f"add_header {header} " not in api, (
            f"{header} is restated in the API set — that is a second definition, "
            "and a second definition is how the values diverged before"
        )
    assert api.count("add_header Content-Security-Policy") == 1


def test_every_api_location_carries_the_api_header_set():
    conf = _vhost_conf()
    api_include = "include /etc/nginx/conf.d/security-headers-api.inc;"
    missing = [
        name
        for name, body in _location_blocks(conf)
        if ("proxy_pass http://lacteva_api" in body) and api_include not in body
    ]
    assert not missing, f"these API locations get no Content-Security-Policy: {missing}"


def _directives(text: str) -> str:
    """The config without its prose — comments name what they rule out."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_the_api_policy_is_the_one_an_api_can_have():
    api = _directives((REPO / "infra/nginx/conf.d/security-headers-api.inc").read_text())
    assert "default-src 'none'" in api
    assert "frame-ancestors 'none'" in api
    # The Swagger relaxation must not come back at the edge: `/openapi.json`
    # is served in production and is data, not a page.
    assert "unsafe-inline" not in api


# --- releases come from the registry (WO-44) -------------------------------
#
# The reproducibility gap these pin shut: `deploy.sh` built a release by
# rsyncing the host's own current tree, so a pushed commit's configuration
# reached production only if a person copied it there. These assert the three
# halves of the fix — the artifact is built, it is published at the tag, and
# the deploy prefers it.


def _release_dockerfile() -> str:
    return (REPO / "infra/deploy/Dockerfile.release").read_text()


def test_the_release_tree_is_built_as_an_artifact():
    df = _release_dockerfile()
    assert "COPY docker-compose.production.yml" in df
    assert "COPY infra" in df


def test_the_release_artifact_cannot_carry_terraform_state():
    # A state file holds real values, and this image is readable by anyone who
    # can pull from the registry.
    ignore = (REPO / ".dockerignore").read_text()
    assert "infra/terraform" in ignore, "terraform state would be baked into a pullable image"
    for secret in ("**/*.pem", "**/*.key"):
        assert secret in ignore


def test_the_release_image_is_published_at_the_same_tag_as_the_code():
    workflow = yaml.safe_load((REPO / ".github/workflows/images.yml").read_text())
    entries = workflow["jobs"]["build"]["strategy"]["matrix"]["include"]
    release = [e for e in entries if e["name"] == "release"]
    assert release, "no release artifact is built — a commit's config is not deployable"
    assert release[0]["dockerfile"] == "infra/deploy/Dockerfile.release"
    assert release[0]["tag_prefix"] == "release-"
    # Every entry must set a prefix, or the build step's expression silently
    # publishes one image over another's tag.
    assert all("tag_prefix" in e and "dockerfile" in e for e in entries)


def test_a_config_only_commit_still_publishes_a_deployable_tag():
    # Before WO-44 the Images workflow ignored infra/, so a commit that fixed
    # only nginx produced no tag to deploy at all.
    raw = (REPO / ".github/workflows/images.yml").read_text()
    workflow = yaml.safe_load(raw)
    paths = workflow[True]["push"]["paths"] if True in workflow else workflow["on"]["push"]["paths"]
    assert "infra/**" in paths
    assert "docker-compose.production.yml" in paths


def test_the_deploy_prefers_the_registry_over_the_host_tree():
    deploy = (REPO / "infra/deploy/deploy.sh").read_text()
    assert 'release_image="${IMAGE}:release-${tag}"' in deploy
    assert "docker cp" in deploy
    # The fallback stays — a rollback to a pre-WO-44 tag has no release image
    # — but it must ANNOUNCE itself, or this defect returns silently.
    fallback = deploy.split("falling back")[1][:400]
    assert "rsync" in fallback
    assert "log " in deploy.split('release_image="')[0][-2000:] or "log " in deploy


def test_the_host_tree_fallback_must_be_asked_for_by_name():
    """WO-70 deploy incident. A transient pull failure met a stale host tree
    and the fallback shipped an August compose file over a September
    platform: the marketing service vanished and lacteva.com served the
    portal's login page. A missing release image is a reason to STOP; the
    rsync path exists only for a pre-WO-44 rollback and needs ALLOW_HOST_TREE=1
    said out loud."""
    deploy = (REPO / "infra/deploy/deploy.sh").read_text()
    branch = deploy.split('if docker pull "${release_image}"')[1]
    fallback = branch.split("\n  else\n", 1)[1].split("\n  fi\n", 1)[0]
    assert "ALLOW_HOST_TREE" in fallback
    assert fallback.index("die ") < fallback.index("rsync "), "refuse BEFORE the rsync"
    # And a copy of the script that is not a release's own says so.
    assert "BASH_SOURCE[0]" in deploy and "not a release's own copy" in deploy


def test_an_incomplete_release_is_refused_rather_than_deployed():
    deploy = (REPO / "infra/deploy/deploy.sh").read_text()
    required_paths = (
        "docker-compose.production.yml",
        "infra/nginx/nginx.conf",
        "infra/nginx/conf.d",
    )
    for required in required_paths:
        assert required in deploy.split("refusing to deploy an incomplete release")[0][-900:]


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


# --- the terraform inputs are recorded, not remembered (WO-48) -------------


def test_the_region_is_stated_rather_than_inherited():
    """`region` defaulted to eu-west-1 while the platform runs in ap-south-1.

    A plan in this directory therefore looked in Ireland, found nothing, and
    reported that the instance, the elastic IP, the security group and the data
    volume had all "been deleted". Applying that writes an empty state and then
    builds a second deployment in the wrong continent, with production still
    running and no longer managed by anything.
    """
    variables = _tf("aws", "variables.tf")
    # Comments explain the absence of a default and say the word; assert on the
    # directives, as the nginx checks learned to.
    block = _directives(variables.split('variable "region"')[1].split("\n}")[0])
    assert "default" not in block, (
        "region has a default again — a wrong one points terraform at an empty "
        "region and reports production as deleted"
    )


def test_every_required_input_is_documented_with_an_example():
    """The deployment was applied with values recorded nowhere.

    Reconstructing them meant reading attributes out of the state file, and one
    wrong guess produced a plan that would have replaced the running instance.
    """
    variables = _tf("aws", "variables.tf")
    required = [
        name
        for name in re.findall(r'variable "([a-z_]+)"', variables)
        if "default" not in _directives(variables.split(f'variable "{name}"')[1].split("\n}")[0])
    ]
    example = _tf("aws", "terraform.tfvars.example")
    missing = [name for name in required if f"{name} " not in example and f"{name}=" not in example]
    assert not missing, f"terraform.tfvars.example does not show how to set: {missing}"


def test_the_real_tfvars_can_never_be_committed():
    # It holds the operators' own addresses.
    ignore = (REPO / ".gitignore").read_text()
    assert "*.tfvars" in ignore
    assert "!*.tfvars.example" in ignore


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
    # WO-63: read by the MARKETING SITE, which is a different application in
    # the same stack — so they are not `Settings` fields and never will be.
    # Same discipline as the two sets above: each must be read by that app's
    # own source, asserted below, or this becomes a place to hide a typo.
    site_only = {
        "LACTEVA_SITE_URL",  # canonical origin for metadata, sitemap, robots
        "LACTEVA_LEADS_WEBHOOK_URL",  # where the demo-request form posts
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

    site = REPO / "apps/marketing-site/src"
    for name in site_only:
        assert (
            any(
                name in path.read_text()
                for path in site.rglob("*")
                if path.is_file() and path.suffix in {".ts", ".tsx"}
            )
            or name in (REPO / "apps/marketing-site/next.config.ts").read_text()
        ), f"{name} is declared site-only but the marketing site never reads it"
        assert name in compose_text, f"{name} is not passed to the site by compose"
    unknown = sorted(
        key
        for key in _example_env()
        if key.startswith("LACTEVA_")
        and key not in known
        and key not in compose_only
        and key not in deploy_only
        and key not in site_only
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
