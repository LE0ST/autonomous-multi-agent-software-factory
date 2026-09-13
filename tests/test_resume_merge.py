"""
tests/test_resume_merge.py - Unit and integration test suite for the --resume-merge pathway.
Verifies:
  1. Valid recovery authorized by can_resume_merge()
  2. Block on invalid state
  3. Block on HALT_HUMAN caused by reason other than AUTO_MERGE
  4. Block when branch task/TASK-ID does not exist
  5. Block when main repository is dirty
  6. Successful Fast-Forward merge and COMPLETED status
  7. Block on branch divergence (no automatic rebase)
  8. Strict isolation: zero calls to pipeline, Worker, LLMs, or gates
  9. Strict budget preservation (no increments)
"""

import json
import subprocess
from pathlib import Path
import pytest

from orchestrator.state_manager import StateManager
import importlib.util

_spec = importlib.util.spec_from_file_location("orchestrator_app", Path(__file__).resolve().parent.parent / "orchestrator.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
resume_merge = _mod.resume_merge

def setup_git_repo(repo_dir: Path) -> str:
    """Initializes a clean Git repository with dev branch."""
    subprocess.run(["git", "init", "-b", "dev"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=repo_dir, capture_output=True, check=True)
    (repo_dir / ".gitignore").write_text("orchestrator/state/\norchestrator/payloads/\n", encoding="utf-8")
    (repo_dir / "README.md").write_text("initial dev content\n", encoding="utf-8")
    (repo_dir / "orchestrator").mkdir(parents=True, exist_ok=True)
    (repo_dir / "orchestrator" / "state").mkdir(parents=True, exist_ok=True)
    config = {
        "budgets": {
            "max_logic_replans": 2,
            "max_security_replans": 1,
            "max_spec_syntax_retries": 1,
            "max_worker_per_epoch": 2,
            "max_cumulative_worker_runs": 5
        }
    }
    (repo_dir / "orchestrator" / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit on dev"], cwd=repo_dir, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()

def setup_orchestrator_structure(repo_dir: Path):
    """Creates minimal configuration and state structure for isolated testing."""
    (repo_dir / "orchestrator").mkdir(parents=True, exist_ok=True)
    (repo_dir / "orchestrator" / "state").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# TEST 1 — Valid recovery
# ---------------------------------------------------------------------------
def test_can_resume_merge_valid(tmp_path):
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-RESUME-01", state_dir=str(state_dir), raise_on_halt=True)
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"].append({
        "timestamp": "2026-09-13T12:00:00Z",
        "from": "AUTO_MERGE",
        "to": "HALT_HUMAN",
        "details": "Fallo durante el merge Fast-Forward: El repositorio principal tiene modificaciones no commiteadas.",
        "epoch": 1
    })
    sm.save()

    can_resume, msg = sm.can_resume_merge()
    assert can_resume is True
    assert "authorized" in msg.lower()

# ---------------------------------------------------------------------------
# TEST 2 — Estado incorrecto
# ---------------------------------------------------------------------------
def test_can_resume_merge_invalid_state(tmp_path):
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-RESUME-02", state_dir=str(state_dir), raise_on_halt=True)
    sm.data["current_state"] = "TESTING"
    sm.data["execution_status"] = "RUNNING"
    sm.save()

    can_resume, msg = sm.can_resume_merge()
    assert can_resume is False
    assert "HALT_HUMAN" in msg or "FAILED" in msg

# ---------------------------------------------------------------------------
# TEST 3 — HALT_HUMAN por otra causa
# ---------------------------------------------------------------------------
def test_can_resume_merge_halt_other_cause(tmp_path):
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-RESUME-03", state_dir=str(state_dir), raise_on_halt=True)
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"].append({
        "timestamp": "2026-09-13T12:00:00Z",
        "from": "TESTING",
        "to": "HALT_HUMAN",
        "details": "Presupuesto de replanificación lógica agotado: tests fallaron",
        "epoch": 1
    })
    sm.save()

    can_resume, msg = sm.can_resume_merge()
    assert can_resume is False
    assert "AUTO_MERGE" in msg

# ---------------------------------------------------------------------------
# TEST 4 — Rama inexistente
# ---------------------------------------------------------------------------
def test_resume_merge_nonexistent_branch(tmp_path):
    setup_git_repo(tmp_path)
    setup_orchestrator_structure(tmp_path)

    task_id = "TASK-NOBRANCH"
    sm = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"].append({
        "timestamp": "2026-09-13T12:00:00Z",
        "from": "AUTO_MERGE",
        "to": "HALT_HUMAN",
        "details": "Fallo durante el merge Fast-Forward: lock error",
        "epoch": 1
    })
    sm.save()
    before_budgets = sm.data["budgets"].copy()

    res = resume_merge(task_id, base_branch="dev", repo_root=tmp_path)
    assert res is False

    sm_reloaded = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    assert sm_reloaded.data["execution_status"] != "COMPLETED"
    assert sm_reloaded.data["budgets"] == before_budgets

