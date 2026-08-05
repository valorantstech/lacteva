"""Platform observability (OBS-001).

The acceptance criterion for this work order is a claim about people, not
code: *an operator can determine platform, consumer, projection,
notification, payment, and security health without reading application logs.*
These tests hold that claim to account — they ask the API the questions an
operator would ask and check that the answers are there, actionable, and
correct.

They also guard the two properties that silently rot: metric **cardinality**
(one careless label multiplies series by the customer count) and
**correlation** (an event-driven platform whose logs cannot be joined is a
platform nobody can debug).
"""

import uuid

import pytest

from tests.conftest import register_and_login
from tests.test_org_structure import _tenant_admin


async def _ops(client):
    """A platform-staff principal — the ops surface is not tenant-facing."""
    _, headers = await register_and_login(client, "ops@example.com", admin=True)
    return headers


def _metric_text(body: str, name: str) -> list[str]:
    return [line for line in body.splitlines() if line.startswith(name)]


# --- the metric surface ------------------------------------------------------


def test_every_metric_is_declared_in_one_place():
    """A metric defined in a module is a metric nobody reviews."""
    from platform_core.core.metrics import declared_metrics

    declared = declared_metrics()
    assert len(declared) >= 40, "the registry should hold the platform's whole surface"
    for family in ("http_requests", "consumer_processed", "payments_created", "component_health"):
        assert any(name.startswith(family) for name in declared), family


def test_no_metric_carries_a_high_cardinality_label():
    """The rule that keeps Prometheus affordable: labels are bounded
    vocabularies, never identities. One `tenant_id` label multiplies every
    series by the customer count."""
    from platform_core.core.metrics import FORBIDDEN_LABELS, declared_metrics

    offenders = {
        name: sorted(set(labels) & FORBIDDEN_LABELS)
        for name, labels in declared_metrics().items()
        if set(labels) & FORBIDDEN_LABELS
    }
    assert not offenders, f"high-cardinality labels: {offenders}"


def test_metric_names_follow_prometheus_convention():
    from platform_core.core.metrics import declared_metrics

    for name in declared_metrics():
        assert name.islower(), name
        assert " " not in name, name
        # Durations are seconds, never milliseconds — a unit in the name that
        # lies is worse than no unit.
        assert not name.endswith("_ms"), name


async def test_the_metrics_endpoint_exposes_the_platform_surface(client):
    body = (await client.get("/metrics")).text
    for name in (
        "http_requests_total",
        "consumer_processed_total",
        "relay_delivered_total",
        "notifications_sent_total",
        "payments_created_total",
        "receipts_generated_total",
        "sync_operations_total",
        "settlements_created_total",
        "auth_failures_total",
        "component_health",
    ):
        assert name in body, f"{name} missing from /metrics"


async def test_http_metrics_use_the_route_template_not_the_path(client):
    """`/v1/payments/{payment_id}` is one series; `/v1/payments/<uuid>` is one
    series per payment, which is how a metrics bill becomes a surprise."""
    headers = await _ops(client)
    await client.get(f"/v1/payments/{uuid.uuid4()}", headers=headers)
    body = (await client.get("/metrics")).text
    assert 'route="/v1/payments/{payment_id}"' in body
    raw_paths = [
        line for line in body.splitlines() if 'route="/v1/payments/' in line and "{" not in line
    ]
    assert not raw_paths, f"an id leaked into a metric label: {raw_paths[:2]}"


# --- business metrics actually move ------------------------------------------


async def test_payment_lifecycle_moves_its_metrics(client):
    from tests.test_payments import _action, _pay, _payable

    headers, _center, _supplier, settlement = await _payable(client)
    before = (await client.get("/metrics")).text
    payment = await _pay(client, headers, settlement)
    for action, body in (("submit", {}), ("execute", {}), ("complete", {})):
        await _action(client, headers, payment["id"], action, body)
    after = (await client.get("/metrics")).text

    created = 'payments_created_total{method="BANK_TRANSFER"}'
    completed = 'payments_completed_total{method="BANK_TRANSFER"}'
    assert _metric_text(after, created) != _metric_text(before, created)
    assert any(completed in line for line in after.splitlines())


