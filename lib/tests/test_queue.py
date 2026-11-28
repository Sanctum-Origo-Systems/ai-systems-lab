import itertools

import pytest
from labkit.queue import InMemoryQueue, InvalidReceiptError, Message, Queue


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def counter_ids(prefix: str = "id"):
    numbers = itertools.count(1)
    return lambda: f"{prefix}-{next(numbers)}"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def test_messages_are_received_in_send_order(clock):
    queue = InMemoryQueue(clock=clock)
    for body in ["A", "B", "C"]:
        queue.send(body)

    first = queue.receive()
    rest = queue.receive(max_messages=10)

    assert [m.body for m in first + rest] == ["A", "B", "C"]


def test_received_message_is_invisible_until_timeout_then_redelivered(clock):
    queue = InMemoryQueue(clock=clock, visibility_timeout=30.0)
    queue.send("job")

    [first] = queue.receive()
    assert first.receive_count == 1

    clock.now = 29.999
    assert queue.receive() == []

    clock.now = 30.0
    [second] = queue.receive()
    assert second.message_id == first.message_id
    assert second.receive_count == 2
    assert second.receipt != first.receipt


def test_per_call_visibility_timeout_overrides_default(clock):
    queue = InMemoryQueue(clock=clock, visibility_timeout=30.0)
    queue.send("job")

    queue.receive(visibility_timeout=5.0)
    clock.now = 4.0
    assert queue.receive() == []
    clock.now = 5.0
    assert [m.receive_count for m in queue.receive()] == [2]


def test_change_visibility_extends_invisibility(clock):
    queue = InMemoryQueue(clock=clock, visibility_timeout=10.0)
    queue.send("job")
    [message] = queue.receive()

    clock.now = 5.0
    queue.change_visibility(message.receipt, 20.0)

    clock.now = 10.0
    assert queue.receive() == []
    clock.now = 24.999
    assert queue.receive() == []
    clock.now = 25.0
    [again] = queue.receive()
    assert again.message_id == message.message_id
    assert again.receive_count == 2


def test_deleted_message_is_never_received_again(clock):
    queue = InMemoryQueue(clock=clock, visibility_timeout=10.0)
    queue.send("job")
    [message] = queue.receive()

    queue.delete(message.receipt)

    assert queue.receive() == []
    clock.now = 1000.0
    assert queue.receive() == []


def test_stale_receipt_is_rejected_after_redelivery(clock):
    queue = InMemoryQueue(clock=clock, visibility_timeout=10.0)
    queue.send("job")
    [first] = queue.receive()
    clock.now = 10.0
    [second] = queue.receive()

    with pytest.raises(InvalidReceiptError):
        queue.delete(first.receipt)
    with pytest.raises(InvalidReceiptError):
        queue.change_visibility(first.receipt, 60.0)

    # The current receipt still works.
    queue.delete(second.receipt)
    clock.now = 1000.0
    assert queue.receive() == []


def test_unknown_receipt_is_rejected(clock):
    queue = InMemoryQueue(clock=clock)
    queue.send("job")

    with pytest.raises(InvalidReceiptError):
        queue.delete("no-such-receipt")
    with pytest.raises(InvalidReceiptError):
        queue.change_visibility("no-such-receipt", 5.0)


def test_receipt_is_invalid_after_delete(clock):
    queue = InMemoryQueue(clock=clock)
    queue.send("job")
    [message] = queue.receive()
    queue.delete(message.receipt)

    with pytest.raises(InvalidReceiptError):
        queue.delete(message.receipt)


def test_message_moves_to_dead_letter_after_max_receives(clock):
    max_receives = 3
    dead_letter = InMemoryQueue(clock=clock)
    queue = InMemoryQueue(
        clock=clock,
        visibility_timeout=10.0,
        max_receive_count=max_receives,
        dead_letter=dead_letter,
    )
    queue.send("poison", {"kind": "test"})

    for attempt in range(1, max_receives + 1):
        [message] = queue.receive()
        assert message.receive_count == attempt
        clock.now += 10.0

    assert queue.receive() == []
    [dead] = dead_letter.receive()
    assert dead.body == "poison"
    assert dead.attributes == {"kind": "test"}

    clock.now += 1000.0
    assert queue.receive() == []


def test_max_receive_count_requires_dead_letter(clock):
    with pytest.raises(ValueError):
        InMemoryQueue(clock=clock, max_receive_count=3)


def test_body_and_attributes_round_trip(clock):
    queue = InMemoryQueue(clock=clock)
    attributes = {"trace_id": "trace-0001", "priority": "high"}

    queue.send("The quick brown fox", attributes)
    [message] = queue.receive()

    assert message.body == "The quick brown fox"
    assert message.attributes == attributes


def test_ids_and_receipts_come_from_id_factory(clock):
    queue = InMemoryQueue(clock=clock, visibility_timeout=10.0, id_factory=counter_ids())

    assert queue.send("A") == "id-1"
    assert queue.send("B") == "id-2"

    [a] = queue.receive()
    assert a == Message(message_id="id-1", body="A", receipt="id-3", receive_count=1, attributes={})
    [b] = queue.receive()
    assert (b.message_id, b.receipt) == ("id-2", "id-4")

    clock.now = 10.0
    [a_again, b_again] = queue.receive(max_messages=2)
    assert (a_again.message_id, a_again.receipt) == ("id-1", "id-5")
    assert (b_again.message_id, b_again.receipt) == ("id-2", "id-6")


def test_in_memory_queue_satisfies_queue_protocol(clock):
    queue: Queue = InMemoryQueue(clock=clock, visibility_timeout=10.0)

    message_id = queue.send("job", {"k": "v"})
    [message] = queue.receive(max_messages=1, visibility_timeout=5.0)
    assert message.message_id == message_id
    queue.change_visibility(message.receipt, 20.0)
    clock.now = 5.0
    assert queue.receive() == []
    queue.delete(message.receipt)
    clock.now = 100.0
    assert queue.receive() == []
