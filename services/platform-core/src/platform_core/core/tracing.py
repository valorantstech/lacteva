"""Distributed tracing (OBS-001).

Metrics say *how much*; traces say *where the time went and what caused what*.
For an event-driven platform that second question is the hard one: a farmer's
collection becomes a pricing call, an outbox row, a consumer run, a
notification, and a receipt, and no single log line explains the chain.

**OpenTelemetry is supported, not required.** The SDK is a large dependency
tree and a deployment concern — a village-scale install should not carry a
tracing pipeline it will never export to. So this module is a thin seam:

- If `opentelemetry-sdk` is installed AND an exporter endpoint is configured,
  spans are real OTel spans.
- Otherwise every span is a no-op costing a context-manager enter and exit.

Instrumentation is written once, at the seams, and does not care which mode
it is in. Correlation ids flow either way, because the platform's own
structured logging already carries them — tracing enriches that story rather
than replacing it.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

from platform_core.core.config import get_settings

log = structlog.get_logger("tracing")

_tracer: Any | None = None
_enabled = False


def setup_tracing() -> bool:
    """Wire OpenTelemetry if it is both installed and configured.

    Returns whether real tracing is active, so startup can log the truth
    rather than implying instrumentation that is not there.
    """
    global _tracer, _enabled
    endpoint = get_settings().otel_exporter_endpoint
    if not endpoint:
        _enabled = False
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        # Configured but not installed: say so loudly rather than pretending.
        log.warning(
            "otel_not_installed",
            endpoint=endpoint,
            hint="pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http",
        )
        _enabled = False
        return False

    provider = TracerProvider(
        resource=Resource.create({"service.name": get_settings().service_name})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("platform-core")
    _enabled = True
    log.info("otel_enabled", endpoint=endpoint)
    return True


def is_enabled() -> bool:
    return _enabled


def reset_tracing() -> None:
    global _tracer, _enabled
    _tracer, _enabled = None, False


@contextmanager
def span(name: str, **attributes) -> Iterator[None]:
    """Trace a unit of work.

    Attribute discipline mirrors the metric cardinality rule for a different
    reason: a span attribute is stored per-span, so an id is fine here — but
    a credential or a farmer's phone number is not. Never put PII or secrets
    in a span.
    """
    if not _enabled or _tracer is None:
        yield
        return
    with _tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, str(value))
        yield


def current_trace_id() -> str | None:
    """The active trace id, for correlating a log line with a trace."""
    if not _enabled:
        return None
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        return format(context.trace_id, "032x") if context.is_valid else None
    except Exception:
        return None
