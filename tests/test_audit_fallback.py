"""
tests/test_audit_fallback.py - Comprehensive test suite for deterministic multi-provider
Logic Security audit fallback policy.

Covers:
  1. Primary Gemini PASS -> zero fallback
  2. Gemini 429 -> DeepSeek PASS
  3. Gemini 503 -> DeepSeek PASS
  4. Gemini unavailable -> DeepSeek unavailable -> Qwen PASS
  5. Gemini unavailable -> DeepSeek unavailable -> Qwen unavailable -> Gemini 3.6 PASS
  6. DeepSeek FAIL semántico -> Qwen NO se invoca
  7. Qwen FAIL semántico -> Gemini 3.6 NO se invoca
  8. UNCERTAIN -> HUMAN_REVIEW sin fallback
  9. Fallback exhaustion -> HUMAN_REVIEW
 10. Provider desconocido -> fail closed
 11. Orden exacto de candidates
 12. audit_model_used correcto para Gemini, DeepSeek y Qwen
 13. Budgets y epoch intactos ante fallos de disponibilidad
 14. 0 llamadas a Worker/Architect/Triage/SPEC/DIFF/TEST/SAST durante resume-audit
 15. --resume-audit reutiliza exactamente la misma política de fallback
 16. Ninguna credencial aparece en logs/state/reportes
 17. Qwen usa DASHSCOPE_API_KEY de forma segura y no la coloca en URLs
 18. Backward compatibility si fallbacks no existe
"""

import json
import os
import subprocess
from pathlib import Path
import pytest

from orchestrator.state_manager import StateManager
from adapters.contracts import LogicAuditOutput
from adapters.network_retry import NetworkTransportError
from adapters import (
    GeminiAdapter,
    DeepSeekAdapter,
    GLMAdapter,
    QwenAdapter,
    sanitize_secret_text
)
import importlib.util

_spec = importlib.util.spec_from_file_location("orchestrator_app", Path(__file__).resolve().parent.parent / "orchestrator.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

create_security_adapter = _mod.create_security_adapter
execute_logic_security_audit = _mod.execute_logic_security_audit
resume_audit = _mod.resume_audit

DEFAULT_FALLBACK_CONFIG = {
    "provider": "gemini",
    "model": "gemini-3.8-flash",
    "fallbacks": [
        {"provider": "deepseek", "model": "deepseek-flash"},
        {"provider": "qwen", "model": "qwen3.8-flash"},
        {"provider": "gemini", "model": "gemini-3.6-flash"}
    ]
}


def setup_test_state_and_spec(tmp_path: Path, task_id: str):
    """Sets up a minimal test environment with spec and state manager."""
    state_dir = tmp_path / "orchestrator" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    spec_path = specs_dir / f"{task_id}.md"
    spec_path.write_text(f"# {task_id}\n\n[SEC-01] Test security invariant.\n", encoding="utf-8")

    sm = StateManager(task_id, state_dir=str(state_dir), raise_on_halt=False)
    sm.transition("LOGIC_AUDIT", "Starting audit...")
    return sm, spec_path


# ---------------------------------------------------------------------------
# TEST 10 & FACTORY: Adapter factory for each provider and fail closed
# ---------------------------------------------------------------------------
def test_10_adapter_factory_supported_providers_and_fail_closed():
    # 1. Gemini
    client_gemini = create_security_adapter("gemini", "gemini-3.8-flash", simulate=True)
    assert isinstance(client_gemini, GeminiAdapter)
    assert client_gemini.model == "gemini-3.8-flash"
    assert client_gemini.is_simulation is True

    # 2. DeepSeek
    client_deepseek = create_security_adapter("deepseek", "deepseek-flash", simulate=True)
    assert isinstance(client_deepseek, DeepSeekAdapter)
    assert client_deepseek.model == "deepseek-flash"

    # 3. Qwen
    client_qwen = create_security_adapter("qwen", "qwen3.8-flash", simulate=True)
    assert isinstance(client_qwen, QwenAdapter)
    assert client_qwen.model == "qwen3.8-flash"

    client_dashscope = create_security_adapter("dashscope", "qwen3.8-flash", simulate=True)
    assert isinstance(client_dashscope, QwenAdapter)

    # 4. GLM
    client_glm = create_security_adapter("glm", "glm-5.3", simulate=True)
    assert isinstance(client_glm, GLMAdapter)
    assert client_glm.model == "glm-5.3"

    # 5. Unknown provider fails closed
    with pytest.raises(ValueError) as exc_info:
        create_security_adapter("unknown_provider", "foo-model")
    assert "Unsupported security logic audit provider" in str(exc_info.value)
    assert "unknown_provider" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TEST 1: Primary Gemini PASS -> zero fallback
# ---------------------------------------------------------------------------
def test_01_primary_gemini_pass_no_fallback(tmp_path, monkeypatch):
    task_id = "TASK-TEST-01"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    calls = []
    def fake_gemini_audit(self, spec, diff):
        calls.append(f"gemini:{self.model}")
        return LogicAuditOutput(status="PASS", justification="Primary passed", violated_invariants=[])

    def fake_deepseek_audit(self, spec, diff):
        calls.append(f"deepseek:{self.model}")
        return LogicAuditOutput(status="PASS", justification="DeepSeek passed", violated_invariants=[])

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_gemini_audit)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_deepseek_audit)

    passed, res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff --git a/test.py",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    assert passed is True
    assert res.status == "PASS"
    assert model_info == {"provider": "gemini", "model": "gemini-3.8-flash"}
    assert calls == ["gemini:gemini-3.8-flash"]
    assert sm.data["audit_model_used"] == {"provider": "gemini", "model": "gemini-3.8-flash"}


