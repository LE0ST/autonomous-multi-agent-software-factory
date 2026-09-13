#!/usr/bin/env python3
"""
scripts/sast_runner.py - Deterministic tri-state SAST validator with Windows and fallback support.
Exit codes:
  0: NO_FINDINGS (zero critical vulnerabilities detected)
  1: FINDINGS (vulnerabilities detected, writes orchestrator/payloads/semgrep_report.json)
  2: TOOL_ERROR (execution failure or corrupted tool; not confused with clean code)
"""

import sys
import json
import shutil
import subprocess
from pathlib import Path

EXIT_NO_FINDINGS = 0
EXIT_FINDINGS = 1
EXIT_TOOL_ERROR = 2

def find_semgrep_cmd() -> list[str] | None:
    if shutil.which("semgrep"):
        return ["semgrep"]
    # Check if available as a Python module
    res = subprocess.run([sys.executable, "-m", "semgrep", "--version"], capture_output=True, text=True)
    if res.returncode == 0:
        return [sys.executable, "-m", "semgrep"]
    return None

def find_bandit_cmd() -> list[str] | None:
    if shutil.which("bandit"):
        return ["bandit"]
    res = subprocess.run([sys.executable, "-m", "bandit", "--version"], capture_output=True, text=True)
    if res.returncode == 0:
        return [sys.executable, "-m", "bandit"]
    return None

def run_sast(worktree_dir: Path) -> tuple[int, dict]:
    semgrep_bin = find_semgrep_cmd()
    
    if semgrep_bin:
        cmd = semgrep_bin + ["scan", "--config", "auto", "--severity", "ERROR", "--json"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=worktree_dir)
            if res.stdout:
                try:
                    data = json.loads(res.stdout)
                    findings = data.get("results", [])
                    if len(findings) > 0:
                        return EXIT_FINDINGS, {
                            "engine": "semgrep",
                            "results": findings,
                            "raw": data
                        }
                    return EXIT_NO_FINDINGS, {
                        "engine": "semgrep",
                        "results": [],
                        "raw": data
                    }
                except json.JSONDecodeError:
                    return EXIT_TOOL_ERROR, {
                        "engine": "semgrep",
                        "error": "Failed to parse JSON output from Semgrep",
                        "stderr": res.stderr,
                        "stdout": res.stdout
                    }
            elif res.returncode != 0:
                return EXIT_TOOL_ERROR, {
                    "engine": "semgrep",
                    "error": f"Semgrep returned code {res.returncode}",
                    "stderr": res.stderr
                }
        except Exception as e:
            # If direct invocation fails, attempt fallback to bandit
            pass

    # Fallback to Bandit for Python projects
    bandit_bin = find_bandit_cmd()
    src_dir = worktree_dir / "src"
    target_scan = str(src_dir) if src_dir.exists() else str(worktree_dir)
    
    if bandit_bin:
        cmd = bandit_bin + ["-r", target_scan, "-f", "json", "-ll"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=worktree_dir)
            if res.stdout:
                try:
                    data = json.loads(res.stdout)
                    results = data.get("results", [])
                    # Filter HIGH or MEDIUM severity
                    critical = [r for r in results if r.get("issue_severity") in ["HIGH", "MEDIUM"]]
                    if critical:
                        return EXIT_FINDINGS, {
                            "engine": "bandit_fallback",
                            "results": critical,
                            "raw": data
                        }
                    return EXIT_NO_FINDINGS, {
                        "engine": "bandit_fallback",
                        "results": [],
                        "raw": data
                    }
                except json.JSONDecodeError:
                    return EXIT_TOOL_ERROR, {
                        "engine": "bandit_fallback",
                        "error": "Failed to parse JSON output from Bandit",
                        "stderr": res.stderr,
                        "stdout": res.stdout
                    }
            elif res.returncode not in [0, 1]:
                return EXIT_TOOL_ERROR, {
                    "engine": "bandit_fallback",
                    "error": f"Bandit finished with exit code {res.returncode}",
                    "stderr": res.stderr
                }
        except Exception as e:
            return EXIT_TOOL_ERROR, {
                "engine": "bandit_fallback",
                "error": f"Failed to execute Bandit: {str(e)}"
            }

    # If neither tool was available
    return EXIT_TOOL_ERROR, {
        "engine": "none",
        "error": "No operational SAST tools found (neither Semgrep nor Bandit in PATH)."
    }

if __name__ == "__main__":
    worktree_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    repo_root = Path.cwd()
    
    code, report = run_sast(worktree_path)
    
    payloads_dir = repo_root / "orchestrator" / "payloads"
    payloads_dir.mkdir(parents=True, exist_ok=True)
    report_file = payloads_dir / "semgrep_report.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    
    if code == EXIT_NO_FINDINGS:
        print(f"[PASS] SAST Gate: PASSED (Zero critical findings detected via {report.get('engine')})")
        sys.exit(EXIT_NO_FINDINGS)
    elif code == EXIT_FINDINGS:
        findings_count = len(report.get("results", []))
        print(f"[FAIL] SAST Gate: FINDINGS ({findings_count} vulnerabilities detected via {report.get('engine')})")
        sys.exit(EXIT_FINDINGS)
    else:
        print(f"[ERROR] SAST Gate: TOOL_ERROR ({report.get('error', 'Unknown tool error')})")
        sys.exit(EXIT_TOOL_ERROR)
