"""
tests/test_resume_audit.py - Test suite for the --resume-audit recovery pathway.
Verifies:
  1. Correct authorization via StateManager.can_resume_audit()
  2. Rejection of invalid states, gates, and missing transitions
  3. Rejection when Git preconditions fail (missing branch/worktree, dirty repo/worktree)
  4. Zero calls to Worker, Architect, Triage, SPEC, DIFF, TESTING, SAST
  5. Exactly one call to Logic Audit
  6. HTTP 429 returns to HUMAN_REVIEW preserving budgets and epoch byte-for-byte
  7. CLEAN audit advances to AUTO_MERGE and COMPLETED
  8. Git divergence NEVER triggers automatic rebase (halts safely)
  9. Invariant failure uses standard pipeline replan behavior
 10. No credentials leak into stdout, exceptions, JSON, or reports
"""

import json
import os
import subprocess
from pathlib import Path
import pytest

from orchestrator.state_manager import StateManager
from adapters.network_retry import NetworkTransportError
from adapters.contracts import LogicAuditOutput
import importlib.util

_spec = importlib.util.spec_from_file_location("orchestrator_app", Path(__file__).resolve().parent.parent / "orchestrator.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
resume_audit = _mod.resume_audit


def setup_git_repo(repo_dir: Path) -> str:
    """Initializes a clean Git repository with dev branch and orchestrator structure."""
    subprocess.run(["git", "init", "-b", "dev"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=repo_dir, capture_output=True, check=True)
    (repo_dir / ".gitignore").write_text(
        ".worktrees/\n"
        "orchestrator/state/\n"
        "orchestrator/payloads/\n"
        "CRASH_REPORT_*.md\n"
        "HUMAN_REVIEW_*.md\n",
        encoding="utf-8"
    )
    (repo_dir / "README.md").write_text("initial dev content\n", encoding="utf-8")
    (repo_dir / "specs").mkdir(parents=True, exist_ok=True)
    (repo_dir / "orchestrator").mkdir(parents=True, exist_ok=True)
    (repo_dir / "orchestrator" / "state").mkdir(parents=True, exist_ok=True)
    (repo_dir / ".worktrees").mkdir(parents=True, exist_ok=True)

    config = {
        "budgets": {
            "max_logic_replans": 2,
            "max_security_replans": 1,
            "max_spec_syntax_retries": 1,
            "max_worker_per_epoch": 2,
            "max_cumulative_worker_runs": 5
        },
        "roles": {
            "logic_security": {
                "provider": "glm",
                "model": "glm-5.3"
            }
        }
    }
    (repo_dir / "orchestrator" / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit on dev"], cwd=repo_dir, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()


def setup_task_in_human_review(repo_dir: Path, task_id: str) -> Path:
    """Sets up branch, worktree, spec, and state for a task halted at LOGIC_AUDIT."""
    # 1. Create and commit SPEC on dev
    spec_file = repo_dir / "specs" / f"{task_id}.md"
    spec_file.write_text(f"# {task_id}\n\nContract specification content.\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", f"spec: add {task_id} contract"], cwd=repo_dir, capture_output=True, check=True)

    # 2. Create task branch and feature commit
    subprocess.run(["git", "checkout", "-b", f"task/{task_id}"], cwd=repo_dir, capture_output=True, check=True)
    (repo_dir / "feature.py").write_text("def feature(): return 42\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", f"feat({task_id}): build"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "checkout", "dev"], cwd=repo_dir, capture_output=True, check=True)

    # 3. Create worktree
    wt_dir = repo_dir / ".worktrees" / f"wt_{task_id}"
    subprocess.run(["git", "worktree", "add", str(wt_dir), f"task/{task_id}"], cwd=repo_dir, capture_output=True, check=True)

    # 4. Create state in HUMAN_REVIEW
    sm = StateManager(
        task_id,
        config_path=str(repo_dir / "orchestrator" / "config.json"),
        state_dir=str(repo_dir / "orchestrator" / "state"),
        raise_on_halt=False
    )
    sm.data["current_state"] = "HUMAN_REVIEW"
    sm.data["execution_status"] = "NEEDS_HUMAN_REVIEW"
    sm.data["epoch"] = 1
    sm.data["budgets"]["worker_attempts_in_epoch"] = 2
    sm.data["budgets"]["total_cumulative_worker_runs"] = 2
    sm.data["budgets"]["logic_replans_used"] = 0
    sm.data["budgets"]["security_replans_used"] = 0
    sm.data["blocked_reason"] = {
        "gate": "LOGIC_AUDIT",
        "reason": "Logic Security LLM unavailable after retries (HTTP 429).",
        "timestamp": "2026-09-13T20:00:00Z"
    }
    sm.data["history"] = [
        {"from": "INIT", "to": "SPEC_GATE", "details": "Spec ok", "epoch": 1},
        {"from": "SPEC_GATE", "to": "BUILDING", "details": "Build attempt 1", "epoch": 1},
        {"from": "BUILDING", "to": "DIFF_GATE", "details": "Diff ok", "epoch": 1},
        {"from": "DIFF_GATE", "to": "TESTING", "details": "Tests passed", "epoch": 1},
        {"from": "TESTING", "to": "SAST_SCAN", "details": "SAST clean", "epoch": 1},
        {"from": "SAST_SCAN", "to": "LOGIC_AUDIT", "details": "Running audit", "epoch": 1},
        {"from": "LOGIC_AUDIT", "to": "HUMAN_REVIEW", "details": "Service unavailable HTTP 429", "epoch": 1},
    ]
    sm.save()
    return wt_dir


# ---------------------------------------------------------------------------
# TEST 1 — Valid authorization
# ---------------------------------------------------------------------------
def test_can_resume_audit_valid(tmp_path):
    setup_git_repo(tmp_path)
    task_id = "TASK-001"
    setup_task_in_human_review(tmp_path, task_id)

    sm = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )

    can_resume, msg = sm.can_resume_audit(repo_root=tmp_path)
    assert can_resume is True
    assert "authorized" in msg.lower()

    # Also validates when repo_root is omitted (pure FSM check)
    can_resume_fsm, _ = sm.can_resume_audit()
    assert can_resume_fsm is True


