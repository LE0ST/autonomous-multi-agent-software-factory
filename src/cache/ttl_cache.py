"""Thread-safe in-memory TTL cache with least-recently-used eviction.

Design notes
------------
* Every entry lives in process memory only.  Keys and values are never
  logged, printed, embedded in exception messages or written to any kind of
  persistent storage.
* No network, subprocess, dynamic-evaluation (``eval``/``exec``) or external
  persistence facilities are used.
* All mutable state is encapsulated in :class:`TTLCache` instances; the only
  module level globals are immutable constants.
* Every public method acquires a single re-entrant lock, so concurrent
  ``get``/``set``/``delete`` calls can never corrupt the internal state nor
  raise race-condition related exceptions.

Example
-------
>>> cache = TTLCache(max_size=2, default_ttl=5.0)
>>> cache.set("a", 1)
>>> cache.get("a")
1
>>> cache.delete("a")
True
>>> cache.delete("a")
False
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict, namedtuple

__all__ = ("TTLCache",)

# Readings at or above this threshold cannot come from ``time.monotonic()``
# on any realistic platform (that would require more than 31 years of uptime),
# so they are interpreted as wall-clock timestamps supplied by callers that
# pass ``now=time.time()``.  This keeps the ``now`` argument of ``get``
# usable with either clock without ever changing the behaviour for internal
# (monotonic) readings.  Immutable module level constant.
_WALL_CLOCK_THRESHOLD = 1000000000.0

# Internal record: the cached value together with its absolute expiry time.
# The type itself is immutable and contains no module level mutable state.
_Entry = namedtuple("_Entry", ("value", "expires_at"))


def _validate_max_size(value):
    """Return ``value`` as a positive ``int`` or raise :class:`ValueError`."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("max_size must be a positive integer")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("max_size must be a positive integer")
        value = int(value)
    if value <= 0:
        raise ValueError("max_size must be a positive integer")
    return int(value)


def _validate_ttl(value, name):
    """Return ``value`` as a positive ``float`` or raise :class:`ValueError`."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be a positive number of seconds")
    number = float(value)
    if math.isnan(number) or number <= 0.0:
        raise ValueError(name + " must be a positive number of seconds")
    return number


class TTLCache:
    """A bounded, thread-safe, in-memory cache with TTL and LRU eviction.

    Parameters
    ----------
    max_size:
        Maximum number of live entries kept in the cache.  Must be positive.
    default_ttl:
        Lifetime, in seconds, applied to entries stored without an explicit
        ``ttl``.  Must be positive.

    Notes
    -----
    The cache uses ``time.monotonic()`` as its clock, so entries are immune to
    wall-clock adjustments.  ``get`` accepts an explicit ``now`` timestamp to
    allow deterministic expiry checks; wall-clock timestamps are transparently
    mapped onto the internal monotonic timeline.
    """

    __slots__ = (
        "_clock",
        "_default_ttl",
        "_entries",
        "_lock",
        "_max_size",
        "_next_expiry",
        "_wall_clock",
    )

    def __init__(self, max_size=128, default_ttl=60.0):
        self._max_size = _validate_max_size(max_size)
        self._default_ttl = _validate_ttl(default_ttl, "default_ttl")
        self._clock = time.monotonic
        self._wall_clock = time.time
        self._lock = threading.RLock()
        # Ordered from least recently used (index 0) to most recently used.
        self._entries = OrderedDict()
        # Lower bound for the earliest expiry; used to skip pointless scans.
        self._next_expiry = math.inf

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set(self, key, value, ttl=None):
        """Store ``value`` under ``key`` for ``ttl`` seconds.

        When ``ttl`` is ``None`` the cache's ``default_ttl`` is used.  A
        non-positive or non-numeric ``ttl`` raises :class:`ValueError`.
        Storing a key that is already present replaces its value, refreshes
        its lifetime and marks it as the most recently used entry.
        """
        lifetime = self._default_ttl if ttl is None else _validate_ttl(ttl, "ttl")

        with self._lock:
            now = self._clock()
            expires_at = now + lifetime
            self._entries[key] = _Entry(value, expires_at)
            # Re-inserting an existing key keeps its old position, so make
            # sure the fresh entry is moved to the most-recently-used end.
            self._entries.move_to_end(key)
            if expires_at < self._next_expiry:
                self._next_expiry = expires_at
            self._purge_expired(now)
            while len(self._entries) > self._max_size:
                # Every expired entry has just been purged, therefore the
                # least recently used remaining entry is a live one.
                self._entries.popitem(last=False)

    def get(self, key, now=None):
        """Return the live value stored under ``key`` or ``None``.

        Expired entries are removed and reported as ``None``; they are never
        returned.  A successful lookup marks the entry as most recently used.
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._resolve_now(now):
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry.value

    def delete(self, key):
        """Remove ``key`` and return whether a live entry was removed.

        An expired entry is treated as absent, so ``False`` is returned for
        it (the stale record is dropped either way).
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            del self._entries[key]
            return entry.expires_at > self._clock()

    def clear(self):
        """Remove every entry from the cache."""
        with self._lock:
            self._entries.clear()
            self._next_expiry = math.inf

    # ------------------------------------------------------------------
    # Mapping-friendly helpers (never expose values through logging)
    # ------------------------------------------------------------------
    def __contains__(self, key):
        """Return ``True`` only for keys holding a live (non-expired) entry."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry.expires_at <= self._clock():
                del self._entries[key]
                return False
            return True

    def __len__(self):
        """Return the number of live entries."""
        with self._lock:
            self._purge_expired(self._clock())
            return len(self._entries)

    def __iter__(self):
        """Iterate over a snapshot of the live keys."""
        with self._lock:
            self._purge_expired(self._clock())
            return iter(tuple(self._entries))

    # ------------------------------------------------------------------
    # Internals (always called with ``self._lock`` held)
    # ------------------------------------------------------------------
    def _purge_expired(self, now):
        """Drop every entry whose expiry time is at or before ``now``."""
        if now < self._next_expiry:
            # ``_next_expiry`` is never larger than the real minimum expiry,
            # so nothing can be expired at this point.
            return
        entries = self._entries
        expired = [key for key, entry in entries.items() if entry.expires_at <= now]
        for key in expired:
            del entries[key]
        self._next_expiry = min(
            (entry.expires_at for entry in entries.values()), default=math.inf
        )

    def _resolve_now(self, now):
        """Normalise the optional ``now`` argument onto the monotonic clock."""
        current = self._clock()
        if now is None:
            return current
        if isinstance(now, bool) or not isinstance(now, (int, float)):
            raise ValueError("now must be a number of seconds")
        value = float(now)
        if math.isnan(value):
            raise ValueError("now must be a number of seconds")
        if value >= _WALL_CLOCK_THRESHOLD:
            return current + (value - self._wall_clock())
        return value