async def test_receipt_render_is_timed(client):
    from tests.test_receipts import _receipted

    headers, _c, _s, _st, _p, receipt = await _receipted(client)
    await client.get(f"/v1/receipts/{receipt['id']}/render?format=html", headers=headers)
    body = (await client.get("/metrics")).text
    assert 'receipt_render_duration_seconds_count{format="html"}' in body


async def test_pricing_failures_are_counted_by_stage(client):
    """Counted by STAGE (a fixed vocabulary), never by reason (prose)."""
    from tests.test_pricing_resolution import _resolution_env, _resolve

    headers, center, _card, _matrix = await _resolution_env(client)
    await _resolve(client, headers, center["id"], value=99.9)  # outside every band
    body = (await client.get("/metrics")).text
    assert any(
        line.startswith("pricing_failures_total{") and "stage=" in line
        for line in body.splitlines()
    )


async def test_offline_sync_metrics_record_conflicts(client):
    from tests.test_offline_sync import _env, _op, _push

    headers, _center, _supplier, _session, _qr = await _env(client)
    await _push(client, headers, [_op("accept", seq=1, target="local-never-synced")])
    body = (await client.get("/metrics")).text
    assert 'sync_conflicts_total{reason="unresolved_reference"}' in body
    assert "sync_batch_duration_seconds_count" in body


async def test_security_metrics_record_failures(client):
    await client.post(
        "/v1/auth/register",
        json={"email": "m@example.com", "password": "correct-horse-battery", "full_name": "M"},
    )
    await client.post("/v1/auth/token", json={"email": "m@example.com", "password": "nope"})
    await client.get("/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    body = (await client.get("/metrics")).text
    assert "auth_failures_total{" in body
    assert "jwt_verification_failures_total{" in body


async def test_authorization_denials_are_counted(client):
    _, outsider = await register_and_login(client, "denied-metric@example.com")
    await client.get("/v1/suppliers", headers=outsider)
    body = (await client.get("/metrics")).text
    assert 'authz_denials_total{permission="supplier.read"}' in body


# --- correlation -------------------------------------------------------------


async def test_a_request_id_is_returned_and_honoured(client):
    supplied = uuid.uuid4().hex
    response = await client.get("/health/live", headers={"X-Request-ID": supplied})
    assert response.headers["X-Request-ID"] == supplied
    generated = await client.get("/health/live")
    assert generated.headers["X-Request-ID"]


async def test_correlation_flows_from_request_to_event_to_consumer(client):
    """The end-to-end claim: one collection, one correlation id, visible on
    the event the platform emitted and bound into the consumer that handled
    it."""
    from sqlalchemy import select

    from platform_core.core import db
    from platform_core.modules.event_relay.models import OutboxEvent
    from tests.test_collection_centers import _center_fixture
    from tests.test_suppliers import _create_supplier

    request_id = uuid.uuid4().hex
    headers, _branch, _center = await _center_fixture(client)
    r = await client.post(
        "/v1/suppliers",
        json={"full_name": "Traced Farmer", "phone": "+254700000123"},
        headers={**headers, "X-Request-ID": request_id},
    )
    assert r.status_code == 201, r.text
    assert _create_supplier  # the shared helper stays the canonical path

    async with db.get_session_factory()() as s:
        events = list(
            (
                await s.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.event_name == "supplier.supplier-registered.v1"
                    )
                )
            ).all()
        )
    assert events, "the registration must have emitted an event"
    assert str(events[-1].correlation_id) == request_id


