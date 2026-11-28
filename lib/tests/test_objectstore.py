import pytest
from labkit.objectstore import (
    InMemoryObjectStore,
    ObjectNotFoundError,
    ObjectStore,
    PreconditionFailedError,
)


def test_put_then_get_returns_same_bytes():
    store = InMemoryObjectStore()
    store.put("results/job-1", b"hello")
    assert store.get("results/job-1") == b"hello"


def test_put_without_if_none_match_overwrites():
    store = InMemoryObjectStore()
    store.put("k", b"first")
    store.put("k", b"second")
    assert store.get("k") == b"second"


def test_put_if_none_match_on_existing_key_raises_and_keeps_original():
    store = InMemoryObjectStore()
    store.put("k", b"first")
    with pytest.raises(PreconditionFailedError):
        store.put("k", b"second", if_none_match=True)
    assert store.get("k") == b"first"


def test_put_if_none_match_on_new_key_stores():
    store = InMemoryObjectStore()
    store.put("k", b"first", if_none_match=True)
    assert store.get("k") == b"first"


def test_get_missing_key_raises_object_not_found_which_is_key_error():
    store = InMemoryObjectStore()
    with pytest.raises(ObjectNotFoundError) as excinfo:
        store.get("missing")
    assert isinstance(excinfo.value, KeyError)


def test_exists_before_put_after_put_after_delete():
    store = InMemoryObjectStore()
    assert store.exists("k") is False
    store.put("k", b"v")
    assert store.exists("k") is True
    store.delete("k")
    assert store.exists("k") is False


def test_delete_twice_and_delete_never_stored_raise_nothing():
    store = InMemoryObjectStore()
    store.put("k", b"v")
    store.delete("k")
    store.delete("k")
    store.delete("never-stored")
    assert store.list_keys() == []


def test_list_keys_filters_by_prefix_and_sorts():
    store = InMemoryObjectStore()
    for key in ["jobs/b", "other/x", "jobs/a", "jobsx", "jobs/c"]:
        store.put(key, b"v")
    assert store.list_keys("jobs/") == ["jobs/a", "jobs/b", "jobs/c"]
    assert store.list_keys() == ["jobs/a", "jobs/b", "jobs/c", "jobsx", "other/x"]


def test_put_stores_a_copy_of_the_buffer():
    store = InMemoryObjectStore()
    buf = bytearray(b"original")
    store.put("k", buf)
    buf[:] = b"mutated!"
    assert store.get("k") == b"original"


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.put("", b"v"),
        lambda s: s.get(""),
        lambda s: s.exists(""),
        lambda s: s.delete(""),
    ],
    ids=["put", "get", "exists", "delete"],
)
def test_empty_key_raises_value_error(call):
    store = InMemoryObjectStore()
    with pytest.raises(ValueError):
        call(store)


def test_in_memory_store_satisfies_protocol():
    store: ObjectStore = InMemoryObjectStore()
    store.put("a/1", b"one")
    assert store.get("a/1") == b"one"
    assert store.exists("a/1") is True
    assert store.list_keys("a/") == ["a/1"]
    store.delete("a/1")
    assert store.exists("a/1") is False
    assert store.list_keys() == []
