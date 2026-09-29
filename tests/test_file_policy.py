"""Unit tests for scripts/file_policy.py: filesystem protection and model file write policy."""

import os
import stat
import pytest
from pathlib import Path

from scripts.file_policy import (
    normalize_relative_path,
    matches_any_pattern,
    validate_file_scope,
    checked_destination,
    safe_atomic_write,
    PROTECTED_ROOT_PATTERNS,
)


def test_normalize_relative_path_valid():
    assert normalize_relative_path("src/auth/validator.py") == "src/auth/validator.py"
    assert normalize_relative_path(r"src\auth\validator.py") == "src/auth/validator.py"
    assert normalize_relative_path("./src/auth/validator.py") == "src/auth/validator.py"


@pytest.mark.parametrize("invalid_path", [
    "",
    None,
    "../evil.py",
    "src/../../evil.py",
    r"src\..\..\evil.py",
    "/etc/passwd",
    "C:/Windows/System32/calc.exe",
    "D:\\secrets.txt",
    "src/foo./bar.py",
    "src/foo /bar.py",
    "CON",
    "con.txt",
    "PRN",
    "prn.py",
    "AUX.py",
    "NUL",
    "com1.txt",
    "lpt9.dat",
    "src/aux/file.py",
    "src/NUL/test.py",
])
def test_normalize_relative_path_invalid_and_devices(invalid_path):
    with pytest.raises(ValueError):
        normalize_relative_path(invalid_path)


@pytest.mark.parametrize("protected", [
    ".git",
    ".git/HEAD",
    ".env",
    ".env.production",
    "apis.txt",
    "orchestrator.py",
    "orchestrator/state_manager.py",
    "scripts/file_policy.py",
    "pyproject.toml",
    "RULES.md",
    "AGENTS.md",
    "conftest.py",
    "tests/conftest.py",
])
def test_validate_file_scope_blocks_protected_infrastructure(protected):
    with pytest.raises(ValueError, match="Protected infrastructure"):
        validate_file_scope(protected, allowed=["**"], forbidden=[])


def test_validate_file_scope_enforces_spec_boundaries():
    allowed = ["src/auth/*.py", "tests/test_auth.py"]
    forbidden = ["src/auth/legacy.py"]

    # Allowed file passes
    assert validate_file_scope("src/auth/login.py", allowed, forbidden) == "src/auth/login.py"

    # Forbidden file rejected
    with pytest.raises(ValueError, match="File strictly forbidden by SPEC"):
        validate_file_scope("src/auth/legacy.py", allowed, forbidden)

    # Outside allowed scope rejected
    with pytest.raises(ValueError, match="File outside allowed scope"):
        validate_file_scope("src/other/module.py", allowed, forbidden)


def test_safe_atomic_write_model_write_success(tmp_path):
    root = tmp_path / "worktree"
    root.mkdir()
    allowed = ["src/math/calc.py"]
    dest = safe_atomic_write(
        root,
        "src/math/calc.py",
        "def add(a, b): return a + b\n",
        allowed=allowed,
        is_model_write=True,
    )
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "def add(a, b): return a + b\n"
    # Ensure no leftover temp files
    assert len(list(dest.parent.glob(".*.tmp.*"))) == 0


def test_safe_atomic_write_model_write_blocks_protected(tmp_path):
    root = tmp_path / "worktree"
    root.mkdir()
    with pytest.raises(ValueError, match="Protected infrastructure"):
        safe_atomic_write(
            root,
            "orchestrator/evil.py",
            "malicious",
            allowed=["orchestrator/**"],
            is_model_write=True,
        )
    assert not (root / "orchestrator" / "evil.py").exists()


def test_safe_atomic_write_trusted_controller_write(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    # Controller writing internal state file (which is a protected path for models)
    dest = safe_atomic_write(
        root,
        "orchestrator/state/state_TASK-01.json",
        '{"status": "RUNNING"}',
        is_model_write=False,
    )
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == '{"status": "RUNNING"}'
    assert len(list(dest.parent.glob(".*.tmp.*"))) == 0


def test_checked_destination_blocks_symlinks_and_reparse(tmp_path):
    root = tmp_path / "worktree"
    root.mkdir()
    src = root / "src"
    src.mkdir()
    target = root / "real.py"
    target.write_text("real")
    link = src / "link.py"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation not permitted in this environment")

    with pytest.raises(ValueError, match="Links and reparse points are forbidden"):
        checked_destination(root, "src/link.py")
