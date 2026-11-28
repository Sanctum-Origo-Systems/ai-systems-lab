import io
import json
import logging
import os
import re

import labkit
import pytest
from labkit import log, tracing
from labkit.tracing import TraceIdFilter, configure_tracing, current_trace_id
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

TRACE_ID = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture(autouse=True)
def clean_env_and_logging(monkeypatch):
    for name in list(os.environ):
        if name.startswith("OTEL_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(log, "_handler_filters", [])
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(level)


@pytest.fixture
def no_otlp_exporter(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("OTLPSpanExporter must not be created")

    monkeypatch.setattr(tracing, "OTLPSpanExporter", refuse)


def only_processor(provider):
    [processor] = provider._active_span_processor._span_processors
    return processor


def test_off_without_env_or_exporter(no_otlp_exporter):
    before = trace.get_tracer_provider()

    assert configure_tracing("svc") is None

    assert trace.get_tracer_provider() is before
    assert log._handler_filters == []


def test_exporter_argument_exports_span_with_service_name():
    exporter = InMemorySpanExporter()
    provider = configure_tracing("svc", exporter=exporter, set_global=False)
    assert provider is not None

    with provider.get_tracer("test").start_as_current_span("handle-job"):
        pass

    [span] = exporter.get_finished_spans()
    assert span.name == "handle-job"
    assert span.resource.attributes["service.name"] == "svc"
    provider.shutdown()


def test_otel_service_name_overrides_argument(monkeypatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "from-env")
    exporter = InMemorySpanExporter()
    provider = configure_tracing("svc", exporter=exporter, set_global=False)

    with provider.get_tracer("test").start_as_current_span("step"):
        pass

    [span] = exporter.get_finished_spans()
    assert span.resource.attributes["service.name"] == "from-env"
    provider.shutdown()


@pytest.mark.parametrize(
    "var", ["OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]
)
def test_endpoint_env_uses_batch_otlp_http(monkeypatch, var):
    monkeypatch.setenv(var, "http://127.0.0.1:4318")

    provider = configure_tracing("svc", set_global=False)

    assert provider is not None
    processor = only_processor(provider)
    assert isinstance(processor, BatchSpanProcessor)
    assert isinstance(processor.span_exporter, OTLPSpanExporter)
    # No span was started, so shutdown has nothing to export and opens no connection.
    provider.shutdown()


def test_set_global_false_leaves_global_provider_alone():
    before = trace.get_tracer_provider()

    provider = configure_tracing("svc", exporter=InMemorySpanExporter(), set_global=False)

    assert trace.get_tracer_provider() is before
    provider.shutdown()


def test_trace_id_inside_span_matches_log_line():
    stream = io.StringIO()
    labkit.configure_logging("svc", stream=stream)
    provider = configure_tracing("svc", exporter=InMemorySpanExporter(), set_global=False)

    with labkit.bind("req-1"), provider.get_tracer("test").start_as_current_span("step"):
        trace_id = current_trace_id()
        logging.getLogger("demo").info("inside")

    assert trace_id is not None and TRACE_ID.match(trace_id)
    record = json.loads(stream.getvalue().splitlines()[0])
    assert record["trace_id"] == trace_id
    assert record["request_id"] == "req-1"
    provider.shutdown()


def test_no_trace_id_outside_span():
    stream = io.StringIO()
    labkit.configure_logging("svc", stream=stream)
    provider = configure_tracing("svc", exporter=InMemorySpanExporter(), set_global=False)

    assert current_trace_id() is None
    logging.getLogger("demo").info("outside")

    record = json.loads(stream.getvalue().splitlines()[0])
    assert "trace_id" not in record
    provider.shutdown()


def test_logging_configured_after_tracing_still_carries_trace_id():
    provider = configure_tracing("svc", exporter=InMemorySpanExporter(), set_global=False)
    stream = io.StringIO()
    labkit.configure_logging("svc", stream=stream)

    with provider.get_tracer("test").start_as_current_span("step"):
        trace_id = current_trace_id()
        logging.getLogger("demo").info("inside")

    assert json.loads(stream.getvalue().splitlines()[0])["trace_id"] == trace_id
    provider.shutdown()


def test_repeat_configure_does_not_stack_filters():
    labkit.configure_logging("svc", stream=io.StringIO())
    providers = [
        configure_tracing("svc", exporter=InMemorySpanExporter(), set_global=False)
        for _ in range(2)
    ]

    [handler] = [h for h in logging.getLogger().handlers if isinstance(h, log._LabkitHandler)]
    assert sum(isinstance(f, TraceIdFilter) for f in handler.filters) == 1
    for provider in providers:
        provider.shutdown()


def test_public_exports():
    from labkit import configure_tracing as ct
    from labkit import current_trace_id as cti

    assert ct is configure_tracing and cti is current_trace_id
    for name in [
        "HealthChecks",
        "HealthServer",
        "LabSettings",
        "RequestIdMiddleware",
        "SettingsError",
        "__version__",
        "bind",
        "configure_from_settings",
        "configure_logging",
        "current",
        "load_settings",
        "serve_from_settings",
    ]:
        assert hasattr(labkit, name), name
