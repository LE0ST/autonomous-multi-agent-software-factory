"""Validate model-controlled file names before any filesystem side effects.

The controller must exclusively own the worktree while applying a response.
These checks reject existing links; they do not isolate a hostile local process
that can concurrently replace parent directories. Execute code in a sandbox.
"""

import fnmatch
import os
import re
import stat
from pathlib import Path, PureWindowsPath

import time

PROTECTED_ROOT_PATTERNS = [
    ".git", ".git/**", ".git*", ".env*", "apis.txt", ".semgrep*",
    ".bandit", ".coverage*", ".coveragerc", ".github/**", ".agents/**",
    ".codex/**", "pyproject.toml", "package*.json", "pytest.ini", "tox.ini",
    "setup.cfg", "setup.py", "RULES.md", "AGENTS.md", "orchestrator.py",
    "orchestrator/**", "adapters/**", "scripts/**", "specs/**",
]
_DEVICE = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)


def normalize_relative_path(value: str, *, pattern: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("File path must be a nonempty string")
    path = value.replace("\\", "/")
    if path.startswith("/") or PureWindowsPath(path).drive:
        raise ValueError("Absolute and drive-relative paths are forbidden")
    while path.startswith("./"):
        path = path[2:]
    if pattern and path.endswith("/"):
        path += "**"
    for part in path.split("/"):
        invalid = '<>:"|' if pattern else '<>:"|?*'
        if (not part or part in (".", "..") or part.endswith((".", " "))
                or any(ord(c) < 32 or c in invalid for c in part)
                or _DEVICE.match(part)):
            raise ValueError("Invalid or ambiguous relative file path")
    return path


def matches_any_pattern(path: str, patterns: list[str]) -> bool:
    # Be equally restrictive on case-sensitive hosts and Windows.
    return any(fnmatch.fnmatchcase(path.casefold(), p.casefold()) for p in patterns)


def validate_file_scope(
    path: str,
    allowed: list[str] | None = None,
    forbidden: list[str] | None = None,
) -> str:
    path = normalize_relative_path(path)
    allowed_norm = [normalize_relative_path(p, pattern=True) for p in (allowed or [])]
    forbidden_norm = [normalize_relative_path(p, pattern=True) for p in (forbidden or [])]
    parts = path.casefold().split("/")
    if (any(p == ".git" or p.startswith(".env") or p == "conftest.py" for p in parts)
            or matches_any_pattern(path, PROTECTED_ROOT_PATTERNS)):
        raise ValueError(f"Protected infrastructure or governance file: {path}")
    if forbidden_norm and matches_any_pattern(path, forbidden_norm):
        raise ValueError(f"File strictly forbidden by SPEC: {path}")
    if allowed is not None:
        if not allowed_norm or not matches_any_pattern(path, allowed_norm):
            raise ValueError(f"File outside allowed scope: {path}")
    return path


def checked_destination(root: Path, relative: str) -> Path:
    """Reject symlinks, Windows junctions/reparse points, and special files."""
    relative = normalize_relative_path(relative)
    current = root.absolute()
    for component in (None, *relative.split("/")):
        if component is not None:
            current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError("Links and reparse points are forbidden in write paths")
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError("Special filesystem objects are forbidden")
    root_resolved = root.resolve(strict=True)
    if not current.resolve().is_relative_to(root_resolved):
        raise ValueError("File destination escapes worktree")
    return current


def safe_atomic_write(
    root: Path,
    relative_path: str,
    content: str | bytes,
    allowed: list[str] | None = None,
    forbidden: list[str] | None = None,
    *,
    is_model_write: bool = True,
    encoding: str = "utf-8",
) -> Path:
    """Safely and atomically write content to a file inside root.

    If is_model_write is True, enforces validate_file_scope to protect
    infrastructure and enforce spec boundaries.
    If is_model_write is False, validates path normalization and destination bounds
    without checking protected root patterns or spec scope (used for trusted controller writes).
    """
    root = Path(root).resolve()
    if is_model_write:
        clean_rel = validate_file_scope(relative_path, allowed=allowed, forbidden=forbidden)
    else:
        clean_rel = normalize_relative_path(relative_path)

    dest_path = checked_destination(root, clean_rel)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = dest_path.with_name(f".{dest_path.name}.tmp.{os.getpid()}.{time.monotonic_ns()}")
    try:
        if isinstance(content, str):
            tmp_path.write_text(content, encoding=encoding)
        else:
            tmp_path.write_bytes(content)
        os.replace(tmp_path, dest_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return dest_path
