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
    
    sm.transition("SPEC_DESIGN", "Generando especificación")
    assert sm.data["current_state"] == "SPEC_DESIGN"
    assert len(sm.data["history"]) == 1
    
    sm.transition("BUILDING", "Iniciando compilación del worker")
    assert sm.data["current_state"] == "BUILDING"
    assert len(sm.data["history"]) == 2
    
    with pytest.raises(ValueError, match="Estado 'INVALID_STATE' inválido"):
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
    
    # Consumir un replan lógico debe generar nueva época y resetear worker_attempts_in_epoch
    sm.consume_logic_replan("Test failure triage")
    assert sm.data["epoch"] == 2
    assert sm.data["budgets"]["worker_attempts_in_epoch"] == 0
    assert sm.data["budgets"]["logic_replans_used"] == 1
    # Pero el total acumulado sigue intacto
    assert sm.data["budgets"]["total_cumulative_worker_runs"] == 2
    assert sm.can_worker_retry_in_epoch() is True

def test_circuit_breaker_on_cumulative_worker_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-CB-01", state_dir=str(state_dir), raise_on_halt=True)
    
    # Ejecutar 5 runs
    for _ in range(5):
        sm.register_worker_run()
    assert sm.data["budgets"]["total_cumulative_worker_runs"] == 5
    
    # El 6to run debe disparar Circuit Breaker
    with pytest.raises(RuntimeError, match="Circuit Breaker activado.*Presupuesto global"):
        sm.register_worker_run()
        
    assert sm.data["current_state"] == "HALT_HUMAN"
    assert sm.data["execution_status"] == "FAILED"
    
    report = tmp_path / "CRASH_REPORT_TASK-CB-01.md"
    assert report.exists()
    assert "CIRCUIT BREAKER ACTIVADO" in report.read_text(encoding="utf-8")

def test_circuit_breaker_on_security_replans(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-CB-02", state_dir=str(state_dir), raise_on_halt=True)
    
    # Máximo 1 security replan
    sm.consume_security_replan("Vulnerabilidad crítica 1")
    assert sm.data["budgets"]["security_replans_used"] == 1
    
    with pytest.raises(RuntimeError, match="Circuit Breaker activado.*seguridad"):
        sm.consume_security_replan("Vulnerabilidad crítica 2")

def test_interrupted_recovery(tmp_path):
    state_dir = tmp_path / "state"
    sm1 = StateManager("TASK-REC", state_dir=str(state_dir), raise_on_halt=True)
    assert sm1.data["execution_status"] == "RUNNING"
    
    # Simular reinicio / nueva instancia
    sm2 = StateManager("TASK-REC", state_dir=str(state_dir), raise_on_halt=True)
    assert sm2.data["execution_status"] == "INTERRUPTED"
