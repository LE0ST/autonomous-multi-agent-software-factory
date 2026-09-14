"""Tests for the thread-safe in-memory TTL/LRU cache (TASK-004)."""

from __future__ import annotations

import inspect
import logging
import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:  # pragma: no cover - import shape depends on repository layout
    from src.cache.ttl_cache import TTLCache
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from cache.ttl_cache import TTLCache


def _module():
    """Return the imported cache module object."""
    return sys.modules[TTLCache.__module__]


# ----------------------------------------------------------------------
# TEST-01 (AC-01, AC-02, AC-03)
# ----------------------------------------------------------------------
def test_basic_set_and_get():
    cache = TTLCache(max_size=2, default_ttl=60.0)

    assert cache.max_size == 2
    assert cache.default_ttl == 60.0

    assert cache.get("missing") is None

    cache.set("a", 1)
    assert cache.get("a") == 1

    payload = {"nested": [1, 2, 3]}
    cache.set("b", payload)
    assert cache.get("b") == payload

    cache.set("a", 42)
    assert cache.get("a") == 42
    assert len(cache) == 2

    assert "a" in cache
    assert "missing" not in cache


def test_default_ttl_accepts_int_and_explicit_ttl_override():
    cache = TTLCache(max_size=5, default_ttl=30)
    assert cache.default_ttl == 30.0

    cache.set("k", "v", ttl=0.5)
    assert cache.get("k") == "v"


# ----------------------------------------------------------------------
# TEST-02 (AC-04)
# ----------------------------------------------------------------------
def test_expired_entries_return_none_and_do_not_affect_cache():
    cache = TTLCache(max_size=2, default_ttl=0.05)
    cache.set("a", 1)
    assert cache.get("a") == 1

    time.sleep(0.12)

    assert cache.get("a") is None
    assert "a" not in cache
    assert len(cache) == 0

    # The expired entry must not consume capacity.
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_expiry_with_explicit_clock():
    cache = TTLCache(max_size=4, default_ttl=10.0)
    cache.set("x", "value")
    start = time.monotonic()

    assert cache.get("x", now=start + 5.0) == "value"
    # Reading does not extend the lifetime of an entry.
    assert cache.get("x", now=start + 9.99) == "value"
    assert cache.get("x", now=start + 10.0) is None
    assert cache.get("x", now=start + 100.0) is None
    assert len(cache) == 0


# ----------------------------------------------------------------------
# TEST-03 (AC-05)
# ----------------------------------------------------------------------
def test_lru_eviction_when_max_size_exceeded():
    cache = TTLCache(max_size=3, default_ttl=60.0)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    cache.set("d", 4)

    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert cache.get("d") == 4
    assert len(cache) == 3

    cache.set("e", 5)
    assert cache.get("b") is None
    assert sorted(["c", "d", "e"]) == ["c", "d", "e"]
    assert cache.get("c") == 3
    assert cache.get("d") == 4
    assert cache.get("e") == 5


def test_eviction_skips_expired_entries():
    cache = TTLCache(max_size=2, default_ttl=60.0)
    cache.set("stale", "value", ttl=0.02)
    cache.set("live", "value")

    time.sleep(0.05)

    cache.set("fresh", "value")

    assert cache.get("stale") is None
    assert cache.get("live") == "value"
    assert cache.get("fresh") == "value"
    assert len(cache) == 2


def test_overwrite_existing_key_does_not_grow_cache():
    cache = TTLCache(max_size=2, default_ttl=60.0)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("a", 11)
    cache.set("b", 22)

    assert len(cache) == 2
    assert cache.get("a") == 11
    assert cache.get("b") == 22


# ----------------------------------------------------------------------
# TEST-04 (AC-06)
# ----------------------------------------------------------------------
def test_get_refreshes_recency_and_changes_next_eviction():
    cache = TTLCache(max_size=3, default_ttl=60.0)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    # Refresh "a" so that "b" becomes the least recently used entry.
    assert cache.get("a") == 1

    cache.set("d", 4)

    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert cache.get("d") == 4


