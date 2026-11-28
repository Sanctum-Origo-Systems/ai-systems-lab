import asyncio
import io
import json
import logging

import labkit
import pytest
from labkit import RequestIdMiddleware, bind, configure_logging, current
from labkit.request_id import HEADER, MAX_LEN, RequestIdFilter, new_id, sanitize


def generated() -> str:
    return "generated-1"


@pytest.fixture(autouse=True)
def restore_root_logger():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(level)


# --- sanitize ---------------------------------------------------------------


def test_constants():
    assert HEADER == "X-Request-ID"
    assert MAX_LEN == 64


def test_new_id_is_uuid4_hex():
    value = new_id()
    assert len(value) == 32
    assert sanitize(value) == value


@pytest.mark.parametrize("value", ["req-17.a_B", "a" * 64])
def test_sanitize_keeps_safe_value(value):
    assert sanitize(value, generate=generated) == value


@pytest.mark.parametrize(
    "value",
    [
        "a" * 65,
        "",
        None,
        "a b",
        "abc\ndef",
        "abc\n",
        "\x1b[31mred",
        "café",
        'x","level":"ERROR',
        "tab\there",
        "nul\x00",
    ],
)
def test_sanitize_replaces_unsafe_value(value):
    assert sanitize(value, generate=generated) == "generated-1"


# --- bind / current ---------------------------------------------------------


def test_bind_sets_and_restores():
    assert current() is None
    with bind("outer"):
        assert current() == "outer"
        with bind("inner"):
            assert current() == "inner"
        assert current() == "outer"
    assert current() is None


# --- middleware -------------------------------------------------------------


def run_http(headers, generate=generated):
    seen: dict = {}
    sent: list = []

    async def app(scope, receive, send):
        seen["request_id"] = current()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"a", b"1")]})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers}
    asyncio.run(RequestIdMiddleware(app, generate=generate)(scope, receive, send))
    return seen, sent


def response_ids(sent) -> list[bytes]:
    [start] = [m for m in sent if m["type"] == "http.response.start"]
    return [v for k, v in start["headers"] if k == b"x-request-id"]


def test_middleware_echoes_valid_id_and_binds_it():
    seen, sent = run_http([(b"X-Request-ID", b"req-17")])
    assert response_ids(sent) == [b"req-17"]
    assert seen["request_id"] == "req-17"


def test_middleware_matches_header_name_case_insensitively():
    seen, sent = run_http([(b"x-request-id", b"req-18")])
    assert response_ids(sent) == [b"req-18"]


def test_middleware_keeps_existing_response_headers():
    _, sent = run_http([(b"x-request-id", b"req-19")])
    assert (b"a", b"1") in sent[0]["headers"]
    assert sent[1] == {"type": "http.response.body", "body": b"ok"}


def test_middleware_replaces_invalid_id():
    seen, sent = run_http([(b"x-request-id", b"abc\r\ndef")])
    assert response_ids(sent) == [b"generated-1"]
    assert seen["request_id"] == "generated-1"


def test_middleware_generates_id_when_header_missing():
    seen, sent = run_http([(b"accept", b"*/*")])
    assert response_ids(sent) == [b"generated-1"]
    assert seen["request_id"] == "generated-1"


def test_current_is_none_after_middleware_call():
    run_http([(b"x-request-id", b"req-17")])
    assert current() is None


def test_middleware_passes_lifespan_through_untouched():
    received: list = []
    sent: list = []
    scope = {"type": "lifespan"}

    async def app(s, receive, send):
        received.append((s, current()))
        await send({"type": "lifespan.startup.complete"})

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(message):
        sent.append(message)

    asyncio.run(RequestIdMiddleware(app, generate=generated)(scope, receive, send))
    assert received == [({"type": "lifespan"}, None)]
    assert sent == [{"type": "lifespan.startup.complete"}]


# --- logging ----------------------------------------------------------------


def test_json_line_carries_bound_request_id():
    stream = io.StringIO()
    configure_logging("demo-service", stream=stream)
    with bind("req-17"):
        logging.getLogger("demo.api").info("handled")
    line = stream.getvalue().splitlines()[0]
    assert '"request_id": "req-17"' in line
    assert json.loads(line)["request_id"] == "req-17"


def test_json_line_has_no_request_id_when_unbound():
    stream = io.StringIO()
    configure_logging("demo-service", stream=stream)
    logging.getLogger("demo.api").info("handled")
    assert "request_id" not in json.loads(stream.getvalue().splitlines()[0])


def test_console_line_shows_request_id():
    stream = io.StringIO()
    configure_logging("demo-service", fmt="console", stream=stream)
    with bind("req-17"):
        logging.getLogger("demo.api").info("handled", extra={"job": "j1"})
    assert "job=j1 request_id=req-17" in stream.getvalue()


def test_filter_leaves_record_unchanged_when_unbound():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "m", None, None)
    assert RequestIdFilter().filter(record) is True
    assert not hasattr(record, "request_id")


# --- exports ----------------------------------------------------------------


def test_package_exports():
    for name in [
        "LabSettings",
        "SettingsError",
        "__version__",
        "configure_from_settings",
        "configure_logging",
        "load_settings",
        "RequestIdMiddleware",
        "bind",
        "current",
    ]:
        assert hasattr(labkit, name), name
        assert name in labkit.__all__, name
