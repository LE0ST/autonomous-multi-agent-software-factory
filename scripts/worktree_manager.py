#!/usr/bin/env python3
"""Manage task worktrees without destroying unrelated or recoverable files.

Worktrees separate Git indexes, not OS permissions. Callers must serialize task
execution and stop task processes before requesting cleanup.
"""

import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path


GIT_TIMEOUT_SECONDS = 30
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z", re.ASCII)


class WorktreeError(RuntimeError):
    """A Git operation or ownership check failed; preserve the remaining data."""


def _exists(path: Path) -> bool:
    # Unlike Path.exists(), also detect dangling symlinks.
    return os.path.lexists(path)


def _reject_redirect(path: Path) -> None:
    if not _exists(path):
        return
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or (
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise WorktreeError(f"Refusing symlink, junction, or reparse point: {path}")


def get_worktree_path(repo_dir: Path, task_id: str) -> Path:
    """Validate an opaque task identifier before constructing any target path."""
    if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
        raise ValueError("task_id must contain 1-128 ASCII letters, digits, '_' or '-', starting with a letter or digit.")
    root = Path(repo_dir).resolve()
    parent = root / ".worktrees"
    target = parent / f"wt_{task_id}"
    _reject_redirect(parent)
    _reject_redirect(target)
    if target.resolve().parent != parent.resolve():
        raise WorktreeError(f"Worktree path escapes its owned directory: {target}")
    return target


def _git(repo_dir: Path, *args: str, allowed_codes: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo_dir, capture_output=True, text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorktreeError(f"Git operation failed ({args[0]}): {exc}") from exc
    if result.returncode not in allowed_codes:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WorktreeError(f"Git {args[0]} failed (exit {result.returncode}): {detail}")
    return result


def _registrations(repo_dir: Path) -> list[dict[str, str]]:
    result = _git(repo_dir, "worktree", "list", "--porcelain", "-z")
    records = []
    record = {}
    for field in result.stdout.split("\0"):
        if not field:
            if record:
                records.append(record)
                record = {}
            continue
        key, _, value = field.partition(" ")
        record[key] = value
    if record:
        records.append(record)
    return records


def _registration(repo_dir: Path, target: Path) -> dict[str, str] | None:
    expected = os.path.normcase(os.path.abspath(target))
    matches = [
        entry for entry in _registrations(repo_dir)
        if "worktree" in entry
        and os.path.normcase(os.path.abspath(entry["worktree"])) == expected
    ]
    if len(matches) > 1:
        raise WorktreeError(f"Ambiguous Git worktree registration: {target}")
    return matches[0] if matches else None


def _require_owned(repo_dir: Path, task_id: str, target: Path) -> None:
    # Repeat filesystem checks immediately before cleanup. This is not a lease:
    # a privileged concurrent process can still change paths after these checks.
    if get_worktree_path(repo_dir, task_id) != target:
        raise WorktreeError("Worktree path changed during cleanup.")
    entry = _registration(repo_dir, target)
    if entry is None or entry.get("branch") != f"refs/heads/task/{task_id}":
        raise WorktreeError(f"Directory is not a Git worktree owned by task '{task_id}': {target}")
    if "locked" in entry:
        raise WorktreeError(f"Worktree is locked; preserving it: {target}")
    if not target.is_dir():
        raise WorktreeError(f"Registered worktree directory is missing: {target}")
    _reject_redirect(target / ".git")
    common_dir = Path(_git(target, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()).resolve()
    expected_common = Path(_git(repo_dir, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()).resolve()
    branch = _git(target, "symbolic-ref", "--quiet", "HEAD").stdout.strip()
    if common_dir != expected_common or branch != entry["branch"]:
        raise WorktreeError(f"Worktree Git metadata does not match the task registration: {target}")


def create_worktree(repo_dir: Path, task_id: str, base_branch: str = "dev") -> tuple[bool, str]:
    try:
        root = Path(repo_dir).resolve()
        target = get_worktree_path(root, task_id)
        if _exists(target) or _registration(root, target) is not None:
            raise WorktreeError(f"Worktree already exists; explicit recovery is required: {target}")
        if not isinstance(base_branch, str) or not base_branch or base_branch.startswith("-"):
            raise ValueError("base_branch must be a valid branch name.")
        _git(root, "check-ref-format", "--branch", base_branch)
        # Resolve a local branch once so checkout does not follow a moving name.
        base_commit = _git(root, "rev-parse", "--verify", f"refs/heads/{base_branch}^{{commit}}").stdout.strip()
        branch_name = f"task/{task_id}"
        exists = _git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}", allowed_codes=(0, 1))
        if exists.returncode == 0:
            raise WorktreeError(f"Task branch '{branch_name}' already exists; explicit recovery is required.")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Revalidate after mkdir; never recursively remove a failed creation.
        get_worktree_path(root, task_id)
        _git(root, "worktree", "add", "-b", branch_name, str(target), base_commit)
        _require_owned(root, task_id, target)
        return True, str(target)
    except (ValueError, OSError, WorktreeError) as exc:
        return False, str(exc)


def remove_worktree(
    repo_dir: Path, task_id: str, delete_branch: bool = False,
    max_retries: int = 3, *, force: bool = False,
) -> tuple[bool, str]:
    """Remove only the registered task worktree, preserving dirty files by default.

    force=True explicitly permits discarding dirty files, but never permits
    removing an unregistered, redirected, differently owned, or locked target.
    Failed Git cleanup remains available for operator recovery; it never falls
    back to recursive deletion or repository-wide pruning.
    """
    try:
        if type(max_retries) is not int or not 1 <= max_retries <= 3:
            raise ValueError("max_retries must be an integer between 1 and 3.")
        if type(force) is not bool or type(delete_branch) is not bool:
            raise ValueError("force and delete_branch must be boolean values.")
        root = Path(repo_dir).resolve()
        target = get_worktree_path(root, task_id)
        branch_name = f"task/{task_id}"
        for attempt in range(max_retries):
            _require_owned(root, task_id, target)
            status = _git(target, "status", "--porcelain=v1", "--untracked-files=all")
            if status.stdout.strip() and not force:
                raise WorktreeError(f"Worktree has uncommitted files; preserving it: {target}")
            if delete_branch:
                _git(root, "merge-base", "--is-ancestor", f"refs/heads/{branch_name}", "HEAD")
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(target))
            result = _git(root, *args, allowed_codes=(0, 1, 128))
            if result.returncode == 0:
                break
            if attempt == max_retries - 1:
                detail = result.stderr.strip() or result.stdout.strip()
                raise WorktreeError(f"Git worktree removal failed; preserving remaining files: {detail}")
            time.sleep(0.1 * (attempt + 1))
        if _exists(target) or _registration(root, target) is not None:
            raise WorktreeError(f"Git cleanup is incomplete; manual recovery is required: {target}")
        if delete_branch:
            _git(root, "branch", "-d", branch_name)
        return True, f"Worktree for {task_id} successfully removed."
    except (ValueError, OSError, WorktreeError) as exc:
        return False, str(exc)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: worktree_manager.py create <task_id> [base_branch]")
        print("       worktree_manager.py remove <task_id> [--delete-branch] [--force]")
        sys.exit(1)
    action, task_id = sys.argv[1].lower(), sys.argv[2]
    if action == "create":
        success, msg = create_worktree(Path.cwd(), task_id, sys.argv[3] if len(sys.argv) > 3 else "dev")
    elif action == "remove":
        success, msg = remove_worktree(Path.cwd(), task_id, "--delete-branch" in sys.argv, force="--force" in sys.argv)
    else:
        success, msg = False, f"Unknown action: {action}"
    print(f"[{'PASS' if success else 'FAIL'}] {msg}")
    sys.exit(0 if success else 1)
