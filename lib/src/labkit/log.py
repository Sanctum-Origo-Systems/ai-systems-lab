"""Root logger setup shared by every service, built on the standard library only.

`fmt="json"` writes one JSON object per line for machines; `fmt="console"` writes
one short line per record for people. Both carry the service name and any `extra` keys.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import IO, Any, Literal

from labkit.settings import LabSettings

LogFormat = Literal["json", "console"]

# Attributes every LogRecord has; anything else on a record came from `extra={...}`.
_RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
}


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in vars(record).items() if k not in _RESERVED}


class JsonFormatter(logging.Formatter):
    """One JSON object per record: ts, level, logger, msg, service, extras, exc."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC)
        payload: dict[str, Any] = {
            "ts": ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "service": self.service_name,
        }
        payload.update(_extras(record))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exc"] = record.exc_text
        return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    """'HH:MM:SS LEVEL logger: msg key=value ...' with extras sorted by key."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S")
        line = f"{ts} {record.levelname} {record.name}: {record.getMessage()}"
        extras = _extras(record)
        if extras:
            line += " " + " ".join(f"{k}={extras[k]}" for k in sorted(extras))
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class _LabkitHandler(logging.StreamHandler):
    """Marker class so a repeat configure_logging call can find and replace it."""


def configure_logging(
    service_name: str,
    level: str = "INFO",
    fmt: LogFormat = "json",
    stream: IO[str] | None = None,
) -> None:
    """Configure the root logger, replacing any handler a previous call installed."""
    if fmt == "json":
        formatter: logging.Formatter = JsonFormatter(service_name)
    elif fmt == "console":
        formatter = ConsoleFormatter()
    else:
        raise ValueError(f"unknown log format {fmt!r}; expected 'json' or 'console'")

    root = logging.getLogger()
    for existing in list(root.handlers):
        if isinstance(existing, _LabkitHandler):
            root.removeHandler(existing)
            existing.close()

    handler = _LabkitHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(level.upper())


def configure_from_settings(settings: LabSettings, stream: IO[str] | None = None) -> None:
    """Configure logging from a LabSettings' service_name, log_level and log_format."""
    configure_logging(
        settings.service_name,
        level=settings.log_level,
        fmt=settings.log_format,
        stream=stream,
    )
