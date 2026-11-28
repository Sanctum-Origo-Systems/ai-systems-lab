"""One request id carried end to end and stamped on every log line.

The id usually arrives in a client-supplied X-Request-ID header. Any caller can set
that header, so a value is kept only when it fully matches a short safe pattern;
anything else (newlines, ANSI escapes, quotes, non-ASCII, over-long) is replaced by
a freshly generated id before it can reach a log line. Standard library only.
"""

import contextvars
import logging
import re
import uuid
from collections.abc import Awaitable, Callable, Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any

HEADER = "X-Request-ID"
MAX_LEN = 64
SAFE_PATTERN = re.compile(rf"[A-Za-z0-9._-]{{1,{MAX_LEN}}}")

_HEADER_BYTES = HEADER.lower().encode("ascii")
_current: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "labkit_request_id", default=None
)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def new_id() -> str:
    """A fresh random id: 32 lowercase hex characters."""
    return uuid.uuid4().hex


def sanitize(value: str | None, generate: Callable[[], str] = new_id) -> str:
    """Return value if it fully matches the safe pattern, else generate()."""
    if isinstance(value, str) and SAFE_PATTERN.fullmatch(value):
        return value
    return generate()


def current() -> str | None:
    """The request id bound in the current context, or None."""
    return _current.get()


@contextmanager
def bind(request_id: str) -> Iterator[str]:
    """Bind request_id for the block; restore the previous value on exit."""
    token = _current.set(request_id)
    try:
        yield request_id
    finally:
        _current.reset(token)


def _header_value(scope: Scope) -> str | None:
    for name, value in scope.get("headers") or ():
        if bytes(name).lower() == _HEADER_BYTES:
            return bytes(value).decode("latin-1")
    return None


class RequestIdMiddleware:
    """Pure ASGI middleware: sanitize, bind and echo X-Request-ID on http scopes."""

    def __init__(self, app: ASGIApp, generate: Callable[[], str] = new_id) -> None:
        self.app = app
        self.generate = generate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = sanitize(_header_value(scope), self.generate)
        header = (_HEADER_BYTES, request_id.encode("ascii"))

        async def send_with_id(message: Message) -> None:
            if message.get("type") == "http.response.start":
                message = dict(message)
                message["headers"] = [*message.get("headers", ()), header]
            await send(message)

        with bind(request_id):
            await self.app(scope, receive, send_with_id)


class RequestIdFilter(logging.Filter):
    """Set record.request_id from the bound id; leave the record alone if none."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = current()
        if request_id is not None:
            record.request_id = request_id
        return True
