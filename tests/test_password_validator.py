"""Unit tests for :mod:`src.auth.password_validator` (TASK-002)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.auth.password_validator import (  # noqa: E402
    MIN_PASSWORD_LENGTH,
    validate_password,
)


INVALID_PASSWORDS = [
    pytest.param("", id="empty-string"),
    pytest.param("Ab1", id="well-below-minimum-length"),
    pytest.param("Abcdef1", id="one-character-below-minimum"),
    pytest.param("abcdefgh", id="letters-only"),
    pytest.param("12345678", id="digits-only"),
    pytest.param("!!!!!!!!", id="no-letter-and-no-digit"),
    pytest.param("        ", id="whitespace-only"),
]

VALID_PASSWORDS = [
    pytest.param("abcdefg1", id="exactly-minimum-length"),
    pytest.param("SecurePass123", id="mixed-case-with-digits"),
    pytest.param("1a2b3c4d5e", id="leading-digit"),
    pytest.param("p@ssw0rd!x", id="letters-digits-and-symbols"),
]


def _tree_snapshot(root: Path) -> set:
    """Return a snapshot of every entry below ``root``."""
    entries = set()
    for current_dir, dirnames, filenames in os.walk(root):
        for name in dirnames:
            entries.add(Path(current_dir, name))
        for name in filenames:
            entries.add(Path(current_dir, name))
    return entries


# ---------------------------------------------------------------------------
# [TEST-01] Rejection cases (covers AC-01 and SEC-01)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("candidate", INVALID_PASSWORDS)
def test_invalid_passwords_are_rejected(candidate: str) -> None:
    assert validate_password(candidate) is False


def test_empty_password_is_rejected() -> None:
    assert validate_password("") is False


def test_password_below_minimum_length_is_rejected() -> None:
    candidate = "a" * (MIN_PASSWORD_LENGTH - 1) + "1"
    assert len(candidate) < MIN_PASSWORD_LENGTH
    assert validate_password(candidate) is False


def test_password_without_letter_is_rejected() -> None:
    assert validate_password("0" * MIN_PASSWORD_LENGTH) is False


def test_password_without_digit_is_rejected() -> None:
    assert validate_password("x" * MIN_PASSWORD_LENGTH) is False


def test_non_string_input_is_rejected() -> None:
    assert validate_password(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# [TEST-02] Acceptance cases and absence of side effects (covers AC-02, SEC-02)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("candidate", VALID_PASSWORDS)
def test_valid_passwords_are_accepted(candidate: str) -> None:
    assert validate_password(candidate) is True


def test_validator_is_stateless_across_calls() -> None:
    assert validate_password("S3curePass") is True
    assert validate_password("onlyletters") is False
    assert validate_password("S3curePass") is True


def test_validate_password_produces_no_stdout_or_stderr(capsys) -> None:
    validate_password("NoLeakPassword123")
    validate_password("nope")

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""


def test_validate_password_does_not_persist_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    password = "TemporaryPass123"

    before = _tree_snapshot(tmp_path)
    validate_password(password)
    after = _tree_snapshot(tmp_path)

    assert after == before


def test_validate_password_does_not_keep_password_in_module_state() -> None:
    password = "ModuleStatePass123"

    validate_password(password)

    module = sys.modules[validate_password.__module__]
    leaked_attributes = [
        attribute
        for attribute, value in vars(module).items()
        if isinstance(value, str) and password in value
    ]

    assert leaked_attributes == []


def test_validator_does_not_return_the_password() -> None:
    password = "ReturnCheckPass123"

    result = validate_password(password)

    assert result is True
    assert result is not password
