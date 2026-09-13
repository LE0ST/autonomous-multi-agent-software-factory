#!/usr/bin/env python3
"""
scripts/test_runner.py - Ejecutor determinista de tests y evaluación de cobertura.
Lee la configuración desde orchestrator/config.json y genera orchestrator/payloads/raw_test_failure.json si falla.
Exit 0: Tests y Cobertura OK. Exit 1: Falla tests o cobertura insuficiente.
"""

import sys
import json
import subprocess
from pathlib import Path

def load_config(repo_root: Path) -> dict:
    for candidate in [repo_root / "orchestrator" / "config.json", repo_root / ".orchestrator" / "config.json"]:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {
        "coverage_threshold": 85.0,
        "test_command": "python -m pytest --cov=src --cov-fail-under=85 -q"
    }

def run_tests(worktree_dir: Path, repo_root: Path) -> tuple[bool, str, str, int]:
    cfg = load_config(repo_root)
    cov_threshold = cfg.get("coverage_threshold", 85.0)
    configured_cmd = cfg.get("test_command")
    
    # Si existe comando configurado explícito, usarlo adaptando el umbral
    if configured_cmd:
        cmd = configured_cmd
    elif (worktree_dir / "package.json").exists():
        cmd = f"npm test -- --coverage --coverageThreshold='{{\"global\":{{\"lines\":{cov_threshold}}}}}'"
    else:
        cmd = f"python -m pytest --cov=src --cov-fail-under={int(cov_threshold)} -q"
        
    res = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=worktree_dir
    )
    
    return res.returncode == 0, res.stdout, res.stderr, res.returncode

if __name__ == "__main__":
    worktree_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    repo_root_path = Path.cwd()
    
    passed, stdout, stderr, code = run_tests(worktree_path, repo_root_path)
    
    payloads_dir = repo_root_path / "orchestrator" / "payloads"
    payloads_dir.mkdir(parents=True, exist_ok=True)
    
    if not passed:
        payload = {
            "exit_code": code,
            "stdout": stdout,
            "stderr": stderr
        }
        failure_file = payloads_dir / "raw_test_failure.json"
        failure_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("[FAIL] Test Gate: FAILED (tests o cobertura insuficiente)")
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        sys.exit(1)
        
    print("[PASS] Test Gate: PASSED (suite y cobertura completadas exitosamente)")
    sys.exit(0)
