"""In-memory rate limiter that does not persist client identifiers."""

from __future__ import annotations

import time


class RateLimiter:
    """Limits the number of requests per client within a fixed time window.

    All state is kept in memory. Client identifiers are used only as
    in-memory dictionary keys and are never logged or persisted.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than zero")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero")

        self._max_requests = max_requests
        self._window_seconds = float(window_seconds)
        self._state: dict[str, tuple[float, int]] = {}

    def allow(self, client_id: str, now: float | None = None) -> bool:
        """Return True if the client may make a request, False otherwise.

        Args:
            client_id: Opaque client identifier. It is used only as an
                in-memory key and is never written to disk or logs.
            now: Optional current timestamp in monotonic seconds. If omitted,
                time.monotonic() is used.

        Returns:
            True if the request is within the configured limit for the
            current window, False if the limit has been exceeded.
        """
        if now is None:
            now = time.monotonic()

        entry = self._state.get(client_id)
        if entry is None:
            self._state[client_id] = (now, 1)
            return True

        window_start, count = entry

        if now - window_start >= self._window_seconds:
            self._state[client_id] = (now, 1)
            return True

        if count < self._max_requests:
            self._state[client_id] = (window_start, count + 1)
            return True

        return False
