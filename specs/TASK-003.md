# TASK-003: Implement an in-memory rate limiter

## 1. Scope and Boundaries
- Allowed files:
  - `src/security/rate_limiter.py`
  - `tests/test_rate_limiter.py`
- Strictly forbidden files:
  - `orchestrator/`
  - `adapters/`
  - `scripts/`
  - `specs/`
  - `pyproject.toml`
  - `.env`
  - `RULES.md`

## 2. Acceptance Criteria (AC)
- [AC-01] Implement a class `RateLimiter` that limits the number of allowed requests per client within a configurable time window.
- [AC-02] The limiter must expose a method `allow(client_id: str, now: float | None = None) -> bool`.
- [AC-03] Requests below or equal to the configured limit within the active window must return `True`; requests exceeding the limit must return `False`.
- [AC-04] After the configured time window expires, the client must be allowed to make requests again and the previous window count must no longer block access.
- [AC-05] Invalid configuration values such as `max_requests <= 0` or `window_seconds <= 0` must raise `ValueError`.

## 3. Security Invariants (SEC)
- [SEC-01] `client_id` values must never be written to disk, logs, stdout, stderr, or exception messages.
- [SEC-02] The implementation must not use `eval`, `exec`, subprocess execution, network access, or external persistence.
- [SEC-03] Internal state must remain encapsulated inside the `RateLimiter` instance and must not rely on global mutable state.

## 4. Required Test Matrix (TEST)
- [TEST-01] Verify that requests up to the configured limit are allowed and the next request inside the same time window is rejected. (Covers: [AC-01], [AC-02], [AC-03], [SEC-03])
- [TEST-02] Verify that once the time window expires, requests are allowed again and stale request state no longer blocks the client. (Covers: [AC-04], [SEC-03])
- [TEST-03] Verify that invalid configuration values raise `ValueError`. (Covers: [AC-05])
- [TEST-04] Verify that `client_id` is never emitted to stdout/stderr and is not persisted to disk. (Covers: [SEC-01])
- [TEST-05] Verify statically or behaviorally that the implementation does not use `eval`, `exec`, subprocesses, network calls, or external persistence. (Covers: [SEC-02])