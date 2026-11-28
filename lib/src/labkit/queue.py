"""Message queue interface with SQS semantics, plus an in-memory fake.

Delivery is at-least-once. A received message becomes invisible for a
visibility timeout; if it is not deleted before the timeout expires it is
delivered again with a higher receive count and a fresh receipt. Only the
most recent receipt for a message is valid. With a max receive count and a
dead-letter queue, a message that keeps failing is moved aside instead of
being redelivered forever.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Message:
    message_id: str
    body: str
    receipt: str
    receive_count: int
    attributes: dict[str, str]


class InvalidReceiptError(Exception):
    """The receipt is unknown, or the message was received again since it was issued."""


class Queue(Protocol):
    def send(self, body: str, attributes: dict[str, str] | None = None) -> str: ...

    def receive(
        self, max_messages: int = 1, visibility_timeout: float | None = None
    ) -> list[Message]: ...

    def delete(self, receipt: str) -> None: ...

    def change_visibility(self, receipt: str, timeout: float) -> None: ...


@dataclass
class _Entry:
    message_id: str
    body: str
    attributes: dict[str, str]
    receive_count: int = 0
    receipt: str | None = None
    visible_at: float = field(default=float("-inf"))


class InMemoryQueue:
    """A single-process Queue that reproduces SQS visibility and redelivery rules."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        visibility_timeout: float = 30.0,
        max_receive_count: int | None = None,
        dead_letter: "InMemoryQueue | None" = None,
        id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        if max_receive_count is not None and dead_letter is None:
            raise ValueError("max_receive_count requires a dead_letter queue")
        self._clock = clock
        self._visibility_timeout = visibility_timeout
        self._max_receive_count = max_receive_count
        self._dead_letter = dead_letter
        self._id_factory = id_factory
        # Insertion order of this dict is send order.
        self._entries: dict[str, _Entry] = {}
        self._by_receipt: dict[str, str] = {}

    def send(self, body: str, attributes: dict[str, str] | None = None) -> str:
        message_id = self._id_factory()
        self._entries[message_id] = _Entry(
            message_id=message_id, body=body, attributes=dict(attributes or {})
        )
        return message_id

    def receive(
        self, max_messages: int = 1, visibility_timeout: float | None = None
    ) -> list[Message]:
        timeout = self._visibility_timeout if visibility_timeout is None else visibility_timeout
        now = self._clock()
        received: list[Message] = []
        for entry in list(self._entries.values()):
            if len(received) >= max_messages:
                break
            if now < entry.visible_at:
                continue
            if (
                self._max_receive_count is not None
                and entry.receive_count >= self._max_receive_count
            ):
                self._remove(entry)
                assert self._dead_letter is not None
                self._dead_letter.send(entry.body, entry.attributes)
                continue
            if entry.receipt is not None:
                del self._by_receipt[entry.receipt]
            entry.receipt = self._id_factory()
            entry.receive_count += 1
            entry.visible_at = now + timeout
            self._by_receipt[entry.receipt] = entry.message_id
            received.append(
                Message(
                    message_id=entry.message_id,
                    body=entry.body,
                    receipt=entry.receipt,
                    receive_count=entry.receive_count,
                    attributes=dict(entry.attributes),
                )
            )
        return received

    def delete(self, receipt: str) -> None:
        self._remove(self._lookup(receipt))

    def change_visibility(self, receipt: str, timeout: float) -> None:
        self._lookup(receipt).visible_at = self._clock() + timeout

    def _lookup(self, receipt: str) -> _Entry:
        message_id = self._by_receipt.get(receipt)
        if message_id is None:
            raise InvalidReceiptError(receipt)
        return self._entries[message_id]

    def _remove(self, entry: _Entry) -> None:
        if entry.receipt is not None:
            del self._by_receipt[entry.receipt]
        del self._entries[entry.message_id]
