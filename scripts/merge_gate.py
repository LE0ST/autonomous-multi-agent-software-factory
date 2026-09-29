#!/usr/bin/env python3
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

def execute_fast_forward_merge(
    repo_dir: Path,
    expected_base_sha: str,
    candidate_sha: str,
    base_branch: str = "dev"
) -> tuple[bool, str]:
    # 1. Verify C descends from B
    ancestor_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", expected_base_sha, candidate_sha],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if ancestor_check.returncode != 0:
        return False, (
            f"TREE DIVERGENCE DETECTED: {expected_base_sha} is not an ancestor of {candidate_sha}.\n"
        )

    # 2 & 3. Atomically update refs/heads/dev: B -> C (fails if dev != B)
    merge_res = subprocess.run(
        ["git", "update-ref", "-m", f"Fast-forward merge to {candidate_sha}", f"refs/heads/{base_branch}", candidate_sha, expected_base_sha],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if merge_res.returncode != 0:
        return False, f"Fast-Forward merge failed (concurrent modification detected or base drifted): {merge_res.stderr.strip()}"

    # Ref integration deliberately leaves working-tree synchronization to its owner.
    return True, f"Successful Fast-Forward merge of '{candidate_sha}' into '{base_branch}'."

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python scripts/merge_gate.py <expected_base_sha> <candidate_sha> [base_branch]")
        sys.exit(1)

    expected_base_sha = sys.argv[1]
    candidate_sha = sys.argv[2]
    base_branch = sys.argv[3] if len(sys.argv) > 3 else "dev"
    root_dir = Path.cwd()

    passed, msg = execute_fast_forward_merge(root_dir, expected_base_sha, candidate_sha, base_branch)
    print(f"[{'PASS' if passed else 'FAIL'}] Merge Gate: {msg}")
    sys.exit(0 if passed else 1)
