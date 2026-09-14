# TASK-004: Implement a thread-safe in-memory TTL/LRU cache

## 1. Scope and Boundaries
- Allowed files:
  - `src/cache/ttl_cache.py`
  - `tests/test_ttl_cache.py`
- Strictly forbidden files:
  - `orchestrator/`
  - `adapters/`
  - `scripts/`
  - `specs/`
  - `pyproject.toml`
  - `.env`
  - `RULES.md`

## 2. Acceptance Criteria (AC)
- [AC-01] Implement a class `TTLCache` with configurable `max_size: int` and `default_ttl: float`.
- [AC-02] Expose `set(key: str, value: object, ttl: float | None = None) -> None`.
- [AC-03] Expose `get(key: str, now: float | None = None) -> object | None`.
- [AC-04] Entries must expire after their configured TTL and expired values must never be returned.
- [AC-05] When the cache exceeds `max_size`, it must evict the least recently used non-expired entry.
- [AC-06] A successful `get()` must update the entry's recency for LRU eviction purposes.
- [AC-07] Expose `delete(key: str) -> bool`, returning `True` only when an existing entry was removed.
- [AC-08] Expose `clear() -> None`.
- [AC-09] Invalid configuration values (`max_size <= 0`, `default_ttl <= 0`) and non-positive per-entry TTL values must raise `ValueError`.
- [AC-10] The implementation must behave correctly under concurrent `get`, `set`, and `delete` operations from multiple threads.

## 3. Security Invariants (SEC)
- [SEC-01] Cache keys and values must never be written to disk, logs, stdout, stderr, or exception messages.
- [SEC-02] The implementation must not use external persistence, network access, subprocesses, `eval`, or `exec`.
- [SEC-03] All mutable cache state must be encapsulated inside the `TTLCache` instance; no global mutable state is allowed.
- [SEC-04] Concurrent access must not corrupt internal state or raise race-condition-related exceptions.

## 4. Required Test Matrix (TEST)
- [TEST-01] Verify basic `set()` and `get()` behavior. (Covers: [AC-01], [AC-02], [AC-03])
- [TEST-02] Verify that expired entries return `None` and no longer affect cache behavior. (Covers: [AC-04])
- [TEST-03] Verify LRU eviction when `max_size` is exceeded. (Covers: [AC-05])
- [TEST-04] Verify that `get()` refreshes recency and changes which entry is evicted next. (Covers: [AC-06])
- [TEST-05] Verify `delete()` return semantics and `clear()` behavior. (Covers: [AC-07], [AC-08])
- [TEST-06] Verify invalid constructor and TTL arguments raise `ValueError`. (Covers: [AC-09])
- [TEST-07] Execute concurrent reads, writes, and deletions from multiple threads and verify internal state remains valid without unexpected exceptions. (Covers: [AC-10], [SEC-03], [SEC-04])
- [TEST-08] Verify keys and values are never emitted through stdout, stderr, logs, or persisted to disk. (Covers: [SEC-01])
- [TEST-09] Verify the implementation does not use network access, subprocesses, external persistence, `eval`, or `exec`. (Covers: [SEC-02])