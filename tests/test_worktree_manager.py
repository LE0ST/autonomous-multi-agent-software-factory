"""Regression coverage for preserving worktrees on invalid or failed cleanup."""

import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import worktree_manager as manager


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        check=True, timeout=30,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-b", "dev")
    git(tmp_path, "config", "user.name", "Worktree Tests")
    git(tmp_path, "config", "user.email", "worktrees@example.invalid")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / ".gitignore").write_text(".worktrees/\n", encoding="utf-8")
    (tmp_path / "feature.py").write_text("value = 1\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "initial")
    return tmp_path


def create(repo, task_id="TASK-001"):
    success, value = manager.create_worktree(repo, task_id)
    assert success, value
    return Path(value)


@pytest.mark.parametrize("task_id", [
    "", "../victim", "x/../../victim", r"x\..\..\victim", "C:/victim",
    "bad:name", "bad name", "-option", "a" * 129, None,
])
def test_invalid_identifier_never_invokes_git_or_deletes(tmp_path, monkeypatch, task_id):
    victim = tmp_path / "victim"
    victim.mkdir()
    marker = victim / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("Git must not run for invalid identifiers")

    monkeypatch.setattr(manager.subprocess, "run", forbidden)
    assert manager.create_worktree(tmp_path, task_id)[0] is False
    assert manager.remove_worktree(tmp_path, task_id, force=True)[0] is False
    assert marker.read_text(encoding="utf-8") == "keep"


def test_second_creation_preserves_live_dirty_worktree(repo):
    target = create(repo)
    marker = target / "uncommitted.txt"
    marker.write_text("in-progress work", encoding="utf-8")
    result, message = manager.create_worktree(repo, "TASK-001")
    assert result is False
    assert "recovery" in message
    assert marker.read_text(encoding="utf-8") == "in-progress work"
    assert git(target, "branch", "--show-current") == "task/TASK-001"


def test_creation_does_not_reuse_old_task_branch(repo):
    git(repo, "branch", "task/TASK-001")
    result, message = manager.create_worktree(repo, "TASK-001")
    assert result is False
    assert "already exists" in message
    assert not (repo / ".worktrees" / "wt_TASK-001").exists()


def test_unregistered_directory_is_never_removed_even_with_force(repo):
    target = repo / ".worktrees" / "wt_TASK-001"
    target.mkdir(parents=True)
    marker = target / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    result, message = manager.remove_worktree(repo, "TASK-001", force=True)
    assert result is False
    assert "not a Git worktree owned" in message
    assert marker.read_text(encoding="utf-8") == "keep"


def test_registered_worktree_on_different_branch_is_preserved(repo):
    target = create(repo)
    git(target, "checkout", "-b", "unrelated")
    result, message = manager.remove_worktree(repo, "TASK-001", force=True)
    assert result is False
    assert "not a Git worktree owned" in message
    assert target.exists()


def test_locked_worktree_is_preserved_even_with_force(repo):
    target = create(repo)
    git(repo, "worktree", "lock", str(target))
    result, message = manager.remove_worktree(repo, "TASK-001", force=True)
    assert result is False
    assert "locked" in message
    assert target.exists()


def test_dirty_worktree_requires_explicit_force(repo):
    target = create(repo)
    marker = target / "new.py"
    marker.write_text("value = 2\n", encoding="utf-8")
    result, message = manager.remove_worktree(repo, "TASK-001")
    assert result is False
    assert "uncommitted" in message
    assert marker.exists()
    result, message = manager.remove_worktree(repo, "TASK-001", force=True)
    assert result is True, message
    assert not target.exists()
    assert git(repo, "rev-parse", "--verify", "refs/heads/task/TASK-001")


def test_clean_cleanup_keeps_branch_and_unregisters_worktree(repo):
    target = create(repo)
    result, message = manager.remove_worktree(repo, "TASK-001")
    assert result is True, message
    assert not target.exists()
    assert "wt_TASK-001" not in git(repo, "worktree", "list", "--porcelain")
    assert git(repo, "rev-parse", "--verify", "refs/heads/task/TASK-001")


def test_unmerged_branch_deletion_preserves_worktree_and_commit(repo):
    target = create(repo)
    (target / "feature.py").write_text("value = 2\n", encoding="utf-8")
    git(target, "add", ".")
    git(target, "commit", "-m", "unmerged work")
    head = git(target, "rev-parse", "HEAD")
    result, message = manager.remove_worktree(repo, "TASK-001", delete_branch=True)
    assert result is False
    assert target.exists()
    assert git(repo, "rev-parse", "task/TASK-001") == head


def test_merged_branch_can_be_deleted(repo):
    target = create(repo)
    result, message = manager.remove_worktree(repo, "TASK-001", delete_branch=True)
    assert result is True, message
    assert not target.exists()
    assert not git(repo, "branch", "--list", "task/TASK-001")


@pytest.mark.parametrize("redirect_parent", [False, True])
def test_reparse_point_rejected_before_git(tmp_path, monkeypatch, redirect_parent):
    parent = tmp_path / ".worktrees"
    target = parent / "wt_TASK-001"
    target.mkdir(parents=True)
    redirect = parent if redirect_parent else target
    real_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        if path == redirect:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR,
                st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
            )
        return real_lstat(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Git must not run for a redirected worktree")

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    monkeypatch.setattr(manager.subprocess, "run", forbidden)
    success, message = manager.remove_worktree(tmp_path, "TASK-001", force=True)
    assert success is False
    assert "reparse" in message


def test_git_removal_failure_preserves_files_and_branch(repo, monkeypatch):
    target = create(repo)
    original_run = manager.subprocess.run
    removal_calls = []

    def failed_remove(command, **kwargs):
        if command[1:3] == ["worktree", "remove"]:
            removal_calls.append(command)
            return subprocess.CompletedProcess(command, 128, "", "file is locked")
        return original_run(command, **kwargs)

    monkeypatch.setattr(manager.subprocess, "run", failed_remove)
    result, message = manager.remove_worktree(repo, "TASK-001")
    assert result is False
    assert "file is locked" in message
    assert len(removal_calls) == 3
    assert (target / "feature.py").exists()
    assert git(repo, "rev-parse", "--verify", "task/TASK-001")


def test_git_timeout_fails_closed_before_cleanup(repo, monkeypatch):
    target = create(repo)

    def timeout(command, **kwargs):
        assert kwargs["timeout"] == manager.GIT_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(manager.subprocess, "run", timeout)
    success, message = manager.remove_worktree(repo, "TASK-001")
    assert success is False
    assert "timed out" in message
    assert (target / "feature.py").exists()
