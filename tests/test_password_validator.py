"""Tests for :mod:`src.auth.password_validator`."""

from __future__ import annotations

import contextlib
import io
import unittest.mock

import pytest

from src.auth.password_validator import validate_password


def _capture_output(callable_obj, *args, **kwargs):
    """Run *callable_obj* while capturing stdout/stderr.

    Returns a tuple of ``(result, stdout_value, stderr_value)``.
    """
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(
        stderr_buffer
    ):
        result = callable_obj(*args, **kwargs)
    return result, stdout_buffer.getvalue(), stderr_buffer.getvalue()


# --- [TEST-01] rejection cases -------------------------------------------


@pytest.mark.parametrize(
    "password",
    [
        "",
        None,
        "short1A",
        "abc12",
        "12345",
        "abcdefgh",
        "12345678",
        "onlyletters",
        "1234567890",
        "aBcDeFgH",
        "!@#$%^&*",
    ],
)
def test_rejects_invalid_passwords(password):
    """[TEST-01] Reject empty, too-short and single-class passwords."""
    result, stdout_value, stderr_value = _capture_output(
        validate_password, password
    )

    assert result is False
    assert stdout_value == ""
    assert stderr_value == ""


# --- [TEST-02] acceptance & secrecy --------------------------------------


@pytest.mark.parametrize(
    "password",
    [
        "password1",
        "Passw0rd",
        "abcdefg1",
        "1abcdefg",
        "a1bcdefg",
        "Abcdefg1!",
        "correcthorse1",
    ],
)
def test_accepts_valid_passwords(password):
    """[TEST-02] Accept passwords meeting the minimum policy."""
    result, stdout_value, stderr_value = _capture_output(
        validate_password, password
    )

    assert result is True
    assert stdout_value == ""
    assert stderr_value == ""


def test_valid_password_produces_no_output():
    """[TEST-02] A valid call must not emit anything on stdout/stderr."""
    password = "password1"
    result, stdout_value, stderr_value = _capture_output(
        validate_password, password
    )

    assert result is True
    assert password not in stdout_value
    assert password not in stderr_value


def test_invalid_password_produces_no_output():
    """[TEST-01] An invalid call must not leak the password anywhere."""
    password = "short"
    result, stdout_value, stderr_value = _capture_output(
        validate_password, password
    )

    assert result is False
    assert password not in stdout_value
    assert password not in stderr_value


def test_does_not_persist_password(tmp_path, monkeypatch):
    """[TEST-02] Validation must not persist the password to disk."""
    password = "supersecret1"
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    # Redirect common write targets into an isolated sandbox so any attempt
    # to persist the password would be observable.
    monkeypatch.chdir(sandbox)

    validate_password(password)

    persisted = list(sandbox.rglob("*"))
    for path in persisted:
        if path.is_file():
            contents = path.read_bytes()
            assert password.encode() not in contents


def test_does_not_call_logging(monkeypatch):
    """[TEST-02] Validation should not invoke logging with the password."""
    captured = []

    def _record(*args, **kwargs):
        captured.append((args, kwargs))

    monkeypatch.setattr("logging.Logger.info", _record, raising=False)
    monkeypatch.setattr("logging.Logger.debug", _record, raising=False)
    monkeypatch.setattr("logging.Logger.warning", _record, raising=False)
    monkeypatch.setattr("logging.Logger.error", _record, raising=False)

    password = "password1"
    validate_password(password)

    for args, kwargs in captured:
        for value in args:
            assert password not in str(value)
        for value in kwargs.values():
            assert password not in str(value)


def test_no_print_called(monkeypatch):
    """[TEST-02] Validation must never call ``print``."""
    calls = []

    def _fake_print(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("builtins.print", _fake_print)

    validate_password("password1")
    validate_password("bad")

    assert calls == []


def test_return_type_is_bool():
    """[AC-01] The result must always be a plain ``bool``."""
    assert isinstance(validate_password("password1"), bool)
    assert isinstance(validate_password(""), bool)