# ---------------------------------------------------------------------------
# TEST 2: Gemini 429 -> DeepSeek PASS
# ---------------------------------------------------------------------------
def test_02_gemini_429_triggers_deepseek_pass(tmp_path, monkeypatch):
    task_id = "TASK-TEST-02"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    calls = []
    def fake_gemini_429(self, spec, diff):
        calls.append(f"gemini:{self.model}")
        raise NetworkTransportError("Rate limit exceeded", status_code=429)

    def fake_deepseek_pass(self, spec, diff):
        calls.append(f"deepseek:{self.model}")
        return LogicAuditOutput(status="PASS", justification="DeepSeek verified invariants", violated_invariants=[])

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_gemini_429)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_deepseek_pass)

    passed, res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff --git a/test.py",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    assert passed is True
    assert res.status == "PASS"
    assert model_info == {"provider": "deepseek", "model": "deepseek-flash"}
    assert calls == ["gemini:gemini-3.8-flash", "deepseek:deepseek-flash"]
    assert sm.data["audit_model_used"] == {"provider": "deepseek", "model": "deepseek-flash"}


# ---------------------------------------------------------------------------
# TEST 3: Gemini 503 -> DeepSeek PASS
# ---------------------------------------------------------------------------
def test_03_gemini_503_triggers_deepseek_pass(tmp_path, monkeypatch):
    task_id = "TASK-TEST-03"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    calls = []
    def fake_gemini_503(self, spec, diff):
        calls.append(f"gemini:{self.model}")
        raise NetworkTransportError("Service unavailable", status_code=503)

    def fake_deepseek_pass(self, spec, diff):
        calls.append(f"deepseek:{self.model}")
        return LogicAuditOutput(status="PASS", justification="DeepSeek passed after 503", violated_invariants=[])

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_gemini_503)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_deepseek_pass)

    passed, res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff --git a/test.py",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    assert passed is True
    assert model_info == {"provider": "deepseek", "model": "deepseek-flash"}
    assert calls == ["gemini:gemini-3.8-flash", "deepseek:deepseek-flash"]


# ---------------------------------------------------------------------------
# TEST 4: Gemini unavailable -> DeepSeek unavailable -> Qwen PASS
# ---------------------------------------------------------------------------
def test_04_gemini_deepseek_unavailable_qwen_pass(tmp_path, monkeypatch):
    task_id = "TASK-TEST-04"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    calls = []
    def fake_gemini(self, spec, diff):
        calls.append(f"gemini:{self.model}")
        raise NetworkTransportError("Gemini 429", status_code=429)

    def fake_deepseek(self, spec, diff):
        calls.append(f"deepseek:{self.model}")
        raise NetworkTransportError("DeepSeek 503", status_code=503)

    def fake_qwen(self, spec, diff):
        calls.append(f"qwen:{self.model}")
        return LogicAuditOutput(status="PASS", justification="Qwen verified invariants", violated_invariants=[])

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_gemini)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_deepseek)
    monkeypatch.setattr(QwenAdapter, "audit_logic_and_security", fake_qwen)

    passed, res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    assert passed is True
    assert model_info == {"provider": "qwen", "model": "qwen3.8-flash"}
    assert calls == ["gemini:gemini-3.8-flash", "deepseek:deepseek-flash", "qwen:qwen3.8-flash"]
    assert sm.data["audit_model_used"] == {"provider": "qwen", "model": "qwen3.8-flash"}


