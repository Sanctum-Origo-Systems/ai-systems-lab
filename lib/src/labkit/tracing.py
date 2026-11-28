"""Opt-in OpenTelemetry tracing, configured only by the standard OTEL_* env vars.

configure_tracing does nothing unless an exporter is passed in or one of
OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_EXPORTER_OTLP_TRACES_ENDPOINT is set, so tests
and local runs never need a collector. OTEL_SDK_DISABLED=true turns tracing off
entirely, and OTEL_TRACES_EXPORTER=none turns off the env-selected exporter.
Spans go out over OTLP/HTTP. While a span is active, labkit.log lines carry its
trace_id next to request_id.
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanProcessor,
)

from labkit.log import add_handler_filter

_ENDPOINT_VARS = ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")


def current_trace_id() -> str | None:
    """The active span's trace id as 32 lowercase hex characters, or None."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return trace.format_trace_id(context.trace_id)


class TraceIdFilter(logging.Filter):
    """Set record.trace_id from the active span; leave the record alone if none."""

    def filter(self, record: logging.LogRecord) -> bool:
        trace_id = current_trace_id()
        if trace_id is not None:
            record.trace_id = trace_id
        return True


def configure_tracing(
    service_name: str,
    exporter: SpanExporter | None = None,
    set_global: bool = True,
) -> TracerProvider | None:
    """Build a TracerProvider if tracing is asked for; otherwise return None.

    A passed exporter is wrapped in a SimpleSpanProcessor. Without one, an OTLP/HTTP
    exporter in a BatchSpanProcessor is used when an OTLP endpoint env var is set.
    OTEL_SERVICE_NAME, when set, overrides service_name.

    OTEL_SDK_DISABLED=true returns None, even with a passed exporter.
    OTEL_TRACES_EXPORTER=none skips the env-selected OTLP exporter but still honors a
    passed exporter, since the caller asked for it directly.
    """
    sdk_disabled = os.environ.get("OTEL_SDK_DISABLED", "").strip().lower() == "true"
    traces_exporter = os.environ.get("OTEL_TRACES_EXPORTER", "").strip().lower()
    if sdk_disabled:
        return None

    processor: SpanProcessor
    if exporter is not None:
        processor = SimpleSpanProcessor(exporter)
    elif traces_exporter != "none" and any(os.environ.get(var) for var in _ENDPOINT_VARS):
        processor = BatchSpanProcessor(OTLPSpanExporter())
    else:
        return None

    name = os.environ.get("OTEL_SERVICE_NAME") or service_name
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: name}))
    provider.add_span_processor(processor)
    if set_global:
        trace.set_tracer_provider(provider)
    add_handler_filter(TraceIdFilter())
    return provider