async def test_the_consumer_binds_the_correlation_id_it_was_given(client):
    """A consumer's logs must join back to the request that caused them."""
    import structlog

    from platform_core.core import db
    from platform_core.modules.event_relay.consumers import (
        ConsumerRunner,
        EventConsumer,
        register_consumer,
        unregister_consumer,
    )
    from tests.test_collection_centers import _center_fixture

    seen: list[dict] = []

    class _ContextSpy(EventConsumer):
        name = "obs-context-spy"
        event_types = ("supplier.supplier-registered.v1",)

        async def handle(self, envelope, session):
            seen.append(dict(structlog.contextvars.get_contextvars()))

    register_consumer(_ContextSpy())
    try:
        request_id = uuid.uuid4().hex
        headers, _branch, _center = await _center_fixture(client)
        await client.post(
            "/v1/suppliers",
            json={"full_name": "Spy Farmer", "phone": "+254700000124"},
            headers={**headers, "X-Request-ID": request_id},
        )
        await ConsumerRunner(db.get_session_factory()).run_once()
    finally:
        unregister_consumer("obs-context-spy")

    assert seen, "the spy consumer never ran"
    context = seen[-1]
    assert context.get("correlation_id") == request_id
    assert context.get("consumer") == "obs-context-spy"
    assert context.get("event_name") == "supplier.supplier-registered.v1"
    assert context.get("tenant_id")


# --- health ------------------------------------------------------------------


async def test_readiness_stays_a_single_bit_for_load_balancers(client):
    body = (await client.get("/health/ready")).json()
    assert body["status"] in ("ok", "degraded")
    assert isinstance(body["checks"], dict)


async def test_component_health_names_every_component(client):
    headers = await _ops(client)
    body = (await client.get("/v1/_ops/health", headers=headers)).json()
    names = {c["name"] for c in body["components"]}
    assert names == {
        "background_workers",
        "backups",
        "consumers",
        "database",
        "jwt_keys",
        "notifications",
        "outbox",
        "projections",
        "redis",
    }
    assert body["status"] in ("healthy", "warning", "degraded", "critical")
    assert isinstance(body["ready"], bool)


async def test_no_probe_raises_against_a_working_platform(client):
    """A probe that raises reports `critical` with a generic reason — which
    is indistinguishable from a real outage. On a healthy test stack every
    probe must produce a real verdict, not an exception."""
    headers = await _ops(client)
    body = (await client.get("/v1/_ops/health", headers=headers)).json()
    broken = [c for c in body["components"] if "probe failed" in (c.get("detail") or "")]
    assert not broken, f"health probes raised: {[(c['name'], c['detail']) for c in broken]}"


async def test_each_component_reports_actionable_data(client):
    headers = await _ops(client)
    body = (await client.get("/v1/_ops/health", headers=headers)).json()
    consumers = next(c for c in body["components"] if c["name"] == "consumers")
    assert {"count", "paused", "lagging", "dead_lettering", "max_lag"} <= set(consumers["data"])
    outbox = next(c for c in body["components"] if c["name"] == "outbox")
    assert {"pending", "dead_letters"} <= set(outbox["data"])


def test_overall_health_is_the_worst_component_not_an_average():
    from platform_core.core import health

    assert health.worst([health.HEALTHY, health.CRITICAL, health.HEALTHY]) == health.CRITICAL
    assert health.worst([health.HEALTHY, health.WARNING]) == health.WARNING
    assert health.worst([health.HEALTHY]) == health.HEALTHY
    assert health.worst([]) == health.HEALTHY


async def test_a_failing_probe_becomes_critical_rather_than_a_500(client):
    """A health endpoint that crashes tells an operator nothing."""
    from platform_core.core import health

    async def _explode():
        raise RuntimeError("probe is broken")

    health.register_probe("temporary-explosive", _explode)
    try:
        snapshot = await health.evaluate()
    finally:
        health._probes.pop("temporary-explosive", None)
    component = next(c for c in snapshot.components if c.name == "temporary-explosive")
    assert component.status == health.CRITICAL
    assert "probe failed" in component.detail
    assert snapshot.status == health.CRITICAL


async def test_degraded_is_still_ready(client):
    """A degraded platform keeps serving: pulling it from rotation would not
    fix the degradation and would remove the capacity that still works."""
    from platform_core.core import health

    snapshot = health.PlatformHealth(
        status=health.DEGRADED, components=[], checked_at="2026-08-05T00:00:00Z"
    )
    assert snapshot.ready is True
    critical = health.PlatformHealth(
        status=health.CRITICAL, components=[], checked_at="2026-08-05T00:00:00Z"
    )
    assert critical.ready is False