# ---------------------------------------------------------------------------
# TEST 5: Gemini -> DeepSeek -> Qwen unavailable -> Gemini 3.6 PASS
# ---------------------------------------------------------------------------
def test_05_all_unavailable_until_gemini_36_pass(tmp_path, monkeypatch):
    task_id = "TASK-TEST-05"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    calls = []
    def fake_gemini(self, spec, diff):
        calls.append(f"gemini:{self.model}")
        if self.model == "gemini-3.8-flash":
            raise NetworkTransportError("Gemini 3.8 429", status_code=429)
        elif self.model == "gemini-3.6-flash":
            return LogicAuditOutput(status="PASS", justification="Gemini 3.6 passed", violated_invariants=[])
        raise RuntimeError("Unexpected model")

    def fake_deepseek(self, spec, diff):
        calls.append(f"deepseek:{self.model}")
        raise NetworkTransportError("DeepSeek timeout")

    def fake_qwen(self, spec, diff):
        calls.append(f"qwen:{self.model}")
        raise NetworkTransportError("Qwen 504", status_code=504)

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_gemini)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_deepseek)
    monkeypatch.setattr(QwenAdapter, "audit_logic_and_security", fake_qwen)

    passed, res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    assert passed is True
    assert model_info == {"provider": "gemini", "model": "gemini-3.6-flash"}
    assert calls == [
        "gemini:gemini-3.8-flash",
        "deepseek:deepseek-flash",
        "qwen:qwen3.8-flash",
        "gemini:gemini-3.6-flash"
    ]
    assert sm.data["audit_model_used"] == {"provider": "gemini", "model": "gemini-3.6-flash"}


# ---------------------------------------------------------------------------
# TEST 6: DeepSeek FAIL semántico -> Qwen NO se invoca
# ---------------------------------------------------------------------------
def test_06_deepseek_fail_semantic_no_qwen_fallback(tmp_path, monkeypatch):
    task_id = "TASK-TEST-06"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    calls = []
    def fake_gemini(self, spec, diff):
        calls.append(f"gemini:{self.model}")
        raise NetworkTransportError("Gemini 429", status_code=429)

    def fake_deepseek_fail(self, spec, diff):
        calls.append(f"deepseek:{self.model}")
        return LogicAuditOutput(
            status="FAIL",
            violated_invariants=["SEC-01"],
            justification="Buffer overflow vulnerability found"
        )

    def fake_qwen(self, spec, diff):
        calls.append(f"qwen:{self.model}")
        return LogicAuditOutput(status="PASS", justification="Should not be called", violated_invariants=[])

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_gemini)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_deepseek_fail)
    monkeypatch.setattr(QwenAdapter, "audit_logic_and_security", fake_qwen)

    security_replans_before = sm.data["budgets"]["security_replans_used"]

    passed, res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    # 1. Audit failed semantically
    assert passed is False
    assert res.status == "FAIL"
    assert model_info is None

    # 2. Qwen was NEVER invoked
    assert calls == ["gemini:gemini-3.8-flash", "deepseek:deepseek-flash"]

    # 3. Security replan budget was consumed
    assert sm.data["budgets"]["security_replans_used"] == security_replans_before + 1


# ---------------------------------------------------------------------------
# TEST 7: Qwen FAIL semántico -> Gemini 3.6 NO se invoca
# ---------------------------------------------------------------------------
def test_07_qwen_fail_semantic_no_gemini36_fallback(tmp_path, monkeypatch):
    task_id = "TASK-TEST-07"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    calls = []
    def fake_gemini(self, spec, diff):
        calls.append(f"gemini:{self.model}")
        raise NetworkTransportError("429", status_code=429)

    def fake_deepseek(self, spec, diff):
        calls.append(f"deepseek:{self.model}")
        raise NetworkTransportError("503", status_code=503)

    def fake_qwen_fail(self, spec, diff):
        calls.append(f"qwen:{self.model}")
        return LogicAuditOutput(
            status="FAIL",
            violated_invariants=["SEC-02"],
            justification="Insecure deserialization detected"
        )

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_gemini)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_deepseek)
    monkeypatch.setattr(QwenAdapter, "audit_logic_and_security", fake_qwen_fail)

    passed, res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    assert passed is False
    assert res.status == "FAIL"
    assert calls == ["gemini:gemini-3.8-flash", "deepseek:deepseek-flash", "qwen:qwen3.8-flash"]


