"""Liveness, readiness and metrics endpoints for every service.

Web services can mount `HealthChecks.live()` and `HealthChecks.ready()` on their own
routes. Services without a web server (workers, the autoscaler) run a `HealthServer`
on a side port instead, so one contract test can probe every service the same way:

- GET /healthz: 200 while the process is up.
- GET /readyz: 200 when every readiness check passes, else 503.
- GET /metrics: the bytes from `metrics_renderer`, or 404 if there is none.

Standard library only, so importing it adds no dependencies.
"""

import json
import re
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from labkit.settings import LabSettings

METRICS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
JSON_CONTENT_TYPE = "application/json"

_CHECK_NAME = re.compile(r"[a-z0-9_]{1,32}")

ReadinessCheck = Callable[[], bool]
MetricsRenderer = Callable[[], bytes]


class HealthChecks:
    """A registry of named readiness checks."""

    def __init__(self) -> None:
        self._checks: dict[str, ReadinessCheck] = {}
        self._lock = threading.Lock()

    def add_readiness(self, name: str, check: ReadinessCheck) -> None:
        """Register `check` under `name`, which must match [a-z0-9_]{1,32}."""
        if not isinstance(name, str) or not _CHECK_NAME.fullmatch(name):
            raise ValueError(f"readiness check name must match [a-z0-9_]{{1,32}}: {name!r}")
        with self._lock:
            self._checks[name] = check

    def live(self) -> tuple[int, dict[str, Any]]:
        """The process is up and answering: always 200."""
        return 200, {"status": "ok"}

    def ready(self) -> tuple[int, dict[str, Any]]:
        """Run every check. 200 if all return True (or none exist), else 503.

        A check that raises counts as failed. Its message is dropped, never returned,
        because exception text can carry connection strings or credentials.
        """
        with self._lock:
            checks = list(self._checks.items())
        results: dict[str, str] = {}
        for name, check in checks:
            try:
                passed = check() is True
            except Exception:
                passed = False
            results[name] = "ok" if passed else "fail"
        if all(result == "ok" for result in results.values()):
            return 200, {"status": "ok", "checks": results}
        return 503, {"status": "unavailable", "checks": results}


class _HealthHandler(BaseHTTPRequestHandler):
    server: "HealthServer"

    def do_GET(self) -> None:
        self._respond(include_body=True)

    def do_HEAD(self) -> None:
        self._respond(include_body=False)

    def __getattr__(self, name: str) -> Any:
        # BaseHTTPRequestHandler answers 501 for methods without a do_<METHOD>;
        # answer every method other than GET and HEAD with 405 instead.
        if name.startswith("do_"):
            return self._method_not_allowed
        raise AttributeError(name)

    def _method_not_allowed(self) -> None:
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, b"", "text/plain", {"Allow": "GET, HEAD"})

    def _respond(self, include_body: bool) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/healthz", "/readyz"):
            checks = self.server.checks
            status, body = checks.live() if path == "/healthz" else checks.ready()
            payload = json.dumps(body).encode("utf-8")
            self._send(status, payload, JSON_CONTENT_TYPE, include_body=include_body)
        elif path == "/metrics" and self.server.metrics_renderer is not None:
            try:
                payload = self.server.metrics_renderer()
            except Exception:
                # Never echo the exception: its text could carry secrets.
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, b"", "text/plain")
                return
            self._send(HTTPStatus.OK, payload, METRICS_CONTENT_TYPE, include_body=include_body)
        else:
            self._send(HTTPStatus.NOT_FOUND, b"", "text/plain")

    def _send(
        self,
        status: int,
        payload: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
        include_body: bool = True,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if include_body and payload:
            self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        # Request logs would go to stderr; services log through labkit logging instead.
        return


class HealthServer(ThreadingHTTPServer):
    """Serves /healthz, /readyz and /metrics on its own port.

    Binds in the constructor, so `server_address` holds the final port (useful with
    port=0) before `start()` is called.
    """

    daemon_threads = True

    def __init__(
        self,
        checks: HealthChecks,
        metrics_renderer: MetricsRenderer | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.checks = checks
        self.metrics_renderer = metrics_renderer
        self._thread: threading.Thread | None = None
        super().__init__((host, port), _HealthHandler)

    def start(self) -> tuple[str, int]:
        """Serve on a daemon thread and return the bound (host, port)."""
        if self._thread is None:
            self._thread = threading.Thread(
                target=self.serve_forever, name="labkit-health", daemon=True
            )
            self._thread.start()
        host, port = self.server_address[:2]
        return str(host), int(port)

    def stop(self) -> None:
        """Stop serving and close the listening socket."""
        if self._thread is not None:
            self.shutdown()
            self._thread.join()
            self._thread = None
        self.server_close()

    def handle_error(self, request: object, client_address: object) -> None:
        # socketserver's default prints a traceback to stderr; drop it so a
        # misbehaving client or handler bug never writes request details there.
        return

    def __enter__(self) -> "HealthServer":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()


def serve_from_settings(
    settings: "LabSettings",
    checks: HealthChecks,
    metrics_renderer: MetricsRenderer | None = None,
) -> HealthServer:
    """Build a HealthServer on settings.metrics_bind:settings.metrics_port and start it."""
    server = HealthServer(
        checks,
        metrics_renderer=metrics_renderer,
        host=settings.metrics_bind,
        port=settings.metrics_port,
    )
    server.start()
    return server