def test_repeated_reads_keep_entry_alive_longest():
    cache = TTLCache(max_size=2, default_ttl=60.0)
    cache.set("hot", 1)
    cache.set("cold", 2)

    for _ in range(5):
        assert cache.get("hot") == 1

    cache.set("new", 3)

    assert cache.get("cold") is None
    assert cache.get("hot") == 1
    assert cache.get("new") == 3


# ----------------------------------------------------------------------
# TEST-05 (AC-07, AC-08)
# ----------------------------------------------------------------------
def test_delete_return_semantics():
    cache = TTLCache(max_size=4, default_ttl=60.0)
    cache.set("a", 1)

    assert cache.delete("a") is True
    assert cache.get("a") is None
    assert cache.delete("a") is False
    assert cache.delete("never-stored") is False

    cache.set("b", 2, ttl=0.02)
    time.sleep(0.05)
    assert cache.delete("b") is False
    assert len(cache) == 0


def test_clear_removes_everything():
    cache = TTLCache(max_size=4, default_ttl=60.0)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert len(cache) == 3

    assert cache.clear() is None

    assert len(cache) == 0
    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.get("c") is None

    # The cache stays usable after being cleared.
    cache.set("d", 4)
    assert cache.get("d") == 4


# ----------------------------------------------------------------------
# TEST-06 (AC-09)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("max_size", [0, -1, -100])
def test_invalid_max_size_raises_value_error(max_size):
    with pytest.raises(ValueError):
        TTLCache(max_size=max_size, default_ttl=1.0)


@pytest.mark.parametrize("default_ttl", [0, -0.5, -10])
def test_invalid_default_ttl_raises_value_error(default_ttl):
    with pytest.raises(ValueError):
        TTLCache(max_size=1, default_ttl=default_ttl)


@pytest.mark.parametrize("bad_type", [None, "5", object()])
def test_non_numeric_configuration_raises_value_error(bad_type):
    with pytest.raises(ValueError):
        TTLCache(max_size=bad_type, default_ttl=1.0)
    with pytest.raises(ValueError):
        TTLCache(max_size=1, default_ttl=bad_type)


@pytest.mark.parametrize("ttl", [0, -1, -0.25])
def test_non_positive_per_entry_ttl_raises_value_error(ttl):
    cache = TTLCache(max_size=2, default_ttl=60.0)
    with pytest.raises(ValueError):
        cache.set("key", "value", ttl=ttl)


def test_invalid_arguments_do_not_corrupt_state():
    cache = TTLCache(max_size=2, default_ttl=60.0)
    cache.set("keep", "value")

    with pytest.raises(ValueError):
        cache.set("rejected", "value", ttl=-1)

    assert cache.get("rejected") is None
    assert cache.get("keep") == "value"
    assert len(cache) == 1


# ----------------------------------------------------------------------
# TEST-07 (AC-10, SEC-03, SEC-04)
# ----------------------------------------------------------------------
def test_concurrent_get_set_delete_keeps_state_consistent():
    max_size = 32
    cache = TTLCache(max_size=max_size, default_ttl=0.5)
    thread_count = 8
    barrier = threading.Barrier(thread_count)
    errors = []
    errors_lock = threading.Lock()

    def worker(worker_id):
        try:
            barrier.wait(timeout=10)
            deadline = time.monotonic() + 0.75
            i = 0
            while time.monotonic() < deadline:
                key = "key-%d-%d" % (worker_id, i % 16)
                if i % 5 == 0:
                    cache.delete(key)
                elif i % 5 == 1:
                    cache.clear()
                else:
                    cache.set(key, i, ttl=0.02 + (i % 7) * 0.01)

                value = cache.get(key)
                if value is not None:
                    assert isinstance(value, int)
                other = "key-%d-%d" % ((worker_id + 1) % thread_count, i % 16)
                cache.get(other)
                assert key not in cache or cache.get(key) is not None
                i += 1
        except BaseException as exc:  # pragma: no cover - failure path
            with errors_lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []

    # Internal invariants must still hold after the concurrent storm.
    assert len(cache) <= max_size
    cache._purge_expired(time.monotonic())
    assert len(cache._entries) <= max_size
    for key, entry in cache._entries.items():
        assert isinstance(key, str)
        assert isinstance(entry, tuple) and len(entry) == 2
        value, expires_at = entry
        assert isinstance(expires_at, float)
        assert expires_at > time.monotonic()