# ---------------------------------------------------------------------------
# TEST 2 — Rejection of invalid states and gates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("state,status,gate,has_trans", [
    ("BUILDING", "RUNNING", "LOGIC_AUDIT", True),
    ("HALT_HUMAN", "FAILED", "LOGIC_AUDIT", True),
    ("HUMAN_REVIEW", "RUNNING", "LOGIC_AUDIT", True),
    ("HUMAN_REVIEW", "NEEDS_HUMAN_REVIEW", "TESTING", True),
    ("HUMAN_REVIEW", "NEEDS_HUMAN_REVIEW", "SPEC_GATE", True),
    ("HUMAN_REVIEW", "NEEDS_HUMAN_REVIEW", "LOGIC_AUDIT", False),
])
def test_can_resume_audit_rejected_invalid_states(tmp_path, state, status, gate, has_trans):
    setup_git_repo(tmp_path)
    task_id = "TASK-INV-STATE"
    setup_task_in_human_review(tmp_path, task_id)

    sm = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    sm.data["current_state"] = state
    sm.data["execution_status"] = status
    sm.data["blocked_reason"]["gate"] = gate
    if not has_trans:
        sm.data["history"] = [{"from": "INIT", "to": "HUMAN_REVIEW", "details": "other", "epoch": 1}]
    sm.save()

    can_resume, msg = sm.can_resume_audit(repo_root=tmp_path)
    assert can_resume is False


# ---------------------------------------------------------------------------
# TEST 3 — Rejection of invalid Git preconditions
# ---------------------------------------------------------------------------
def test_can_resume_audit_missing_branch(tmp_path):
    setup_git_repo(tmp_path)
    task_id = "TASK-NOBRANCH"
    setup_task_in_human_review(tmp_path, task_id)
    # Remove branch
    subprocess.run(["git", "worktree", "remove", "--force", str(tmp_path / ".worktrees" / f"wt_{task_id}")], cwd=tmp_path, check=True)
    subprocess.run(["git", "branch", "-D", f"task/{task_id}"], cwd=tmp_path, check=True)

    sm = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    can_resume, msg = sm.can_resume_audit(repo_root=tmp_path)
    assert can_resume is False
    assert "Branch" in msg


