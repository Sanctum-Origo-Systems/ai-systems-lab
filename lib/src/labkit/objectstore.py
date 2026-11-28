"""Object store interface and an in-memory fake with S3-like semantics.

``put(..., if_none_match=True)`` mirrors S3's ``If-None-Match: *`` conditional put:
it fails with ``PreconditionFailedError`` (S3's 412) when the key already exists, so a
duplicate writer can't overwrite the first result.
"""

from typing import Protocol


class ObjectNotFoundError(KeyError):
    """Raised by get when the key does not exist."""


class PreconditionFailedError(Exception):
    """Raised by put with if_none_match=True when the key already exists."""


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, if_none_match: bool = False) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def list_keys(self, prefix: str = "") -> list[str]: ...


def _check_key(key: str) -> None:
    if not key:
        raise ValueError("object key must be a non-empty string")


class InMemoryObjectStore:
    """Dict-backed ObjectStore for tests. Not thread-safe."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, if_none_match: bool = False) -> None:
        _check_key(key)
        if if_none_match and key in self._objects:
            raise PreconditionFailedError(key)
        self._objects[key] = bytes(data)

    def get(self, key: str) -> bytes:
        _check_key(key)
        try:
            return self._objects[key]
        except KeyError:
            raise ObjectNotFoundError(key) from None

    def exists(self, key: str) -> bool:
        _check_key(key)
        return key in self._objects

    def delete(self, key: str) -> None:
        _check_key(key)
        self._objects.pop(key, None)

    def list_keys(self, prefix: str = "") -> list[str]:
        return sorted(k for k in self._objects if k.startswith(prefix))