# ---------------------------------------------------------------------------
# TEST 5 — Repositorio sucio
# ---------------------------------------------------------------------------
def test_resume_merge_dirty_repository(tmp_path):
    setup_git_repo(tmp_path)
    setup_orchestrator_structure(tmp_path)

    task_id = "TASK-DIRTY"
    # Crear rama de tarea con commit
    subprocess.run(["git", "checkout", "-b", f"task/{task_id}"], cwd=tmp_path, check=True)
    (tmp_path / "code.py").write_text("valid code\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "feature commit"], cwd=tmp_path, check=True)
    subprocess.run(["git", "checkout", "dev"], cwd=tmp_path, check=True)

    # Dejar el repositorio dev sucio con cambios no commiteados
    (tmp_path / "dirty_file.txt").write_text("uncommitted changes\n", encoding="utf-8")

    sm = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"].append({
        "timestamp": "2026-09-13T12:00:00Z",
        "from": "AUTO_MERGE",
        "to": "HALT_HUMAN",
        "details": "Fallo durante el merge Fast-Forward: El repositorio principal tiene modificaciones no commiteadas.",
        "epoch": 1
    })
    sm.save()
    before_budgets = sm.data["budgets"].copy()

    res = resume_merge(task_id, base_branch="dev", repo_root=tmp_path)
    assert res is False

    sm_reloaded = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    assert sm_reloaded.data["execution_status"] != "COMPLETED"
    assert sm_reloaded.data["budgets"] == before_budgets

# ---------------------------------------------------------------------------
# TEST 6 — Fast-Forward exitoso
# ---------------------------------------------------------------------------
def test_resume_merge_fast_forward_success(tmp_path):
    setup_git_repo(tmp_path)
    setup_orchestrator_structure(tmp_path)

    task_id = "TASK-FF-OK"
    subprocess.run(["git", "checkout", "-b", f"task/{task_id}"], cwd=tmp_path, check=True)
    (tmp_path / "feature.py").write_text("def feature(): return True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "feat: implement feature"], cwd=tmp_path, check=True)
    task_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    subprocess.run(["git", "checkout", "dev"], cwd=tmp_path, check=True)

    sm = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"].append({
        "timestamp": "2026-09-13T12:00:00Z",
        "from": "AUTO_MERGE",
        "to": "HALT_HUMAN",
        "details": "Fallo durante el merge Fast-Forward: lock transitorio",
        "epoch": 1
    })
    sm.save()

    res = resume_merge(task_id, base_branch="dev", repo_root=tmp_path)
    assert res is True

    sm_reloaded = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    assert sm_reloaded.data["execution_status"] == "COMPLETED"
    assert sm_reloaded.data["current_state"] == "AUTO_MERGE"

    dev_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    assert dev_head == task_head
    assert (tmp_path / "feature.py").exists()

# ---------------------------------------------------------------------------
# TEST 7 — Fast-Forward rechazado (divergencia)
# ---------------------------------------------------------------------------
def test_resume_merge_divergence_rejected(tmp_path):
    setup_git_repo(tmp_path)
    setup_orchestrator_structure(tmp_path)

    task_id = "TASK-DIVERGED"
    subprocess.run(["git", "checkout", "-b", f"task/{task_id}"], cwd=tmp_path, check=True)
    (tmp_path / "task_code.py").write_text("task code\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "task commit"], cwd=tmp_path, check=True)

    # Avanzar dev de forma independiente creando divergencia
    subprocess.run(["git", "checkout", "dev"], cwd=tmp_path, check=True)
    (tmp_path / "dev_advance.py").write_text("dev advance\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "manual commit on dev causing divergence"], cwd=tmp_path, check=True)

    sm = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"].append({
        "timestamp": "2026-09-13T12:00:00Z",
        "from": "AUTO_MERGE",
        "to": "HALT_HUMAN",
        "details": "Fallo durante el merge Fast-Forward: ramas divergentes",
        "epoch": 1
    })
    sm.save()

    res = resume_merge(task_id, base_branch="dev", repo_root=tmp_path)
    assert res is False

    sm_reloaded = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    assert sm_reloaded.data["execution_status"] != "COMPLETED"

