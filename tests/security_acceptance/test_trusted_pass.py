import json
from pathlib import Path
from scripts.test_runner import TestSupervisor
from orchestrator.execution_backend import ExecutionBackend, ExecutionResult

class MockBackend(ExecutionBackend):
    def execute(self, command, candidate_dir, scratch_dir, timeout_seconds, env=None):
        cmd_str = " ".join(command)
        if "Valid123!" in cmd_str:
            return ExecutionResult(0, "True\n", "", False)
        elif "short" in cmd_str:
            return ExecutionResult(0, "False\n", "", False)
        return ExecutionResult(0, "Coverage 100%\n", "", False)

def test_valid_candidate_passes(tmp_path):
    repo_root = tmp_path / "repo"
    worktree_dir = tmp_path / "worktree"
    scratch_dir = tmp_path / "scratch"
    worktree_dir.mkdir(parents=True)
    repo_root.mkdir(parents=True)
    scratch_dir.mkdir(parents=True)

    trusted_tests = repo_root / "trusted_tests"
    trusted_tests.mkdir()

    # We copy the actual current suite.py to reproduce the failure.
    actual_suite = Path("trusted_tests/suite.py").read_text()
    (trusted_tests / "suite.py").write_text(actual_suite)

    backend = MockBackend()
    supervisor = TestSupervisor(backend=backend, repo_root=repo_root)
    passed, stdout, stderr, code, evidence = supervisor.verify_candidate(worktree_dir, scratch_dir)
    assert passed, "A clean valid candidate must PASS"
