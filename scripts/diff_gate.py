#!/usr/bin/env python3
"""Fail-closed verification of committed, staged, unstaged and untracked paths."""

import json
import re
import subprocess
from pathlib import Path

if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.file_policy import (
    PROTECTED_ROOT_PATTERNS, matches_any_pattern, normalize_relative_path,
    validate_file_scope,
)


def normalize_path(path: str) -> str:
    return normalize_relative_path(path, pattern=True)


def parse_spec_boundaries(spec_path: Path) -> tuple[list[str], list[str]]:
    return parse_spec_boundaries_content(spec_path.read_text(encoding="utf-8"))


def parse_spec_boundaries_content(content: str) -> tuple[list[str], list[str]]:
    section = re.search(
        r"^#+\s*1[\.\):\-]?\s*(?:Alcance\s+y\s+Fronteras|Scope\s+and\s+Boundaries)(.*?)(?=^#+\s*2[\.\):\-]?\s|\Z)",
        content, re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )
    if not section:
        return [], []
    text = section.group(1)
    allowed = re.search(
        r"-\s+(?:Archivos permitidos|Allowed files):(.*?)(?=-\s+(?:Archivos estrictamente prohibidos|Strictly forbidden files):|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    forbidden = re.search(
        r"-\s+(?:Archivos estrictamente prohibidos|Strictly forbidden files):(.*)",
        text, re.DOTALL | re.IGNORECASE,
    )

    def extract(match):
        result = []
        if match:
            for line in match.group(1).splitlines():
                paths = re.findall(r"`([^`]+)`", line)
                if not paths and line.strip().startswith(("-", "*")):
                    paths = [line.strip().lstrip("-* \t")]
                result.extend(normalize_path(p) for p in paths if p)
        return result

    return extract(allowed), extract(forbidden)


def get_modified_files(repo_root: Path, base_sha: str, candidate_sha: str) -> list[str]:
    # Use exact object identities, no branch names.
    res = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "-z", base_sha, candidate_sha],
        cwd=repo_root, capture_output=True, text=True, check=True, timeout=30
    )
    modified = set(normalize_relative_path(p) for p in res.stdout.split("\0") if p)
    return sorted(modified)


def validate_diff(repo_root: Path, base_sha: str, candidate_sha: str, spec_path: Path) -> tuple[bool, dict]:
    allowed, forbidden, modified, violations = [], [], [], []
    try:
        allowed, forbidden = parse_spec_boundaries(spec_path)
        if not allowed:
            raise ValueError("SPEC must provide a nonempty allowed-file list")
        modified = get_modified_files(repo_root, base_sha, candidate_sha)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        violations.append(f"Cannot establish modification boundaries: {type(exc).__name__}: {exc}")
    for path in modified:
        try:
            validate_file_scope(path, allowed, forbidden)
        except ValueError as exc:
            violations.append(str(exc))
    return not violations, {
        "status": "FAIL" if violations else "PASS", "modified_files": modified,
        "allowed_files": allowed, "forbidden_files": forbidden, "violations": violations,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--spec", required=True)
    args = parser.parse_args()
    passed, report = validate_diff(Path(args.repo_root).resolve(), args.base_sha, args.candidate_sha, Path(args.spec).resolve())
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if passed else 1)
