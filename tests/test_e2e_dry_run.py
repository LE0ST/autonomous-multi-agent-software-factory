import os
import sys
import shutil
import subprocess
from pathlib import Path
import pytest

from orchestrator.state_manager import StateManager
from scripts.discovery import run_discovery
from scripts.spec_gate import validate_spec
from scripts.diff_gate import validate_diff
from scripts.test_runner import run_tests
from scripts.sast_runner import run_sast, EXIT_NO_FINDINGS
from scripts.merge_gate import execute_fast_forward_merge
from scripts.worktree_manager import create_worktree, remove_worktree

def cleanup_task(repo_root: Path, task_id: str):
    remove_worktree(repo_root, task_id, delete_branch=True)
    state_file = repo_root / "orchestrator" / "state" / f"state_{task_id}.json"
    if state_file.exists():
        try:
            state_file.unlink()
        except Exception:
            pass

def test_e2e_dry_run_success_flow():
    task_id = "TASK-E2E-SUCCESS"
    repo_root = Path.cwd()
    cleanup_task(repo_root, task_id)
    
    try:
        spec_path = repo_root / "specs" / "TASK-001.md"
        
        # 1. Discovery
        passed_disc, _ = run_discovery(repo_root, "dev")
        assert passed_disc is True
        
        # 2. FSM Init
        sm = StateManager(task_id, state_dir=str(repo_root / "orchestrator" / "state"), raise_on_halt=True)
        assert sm.data["current_state"] == "INIT"
        
        # 3. Spec Gate
        sm.transition("SPEC_GATE")
        valid_spec, spec_msg = validate_spec(spec_path)
        assert valid_spec is True
        
        # 4. Create Worktree
        sm.transition("BUILDING")
        wt_created, wt_path_str = create_worktree(repo_root, task_id, "dev")
        assert wt_created is True
        wt_path = Path(wt_path_str)
        assert wt_path.exists()
        
        # 5. Worker builds code in worktree (allowed files according to TASK-001)
        sm.register_worker_run()
        src_dir = wt_path / "src" / "auth"
        src_dir.mkdir(parents=True, exist_ok=True)
        code_file = src_dir / "token_validator.py"
        code_file.write_text(
            "import hmac\nimport hashlib\n\ndef validate_token(token: str, secret: str = 'key') -> bool:\n"
            "    if not token or not isinstance(token, str):\n"
            "        return False\n"
            "    expected = hmac.new(secret.encode(), b'valid', hashlib.sha256).hexdigest()\n"
            "    return hmac.compare_digest(token, expected)\n",
            encoding="utf-8"
        )
        
        test_dir = wt_path / "tests"
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / "test_token_validator.py"
        test_file.write_text(
            "import hmac\nimport hashlib\nfrom src.auth.token_validator import validate_token\n\n"
            "def test_token_empty():\n"
            "    assert validate_token('') is False\n"
            "    assert validate_token(None) is False\n\n"
            "def test_token_valid():\n"
            "    valid_token = hmac.new(b'key', b'valid', hashlib.sha256).hexdigest()\n"
            "    assert validate_token(valid_token) is True\n",
            encoding="utf-8"
        )
        
        # Commit changes in worktree
        subprocess.run(["git", "add", "."], cwd=wt_path, check=True)
        subprocess.run(["git", "commit", "-m", f"feat({task_id}): implement token validator"], cwd=wt_path, check=True)
        
        # 6. Diff Gate
        sm.transition("DIFF_GATE")
        diff_ok, diff_rep = validate_diff(wt_path, spec_path, "dev")
        assert diff_ok is True, f"Diff Gate violado: {diff_rep.get('violations')}"
        
        # 7. Testing Gate
        sm.transition("TESTING")
        tests_ok, stdout, stderr, code = run_tests(wt_path, repo_root)
        assert tests_ok is True, f"Tests fallaron:\n{stdout}\n{stderr}"
        
        # 8. SAST Scan
        sm.transition("SAST_SCAN")
        sast_code, sast_rep = run_sast(wt_path)
        assert sast_code == EXIT_NO_FINDINGS
        
        # 9. Auto Merge
        sm.transition("AUTO_MERGE")
        # Remover worktree antes del merge a dev
        remove_worktree(repo_root, task_id)
        merge_ok, merge_msg = execute_fast_forward_merge(repo_root, task_id, "dev")
        assert merge_ok is True, f"Merge falló: {merge_msg}"
        
        sm.set_execution_status("COMPLETED")
        assert sm.data["execution_status"] == "COMPLETED"
    finally:
        cleanup_task(repo_root, task_id)

def test_e2e_dry_run_with_retry_flow():
    task_id = "TASK-E2E-RETRY"
    repo_root = Path.cwd()
    cleanup_task(repo_root, task_id)
    
    try:
        sm = StateManager(task_id, state_dir=str(repo_root / "orchestrator" / "state"), raise_on_halt=True)
        
        # Crear Worktree
        wt_created, wt_path_str = create_worktree(repo_root, task_id, "dev")
        assert wt_created is True
        wt_path = Path(wt_path_str)
        
        # Intento 1: Worker introduce código con test defectuoso
        sm.register_worker_run()
        assert sm.data["budgets"]["worker_attempts_in_epoch"] == 1
        
        src_dir = wt_path / "src" / "auth"
        src_dir.mkdir(parents=True, exist_ok=True)
        code_file = src_dir / "token_validator.py"
        code_file.write_text("def validate_token(token):\n    return False\n", encoding="utf-8")
        
        test_dir = wt_path / "tests"
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / "test_token_validator.py"
        test_file.write_text(
            "from src.auth.token_validator import validate_token\n"
            "def test_token_fail():\n"
            "    assert validate_token('any') is True\n",
            encoding="utf-8"
        )
        
        tests_ok, _, _, _ = run_tests(wt_path, repo_root)
        assert tests_ok is False
        
        # Triage: Worker puede reintentar en la misma época sin consumir logic_replan
        assert sm.can_worker_retry_in_epoch() is True
        sm.transition("TRIAGING", "Diagnóstico de fallo en test_token_fail")
        
        # Intento 2: Worker corrige el código
        sm.register_worker_run()
        assert sm.data["budgets"]["worker_attempts_in_epoch"] == 2
        assert sm.data["budgets"]["logic_replans_used"] == 0  # Reintento dentro de la época
        
        code_file.write_text("def validate_token(token):\n    return token == 'any'\n", encoding="utf-8")
        tests_ok, _, _, _ = run_tests(wt_path, repo_root)
        assert tests_ok is True
    finally:
        cleanup_task(repo_root, task_id)