# ---------------------------------------------------------------------------
# TEST 8: UNCERTAIN -> HUMAN_REVIEW sin fallback
# ---------------------------------------------------------------------------
def test_08_uncertain_status_transitions_to_human_review_without_fallback(tmp_path, monkeypatch):
    task_id = "TASK-TEST-08"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    calls = []
    def fake_gemini_uncertain(self, spec, diff):
        calls.append(f"gemini:{self.model}")
        return LogicAuditOutput(
            status="UNCERTAIN",
            violated_invariants=[],
            justification="Model uncertain about concurrency model"
        )

    def fake_deepseek(self, spec, diff):
        calls.append(f"deepseek:{self.model}")
        return LogicAuditOutput(status="PASS", justification="Unreachable", violated_invariants=[])

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_gemini_uncertain)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_deepseek)

    passed, res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    assert passed is False
    assert res.status == "UNCERTAIN"
    assert calls == ["gemini:gemini-3.8-flash"]
    assert sm.data["current_state"] == "HUMAN_REVIEW"
    assert sm.data["execution_status"] == "NEEDS_HUMAN_REVIEW"


# ---------------------------------------------------------------------------
# TEST 9: Fallback exhaustion -> HUMAN_REVIEW
# ---------------------------------------------------------------------------
def test_09_fallback_exhaustion_transitions_to_human_review(tmp_path, monkeypatch):
    task_id = "TASK-TEST-09"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    def fake_transport_error(self, spec, diff):
        raise NetworkTransportError(f"{self.model} rate limit", status_code=429)

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_transport_error)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_transport_error)
    monkeypatch.setattr(QwenAdapter, "audit_logic_and_security", fake_transport_error)

    passed, res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    assert passed is False
    assert res is None
    assert sm.data["current_state"] == "HUMAN_REVIEW"
    assert sm.data["execution_status"] == "NEEDS_HUMAN_REVIEW"
    assert sm.data["blocked_reason"]["gate"] == "LOGIC_AUDIT"
    assert "All logic security audit models unavailable" in sm.data["blocked_reason"]["reason"]


# ---------------------------------------------------------------------------
# TEST 11: Exact candidate ordering
# ---------------------------------------------------------------------------
def test_11_exact_candidate_ordering_preserved(tmp_path, monkeypatch):
    task_id = "TASK-TEST-11"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    order_attempted = []
    def record_call(provider, model):
        order_attempted.append(f"{provider}:{model}")
        raise NetworkTransportError("transient error", status_code=503)

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", lambda s, spec, diff: record_call("gemini", s.model))
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", lambda s, spec, diff: record_call("deepseek", s.model))
    monkeypatch.setattr(QwenAdapter, "audit_logic_and_security", lambda s, spec, diff: record_call("qwen", s.model))

    execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    expected_order = [
        "gemini:gemini-3.8-flash",
        "deepseek:deepseek-flash",
        "qwen:qwen3.8-flash",
        "gemini:gemini-3.6-flash"
    ]
    assert order_attempted == expected_order


# ---------------------------------------------------------------------------
# TEST 12: audit_model_used correct for Gemini, DeepSeek y Qwen
# ---------------------------------------------------------------------------
def test_12_audit_model_used_structured_ledger(tmp_path):
    task_id = "TASK-TEST-12"
    sm, _ = setup_test_state_and_spec(tmp_path, task_id)

    sm.record_audit_model("gemini", "gemini-3.8-flash")
    assert sm.data["audit_model_used"] == {"provider": "gemini", "model": "gemini-3.8-flash"}

    sm.record_audit_model("deepseek", "deepseek-flash")
    assert sm.data["audit_model_used"] == {"provider": "deepseek", "model": "deepseek-flash"}

    sm.record_audit_model("qwen", "qwen3.8-flash")
    assert sm.data["audit_model_used"] == {"provider": "qwen", "model": "qwen3.8-flash"}


