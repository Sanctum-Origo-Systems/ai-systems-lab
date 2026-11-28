import json
import socket
import sys
import urllib.error
import urllib.request

import labkit
import pytest
from labkit import HealthChecks, HealthServer, LabSettings, serve_from_settings
from labkit.health import METRICS_CONTENT_TYPE

TIMEOUT = 2.0


def fetch(port: int, path: str, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        with error:
            return error.code, dict(error.headers), error.read()


class Toggle:
    def __init__(self, value: bool = True) -> None:
        self.value = value

    def __call__(self) -> bool:
        return self.value


def failing_check() -> bool:
    raise RuntimeError("password=example-secret")


@pytest.fixture
def checks() -> HealthChecks:
    return HealthChecks()


@pytest.fixture
def server(checks):
    with HealthServer(checks, metrics_renderer=lambda: b"lab_up 1\n") as running:
        yield running


# HealthChecks


def test_live_is_always_ok(checks):
    checks.add_readiness("db", Toggle(False))

    assert checks.live() == (200, {"status": "ok"})


def test_ready_with_no_checks_is_ok(checks):
    assert checks.ready() == (200, {"status": "ok", "checks": {}})


def test_ready_when_every_check_passes(checks):
    checks.add_readiness("db", Toggle(True))
    checks.add_readiness("queue", Toggle(True))

    assert checks.ready() == (200, {"status": "ok", "checks": {"db": "ok", "queue": "ok"}})


def test_ready_marks_failing_check(checks):
    checks.add_readiness("db", Toggle(True))
    checks.add_readiness("queue", Toggle(False))

    assert checks.ready() == (
        503,
        {"status": "unavailable", "checks": {"db": "ok", "queue": "fail"}},
    )


def test_raising_check_fails_without_leaking_message(checks):
    checks.add_readiness("db", failing_check)

    status, body = checks.ready()

    assert status == 503
    assert body == {"status": "unavailable", "checks": {"db": "fail"}}
    serialized = json.dumps(body)
    assert "example-secret" not in serialized
    assert "RuntimeError" not in serialized


@pytest.mark.parametrize("name", ["", "DB", "db-check", "db check", "a" * 33, "dé"])
def test_add_readiness_rejects_bad_names(checks, name):
    with pytest.raises(ValueError):
        checks.add_readiness(name, Toggle())


@pytest.mark.parametrize("name", ["db", "queue_2", "a" * 32])
def test_add_readiness_accepts_valid_names(checks, name):
    checks.add_readiness(name, Toggle())

    assert checks.ready()[1]["checks"] == {name: "ok"}


# HealthServer


def test_healthz_returns_json(server):
    status, headers, body = fetch(server.server_address[1], "/healthz")

    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == {"status": "ok"}


def test_readyz_flips_to_503_when_check_fails(checks, server):
    toggle = Toggle(True)
    checks.add_readiness("db", toggle)
    port = server.server_address[1]

    status, headers, body = fetch(port, "/readyz")
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == {"status": "ok", "checks": {"db": "ok"}}

    toggle.value = False
    status, headers, body = fetch(port, "/readyz")
    assert status == 503
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == {"status": "unavailable", "checks": {"db": "fail"}}


def test_readyz_body_hides_exception_message(checks, server):
    checks.add_readiness("db", failing_check)

    status, _, body = fetch(server.server_address[1], "/readyz")

    assert status == 503
    assert b"example-secret" not in body


def test_metrics_returns_renderer_bytes(server):
    status, headers, body = fetch(server.server_address[1], "/metrics")

    assert status == 200
    assert headers["Content-Type"] == METRICS_CONTENT_TYPE
    assert headers["Content-Type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert body == b"lab_up 1\n"


def test_metrics_404_without_renderer(checks):
    with HealthServer(checks) as running:
        status, _, _ = fetch(running.server_address[1], "/metrics")

    assert status == 404


def test_unknown_path_is_404(server):
    assert fetch(server.server_address[1], "/nope")[0] == 404


@pytest.mark.parametrize("path", ["/healthz", "/readyz", "/metrics"])
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_other_methods_are_405(server, path, method):
    assert fetch(server.server_address[1], path, method=method)[0] == 405


def test_head_returns_headers_without_body(server):
    status, headers, body = fetch(server.server_address[1], "/healthz", method="HEAD")

    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert body == b""


def test_default_host_is_loopback(checks):
    server = HealthServer(checks)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.stop()


def test_port_is_final_after_constructor(checks):
    server = HealthServer(checks, port=0)
    try:
        port = server.server_address[1]
        assert port != 0
        assert server.start() == ("127.0.0.1", port)
        assert fetch(port, "/healthz")[0] == 200
    finally:
        server.stop()


def test_serving_writes_nothing_to_stderr(checks, capfd):
    checks.add_readiness("db", Toggle(False))
    with HealthServer(checks, metrics_renderer=lambda: b"") as running:
        port = running.server_address[1]
        for path in ["/healthz", "/readyz", "/metrics", "/nope"]:
            fetch(port, path)
        fetch(port, "/healthz", method="POST")
    sys.stderr.flush()

    assert capfd.readouterr().err == ""


def test_stop_refuses_new_connections(checks):
    server = HealthServer(checks)
    _, port = server.start()
    assert fetch(port, "/healthz")[0] == 200

    server.stop()

    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", port), timeout=TIMEOUT)


def test_stop_without_start_closes_socket(checks):
    server = HealthServer(checks)
    port = server.server_address[1]

    server.stop()

    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", port), timeout=TIMEOUT)


# serve_from_settings


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_serve_from_settings_binds_settings_address(checks):
    port = free_port()
    settings = LabSettings(service_name="demo-service", metrics_port=port)

    server = serve_from_settings(settings, checks, metrics_renderer=lambda: b"lab_up 1\n")
    try:
        assert isinstance(server, HealthServer)
        assert server.server_address[:2] == (settings.metrics_bind, port)
        assert fetch(port, "/healthz")[0] == 200
        assert fetch(port, "/metrics")[2] == b"lab_up 1\n"
    finally:
        server.stop()


def test_package_exports():
    for name in [
        "HealthChecks",
        "HealthServer",
        "serve_from_settings",
        "LabSettings",
        "SettingsError",
        "load_settings",
        "__version__",
    ]:
        assert name in labkit.__all__
        assert hasattr(labkit, name)
