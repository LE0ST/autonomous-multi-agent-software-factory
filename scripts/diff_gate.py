#!/usr/bin/env python3
"""
scripts/diff_gate.py - Hard boundary enforcement for code modifications.
Checks:
1. modified_files ⊆ allowed_files (defined in SPEC)
2. forbidden_files ∩ modified_files == ∅
3. No critical root infrastructure files modified (pyproject.toml, .env, orchestrator/, scripts/, RULES.md)
Exit 0 if passed, Exit 1 if violations found (dumps report to orchestrator/payloads/diff_violation.json).
"""

import re
import sys
import json
import fnmatch
import subprocess
from pathlib import Path

PROTECTED_ROOT_PATTERNS = [
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    ".env*",
    "apis.txt",
    ".gitignore",
    ".semgrepignore",
    "RULES.md",
    "orchestrator/**",
    "scripts/**",
    "specs/TEMPLATE.md"
]

def normalize_path(p: str) -> str:
    return p.replace("\\", "/").strip().lstrip("./")

def parse_spec_boundaries(spec_path: Path) -> tuple[list[str], list[str]]:
    if not spec_path.exists():
        return [], []
    
    content = spec_path.read_text(encoding="utf-8")
    
    # Extract Section 1. Scope and Boundaries / Alcance y Fronteras
    section1_match = re.search(
        r"##\s+1\.\s+(?:Alcance y Fronteras|Scope and Boundaries)(.*?)(?=##\s+2\.\s+(?:Criterios de Aceptación|Acceptance Criteria)|$)",
        content,
        re.DOTALL | re.IGNORECASE
    )
    if not section1_match:
        return [], []
        
    section1_text = section1_match.group(1)
    
    # Extract allowed files
    allowed = []
    allowed_match = re.search(
        r"-\s+(?:Archivos permitidos|Allowed files):(.*?)(?=-\s+(?:Archivos estrictamente prohibidos|Strictly forbidden files):|$)",
        section1_text,
        re.DOTALL | re.IGNORECASE
    )
    if allowed_match:
        for line in allowed_match.group(1).splitlines():
            # Look for patterns in backticks or bullet text
            m = re.findall(r"`([^`]+)`", line)
            if m:
                allowed.extend([normalize_path(x) for x in m])
            elif line.strip().startswith("-") or line.strip().startswith("*"):
                cleaned = normalize_path(line.strip().lstrip("-* \t"))
                if cleaned:
                    allowed.append(cleaned)

    # Extract forbidden files
    forbidden = []
    forbidden_match = re.search(
        r"-\s+(?:Archivos estrictamente prohibidos|Strictly forbidden files):(.*)",
        section1_text,
        re.DOTALL | re.IGNORECASE
    )
    if forbidden_match:
        for line in forbidden_match.group(1).splitlines():
            m = re.findall(r"`([^`]+)`", line)
            if m:
                forbidden.extend([normalize_path(x) for x in m])
            elif line.strip().startswith("-") or line.strip().startswith("*"):
                cleaned = normalize_path(line.strip().lstrip("-* \t"))
                if cleaned:
                    forbidden.append(cleaned)
                    
    return allowed, forbidden

def get_modified_files(worktree_dir: Path, base_branch: str = "dev") -> list[str]:
    # Files modified or added relative to base branch
    diff_res = subprocess.run(
        ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
        cwd=worktree_dir,
        capture_output=True,
        text=True
    )
    
    # If HEAD and base_branch have no common ancestor or three-dot fails, try direct diff
    if diff_res.returncode != 0 or not diff_res.stdout.strip():
        diff_res = subprocess.run(
            ["git", "diff", "--name-only", base_branch],
            cwd=worktree_dir,
            capture_output=True,
            text=True
        )

    # Also consider changes in current working tree (staged or unstaged)
    status_res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=worktree_dir,
        capture_output=True,
        text=True
    )
    
    modified = set()
    if diff_res.stdout:
        for line in diff_res.stdout.splitlines():
            if line.strip():
                modified.add(normalize_path(line))
                
    if status_res.stdout:
        for line in status_res.stdout.splitlines():
            # Porcelain format: XY PATH or XY "PATH"
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                raw_p = parts[1].strip().strip('"')
                if " -> " in raw_p: # Rename
                    raw_p = raw_p.split(" -> ")[1].strip().strip('"')
                modified.add(normalize_path(raw_p))

    # Filter worktree files that are not code (e.g., .git)
    return [p for p in sorted(modified) if not p.startswith(".git/")]

def matches_any_pattern(file_path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(file_path, pattern) or file_path == pattern:
            return True
        if pattern.endswith("/") and file_path.startswith(pattern):
            return True
    return False

def validate_diff(worktree_dir: Path, spec_path: Path, base_branch: str = "dev") -> tuple[bool, dict]:
    allowed, forbidden = parse_spec_boundaries(spec_path)
    modified = get_modified_files(worktree_dir, base_branch)
    
    violations = []
    
    for f in modified:
        # Exclude compiled bytecode generated at runtime by interpreter/pytest
        if f.endswith(".pyc") or "/__pycache__/" in f or f.startswith("__pycache__/"):
            continue
            
        # 1. Protected root infrastructure rule
        if matches_any_pattern(f, PROTECTED_ROOT_PATTERNS):
            violations.append(f"Protected infrastructure or governance file modified: '{f}'")
            continue
            
        # 2. Forbidden files rule
        if matches_any_pattern(f, forbidden):
            violations.append(f"File strictly forbidden by SPEC modified: '{f}'")
            continue
            
        # 3. Allowed files rule
        if allowed and not matches_any_pattern(f, allowed):
            violations.append(f"File outside allowed scope modified: '{f}'")
            
    payload = {
        "status": "PASS" if not violations else "FAIL",
        "modified_files": modified,
        "allowed_files": allowed,
        "forbidden_files": forbidden,
        "violations": violations
    }
    
    return len(violations) == 0, payload

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hard code boundary enforcer")
    parser.add_argument("--worktree", default=".", help="Worktree or repository directory")
    parser.add_argument("--spec", required=True, help="Path to SPEC.md file")
    parser.add_argument("--base", default="dev", help="Base branch for comparison")
    args = parser.parse_args()
    
    wt_dir = Path(args.worktree).resolve()
    sp_path = Path(args.spec).resolve()
    
    passed, report = validate_diff(wt_dir, sp_path, args.base)
    
    payloads_dir = Path(".orchestrator/payloads") if Path(".orchestrator").exists() else Path("orchestrator/payloads")
    payloads_dir.mkdir(parents=True, exist_ok=True)
    violation_file = payloads_dir / "diff_violation.json"
    
    if not passed:
        violation_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[FAIL] Diff Gate violated. Found {len(report['violations'])} violations:")
        for v in report["violations"]:
            print(f"  - {v}")
        sys.exit(1)
        
    print(f"[PASS] Diff Gate passed. {len(report['modified_files'])} files within allowed scope.")
    sys.exit(0)