# ---------------------------------------------------------------------------
# TEST 13: Budgets and epoch intact on availability failures
# ---------------------------------------------------------------------------
def test_13_budgets_and_epoch_intact_on_availability_failures(tmp_path, monkeypatch):
    task_id = "TASK-TEST-13"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    before_budgets = sm.data["budgets"].copy()
    before_epoch = sm.data["epoch"]

    def fake_avail_error(self, spec, diff):
        raise NetworkTransportError("HTTP 429 quota exhausted", status_code=429)

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_avail_error)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_avail_error)
    monkeypatch.setattr(QwenAdapter, "audit_logic_and_security", fake_avail_error)

    execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    assert sm.data["budgets"] == before_budgets
    assert sm.data["epoch"] == before_epoch


# ---------------------------------------------------------------------------
# TEST 14 & 15: --resume-audit reuses exact same fallback policy + zero unrelated calls
# ---------------------------------------------------------------------------
def test_14_and_15_resume_audit_with_fallback_and_zero_unrelated_calls(tmp_path, monkeypatch):
    # Setup full mock git repo
    subprocess.run(["git", "init", "-b", "dev"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=tmp_path, capture_output=True, check=True)
    (tmp_path / ".gitignore").write_text(
        ".worktrees/\n"
        "orchestrator/state/\n"
        "orchestrator/payloads/\n"
        "CRASH_REPORT_*.md\n"
        "HUMAN_REVIEW_*.md\n",
        encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("dev\n", encoding="utf-8")
    (tmp_path / "specs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "orchestrator" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".worktrees").mkdir(parents=True, exist_ok=True)

    config = {
        "budgets": {
            "max_logic_replans": 2,
            "max_security_replans": 1,
            "max_spec_syntax_retries": 1,
            "max_worker_per_epoch": 2,
            "max_cumulative_worker_runs": 5
        },
        "roles": {
            "logic_security": DEFAULT_FALLBACK_CONFIG
        }
    }
    (tmp_path / "orchestrator" / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init dev"], cwd=tmp_path, check=True)

    task_id = "TASK-RESUME-FALLBACK"
    spec_file = tmp_path / "specs" / f"{task_id}.md"
    spec_file.write_text(f"# {task_id}\n\n[SEC-01] Test\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "spec commit"], cwd=tmp_path, check=True)

    subprocess.run(["git", "checkout", "-b", f"task/{task_id}"], cwd=tmp_path, check=True)
    (tmp_path / "feature.py").write_text("def test(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "feat commit"], cwd=tmp_path, check=True)
    subprocess.run(["git", "checkout", "dev"], cwd=tmp_path, check=True)

    wt_dir = tmp_path / ".worktrees" / f"wt_{task_id}"
    subprocess.run(["git", "worktree", "add", str(wt_dir), f"task/{task_id}"], cwd=tmp_path, check=True)

    sm = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    sm.data["current_state"] = "HUMAN_REVIEW"
    sm.data["execution_status"] = "NEEDS_HUMAN_REVIEW"
    sm.data["blocked_reason"] = {"gate": "LOGIC_AUDIT", "reason": "rate limit"}
    sm.data["history"] = [
        {"from": "INIT", "to": "SPEC_GATE", "details": "", "epoch": 1},
        {"from": "SPEC_GATE", "to": "BUILDING", "details": "", "epoch": 1},
        {"from": "BUILDING", "to": "LOGIC_AUDIT", "details": "", "epoch": 1},
        {"from": "LOGIC_AUDIT", "to": "HUMAN_REVIEW", "details": "429 rate limit", "epoch": 1}
    ]
    sm.save()

    # Track calls to ensure zero calls to unrelated agents
    unrelated_calls = []
    monkeypatch.setattr(_mod, "run_tests", lambda *a, **kw: unrelated_calls.append("run_tests"))
    monkeypatch.setattr(_mod, "run_sast", lambda *a, **kw: unrelated_calls.append("run_sast"))
    monkeypatch.setattr(_mod, "validate_spec", lambda *a, **kw: unrelated_calls.append("validate_spec"))
    monkeypatch.setattr(_mod, "validate_diff", lambda *a, **kw: unrelated_calls.append("validate_diff"))

    # Primary Gemini fails (429), DeepSeek succeeds!
    audit_calls = []
    def fake_gemini(self, spec, diff):
        audit_calls.append(f"gemini:{self.model}")
        raise NetworkTransportError("429 rate limit", status_code=429)

    def fake_deepseek(self, spec, diff):
        audit_calls.append(f"deepseek:{self.model}")
        return LogicAuditOutput(status="PASS", justification="DeepSeek passed in resume-audit", violated_invariants=[])

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_gemini)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_deepseek)

    success = resume_audit(task_id, base_branch="dev", repo_root=tmp_path)

    # 1. Successful resume
    assert success is True
    assert audit_calls == ["gemini:gemini-3.8-flash", "deepseek:deepseek-flash"]

    # 2. Zero unrelated agent or gate calls
    assert unrelated_calls == []

    # 3. State finalized as COMPLETED and merged
    sm_after = StateManager(task_id, config_path=str(tmp_path / "orchestrator" / "config.json"), state_dir=str(tmp_path / "orchestrator" / "state"))
    assert sm_after.data["execution_status"] == "COMPLETED"
    assert sm_after.data["audit_model_used"] == {"provider": "deepseek", "model": "deepseek-flash"}


# ---------------------------------------------------------------------------
# TEST 16: Credential hygiene in logs/state/reports
# ---------------------------------------------------------------------------
def test_16_credential_hygiene_in_fallback_records(tmp_path, monkeypatch):
    dummy_key = "sk-super-secret-dashscope-99999"
    monkeypatch.setenv("DASHSCOPE_API_KEY", dummy_key)

    task_id = "TASK-TEST-16"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    def fake_failing_with_secret(self, spec, diff):
        raise NetworkTransportError(f"HTTP 429 error with key {dummy_key} on https://api.aliyun.com?key={dummy_key}", status_code=429)

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_failing_with_secret)
    monkeypatch.setattr(DeepSeekAdapter, "audit_logic_and_security", fake_failing_with_secret)
    monkeypatch.setattr(QwenAdapter, "audit_logic_and_security", fake_failing_with_secret)

    execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff",
        sec_role=DEFAULT_FALLBACK_CONFIG,
        simulate=False,
        exit_process=False
    )

    state_json = sm.state_file.read_text(encoding="utf-8")
    assert dummy_key not in state_json
    assert "[REDACTED_API_KEY]" in state_json


# ---------------------------------------------------------------------------
# TEST 17: Qwen uses DASHSCOPE_API_KEY safely and never in URLs
# ---------------------------------------------------------------------------
def test_17_qwen_uses_dashscope_api_key_safely_never_in_url(monkeypatch):
    dummy_dashscope = "sk-dashscope-token-abcdef123456"
    captured_requests = []

    class FakeResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "status": "PASS",
                            "violated_invariants": [],
                            "justification": "Qwen passed safely"
                        })
                    }
                }]
            }

    def fake_post(url, json=None, headers=None, timeout=None):
        captured_requests.append({"url": url, "headers": headers, "json": json})
        return FakeResponse()

    import requests
    monkeypatch.setattr(requests, "post", fake_post)

    adapter = QwenAdapter(model="qwen3.8-flash", api_key=dummy_dashscope)
    res = adapter.audit_logic_and_security("spec content", "code diff")

    assert res.status == "PASS"
    assert len(captured_requests) == 1
    req = captured_requests[0]

    # API key is NEVER in URL
    assert dummy_dashscope not in req["url"]
    assert "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions" in req["url"]

    # API key is only in Authorization Bearer header
    assert req["headers"]["Authorization"] == f"Bearer {dummy_dashscope}"


# ---------------------------------------------------------------------------
# TEST 18: Backward compatibility if fallbacks is absent
# ---------------------------------------------------------------------------
def test_18_backward_compatibility_when_fallbacks_missing(tmp_path, monkeypatch):
    task_id = "TASK-TEST-18"
    sm, spec_path = setup_test_state_and_spec(tmp_path, task_id)

    sec_role_no_fallbacks = {
        "provider": "gemini",
        "model": "gemini-3.8-flash"
    }

    calls = []
    def fake_gemini_pass(self, spec, diff):
        calls.append(f"gemini:{self.model}")
        return LogicAuditOutput(status="PASS", justification="Solo primary passed", violated_invariants=[])

    monkeypatch.setattr(GeminiAdapter, "audit_logic_and_security", fake_gemini_pass)

    passed, res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output="diff",
        sec_role=sec_role_no_fallbacks,
        simulate=False,
        exit_process=False
    )

    assert passed is True
    assert model_info == {"provider": "gemini", "model": "gemini-3.8-flash"}
    assert calls == ["gemini:gemini-3.8-flash"]
