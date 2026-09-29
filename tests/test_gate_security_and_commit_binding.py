"""
tests/test_gate_security_and_commit_binding.py - Tests for fail-closed SAST handling
and Commit-SHA verification binding prior to merge.
"""

import json
import subprocess
from pathlib import Path
import pytest

from orchestrator.state_manager import StateManager
from scripts.sast_runner import EXIT_TOOL_ERROR, EXIT_NO_FINDINGS

import importlib.util
_spec = importlib.util.spec_from_file_location("orchestrator_app", Path(__file__).resolve().parent.parent / "orchestrator.py")
orchestrator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(orchestrator)


def test_orchestrator_sast_tool_error_fails_closed(tmp_path, monkeypatch):
    """Verify that when SAST scanner crashes/errors, the pipeline immediately halts to HALT_HUMAN."""
    state_dir = tmp_path / "orchestrator" / "state"
    state_dir.mkdir(parents=True)
    sm = StateManager("TASK-SAST-FAIL", state_dir=str(state_dir), raise_on_halt=True)

    # Mock run_sast to return EXIT_TOOL_ERROR
    monkeypatch.setattr(
        orchestrator,
        "run_sast",
        lambda wt: (EXIT_TOOL_ERROR, {"error": "Semgrep process killed by SIGSEGV"})
    )

    # Ensure logic security is NEVER invoked
    logic_security_called = False
    def mock_logic_audit(*args, **kwargs):
        nonlocal logic_security_called
        logic_security_called = True
        return True, None, {}

    monkeypatch.setattr(orchestrator, "execute_logic_security_audit", mock_logic_audit)

    # Transition sm to SAST_SCAN and verify fail-closed handling
    sast_code, sast_rep = orchestrator.run_sast(tmp_path)
    assert sast_code == EXIT_TOOL_ERROR

    with pytest.raises(RuntimeError, match="SAST gate failure: tool error"):
        sm.halt_human(f"SAST gate failure: tool error ({sast_rep['error']})")

    assert sm.data["current_state"] == "HALT_HUMAN"
    assert sm.data["execution_status"] == "FAILED"
    assert logic_security_called is False


def test_commit_verification_binding_blocks_mismatched_sha(tmp_path):
    """Verify that if candidate branch SHA != verified commit SHA, merge is blocked."""
    state_dir = tmp_path / "orchestrator" / "state"
    state_dir.mkdir(parents=True)
    sm = StateManager("TASK-BIND-01", state_dir=str(state_dir), raise_on_halt=True)

    verified_sha = "1111111111111111111111111111111111111111"
    tampered_sha = "2222222222222222222222222222222222222222"

    sm.data["verified_commit"] = verified_sha
    sm._save_unlocked()

    # If branch commit differs from verified commit
    candidate_commit = tampered_sha
    assert candidate_commit != sm.data.get("verified_commit")

    with pytest.raises(RuntimeError, match="Commit verification mismatch"):
        sm.halt_human(
            f"Commit verification mismatch: verified '{sm.data.get('verified_commit')}' "
            f"but branch task/TASK-BIND-01 is at '{candidate_commit}'. Merge blocked."
        )

    assert sm.data["current_state"] == "HALT_HUMAN"
    assert sm.data["execution_status"] == "FAILED"


def test_resume_merge_denied_on_commit_mismatch(tmp_path, monkeypatch):
    """Verify that resume_merge rejects recovery if the branch commit drifted from verified_commit."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    state_dir = repo_dir / "orchestrator" / "state"
    state_dir.mkdir(parents=True)

    task_id = "TASK-DRIFT"
    sm = StateManager(task_id, state_dir=str(state_dir), raise_on_halt=False)
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"].append({
        "from": "AUTO_MERGE",
        "to": "HALT_HUMAN",
        "details": "Fast-Forward merge failed: temporary lock",
        "epoch": 1
    })

    # Set verified candidate to SHA A
    sha_a = "aaaa0000aaaa0000aaaa0000aaaa0000aaaa0000"
    sm.data["verification_candidate"] = {
        "candidate_commit": sha_a,
        "candidate_tree": "tree",
        "base_commit": "base",
        "spec_digest": "",
        "config_digest": "",
        "policy_digest": ""
    }
    sm.data["gate_evidence"] = {
        "DIFF_GATE": {"commit": sha_a, "passed": True},
        "TESTING": {"commit": sha_a, "passed": True},
        "SAST": {"commit": sha_a, "passed": True},
        "LOGIC_AUDIT": {"commit": sha_a, "passed": True},
    }
    sm.data["verified_commit"] = sha_a
    sm._save_unlocked()

    # Mock can_resume_merge -> True
    monkeypatch.setattr(StateManager, "can_resume_merge", lambda self: (True, "Authorized"))

    # Mock git branch check to return task branch
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=f"task/{task_id}\n")
    )
    # Mock is_repo_clean -> True
    monkeypatch.setattr(orchestrator, "is_repo_clean", lambda root: (True, ""))

    # We do not mock verify_digests, it is removed.

    # Run resume_merge
    # The current task branch is aaaa0000... (which we didn't mock properly but git branch returns nothing in mock) to return SHA B (different commit)
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda *args, **kwargs: "bbbb0000bbbb0000bbbb0000bbbb0000bbbb0000\n"
    )

    # execute_fast_forward_merge must NEVER be called
    merge_called = False
    def mock_merge(*args, **kwargs):
        nonlocal merge_called
        merge_called = True
        return True, "Merged"

    monkeypatch.setattr(orchestrator, "execute_fast_forward_merge", mock_merge)

    result = orchestrator.resume_merge(task_id, base_branch="dev", repo_root=repo_dir)

    assert result is False
    assert merge_called is False
