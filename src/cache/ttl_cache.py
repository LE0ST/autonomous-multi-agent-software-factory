"""A thread-safe, in-memory TTL cache with least-recently-used eviction.

The cache is intentionally self contained: every entry is held in the memory of
a single :class:`TTLCache` instance.  Nothing is written to disk, nothing is
sent over a network connection, and cache keys or values are never emitted to
standard output, standard error, log records, or exception messages.

Time is measured with :func:`time.monotonic`, which is immune to wall-clock
adjustments.  Callers that want to drive the clock explicitly may pass an
absolute ``now`` value expressed on that same monotonic timeline.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple

__all__ = ["TTLCache"]

#: Monotonic clock used for every TTL computation in this module.
_clock = time.monotonic


def _validate_max_size(value: Any) -> int:
    """Return ``value`` coerced to a positive ``int``.

    Raises :class:`ValueError` when the value is not a strictly positive,
    integral number.  The offending value is never included in the message.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("max_size must be a positive integer")
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError("max_size must be a positive integer")
        value = int(value)
    if value <= 0:
        raise ValueError("max_size must be a positive integer")
    return int(value)


def _validate_ttl(value: Any, name: str) -> float:
    """Return ``value`` coerced to a strictly positive ``float`` TTL.

    Raises :class:`ValueError` for non-numeric, NaN, zero, or negative values.
    ``name`` is always a fixed literal supplied by this module, so no cache key
    or value can ever leak into the resulting message.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive number")
    if isinstance(value, float) and math.isnan(value):
        raise ValueError(f"{name} must be a positive number")
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return float(value)


class TTLCache:
    """A bounded, thread-safe cache whose entries expire after a TTL.

    Entries are ordered from least recently used to most recently used.  A
    successful :meth:`get` refreshes an entry's position, and inserting into a
    full cache evicts the least recently used non-expired entry.

    All mutable state lives inside the instance; no module level mutable state
    exists.  Every public method is guarded by a single re-entrant lock, so
    concurrent ``get``, ``set`` and ``delete`` calls cannot corrupt the cache.
    """

    def __init__(self, max_size: int, default_ttl: float) -> None:
        """Create a cache holding at most ``max_size`` entries.

        ``default_ttl`` is applied when :meth:`set` is called without an
        explicit ``ttl``.  Both arguments must be strictly positive, otherwise
        :class:`ValueError` is raised.
        """
        self._max_size: int = _validate_max_size(max_size)
        self._default_ttl: float = _validate_ttl(default_ttl, "default_ttl")
        # OrderedDict maps key -> (value, absolute expiry on the monotonic clock)
        self._entries: "OrderedDict[Any, Tuple[Any, float]]" = OrderedDict()
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def max_size(self) -> int:
        """Maximum number of entries the cache will retain."""
        return self._max_size

    @property
    def default_ttl(self) -> float:
        """TTL, in seconds, used when :meth:`set` receives no explicit TTL."""
        return self._default_ttl

    def __len__(self) -> int:
        """Return the number of live (non-expired) entries."""
        now = _clock()
        with self._lock:
            self._purge_expired(now)
            return len(self._entries)

    def __contains__(self, key: object) -> bool:
        """Return ``True`` when ``key`` maps to a live, non-expired entry."""
        now = _clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry[1] <= now:
                del self._entries[key]
                return False
            return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set(self, key: str, value: object, ttl: Optional[float] = None) -> None:
        """Store ``value`` under ``key``.

        The entry expires ``ttl`` seconds from now, or ``default_ttl`` seconds
        from now when ``ttl`` is ``None``.  A non-positive ``ttl`` raises
        :class:`ValueError`.  If the cache is full, expired entries are dropped
        first and then the least recently used remaining entry is evicted.
        """
        if ttl is None:
            effective_ttl = self._default_ttl
        else:
            effective_ttl = _validate_ttl(ttl, "ttl")

        now = _clock()
        expires_at = now + effective_ttl

        with self._lock:
            self._entries[key] = (value, expires_at)
            # Assignment alone does not refresh recency on an OrderedDict.
            self._entries.move_to_end(key)
            self._purge_expired(now)
            while len(self._entries) > self._max_size:
                self._entries.popitem(last=False)

    def get(self, key: str, now: Optional[float] = None) -> object:
        """Return the live value stored for ``key``, or ``None``.

        Expired entries are removed and never returned.  A successful lookup
        marks the entry as most recently used.  ``now`` may be supplied to use
        an explicit point on the monotonic timeline instead of the current one.
        """
        current = _clock() if now is None else float(now)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at <= current:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return value

    def delete(self, key: str) -> bool:
        """Remove ``key`` and return ``True`` only if a live entry was removed.

        Missing entries and already-expired entries both yield ``False``; a
        stale entry encountered here is dropped from the internal mapping.
        """
        now = _clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            del self._entries[key]
            return entry[1] > now

    def clear(self) -> None:
        """Remove every entry from the cache."""
        with self._lock:
            self._entries.clear()

    # ------------------------------------------------------------------
    # Internals (callers must already hold the lock)
    # ------------------------------------------------------------------
    def _purge_expired(self, now: float) -> None:
        """Drop every entry whose expiry is at or before ``now``."""
        entries = self._entries
        if not entries:
            return
        expired = [key for key, entry in entries.items() if entry[1] <= now]
        for key in expired:
            del entries[key]
