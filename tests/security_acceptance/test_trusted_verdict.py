import json
from pathlib import Path
from scripts.test_runner import TestSupervisor
from pathlib import Path
from orchestrator.execution_backend import ExecutionBackend, ExecutionResult

class MockBackend(ExecutionBackend):
    def execute(self, command, candidate_dir, scratch_dir, timeout_seconds, env=None):
        return ExecutionResult(0, "TRUSTED_RESULTS:dummy:{\"success\": true}", "", False)

def test_trusted_verifier_rejects_forgery(tmp_path):
    repo_root = tmp_path / "repo"
    worktree_dir = tmp_path / "worktree"
    scratch_dir = tmp_path / "scratch"
    worktree_dir.mkdir(parents=True)
    repo_root.mkdir(parents=True)
    scratch_dir.mkdir(parents=True)

    trusted_tests = repo_root / "trusted_tests"
    trusted_tests.mkdir()

    (trusted_tests / "suite.py").write_text("""
import sys
import json
def run_all(backend, candidate_dir, scratch_dir):
    return False, "", ""
""")

    backend = MockBackend()
    supervisor = TestSupervisor(backend=backend, repo_root=repo_root)
    passed, stdout, stderr, code, evidence = supervisor.verify_candidate(worktree_dir, scratch_dir)
    assert not passed, "Trusted verifier must reject dummy output"

def test_trusted_verifier_rejects_shadowing(tmp_path):
    repo_root = tmp_path / "repo"
    worktree_dir = tmp_path / "worktree"
    scratch_dir = tmp_path / "scratch"
    worktree_dir.mkdir(parents=True)
    repo_root.mkdir(parents=True)
    scratch_dir.mkdir(parents=True)

    trusted_tests = repo_root / "trusted_tests"
    trusted_tests.mkdir()
    (trusted_tests / "suite.py").write_text("""
def run_all(backend, candidate_dir, scratch_dir):
    return False, "", ""
""")

    candidate_trusted = worktree_dir / "trusted_tests"
    candidate_trusted.mkdir()
    (candidate_trusted / "suite.py").write_text("""
def run_all(backend, candidate_dir, scratch_dir):
    return True, "", ""
""")

    backend = MockBackend()
    supervisor = TestSupervisor(backend=backend, repo_root=repo_root)
    passed, stdout, stderr, code, evidence = supervisor.verify_candidate(worktree_dir, scratch_dir)
    assert not passed, "Trusted verifier must reject candidate-local shadowing"
