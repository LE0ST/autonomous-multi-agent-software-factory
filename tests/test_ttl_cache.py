"""Tests for the thread-safe TTL/LRU cache (``src/cache/ttl_cache.py``).

The test module covers the full required matrix:
[TEST-01] basic set/get, [TEST-02] expiry, [TEST-03] LRU eviction,
[TEST-04] recency refresh, [TEST-05] delete/clear, [TEST-06] validation,
[TEST-07] concurrency, [TEST-08] no key/value leakage and
[TEST-09] no forbidden facilities.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
import threading
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPO_ROOT / "src", _REPO_ROOT):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))


def _import_cache_module():
    """Import ``src/cache/ttl_cache.py`` independently of the test layout."""
    try:
        import cache.ttl_cache as module  # type: ignore[import-not-found]
        return module
    except ImportError:
        pass

    module_path = _REPO_ROOT / "src" / "cache" / "ttl_cache.py"
    spec = importlib.util.spec_from_file_location("_ttl_cache_under_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_cache_module = _import_cache_module()
TTLCache = _cache_module.TTLCache


# ----------------------------------------------------------------------
# [TEST-01] Basic behaviour (AC-01, AC-02, AC-03)
# ----------------------------------------------------------------------
def test_set_and_get_basic_behavior():
    cache = TTLCache(max_size=4, default_ttl=30.0)

    assert cache.get("missing") is None
    assert cache.get("missing", now=time.monotonic()) is None

    cache.set("alpha", "a")
    cache.set("beta", {"nested": [1, 2, 3]})
    cache.set("gamma", None)

    assert cache.get("alpha") == "a"
    assert cache.get("beta") == {"nested": [1, 2, 3]}
    assert "gamma" in cache
    assert len(cache) == 3

    cache.set("alpha", "updated")
    assert cache.get("alpha") == "updated"
    assert len(cache) == 3


# ----------------------------------------------------------------------
# [TEST-02] Expiry (AC-04)
# ----------------------------------------------------------------------
def test_expired_entries_are_never_returned():
    cache = TTLCache(max_size=8, default_ttl=0.05)

    cache.set("short-lived", "value")
    assert cache.get("short-lived") == "value"

    time.sleep(0.12)
    assert cache.get("short-lived") is None
    assert "short-lived" not in cache
    assert len(cache) == 0

    start = time.monotonic()
    cache.set("explicit", "value", ttl=5.0)
    assert cache.get("explicit", now=start + 4.0) == "value"
    assert cache.get("explicit", now=start + 6.0) is None
    assert cache.get("explicit") is None
    assert len(cache) == 0

    cache.set("far-future", "value", ttl=100.0)
    assert cache.get("far-future", now=time.time() + 10000.0) is None
    assert len(cache) == 0


# ----------------------------------------------------------------------
# [TEST-03] LRU eviction (AC-05)
# ----------------------------------------------------------------------
def test_lru_eviction_when_max_size_exceeded():
    cache = TTLCache(max_size=3, default_ttl=60.0)

    for name in ("a", "b", "c"):
        cache.set(name, name)
    assert len(cache) == 3

    cache.get("a")  # "a" becomes the most recently used entry
    cache.set("d", "d")  # must evict the least recently used entry ("b")

    assert cache.get("b") is None
    assert cache.get("a") == "a"
    assert cache.get("c") == "c"
    assert cache.get("d") == "d"
    assert len(cache) == 3


# ----------------------------------------------------------------------
# [TEST-04] Recency refresh on get (AC-06)
# ----------------------------------------------------------------------
def test_get_refreshes_recency_for_eviction():
    cache = TTLCache(max_size=2, default_ttl=60.0)
    cache.set("old", 1)
    cache.set("new", 2)

    assert cache.get("old") == 1  # "old" is now the most recently used
    cache.set("fresh", 3)  # must evict "new" instead of "old"

    assert cache.get("new") is None
    assert cache.get("old") == 1
    assert cache.get("fresh") == 3

    untouched = TTLCache(max_size=2, default_ttl=60.0)
    untouched.set("old", 1)
    untouched.set("new", 2)
    untouched.set("fresh", 3)  # no refresh happened, evicts "old"

    assert untouched.get("old") is None
    assert untouched.get("new") == 2
    assert untouched.get("fresh") == 3


# ----------------------------------------------------------------------
# [TEST-05] delete()/clear() semantics (AC-07, AC-08)
# ----------------------------------------------------------------------
def test_delete_and_clear_semantics():
    cache = TTLCache(max_size=4, default_ttl=60.0)

    assert cache.delete("never-set") is False
    cache.set("a", 1)
    assert cache.delete("a") is True
    assert cache.delete("a") is False
    assert cache.get("a") is None
    assert len(cache) == 0

    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.clear() is None
    assert len(cache) == 0
    assert cache.get("b") is None
    assert cache.get("c") is None

    # Expired entries count as absent.
    cache.set("expired", 4, ttl=0.05)
    time.sleep(0.12)
    assert cache.delete("expired") is False
    assert len(cache) == 0


# ----------------------------------------------------------------------
# [TEST-06] Configuration validation (AC-09)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("max_size", [0, -1, -25])
def test_invalid_max_size_raises_value_error(max_size):
    with pytest.raises(ValueError):
        TTLCache(max_size=max_size, default_ttl=10.0)


@pytest.mark.parametrize("default_ttl", [0, -1, -0.5])
def test_invalid_default_ttl_raises_value_error(default_ttl):
    with pytest.raises(ValueError):
        TTLCache(max_size=4, default_ttl=default_ttl)


@pytest.mark.parametrize("ttl", [0, -1, -2.5])
def test_invalid_per_entry_ttl_raises_value_error(ttl):
    cache = TTLCache(max_size=4, default_ttl=10.0)

    with pytest.raises(ValueError):
        cache.set("key", "value", ttl=ttl)

    # The failed call must not have stored anything.
    assert cache.get("key") is None
    assert len(cache) == 0


def test_valid_configuration_is_accepted():
    cache = TTLCache(max_size=1, default_ttl=0.001)
    cache.set("key", "value", ttl=0.001)
    assert cache.get("key") == "value"


# ----------------------------------------------------------------------
# [TEST-07] Concurrency (AC-10, SEC-03, SEC-04)
# ----------------------------------------------------------------------
def test_concurrent_get_set_delete_keeps_state_consistent():
    max_size = 32
    worker_count = 8
    iterations = 120
    cache = TTLCache(max_size=max_size, default_ttl=300.0)

    stable_keys = ["stable-%d" % index for index in range(max_size // 2)]
    churn_keys = [
        "key-%d-%d" % (worker, index)
        for worker in range(worker_count)
        for index in range(6)
    ]

    errors = []
    barrier = threading.Barrier(worker_count)

    # Phase 1: concurrent set/get with no deletions, no eviction (the number
    # of distinct live keys is below ``max_size``) and a long TTL, so
    # "key in cache" must imply "cache.get(key) is not None".
    def stable_worker(worker_id):
        try:
            barrier.wait(timeout=30)
            for index in range(iterations):
                key = stable_keys[(worker_id + index) % len(stable_keys)]
                expected = "value-" + key
                cache.set(key, expected)
                assert cache.get(key) is not None
                assert cache.get(key) == expected
                assert len(cache) <= max_size
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [
        threading.Thread(target=stable_worker, args=(worker_id,), daemon=True)
        for worker_id in range(worker_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []

    # Phase 2: concurrent set/get/delete (each worker owns disjoint keys), so
    # eviction and expiry pressure are exercised together with reads.
    def churn_worker(worker_id):
        try:
            barrier.wait(timeout=30)
            own_keys = ["key-%d-%d" % (worker_id, index) for index in range(6)]
            for index in range(iterations):
                key = own_keys[index % len(own_keys)]
                expected = "value-" + key
                cache.set(key, expected)
                observed = cache.get(key)
                assert observed is None or observed == expected
                if index % 3 == 0:
                    assert cache.delete(key) in (True, False)
                if index % 7 == 0:
                    assert len(cache) <= max_size
                if index % 11 == 0:
                    assert (key in cache) in (True, False)
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    churn_threads = [
        threading.Thread(target=churn_worker, args=(worker_id,), daemon=True)
        for worker_id in range(worker_count)
    ]
    for thread in churn_threads:
        thread.start()
    for thread in churn_threads:
        thread.join(timeout=60)

    assert all(not thread.is_alive() for thread in churn_threads)
    assert errors == []

    # Single threaded final consistency check: every key still present must
    # resolve to a value and the size bound must hold.
    assert len(cache) <= max_size
    for key in stable_keys + churn_keys:
        if key in cache:
            assert cache.get(key) is not None


def test_instances_do_not_share_mutable_state():
    first = TTLCache(max_size=2, default_ttl=30.0)
    second = TTLCache(max_size=2, default_ttl=30.0)

    first.set("only-first", "value")
    assert second.get("only-first") is None
    assert len(second) == 0

    second.set("only-second", "value")
    second.clear()

    assert first.get("only-first") == "value"
    assert first.get("only-second") is None


# ----------------------------------------------------------------------
# [TEST-08] No key/value leakage (SEC-01)
# ----------------------------------------------------------------------
def test_keys_and_values_are_never_leaked(capsys, caplog, monkeypatch, tmp_path):
    secret_key = "secret-key-8f3a1c"
    secret_value = "secret-value-91bc7d"

    monkeypatch.chdir(tmp_path)
    cache = TTLCache(max_size=2, default_ttl=5.0)

    with caplog.at_level(logging.DEBUG):
        cache.set(secret_key, secret_value)
        cache.get(secret_key)
        cache.set(secret_key, {"nested": secret_value})
        cache.get(secret_key, now=time.monotonic())
        cache.delete(secret_key)
        cache.set(secret_key, secret_value, ttl=0.01)
        time.sleep(0.03)
        cache.get(secret_key)
        cache.clear()
        with pytest.raises(ValueError) as excinfo:
            cache.set(secret_key, secret_value, ttl=0)
        error_text = str(excinfo.value)

    captured = capsys.readouterr()
    logged = caplog.text

    assert secret_key not in captured.out
    assert secret_key not in captured.err
    assert secret_value not in captured.out
    assert secret_value not in captured.err
    assert secret_key not in logged
    assert secret_value not in logged
    assert secret_key not in error_text
    assert secret_value not in error_text

    # Nothing was persisted to disk either.
    assert list(tmp_path.iterdir()) == []


# ----------------------------------------------------------------------
# [TEST-09] No forbidden facilities / no global mutable state (SEC-02, SEC-03)
# ----------------------------------------------------------------------
_ALLOWED_MODULES = frozenset({"__future__", "collections", "math", "threading", "time"})
_FORBIDDEN_CALLS = frozenset(
    {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"}
)
_FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "Popen",
        "check_call",
        "check_output",
        "connect",
        "create_connection",
        "dump",
        "dumps",
        "fork",
        "popen",
        "spawn",
        "system",
        "urlopen",
        "urlretrieve",
    }
)


def _module_level_assignment_names(tree):
    names = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return names


def test_implementation_avoids_forbidden_facilities():
    source_path = Path(_cache_module.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    imported = set()
    call_names = set()
    attribute_names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                call_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                attribute_names.add(func.attr)

    assert imported <= _ALLOWED_MODULES, "unexpected imports: %s" % (imported - _ALLOWED_MODULES)
    assert call_names & _FORBIDDEN_CALLS == set()
    assert attribute_names & _FORBIDDEN_ATTRIBUTES == set()

    # No mutable module level state: entries only ever live in instances.
    for name in _module_level_assignment_names(tree):
        value = getattr(_cache_module, name, None)
        assert not isinstance(value, (dict, list, set, bytearray)), (
            "mutable module level state: %s" % name
        )