def test_can_resume_audit_missing_worktree(tmp_path):
    setup_git_repo(tmp_path)
    task_id = "TASK-NOWT"
    setup_task_in_human_review(tmp_path, task_id)
    subprocess.run(["git", "worktree", "remove", "--force", str(tmp_path / ".worktrees" / f"wt_{task_id}")], cwd=tmp_path, check=True)

    sm = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    can_resume, msg = sm.can_resume_audit(repo_root=tmp_path)
    assert can_resume is False
    assert "Worktree" in msg


def test_can_resume_audit_dirty_worktree(tmp_path):
    setup_git_repo(tmp_path)
    task_id = "TASK-DIRTY-WT"
    wt_dir = setup_task_in_human_review(tmp_path, task_id)
    (wt_dir / "uncommitted.txt").write_text("dirty\n", encoding="utf-8")

    sm = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    can_resume, msg = sm.can_resume_audit(repo_root=tmp_path)
    assert can_resume is False
    assert "Worktree" in msg and "uncommitted" in msg


def test_can_resume_audit_dirty_main_repo(tmp_path):
    setup_git_repo(tmp_path)
    task_id = "TASK-DIRTY-REPO"
    setup_task_in_human_review(tmp_path, task_id)
    (tmp_path / "uncommitted_main.txt").write_text("dirty\n", encoding="utf-8")

    sm = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    can_resume, msg = sm.can_resume_audit(repo_root=tmp_path)
    assert can_resume is False
    assert "Main repository" in msg and "uncommitted" in msg


# ---------------------------------------------------------------------------
# TEST 4 — Zero calls to Worker/Architect/Triage/Gates & exactly one to Audit
# ---------------------------------------------------------------------------
def test_resume_audit_zero_calls_to_other_stages_and_one_audit_call(tmp_path, monkeypatch):
    setup_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    task_id = "TASK-EXCLUSIVE-AUDIT"
    setup_task_in_human_review(tmp_path, task_id)

    counts = {
        "spec_gate": 0,
        "diff_gate": 0,
        "test_runner": 0,
        "sast_runner": 0,
        "worker": 0,
        "architect": 0,
        "triage": 0,
        "audit": 0
    }

    def fake_validate_spec(*args, **kwargs):
        counts["spec_gate"] += 1
        return True, "ok"

    def fake_validate_diff(*args, **kwargs):
        counts["diff_gate"] += 1
        return True, {}

    def fake_run_tests(*args, **kwargs):
        counts["test_runner"] += 1
        return True, "", "", 0

    def fake_run_sast(*args, **kwargs):
        counts["sast_runner"] += 1
        return 0, {}

    def fake_worker_gen(*args, **kwargs):
        counts["worker"] += 1

    def fake_arch_gen(*args, **kwargs):
        counts["architect"] += 1
        return ""

    def fake_triage(*args, **kwargs):
        counts["triage"] += 1

    def fake_audit(*args, **kwargs):
        counts["audit"] += 1
        return LogicAuditOutput(status="PASS", justification="Audit passed", violated_invariants=[])

    monkeypatch.setattr(_mod, "validate_spec", fake_validate_spec)
    monkeypatch.setattr(_mod, "validate_diff", fake_validate_diff)
    monkeypatch.setattr(_mod, "run_tests", fake_run_tests)
    monkeypatch.setattr(_mod, "run_sast", fake_run_sast)
    monkeypatch.setattr(_mod.DeepSeekAdapter, "generate_code_and_tests", fake_worker_gen)
    monkeypatch.setattr(_mod.GeminiAdapter, "generate_spec", fake_arch_gen)
    monkeypatch.setattr(_mod.GeminiAdapter, "triage_failure", fake_triage)
    monkeypatch.setattr(_mod.GLMAdapter, "audit_logic_and_security", fake_audit)

    success = resume_audit(task_id, base_branch="dev", repo_root=tmp_path)
    assert success is True

    # Assert ZERO calls to forbidden stages
    assert counts["spec_gate"] == 0
    assert counts["diff_gate"] == 0
    assert counts["test_runner"] == 0
    assert counts["sast_runner"] == 0
    assert counts["worker"] == 0
    assert counts["architect"] == 0
    assert counts["triage"] == 0

    # Assert EXACTLY ONE call to Logic Audit
    assert counts["audit"] == 1