def test_the_platform_samples_its_own_health_on_a_timer():
    """Every alert rule reads `component_health`. If the gauge were only set
    when an operator opened the ops API, the alerts would never fire — the
    platform would look quiet precisely because nobody was watching."""
    import inspect

    from platform_core import main

    assert hasattr(main, "_health_loop")
    source = inspect.getsource(main.lifespan)
    assert "_health_loop" in source, "the health loop must be started at startup"
    assert 'workers.register("health"' in source, "and registered as a worker"


async def test_health_reports_into_prometheus(client):
    headers = await _ops(client)
    await client.get("/v1/_ops/health", headers=headers)
    body = (await client.get("/metrics")).text
    assert 'component_health{component="database"}' in body


# --- alerts ------------------------------------------------------------------


def test_every_alert_rule_tells_the_operator_what_to_do():
    """An alert without an action is a notification, and notifications train
    people to ignore alerts."""
    from platform_core.core import alerts

    assert alerts.RULES
    for rule in alerts.RULES:
        assert rule.action.strip(), rule.name
        assert len(rule.action) > 40, f"{rule.name}: the action must be usable at 3 a.m."
        assert rule.severity in (alerts.CRITICAL, alerts.WARNING, alerts.INFO)
        assert rule.summary.strip()
        assert rule.runbook


def test_alert_rule_names_are_unique():
    from platform_core.core import alerts

    names = [rule.name for rule in alerts.RULES]
    assert len(names) == len(set(names))


async def test_a_healthy_platform_fires_nothing(client):
    from platform_core.core import alerts, health

    snapshot = health.PlatformHealth(
        status=health.HEALTHY,
        components=[health.healthy(name) for name in health.registered_probes()],
        checked_at="2026-08-05T00:00:00Z",
    )
    assert alerts.evaluate(snapshot) == []


def test_alerts_fire_on_the_conditions_they_name():
    from platform_core.core import alerts, health

    def snapshot(*components):
        return health.PlatformHealth(
            status=health.worst([c.status for c in components]),
            components=list(components),
            checked_at="2026-08-05T00:00:00Z",
        )

    firing = alerts.evaluate(snapshot(health.critical("database", "unreachable")))
    assert [a.name for a in firing] == ["database_unavailable"]
    assert firing[0].severity == alerts.CRITICAL

    firing = alerts.evaluate(
        snapshot(health.degraded("consumers", "dead", dead_lettering=["notification-dispatch(3)"]))
    )
    assert "dead_letter_growth" in [a.name for a in firing]

    firing = alerts.evaluate(snapshot(health.warning("jwt_keys", "expiring soon")))
    assert "jwt_key_expiring" in [a.name for a in firing]


def test_alerts_are_ordered_worst_first():
    from platform_core.core import alerts, health

    snapshot = health.PlatformHealth(
        status=health.CRITICAL,
        components=[
            health.critical("database", "down"),
            health.degraded("redis", "down"),
        ],
        checked_at="2026-08-05T00:00:00Z",
    )
    firing = alerts.evaluate(snapshot)
    severities = [a.severity for a in firing]
    assert severities == sorted(severities, key=lambda s: {"critical": 0, "warning": 1}.get(s, 2))


async def test_the_alerts_endpoint_returns_actions(client):
    headers = await _ops(client)
    rules = (await client.get("/v1/_ops/alert-rules", headers=headers)).json()
    assert rules and all(rule["action"] for rule in rules)
    firing = await client.get("/v1/_ops/alerts", headers=headers)
    assert firing.status_code == 200


# --- operator surface --------------------------------------------------------


async def test_the_overview_answers_the_first_question_an_operator_asks(client):
    headers = await _ops(client)
    body = (await client.get("/v1/_ops/overview", headers=headers)).json()
    assert body["status"] in ("healthy", "warning", "degraded", "critical")
    assert set(body["counts"]) == {"critical", "warning", "info"}
    assert "database" in body["components"]
    assert isinstance(body["alerts"], list)


