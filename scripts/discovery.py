#!/usr/bin/env python3
"""
scripts/discovery.py - Deterministic pre-flight checker for Autonomous Multi-Agent Software Factory.
Validates:
1. Python version >= 3.10
2. Git initialized (.git)
3. Existence of base branch (dev)
4. Availability of pytest in environment
Exit 0 if valid, Exit 1 on failure.
"""

import sys
import subprocess
from pathlib import Path

def check_python_version() -> tuple[bool, str]:
    v = sys.version_info
    if v.major == 3 and v.minor >= 10:
        return True, f"Python {v.major}.{v.minor}.{v.micro} meets requirement (>= 3.10)."
    return False, f"Python {v.major}.{v.minor}.{v.micro} does not meet requirement (>= 3.10 required)."

def check_git_initialized(repo_dir: Path) -> tuple[bool, str]:
    res = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if res.returncode == 0 and res.stdout.strip() == "true":
        return True, "Git repository successfully initialized."
    return False, "Directory is not a valid Git repository (.git not found)."

def check_base_branch(repo_dir: Path, base_branch: str = "dev") -> tuple[bool, str]:
    res = subprocess.run(
        ["git", "branch", "--list", base_branch],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if res.returncode == 0 and base_branch in res.stdout:
        return True, f"Base branch '{base_branch}' verified."
    return False, f"Base branch '{base_branch}' does not exist in repository."

def check_pytest_available() -> tuple[bool, str]:
    try:
        import pytest  # noqa: F401
        return True, f"pytest is installed ({pytest.__version__})."
    except ImportError:
        return False, "pytest is not available in Python environment."

def run_discovery(repo_dir: Path, base_branch: str = "dev") -> tuple[bool, list[str]]:
    checks = [
        ("Python Version", check_python_version()),
        ("Git Repository", check_git_initialized(repo_dir)),
        ("Base Branch", check_base_branch(repo_dir, base_branch)),
        ("Pytest Availability", check_pytest_available()),
    ]
    
    all_passed = True
    messages = []
    for name, (passed, msg) in checks:
        status = "PASS" if passed else "FAIL"
        messages.append(f"[{status}] {name}: {msg}")
        if not passed:
            all_passed = False
            
    return all_passed, messages

if __name__ == "__main__":
    repo_path = Path.cwd()
    base_branch = "dev"
    if len(sys.argv) > 1:
        base_branch = sys.argv[1]
        
    passed, logs = run_discovery(repo_path, base_branch)
    for line in logs:
        print(line)
        
    sys.exit(0 if passed else 1)