# ---------------------------------------------------------------------------
# TEST 5 — HTTP 429 returns to HUMAN_REVIEW preserving budgets byte-for-byte
# ---------------------------------------------------------------------------
def test_resume_audit_http_429_preserves_budgets_and_epoch(tmp_path, monkeypatch):
    setup_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    task_id = "TASK-HTTP-429"
    setup_task_in_human_review(tmp_path, task_id)

    sm_before = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    before_budgets = sm_before.data["budgets"].copy()
    before_epoch = sm_before.data["epoch"]

    def fake_audit_429(*args, **kwargs):
        raise NetworkTransportError(
            message="429 Client Error: Too Many Requests",
            status_code=429
        )

    monkeypatch.setattr(_mod.GLMAdapter, "audit_logic_and_security", fake_audit_429)

    success = resume_audit(task_id, base_branch="dev", repo_root=tmp_path)
    assert success is False

    sm_after = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    assert sm_after.data["current_state"] == "HUMAN_REVIEW"
    assert sm_after.data["execution_status"] == "NEEDS_HUMAN_REVIEW"
    assert sm_after.data["blocked_reason"]["gate"] == "LOGIC_AUDIT"
    assert sm_after.data["epoch"] == before_epoch
    assert sm_after.data["budgets"] == before_budgets

    report_file = tmp_path / f"HUMAN_REVIEW_{task_id}.md"
    assert report_file.exists()
    assert "429" in report_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# TEST 6 — CLEAN allows continuing to AUTO_MERGE
# ---------------------------------------------------------------------------
def test_resume_audit_clean_advances_to_auto_merge(tmp_path, monkeypatch):
    setup_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    task_id = "TASK-CLEAN"
    setup_task_in_human_review(tmp_path, task_id)

    def fake_audit_clean(*args, **kwargs):
        return LogicAuditOutput(status="PASS", justification="All invariants verified", violated_invariants=[])

    monkeypatch.setattr(_mod.GLMAdapter, "audit_logic_and_security", fake_audit_clean)

    task_head = subprocess.check_output(["git", "rev-parse", f"task/{task_id}"], cwd=tmp_path, text=True).strip()

    success = resume_audit(task_id, base_branch="dev", repo_root=tmp_path)
    assert success is True

    sm_after = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    assert sm_after.data["current_state"] == "AUTO_MERGE"
    assert sm_after.data["execution_status"] == "COMPLETED"

    dev_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    assert dev_head == task_head
    assert (tmp_path / "feature.py").exists()

    # Worktree is removed only when Fast-Forward was guaranteed and completed
    assert not (tmp_path / ".worktrees" / f"wt_{task_id}").exists()