# ---------------------------------------------------------------------------
# TEST 8 — No ejecuta el pipeline ni invoca agentes/gates
# ---------------------------------------------------------------------------
def test_resume_merge_does_not_call_pipeline_or_agents(tmp_path, monkeypatch):
    setup_git_repo(tmp_path)
    setup_orchestrator_structure(tmp_path)

    task_id = "TASK-ISOLATED"
    subprocess.run(["git", "checkout", "-b", f"task/{task_id}"], cwd=tmp_path, check=True)
    (tmp_path / "isolated.py").write_text("isolated\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "feat: isolated commit"], cwd=tmp_path, check=True)
    subprocess.run(["git", "checkout", "dev"], cwd=tmp_path, check=True)

    sm = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"].append({
        "timestamp": "2026-09-13T12:00:00Z",
        "from": "AUTO_MERGE",
        "to": "HALT_HUMAN",
        "details": "Fallo durante el merge Fast-Forward",
        "epoch": 1
    })
    sm.save()

    calls = {
        "run_pipeline": 0,
        "worker": 0,
        "gemini": 0,
        "pytest": 0,
        "sast": 0,
        "triage": 0,
        "logic_audit": 0
    }

    def fail_pipeline(*args, **kwargs):
        calls["run_pipeline"] += 1
        raise AssertionError("run_pipeline must NOT be called during --resume-merge")
    monkeypatch.setattr(_mod, "run_pipeline", fail_pipeline)

    def fail_worker(*args, **kwargs):
        calls["worker"] += 1
        raise AssertionError("Worker must NOT be called during --resume-merge")
    monkeypatch.setattr("adapters.deepseek_adapter.DeepSeekAdapter.generate_code_and_tests", fail_worker)

    def fail_gemini_spec(*args, **kwargs):
        calls["gemini"] += 1
        raise AssertionError("Gemini Architect must NOT be called during --resume-merge")
    monkeypatch.setattr("adapters.gemini_adapter.GeminiAdapter.generate_spec", fail_gemini_spec)

    def fail_triage(*args, **kwargs):
        calls["triage"] += 1
        raise AssertionError("Triage must NOT be called during --resume-merge")
    monkeypatch.setattr("adapters.gemini_adapter.GeminiAdapter.triage_failure", fail_triage)

    def fail_tests(*args, **kwargs):
        calls["pytest"] += 1
        raise AssertionError("test_runner / pytest must NOT be called during --resume-merge")
    monkeypatch.setattr("scripts.test_runner.run_tests", fail_tests)

    def fail_sast(*args, **kwargs):
        calls["sast"] += 1
        raise AssertionError("sast_runner must NOT be called during --resume-merge")
    monkeypatch.setattr("scripts.sast_runner.run_sast", fail_sast)

    res = resume_merge(task_id, base_branch="dev", repo_root=tmp_path)
    assert res is True

    # Explicitly demonstrate that no agents or gates were called
    assert calls["run_pipeline"] == 0
    assert calls["worker"] == 0
    assert calls["gemini"] == 0
    assert calls["pytest"] == 0
    assert calls["sast"] == 0
    assert calls["triage"] == 0
    assert calls["logic_audit"] == 0

# ---------------------------------------------------------------------------
# TEST 9 — No consume budget
# ---------------------------------------------------------------------------
def test_resume_merge_preserves_budgets_exactly(tmp_path):
    setup_git_repo(tmp_path)
    setup_orchestrator_structure(tmp_path)

    task_id = "TASK-BUDGET-CHECK"
    subprocess.run(["git", "checkout", "-b", f"task/{task_id}"], cwd=tmp_path, check=True)
    (tmp_path / "budget_file.py").write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "task commit"], cwd=tmp_path, check=True)
    subprocess.run(["git", "checkout", "dev"], cwd=tmp_path, check=True)

    sm = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["budgets"]["worker_attempts_in_epoch"] = 2
    sm.data["budgets"]["total_cumulative_worker_runs"] = 2
    sm.data["budgets"]["logic_replans_used"] = 1
    sm.data["budgets"]["security_replans_used"] = 0
    sm.data["budgets"]["spec_syntax_retries_used"] = 0
    sm.data["history"].append({
        "timestamp": "2026-09-13T12:00:00Z",
        "from": "AUTO_MERGE",
        "to": "HALT_HUMAN",
        "details": "Fallo durante el merge Fast-Forward: lock transitorio",
        "epoch": 1
    })
    sm.save()

    before_budgets = sm.data["budgets"].copy()
    before_epoch = sm.data["epoch"]

    res = resume_merge(task_id, base_branch="dev", repo_root=tmp_path)
    assert res is True

    sm_reloaded = StateManager(
        task_id,
        config_path=str(tmp_path / "orchestrator" / "config.json"),
        state_dir=str(tmp_path / "orchestrator" / "state"),
        raise_on_halt=False
    )
    after_budgets = sm_reloaded.data["budgets"].copy()
    after_epoch = sm_reloaded.data["epoch"]

    assert after_budgets == before_budgets
    assert after_epoch == before_epoch
    assert after_budgets["worker_attempts_in_epoch"] == 2
    assert after_budgets["total_cumulative_worker_runs"] == 2
