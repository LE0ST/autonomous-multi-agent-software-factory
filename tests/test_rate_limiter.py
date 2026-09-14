"""Tests for the in-memory rate limiter."""

from __future__ import annotations

import builtins
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from security.rate_limiter import RateLimiter  # noqa: E402


def test_allows_up_to_limit_and_rejects_next() -> None:
    """TEST-01: requests up to limit allowed; next request rejected."""
    limiter = RateLimiter(max_requests=3, window_seconds=10.0)

    assert limiter.allow("client-a", now=0.0) is True
    assert limiter.allow("client-a", now=0.1) is True
    assert limiter.allow("client-a", now=0.2) is True
    assert limiter.allow("client-a", now=0.3) is False


def test_window_expiry_allows_requests_again() -> None:
    """TEST-02: after window expires, stale state no longer blocks."""
    limiter = RateLimiter(max_requests=2, window_seconds=5.0)

    assert limiter.allow("client-b", now=0.0) is True
    assert limiter.allow("client-b", now=1.0) is True
    assert limiter.allow("client-b", now=2.0) is False

    # At exactly the window boundary the old window has expired.
    assert limiter.allow("client-b", now=5.0) is True
    assert limiter.allow("client-b", now=5.1) is True
    assert limiter.allow("client-b", now=5.2) is False


def test_invalid_configuration_raises_value_error() -> None:
    """TEST-03: invalid max_requests or window_seconds raise ValueError."""
    with pytest.raises(ValueError):
        RateLimiter(max_requests=0, window_seconds=10.0)

    with pytest.raises(ValueError):
        RateLimiter(max_requests=-1, window_seconds=10.0)

    with pytest.raises(ValueError):
        RateLimiter(max_requests=1, window_seconds=0)

    with pytest.raises(ValueError):
        RateLimiter(max_requests=1, window_seconds=-1.0)


def test_client_id_not_emitted(capsys: pytest.CaptureFixture[str]) -> None:
    """TEST-04: client_id never appears on stdout or stderr."""
    secret = "super-secret-client-id-123"
    limiter = RateLimiter(max_requests=1, window_seconds=10.0)

    assert limiter.allow(secret, now=0.0) is True
    assert limiter.allow(secret, now=0.1) is False

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_no_disk_access_during_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    """TEST-04: allow() must not touch the filesystem."""
    secret = "disk-secret-client"
    limiter = RateLimiter(max_requests=1, window_seconds=10.0)

    def guarded_open(*args: object, **kwargs: object) -> None:
        raise AssertionError("filesystem access attempted")

    monkeypatch.setattr(builtins, "open", guarded_open)

    assert limiter.allow(secret, now=0.0) is True
    assert limiter.allow(secret, now=0.1) is False


def test_no_forbidden_constructs_in_source() -> None:
    """TEST-05: no eval/exec/subprocess/network/external persistence."""
    source_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "security"
        / "rate_limiter.py"
    )
    source = source_path.read_text(encoding="utf-8")

    forbidden_tokens = ["eval(", "exec(", "subprocess", "socket", "open("]
    for token in forbidden_tokens:
        assert token not in source, (
            f"forbidden token {token!r} found in rate_limiter.py"
        )