# ---------------------------------------------------------------------------
# TEST 7 — Prior Git divergence blocks audit, preserves FSM/budgets and worktree
# ---------------------------------------------------------------------------
def test_resume_audit_prior_divergence_blocks_audit_and_preserves_worktree(tmp_path, monkeypatch):
    setup_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    task_id = "TASK-DIVERGENCE-PRE"
    wt_dir = setup_task_in_human_review(tmp_path, task_id)

    # Advance dev independently causing divergence
    subprocess.run(["git", "checkout", "dev"], cwd=tmp_path, capture_output=True, check=True)
    (tmp_path / "dev_diverge.txt").write_text("divergence\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "commit on dev creating divergence"], cwd=tmp_path, capture_output=True, check=True)

    task_head_before = subprocess.check_output(["git", "rev-parse", f"task/{task_id}"], cwd=tmp_path, text=True).strip()

    sm_before = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    before_state = sm_before.data["current_state"]
    before_status = sm_before.data["execution_status"]
    before_budgets = sm_before.data["budgets"].copy()
    before_epoch = sm_before.data["epoch"]
    before_history_len = len(sm_before.data["history"])

    audit_calls = []
    def fake_audit_clean(*args, **kwargs):
        audit_calls.append(1)
        return LogicAuditOutput(status="PASS", justification="All invariants verified", violated_invariants=[])

    monkeypatch.setattr(_mod.GLMAdapter, "audit_logic_and_security", fake_audit_clean)

    success = resume_audit(task_id, base_branch="dev", repo_root=tmp_path)
    assert success is False

    # 1. 0 calls to Logic Audit
    assert len(audit_calls) == 0

    # 2. FSM, budgets, epoch, and history completely unchanged
    sm_after = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    assert sm_after.data["current_state"] == before_state
    assert sm_after.data["execution_status"] == before_status
    assert sm_after.data["budgets"] == before_budgets
    assert sm_after.data["epoch"] == before_epoch
    assert len(sm_after.data["history"]) == before_history_len

    # 3. Worktree preserved
    assert wt_dir.exists()
    assert (wt_dir / "feature.py").exists()

    # 4. Zero rebase or branch movement
    task_head_after = subprocess.check_output(["git", "rev-parse", f"task/{task_id}"], cwd=tmp_path, text=True).strip()
    assert task_head_before == task_head_after


# ---------------------------------------------------------------------------
# TEST 7b — TOCTOU divergence detected after audit preserves worktree
# ---------------------------------------------------------------------------
def test_resume_audit_toctou_divergence_preserves_worktree(tmp_path, monkeypatch):
    setup_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    task_id = "TASK-DIVERGENCE-TOCTOU"
    wt_dir = setup_task_in_human_review(tmp_path, task_id)

    def fake_audit_with_concurrent_divergence(*args, **kwargs):
        # Simulate a concurrent commit landing on dev while audit was executing
        subprocess.run(["git", "checkout", "dev"], cwd=tmp_path, capture_output=True, check=True)
        (tmp_path / "concurrent_dev.txt").write_text("concurrent\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "concurrent commit on dev during audit"], cwd=tmp_path, capture_output=True, check=True)
        return LogicAuditOutput(status="PASS", justification="All invariants verified", violated_invariants=[])

    monkeypatch.setattr(_mod.GLMAdapter, "audit_logic_and_security", fake_audit_with_concurrent_divergence)

    success = resume_audit(task_id, base_branch="dev", repo_root=tmp_path)
    assert success is False

    # Worktree MUST be preserved despite audit PASS
    assert wt_dir.exists()
    assert (wt_dir / "feature.py").exists()

    sm_after = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    assert sm_after.data["current_state"] == "HALT_HUMAN"
    assert sm_after.data["execution_status"] == "FAILED"
    assert "divergence" in sm_after.data["history"][-1]["details"].lower() or "merge" in sm_after.data["history"][-1]["details"].lower()


# ---------------------------------------------------------------------------
# TEST 8 — Invariant failure uses standard pipeline replan behavior
# ---------------------------------------------------------------------------
def test_resume_audit_invariant_failure_uses_standard_replan(tmp_path, monkeypatch):
    setup_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    task_id = "TASK-FAIL-AUDIT"
    setup_task_in_human_review(tmp_path, task_id)

    sm_before = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    initial_sec_replans = sm_before.data["budgets"]["security_replans_used"]

    def fake_audit_fail(*args, **kwargs):
        return LogicAuditOutput(status="FAIL", justification="Invariant SEC-01 violated", violated_invariants=["SEC-01"])

    monkeypatch.setattr(_mod.GLMAdapter, "audit_logic_and_security", fake_audit_fail)

    success = resume_audit(task_id, base_branch="dev", repo_root=tmp_path)
    assert success is False

    sm_after = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    # Consumed standard security replan
    assert sm_after.data["budgets"]["security_replans_used"] == initial_sec_replans + 1


# ---------------------------------------------------------------------------
# TEST 9 — No credentials leak into stdout, exceptions, JSON, or reports
# ---------------------------------------------------------------------------
def test_resume_audit_no_credentials_leak(tmp_path, monkeypatch, capsys):
    setup_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    task_id = "TASK-SECRET-AUDIT"
    setup_task_in_human_review(tmp_path, task_id)

    secret_key = "AIzaSySecretLeakTestValue12345678"
    monkeypatch.setenv("GEMINI_API_KEY", secret_key)
    monkeypatch.setenv("GLM_API_KEY", secret_key)

    def fake_audit_leak(*args, **kwargs):
        raise NetworkTransportError(
            message=f"403 Client Error for url: https://api.example.com?key={secret_key}",
            status_code=403
        )

    monkeypatch.setattr(_mod.GLMAdapter, "audit_logic_and_security", fake_audit_leak)

    resume_audit(task_id, base_branch="dev", repo_root=tmp_path)

    captured = capsys.readouterr()
    assert secret_key not in captured.out
    assert secret_key not in captured.err

    state_file = tmp_path / "orchestrator" / "state" / f"state_{task_id}.json"
    assert secret_key not in state_file.read_text(encoding="utf-8")

    report_file = tmp_path / f"HUMAN_REVIEW_{task_id}.md"
    assert report_file.exists()
    assert secret_key not in report_file.read_text(encoding="utf-8")
