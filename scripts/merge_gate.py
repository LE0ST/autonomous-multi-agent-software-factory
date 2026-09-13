#!/usr/bin/env python3
"""
scripts/merge_gate.py - Atomic integration gate with Fast-Forward merge to base branch (dev).
Validates that the repository is clean and executes:
  git checkout <base_branch> && git merge --ff-only task/<task_id>
Exit 0 on success, Exit 1 if fast-forward is not possible or there are uncommitted changes.
"""

import sys
import subprocess
from pathlib import Path

def is_repo_clean(repo_dir: Path) -> tuple[bool, str]:
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    clean = res.returncode == 0 and res.stdout.strip() == ""
    return clean, res.stdout.strip()

def execute_fast_forward_merge(repo_dir: Path, task_id: str, base_branch: str = "dev") -> tuple[bool, str]:
    task_branch = f"task/{task_id}"
    
    # 1. Verify no dirty changes in the main working tree
    clean, dirty_files = is_repo_clean(repo_dir)
    if not clean:
        return False, (
            f"Main repository has uncommitted modifications. Merge aborted.\n"
            f"Detected files:\n{dirty_files}"
        )

    # 2. Checkout base branch
    co_res = subprocess.run(
        ["git", "checkout", base_branch],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if co_res.returncode != 0:
        return False, f"Failed to checkout base branch '{base_branch}': {co_res.stderr.strip()}"

    # 3. Check if base_branch is direct ancestor (condition for Fast-Forward)
    ancestor_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_branch, task_branch],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if ancestor_check.returncode != 0:
        return False, (
            f"TREE DIVERGENCE DETECTED: The branch '{base_branch}' received manual commits "
            f"while the orchestrator was working on '{task_branch}'.\n"
            f"To resolve it safely:\n"
            f"  git checkout {task_branch}\n"
            f"  git rebase {base_branch}\n"
            f"  git checkout {base_branch}\n"
            f"  python scripts/merge_gate.py {task_id} {base_branch}"
        )

    # 4. Execute atomic Fast-Forward merge
    merge_res = subprocess.run(
        ["git", "merge", "--ff-only", task_branch],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if merge_res.returncode != 0:
        return False, f"Fast-Forward merge failed: {merge_res.stderr.strip()}"

    return True, f"Successful Fast-Forward merge of '{task_branch}' into '{base_branch}'."

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/merge_gate.py <task_id> [base_branch]")
        sys.exit(1)
        
    task_id = sys.argv[1]
    base_branch = sys.argv[2] if len(sys.argv) > 2 else "dev"
    root_dir = Path.cwd()
    
    passed, msg = execute_fast_forward_merge(root_dir, task_id, base_branch)
    print(f"[{'PASS' if passed else 'FAIL'}] Merge Gate: {msg}")
    sys.exit(0 if passed else 1)