def test_concurrent_readers_do_not_observe_expired_values():
    cache = TTLCache(max_size=8, default_ttl=0.03)
    errors = []

    def writer():
        try:
            for i in range(200):
                cache.set("k-%d" % (i % 8), i, ttl=0.01)
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    def reader():
        try:
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                value = cache.get("k-%d" % (int(time.monotonic() * 1000) % 8))
                assert value is None or isinstance(value, int)
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(2)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(cache) <= 8


# ----------------------------------------------------------------------
# TEST-08 (SEC-01)
# ----------------------------------------------------------------------
def test_keys_and_values_never_leak_to_stdio_logs_or_disk(tmp_path, monkeypatch, capsys, caplog):
    secret_key = "SUPER-SECRET-KEY-9f3a"
    secret_value = "SUPER-SECRET-VALUE-4b7c"
    secret_ttl_key = "TTL-SECRET-KEY-1a2b"

    monkeypatch.chdir(tmp_path)
    cache = TTLCache(max_size=2, default_ttl=60.0)

    with caplog.at_level(logging.DEBUG):
        cache.set(secret_key, secret_value)
        assert cache.get(secret_key) == secret_value
        cache.set(secret_ttl_key, secret_value, ttl=0.01)
        time.sleep(0.03)
        assert cache.get(secret_ttl_key) is None
        assert cache.delete(secret_key) is True
        assert cache.delete(secret_key) is False
        cache.clear()

        with pytest.raises(ValueError) as excinfo:
            cache.set(secret_key, secret_value, ttl=-1)
        assert secret_key not in str(excinfo.value)
        assert secret_value not in str(excinfo.value)

        with pytest.raises(ValueError) as excinfo:
            TTLCache(max_size=0, default_ttl=1.0)
        assert secret_key not in str(excinfo.value)
        assert secret_value not in str(excinfo.value)

    captured = capsys.readouterr()
    assert secret_key not in captured.out
    assert secret_value not in captured.out
    assert secret_key not in captured.err
    assert secret_value not in captured.err

    for record in caplog.records:
        message = record.getMessage()
        assert secret_key not in message
        assert secret_value not in message
        if record.args:
            assert secret_key not in str(record.args)
            assert secret_value not in str(record.args)

    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []


# ----------------------------------------------------------------------
# TEST-09 (SEC-02)
# ----------------------------------------------------------------------
def test_implementation_has_no_network_subprocess_persistence_or_dynamic_code():
    module = _module()
    source = inspect.getsource(module)
    lowered = source.lower()

    forbidden_modules = (
        "subprocess",
        "socket",
        "urllib",
        "http.client",
        "httplib",
        "requests",
        "pickle",
        "shelve",
        "sqlite3",
        "dbm",
        "tempfile",
        "pathlib",
        "shutil",
        "os.system",
        "os.popen",
        "os.fork",
    )
    for token in forbidden_modules:
        assert token not in lowered, "forbidden token in cache module: %s" % token

    forbidden_calls = ("eval(", "exec(", "compile(", "__import__(", "open(", "print(", "input(")
    for token in forbidden_calls:
        assert token not in lowered, "forbidden call in cache module: %s" % token

    module_file = Path(inspect.getfile(module)).resolve()
    assert module_file == (PROJECT_ROOT / "src" / "cache" / "ttl_cache.py").resolve()


def test_no_global_mutable_state_is_shared_between_instances():
    module = _module()
    mutable_globals = [
        name
        for name, value in vars(module).items()
        if isinstance(value, (dict, list, set, bytearray)) and not name.startswith("__")
    ]
    assert mutable_globals == []

    first = TTLCache(max_size=2, default_ttl=60.0)
    second = TTLCache(max_size=2, default_ttl=60.0)
    first.set("shared", "first")
    second.set("shared", "second")

    assert first.get("shared") == "first"
    assert second.get("shared") == "second"
