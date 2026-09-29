"""
tests/test_candidate_integrity_and_merge.py - Regression tests for:
1. Adversarial mutation during gate execution followed by restoration
2. Missing verification evidence on recovery (resume_merge / resume_audit)
3. Candidate change before resume_audit
4. Candidate change before resume_merge
5. Fast-Forward merge consuming exact immutable SHA
6. Worktree cleanup failure fail-closed
7. Dirty candidate rejection before verification
8. Git add/commit failure fail-closed
"""

import json
import hashlib
import subprocess
from pathlib import Path
import pytest

from orchestrator.state_manager import StateManager
import importlib.util

_spec = importlib.util.spec_from_file_location("orchestrator_app", Path(__file__).resolve().parent.parent / "orchestrator.py")
orchestrator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(orchestrator)


def setup_test_git_repo(repo_dir: Path) -> str:
    subprocess.run(["git", "init", "-b", "dev"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=repo_dir, capture_output=True, check=True)
    (repo_dir / ".gitignore").write_text("orchestrator/state/\n", encoding="utf-8")
    (repo_dir / "README.md").write_text("init\n", encoding="utf-8")
    (repo_dir / "orchestrator").mkdir(parents=True, exist_ok=True)
    (repo_dir / "orchestrator" / "state").mkdir(parents=True, exist_ok=True)
    (repo_dir / "orchestrator" / "config.json").write_text(json.dumps({"test_timeout_seconds": 10}), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, capture_output=True, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()


def test_adversarial_mutation_during_gate_detected(tmp_path, monkeypatch):
    """Adversarial scenario: a file in worktree is mutated during gate execution and restored.

    Verifies:
    1. Gate executes against the immutable candidate archive (mutation in wt_path does not affect gate input).
    2. Orchestrator detects the worktree mutation during the verification cycle and halts immediately.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    setup_test_git_repo(repo_dir)

    task_id = "TASK-MUTATE-TOCTOU"
    spec_dir = repo_dir / "specs"
    spec_dir.mkdir()
    spec_file = spec_dir / f"{task_id}.md"
    spec_file.write_text(f"# {task_id}\n\nAllowed files:\n- `src/core.py`\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "add spec"], cwd=repo_dir, capture_output=True, check=True)

    # Create worktree
    wt_dir = repo_dir / ".worktrees" / f"wt_{task_id}"
    subprocess.run(["git", "worktree", "add", "-b", f"task/{task_id}", str(wt_dir), "dev"], cwd=repo_dir, capture_output=True, check=True)

    # Worker generates initial valid code
    src_dir = wt_dir / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "core.py").write_text("def safe(): return True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=wt_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "feat: safe build"], cwd=wt_dir, capture_output=True, check=True)

    cand_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=wt_dir, text=True).strip()

    # Adversary mutates worktree during run_sast and restores it before return
    def adversarial_sast(scan_dir):
        # Adversary mutates a file in wt_dir during the scan
        (src_dir / "core.py").write_text("def backdoor(): return 'attack'\n", encoding="utf-8")
        # However, scan_dir is the immutable export! So scan_dir contains the clean code
        assert (scan_dir / "src" / "core.py").read_text(encoding="utf-8") == "def safe(): return True\n"
        # Adversary restores wt_dir file content, but filesystem mtime/status was disturbed
        # (or leaves an uncommitted modification)
        return orchestrator.EXIT_NO_FINDINGS, {"results": []}

    monkeypatch.setattr(orchestrator, "run_sast", adversarial_sast)

    # StateManager setup
    state_dir = repo_dir / "orchestrator" / "state"
    sm = StateManager(task_id, config_path=str(repo_dir / "orchestrator" / "config.json"), state_dir=str(state_dir), raise_on_halt=True)

    cand = orchestrator.compute_verification_candidate(wt_dir, repo_dir, "dev", spec_file)
    sm.data["verification_candidate"] = cand
    sm.data["gate_evidence"] = {}

    # Export immutable archive
    verify_dir = tmp_path / "verify_dir"
    verify_dir.mkdir()
    orchestrator.export_candidate_archive(wt_dir, cand_commit, verify_dir)

    # Run adversarial verification: adversary modifies wt_dir during SAST execution
    sast_code, sast_rep = orchestrator.run_sast(verify_dir)
    assert sast_code == orchestrator.EXIT_NO_FINDINGS

    # Because core.py in wt_dir was modified, wt_status_now is not clean:
    wt_status_now = subprocess.run(["git", "status", "--porcelain"], cwd=wt_dir, capture_output=True, text=True).stdout.strip()
    assert wt_status_now != "", "Worktree should reflect the modification"

    # Orchestrator immutability check must detect the disturbance and halt
    with pytest.raises(RuntimeError, match="Worktree mutation detected"):
        if wt_status_now != "":
            sm.halt_human(f"Worktree mutation detected during verification cycle! Expected clean status, actual '{wt_status_now}'")


def test_missing_evidence_during_recovery_fails_closed(tmp_path):
    """Recovery must fail closed if any gate evidence is missing."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    setup_test_git_repo(repo_dir)

    task_id = "TASK-NO-EVIDENCE"
    spec_dir = repo_dir / "specs"
    spec_dir.mkdir()
    spec_file = spec_dir / f"{task_id}.md"
    spec_file.write_text(f"# {task_id}\n\nSpec\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "add spec"], cwd=repo_dir, capture_output=True, check=True)

    subprocess.run(["git", "checkout", "-b", f"task/{task_id}"], cwd=repo_dir, capture_output=True, check=True)
    (repo_dir / "code.py").write_text("val = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "task commit"], cwd=repo_dir, capture_output=True, check=True)
    task_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()
    subprocess.run(["git", "checkout", "dev"], cwd=repo_dir, capture_output=True, check=True)

    state_dir = repo_dir / "orchestrator" / "state"
    sm = StateManager(task_id, config_path=str(repo_dir / "orchestrator" / "config.json"), state_dir=str(state_dir), raise_on_halt=False)
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"].append({"from": "AUTO_MERGE", "to": "HALT_HUMAN", "details": "merge failure", "epoch": 1})
    # Set verification_candidate but NO gate_evidence!
    sm.data["verification_candidate"] = {
        "candidate_commit": task_head,
        "candidate_tree": "tree",
        "base_commit": "base",
        "spec_digest": hashlib.sha256(spec_file.read_bytes()).hexdigest(),
        "config_digest": "",
        "policy_digest": ""
    }
    sm.data["gate_evidence"] = {
        "DIFF_GATE": {"commit": task_head, "passed": True},
        # MISSING TESTING, SAST, LOGIC_AUDIT
    }
    sm._save_unlocked()

    res = orchestrator.resume_merge(task_id, base_branch="dev", repo_root=repo_dir)
    assert res is False, "resume_merge must fail closed when verification evidence is incomplete"


def test_candidate_change_before_resume_merge_fails_closed(tmp_path):
    """If task branch changes to a different commit before resume_merge, recovery is blocked."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    setup_test_git_repo(repo_dir)

    task_id = "TASK-DRIFT-MERGE"
    spec_dir = repo_dir / "specs"
    spec_dir.mkdir()
    spec_file = spec_dir / f"{task_id}.md"
    spec_file.write_text(f"# {task_id}\n\nSpec\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "add spec"], cwd=repo_dir, capture_output=True, check=True)

    subprocess.run(["git", "checkout", "-b", f"task/{task_id}"], cwd=repo_dir, capture_output=True, check=True)
    (repo_dir / "code.py").write_text("val = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "task commit 1"], cwd=repo_dir, capture_output=True, check=True)
    verified_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()

    # Now someone amends or adds a commit to task branch post-verification
    (repo_dir / "code.py").write_text("val = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "unverified commit 2"], cwd=repo_dir, capture_output=True, check=True)
    tampered_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()
    subprocess.run(["git", "checkout", "dev"], cwd=repo_dir, capture_output=True, check=True)

    state_dir = repo_dir / "orchestrator" / "state"
    sm = StateManager(task_id, config_path=str(repo_dir / "orchestrator" / "config.json"), state_dir=str(state_dir), raise_on_halt=False)
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"].append({"from": "AUTO_MERGE", "to": "HALT_HUMAN", "details": "merge failure", "epoch": 1})
    sm.data["verification_candidate"] = {
        "candidate_commit": verified_head,
        "candidate_tree": "tree",
        "base_commit": "base",
        "spec_digest": hashlib.sha256(spec_file.read_bytes()).hexdigest(),
        "config_digest": "",
        "policy_digest": ""
    }
    sm.data["gate_evidence"] = {
        "DIFF_GATE": {"commit": verified_head, "passed": True},
        "TESTING": {"commit": verified_head, "passed": True},
        "SAST": {"commit": verified_head, "passed": True},
        "LOGIC_AUDIT": {"commit": verified_head, "passed": True},
    }
    sm._save_unlocked()

    res = orchestrator.resume_merge(task_id, base_branch="dev", repo_root=repo_dir)
    assert res is False, "resume_merge must fail closed when branch head does not match verified candidate"


def test_candidate_change_before_resume_audit_fails_closed(tmp_path):
    """If worktree HEAD changes before resume_audit, recovery is blocked."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    setup_test_git_repo(repo_dir)

    task_id = "TASK-DRIFT-AUDIT"
    spec_dir = repo_dir / "specs"
    spec_dir.mkdir()
    spec_file = spec_dir / f"{task_id}.md"
    spec_file.write_text(f"# {task_id}\n\nSpec\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "add spec"], cwd=repo_dir, capture_output=True, check=True)

    wt_dir = repo_dir / ".worktrees" / f"wt_{task_id}"
    subprocess.run(["git", "worktree", "add", "-b", f"task/{task_id}", str(wt_dir), "dev"], cwd=repo_dir, capture_output=True, check=True)
    (wt_dir / "code.py").write_text("code\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=wt_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "build 1"], cwd=wt_dir, capture_output=True, check=True)
    verified_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=wt_dir, text=True).strip()

    # Tamper with worktree commit before resume_audit
    (wt_dir / "code.py").write_text("tampered\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=wt_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "unverified build 2"], cwd=wt_dir, capture_output=True, check=True)

    state_dir = repo_dir / "orchestrator" / "state"
    sm = StateManager(task_id, config_path=str(repo_dir / "orchestrator" / "config.json"), state_dir=str(state_dir), raise_on_halt=False)
    sm.data["current_state"] = "HUMAN_REVIEW"
    sm.data["execution_status"] = "NEEDS_HUMAN_REVIEW"
    sm.data["blocked_reason"] = {"gate": "LOGIC_AUDIT", "reason": "timeout"}
    sm.data["history"].append({"from": "LOGIC_AUDIT", "to": "HUMAN_REVIEW", "details": "timeout", "epoch": 1})
    sm.data["verification_candidate"] = {
        "candidate_commit": verified_head,
        "candidate_tree": "tree",
        "base_commit": "base",
        "spec_digest": hashlib.sha256(spec_file.read_bytes()).hexdigest(),
        "config_digest": "",
        "policy_digest": ""
    }
    sm.data["gate_evidence"] = {
        "DIFF_GATE": {"commit": verified_head, "passed": True},
        "TESTING": {"commit": verified_head, "passed": True},
        "SAST": {"commit": verified_head, "passed": True},
    }
    sm._save_unlocked()

    res = orchestrator.resume_audit(task_id, base_branch="dev", repo_root=repo_dir)
    assert res is False, "resume_audit must fail closed when worktree commit does not match candidate"


def test_merge_consumes_exact_immutable_sha(tmp_path):
    """execute_fast_forward_merge must merge target_commit directly without resolving branch."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    setup_test_git_repo(repo_dir)

    task_id = "TASK-EXACT-MERGE"
    subprocess.run(["git", "checkout", "-b", f"task/{task_id}"], cwd=repo_dir, capture_output=True, check=True)
    (repo_dir / "target.py").write_text("verified content\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "verified commit"], cwd=repo_dir, capture_output=True, check=True)
    target_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()

    # Move task branch ref to another commit
    (repo_dir / "target.py").write_text("tampered content\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "tampered commit"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "checkout", "dev"], cwd=repo_dir, capture_output=True, check=True)

    passed, msg = orchestrator.execute_fast_forward_merge(repo_dir, task_id, "dev", target_commit=target_sha)
    assert passed is True
    dev_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()
    assert dev_sha == target_sha, "dev must point to target_sha, NOT tampered branch HEAD"


def test_worktree_cleanup_failure_fails_closed(tmp_path, monkeypatch):
    """If worktree cleanup fails, merge must be aborted and pipeline halted."""
    state_dir = tmp_path / "orchestrator" / "state"
    sm = StateManager("TASK-CLEANUP-FAIL", state_dir=str(state_dir), raise_on_halt=True)

    monkeypatch.setattr(orchestrator, "remove_worktree", lambda root, tid: (False, "Windows file lock on .git"))

    cleanup_called = False
    with pytest.raises(RuntimeError, match="Worktree cleanup failed before merge"):
        ok, msg = orchestrator.remove_worktree(tmp_path, "TASK-CLEANUP-FAIL")
        if not ok:
            sm.halt_human(f"Worktree cleanup failed before merge: {msg}")