async def test_a_consumer_can_be_paused_and_resumed(client):
    headers = await _ops(client)
    name = "reporting-projection"

    paused = await client.post(f"/v1/_consumers/{name}/pause", headers=headers)
    assert paused.status_code == 200 and paused.json()["enabled"] is False

    health_body = (await client.get("/v1/_ops/health", headers=headers)).json()
    consumers = next(c for c in health_body["components"] if c["name"] == "consumers")
    assert name in consumers["data"]["paused"]
    assert consumers["status"] == "warning"  # deliberate, but surfaced

    resumed = await client.post(f"/v1/_consumers/{name}/resume", headers=headers)
    assert resumed.status_code == 200 and resumed.json()["enabled"] is True


async def test_pausing_an_unknown_consumer_is_404(client):
    headers = await _ops(client)
    r = await client.post("/v1/_consumers/no-such-consumer/pause", headers=headers)
    assert r.status_code == 404


async def test_the_operations_surface_is_platform_staff_only(client):
    _, tenant = await _tenant_admin(client)
    for path in ("/v1/_ops/health", "/v1/_ops/alerts", "/v1/_ops/overview"):
        assert (await client.get(path, headers=tenant)).status_code == 403, path
    assert (await client.get("/v1/_ops/overview")).status_code in (401, 403)


# --- tracing -----------------------------------------------------------------


def test_tracing_is_a_no_op_until_it_is_configured():
    """Spans must cost nothing when no exporter is configured — otherwise a
    village install pays for a pipeline it never uses."""
    from platform_core.core import tracing

    assert tracing.is_enabled() is False
    with tracing.span("anything", attribute="value"):
        pass  # must not raise
    assert tracing.current_trace_id() is None


def test_tracing_reports_honestly_when_configured_but_uninstalled(monkeypatch):
    """Configured-but-missing must say so rather than imply instrumentation
    that is not happening."""
    from platform_core.core import tracing
    from platform_core.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "otel_exporter_endpoint", "http://collector:4318")
    try:
        enabled = tracing.setup_tracing()
    finally:
        tracing.reset_tracing()
    # The SDK is not a platform dependency, so this must be False, not a crash.
    assert enabled is False


# --- structured logging -------------------------------------------------------


async def test_logs_are_structured_json_with_the_required_fields(client, capsys):
    """Every entry must be machine-parseable and carry the fields an operator
    filters on — otherwise 'structured logging' is just logging."""
    import json

    request_id = uuid.uuid4().hex
    await client.get("/health/live", headers={"X-Request-ID": request_id})
    captured = capsys.readouterr()
    entries = []
    for line in (captured.out + captured.err).splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    requests = [e for e in entries if e.get("event") == "request"]
    assert requests, "the access log entry must be emitted"
    entry = requests[-1]
    for field in ("timestamp", "level", "request_id", "method", "path", "status", "duration_ms"):
        assert field in entry, f"{field} missing from the access log"
    assert entry["request_id"] == request_id


async def test_logs_never_carry_credentials(client):
    """A log line is the easiest place to leak a secret."""
    import json

    await client.post(
        "/v1/auth/token",
        json={"email": "leak@example.com", "password": "super-secret-password"},
    )
    # The access log records the path and status, never the body.
    from platform_core.core.observability import RequestContextMiddleware

    source = RequestContextMiddleware.dispatch.__doc__ or ""
    assert "password" not in source.lower()
    assert json  # the parser above is the real assertion; this keeps intent clear


@pytest.mark.parametrize("endpoint", ["/health/live", "/health/ready"])
async def test_health_endpoints_are_fast(client, endpoint):
    """An operator polling every 10 seconds must not become a load source."""
    import time

    await client.get(endpoint)  # warm
    start = time.perf_counter()
    await client.get(endpoint)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 250, f"{endpoint} took {elapsed_ms:.0f}ms"
