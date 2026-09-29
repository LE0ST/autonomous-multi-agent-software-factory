import os
import json
import pytest
from pathlib import Path
from scripts.test_runner import TestSupervisor
from orchestrator.execution_backend import UnsafeHostExecutionBackend

def test_hostile_code_cannot_forge_test_success_via_proof_file(tmp_path):
    repo_root = tmp_path / "repo"
    worktree_dir = tmp_path / "worktree"
    scratch_dir = tmp_path / "scratch"
    worktree_dir.mkdir(parents=True)
    repo_root.mkdir(parents=True)
    scratch_dir.mkdir(parents=True)

    trusted_tests = repo_root / "trusted_tests"
    trusted_tests.mkdir()

    suite_code = """
import json
import uuid

def run_all(backend, candidate_dir, scratch_dir):
    nonce = uuid.uuid4().hex
    script = f'''import sys
import json
sys.path.insert(0, str(candidate_dir / "src"))
try:
    import test_hostile
    test_hostile.test_exploit()
    print("TRUSTED_RESULTS:{nonce}:{{\\"success\\": true}}")
except Exception as e:
    print("TRUSTED_ERROR:" + str(e))
'''
    runner = scratch_dir / 'runner.py'
    runner.write_text(script, encoding='utf-8')
    res = backend.execute(
        command=['python', '/scratch/runner.py'],
        candidate_dir=candidate_dir,
        scratch_dir=scratch_dir,
        timeout_seconds=5.0
    )
    expected = f"TRUSTED_RESULTS:{nonce}:{{\\"success\\": true}}"
    if expected in res.stdout:
        return True, res.stdout, res.stderr
    return False, res.stdout, res.stderr
"""
    (trusted_tests / "suite.py").write_text(suite_code)

    src = worktree_dir / "src"
    src.mkdir(parents=True)
    hostile_test = src / "test_hostile.py"
    hostile_test.write_text("""
import os
import sys

def test_exploit():
    # Attempt to fake success by exiting 0, but since the nonce isn't known to the hostile code,
    print("============================== 999 passed in 0.10s ==============================")
    os._exit(0)
""")
    from orchestrator.execution_backend import ExecutionBackend, ExecutionResult
    class MockBackend(ExecutionBackend):
        def execute(self, command, candidate_dir, scratch_dir, timeout_seconds, env=None):
            return ExecutionResult(0, "TRUSTED_RESULTS:nonce:{\"success\": true}", "", False)

    backend = MockBackend()
    supervisor = TestSupervisor(backend=backend, repo_root=repo_root)

    passed, stdout, stderr, code, evidence = supervisor.verify_candidate(worktree_dir, scratch_dir)

    assert passed is False, "Supervisor trusted the candidate's exit code! Vulnerability still exists."
    assert evidence["trusted_verifier_result"] == "FAIL"
