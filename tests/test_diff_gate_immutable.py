import os
import pytest
import subprocess
from pathlib import Path
from scripts.diff_gate import validate_diff

def test_diff_gate_uses_immutable_git_objects(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    subprocess.run(["git", "init"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root)

    (repo_root / "allowed.py").write_text("print('base')")
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "Base"], cwd=repo_root, check=True)
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    (repo_root / "allowed.py").write_text("print('candidate')")
    (repo_root / "forbidden.py").write_text("print('candidate')")
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "Candidate"], cwd=repo_root, check=True)
    candidate_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    # Write a spec file
    spec_path = tmp_path / "SPEC.md"
    spec_path.write_text("""
# TASK-001

## 1. Scope and Boundaries
- Allowed files:
  - `allowed.py`
- Strictly forbidden files:
  - `forbidden.py`
    """, encoding="utf-8")

    # Validate diff (it should fail because forbidden.py was modified)
    passed, report = validate_diff(repo_root, base_sha, candidate_sha, spec_path)
    assert passed is False
    assert "forbidden.py" in report["violations"][0]

    # 1. Test that moving a branch doesn't trick the diff gate
    # We move candidate_sha back to base_sha using a branch name (if diff gate used branch names)
    subprocess.run(["git", "branch", "dev", candidate_sha], cwd=repo_root, check=True)
    subprocess.run(["git", "reset", "--hard", base_sha], cwd=repo_root, check=True)

    # Validate diff again with exact SHAs. It should still fail, because the SHAs point to the exact objects.
    passed, report = validate_diff(repo_root, base_sha, candidate_sha, spec_path)
    assert passed is False
    assert "forbidden.py" in report["violations"][0]

    # 2. .gitattributes transformations bypass attempt
    # Diff gate should use exactly the objects, bypassing local transformations
    (repo_root / ".gitattributes").write_text("* -diff\\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "Attrs"], cwd=repo_root, check=True)

    passed, report = validate_diff(repo_root, base_sha, candidate_sha, spec_path)
    # the diff output should still report forbidden.py since we use low level flags
    assert passed is False
    assert "forbidden.py" in report["violations"][0]
