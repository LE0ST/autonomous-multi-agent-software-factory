import json
import pytest
from pathlib import Path
from orchestrator.state_manager import StateManager

def test_state_manager_initialization(tmp_path):
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-TEST-01", state_dir=str(state_dir), raise_on_halt=True)
    
    assert sm.data["task_id"] == "TASK-TEST-01"
    assert sm.data["epoch"] == 1
    assert sm.data["current_state"] == "INIT"
    assert sm.data["execution_status"] == "RUNNING"
    assert sm.data["budgets"]["total_cumulative_worker_runs"] == 0
    assert sm.data["budgets"]["logic_replans_used"] == 0
    assert sm.data["budgets"]["security_replans_used"] == 0
    assert sm.data["budgets"]["spec_syntax_retries_used"] == 0

def test_state_transitions(tmp_path):
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-TEST-02", state_dir=str(state_dir), raise_on_halt=True)
    
    sm.transition("SPEC_DESIGN", "Generating specification")
    assert sm.data["current_state"] == "SPEC_DESIGN"
    assert len(sm.data["history"]) == 1
    
    sm.transition("BUILDING", "Starting worker build")
    assert sm.data["current_state"] == "BUILDING"
    assert len(sm.data["history"]) == 2
    
    with pytest.raises(ValueError, match="Invalid state 'INVALID_STATE'"):
        sm.transition("INVALID_STATE")

def test_worker_runs_and_epoch_reset(tmp_path):
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-TEST-03", state_dir=str(state_dir), raise_on_halt=True)
    
    assert sm.can_worker_retry_in_epoch() is True
    sm.register_worker_run()
    assert sm.data["budgets"]["worker_attempts_in_epoch"] == 1
    assert sm.data["budgets"]["total_cumulative_worker_runs"] == 1
    
    sm.register_worker_run()
    assert sm.data["budgets"]["worker_attempts_in_epoch"] == 2
    assert sm.can_worker_retry_in_epoch() is False
    
    # Consuming a logic replan should trigger new epoch and reset worker_attempts_in_epoch
    sm.consume_logic_replan("Test failure triage")
    assert sm.data["epoch"] == 2
    assert sm.data["budgets"]["worker_attempts_in_epoch"] == 0
    assert sm.data["budgets"]["logic_replans_used"] == 1
    # But cumulative total remains intact
    assert sm.data["budgets"]["total_cumulative_worker_runs"] == 2
    assert sm.can_worker_retry_in_epoch() is True

def test_circuit_breaker_on_cumulative_worker_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-CB-01", state_dir=str(state_dir), raise_on_halt=True)
    
    # Execute 5 runs distributed across valid epochs
    # Epoch 1 (2 runs)
    sm.register_worker_run()
    sm.register_worker_run()
    sm.consume_logic_replan("replan 1")
    # Epoch 2 (2 runs)
    sm.register_worker_run()
    sm.register_worker_run()
    sm.consume_logic_replan("replan 2")
    # Epoch 3 (1 run -> 5 total cumulative)
    sm.register_worker_run()
    assert sm.data["budgets"]["total_cumulative_worker_runs"] == 5
    
    # 6th run must trigger Circuit Breaker due to independent cumulative ceiling
    with pytest.raises(RuntimeError, match="Circuit Breaker triggered.*Global cumulative"):
        sm.register_worker_run()
        
    assert sm.data["current_state"] == "HALT_HUMAN"
    assert sm.data["execution_status"] == "FAILED"
    
    report = tmp_path / "CRASH_REPORT_TASK-CB-01.md"
    assert report.exists()
    assert "CIRCUIT BREAKER TRIGGERED" in report.read_text(encoding="utf-8")

def test_circuit_breaker_on_worker_attempts_in_epoch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-EPOCH-01", state_dir=str(state_dir), raise_on_halt=True)

    # 1. With worker_attempts_in_epoch = 0, 1st Worker run is allowed
    assert sm.data["budgets"]["worker_attempts_in_epoch"] == 0
    assert sm.register_worker_run() is True
    assert sm.data["budgets"]["worker_attempts_in_epoch"] == 1
    assert sm.data["budgets"]["total_cumulative_worker_runs"] == 1

    # 2. With worker_attempts_in_epoch = 1, 2nd Worker run is allowed
    assert sm.register_worker_run() is True
    assert sm.data["budgets"]["worker_attempts_in_epoch"] == 2
    assert sm.data["budgets"]["total_cumulative_worker_runs"] == 2

    # 3. With worker_attempts_in_epoch = 2, 3rd Worker run is blocked before incrementing
    with pytest.raises(RuntimeError, match="Circuit Breaker triggered.*Worker attempt limit per epoch exceeded"):
        sm.register_worker_run()

    # Counters must remain intact and FSM in HALT_HUMAN
    assert sm.data["budgets"]["worker_attempts_in_epoch"] == 2
    assert sm.data["budgets"]["total_cumulative_worker_runs"] == 2
    assert sm.data["current_state"] == "HALT_HUMAN"
    assert sm.data["execution_status"] == "FAILED"

def test_circuit_breaker_on_security_replans(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-CB-02", state_dir=str(state_dir), raise_on_halt=True)
    
    # Maximum 1 security replan
    sm.consume_security_replan("Critical vulnerability 1")
    assert sm.data["budgets"]["security_replans_used"] == 1
    
    with pytest.raises(RuntimeError, match=r"(?i)Circuit Breaker triggered.*security"):
        sm.consume_security_replan("Critical vulnerability 2")

def test_interrupted_recovery(tmp_path):
    state_dir = tmp_path / "state"
    sm1 = StateManager("TASK-REC", state_dir=str(state_dir), raise_on_halt=True)
    assert sm1.data["execution_status"] == "RUNNING"
    
    # Simulate restart / new instance
    sm2 = StateManager("TASK-REC", state_dir=str(state_dir), raise_on_halt=True)
    assert sm2.data["execution_status"] == "INTERRUPTED"

def test_request_human_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-HR-01", state_dir=str(state_dir), raise_on_halt=True)

    with pytest.raises(RuntimeError, match="Human review required"):
        sm.request_human_review(reason="429 Rate limit exceeded on GLM", gate="LOGIC_AUDIT")

    assert sm.data["current_state"] == "HUMAN_REVIEW"
    assert sm.data["execution_status"] == "NEEDS_HUMAN_REVIEW"
    assert sm.data["blocked_reason"]["gate"] == "LOGIC_AUDIT"
    assert "429 Rate limit" in sm.data["blocked_reason"]["reason"]

    # Verify that NO Worker budgets or replans were consumed
    assert sm.data["budgets"]["worker_attempts_in_epoch"] == 0
    assert sm.data["budgets"]["total_cumulative_worker_runs"] == 0
    assert sm.data["budgets"]["security_replans_used"] == 0
    assert sm.data["budgets"]["logic_replans_used"] == 0

    report = tmp_path / "HUMAN_REVIEW_TASK-HR-01.md"
    assert report.exists()
    assert "HUMAN REVIEW REQUIRED" in report.read_text(encoding="utf-8")
