#!/usr/bin/env python3
"""
scripts/worktree_manager.py - Defensive Git Worktrees manager with robust Windows locking resilience.
Handles file locks (WinError 5 / PermissionError) via retries and read-only attribute stripping.
"""

import os
import sys
import time
import stat
import shutil
import subprocess
from pathlib import Path

def _remove_readonly(func, path, excinfo):
    """Error callback for shutil.rmtree: clears read-only attributes on Windows."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

def get_worktree_path(repo_dir: Path, task_id: str) -> Path:
    return repo_dir / ".worktrees" / f"wt_{task_id}"

def create_worktree(repo_dir: Path, task_id: str, base_branch: str = "dev") -> tuple[bool, str]:
    branch_name = f"task/{task_id}"
    target_path = get_worktree_path(repo_dir, task_id)
    
    if target_path.exists():
        remove_worktree(repo_dir, task_id)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if task branch already exists
    check_branch = subprocess.run(
        ["git", "branch", "--list", branch_name],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    
    if branch_name in check_branch.stdout:
        # If branch exists, attach worktree reusing existing branch
        cmd = ["git", "worktree", "add", str(target_path), branch_name]
    else:
        # If branch does not exist, create branch from base_branch
        cmd = ["git", "worktree", "add", "-b", branch_name, str(target_path), base_branch]
        
    res = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
    if res.returncode == 0:
        return True, str(target_path)
    return False, f"Failed to create worktree: {res.stderr.strip() or res.stdout.strip()}"

def remove_worktree(repo_dir: Path, task_id: str, delete_branch: bool = False, max_retries: int = 3) -> tuple[bool, str]:
    target_path = get_worktree_path(repo_dir, task_id)
    branch_name = f"task/{task_id}"
    
    # 1. Attempt unlinking via git worktree remove
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(target_path)],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    
    # 2. If directory still exists (typical Windows lock), defensive cleanup with backoff retries
    backoff = [0.1, 0.3, 1.0]
    if target_path.exists():
        for attempt in range(max_retries):
            try:
                shutil.rmtree(target_path, onerror=_remove_readonly)
                break
            except (PermissionError, OSError):
                if attempt < len(backoff):
                    time.sleep(backoff[attempt])
                else:
                    time.sleep(1.0)
                    
    # 3. Prune worktrees in git
    subprocess.run(["git", "worktree", "prune"], cwd=repo_dir, capture_output=True, text=True)
    
    # 4. Optionally delete branch
    if delete_branch:
        subprocess.run(["git", "branch", "-D", branch_name], cwd=repo_dir, capture_output=True, text=True)
        
    if target_path.exists():
        return False, f"Could not completely remove worktree directory {target_path} after {max_retries} attempts."
        
    return True, f"Worktree for {task_id} successfully removed."

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python scripts/worktree_manager.py create <task_id> [base_branch]")
        print("  python scripts/worktree_manager.py remove <task_id> [--delete-branch]")
        sys.exit(1)
        
    action = sys.argv[1].lower()
    task_id = sys.argv[2]
    repo_root = Path.cwd()
    
    if action == "create":
        base_branch = sys.argv[3] if len(sys.argv) > 3 else "dev"
        success, msg = create_worktree(repo_root, task_id, base_branch)
        print(f"[{'PASS' if success else 'FAIL'}] {msg}")
        sys.exit(0 if success else 1)
    elif action == "remove":
        delete_branch = "--delete-branch" in sys.argv
        success, msg = remove_worktree(repo_root, task_id, delete_branch)
        print(f"[{'PASS' if success else 'FAIL'}] {msg}")
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
