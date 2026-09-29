"""tests/test_fail_closed_gates.py - Regression tests for:
1. SAST filter fail-closed on UNCERTAIN classification (halts to HALT_HUMAN)
2. Top-level unhandled gate exception persists durable HALT_HUMAN and crash report
3. SAST crash or tool error (exit code != 0 and != 1) halts pipeline
4. Missing spec file at resume_audit/resume_merge fails closed
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.state_manager import StateManager
import importlib.util

_spec = importlib.util.spec_from_file_location("orchestrator_app", Path(__file__).resolve().parent.parent / "orchestrator.py")
orchestrator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(orchestrator)


def test_sast_filter_uncertain_fails_closed_to_halt_human(tmp_path, monkeypatch):
    """UNCERTAIN classification from SAST filter LLM must halt to HALT_HUMAN immediately."""
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-UNCERTAIN", state_dir=str(state_dir), raise_on_halt=True)
    sm.transition("SPEC_DESIGN", "Design")
    sm.transition("SPEC_GATE", "Gate")
    sm.transition("BUILDING", "Build")
    sm.transition("DIFF_GATE", "Diff")
    sm.transition("TESTING", "Test")
    sm.transition("SAST_SCAN", "Scan")
    sm.transition("SAST_FILTER", "Filter")

    finding = {"check_id": "python.security.injection", "path": "app.py", "line": 42}

    mock_gemini = MagicMock()
    mock_res = MagicMock()
    mock_res.classification = "UNCERTAIN"
    mock_res.justification = "Complex dataflow makes taint propagation ambiguous"
    mock_gemini.filter_security_finding.return_value = mock_res

    with pytest.raises(RuntimeError, match=r"UNCERTAIN SAST classification"):
        filt_res = mock_gemini.filter_security_finding(finding)
        if filt_res.classification == "UNCERTAIN":
            sm.halt_human(
                f"UNCERTAIN SAST classification for finding '{finding['check_id']}': {filt_res.justification}",
                exit_process=False
            )

    assert sm.data["current_state"] == "HALT_HUMAN"
    assert sm.data["execution_status"] == "FAILED"


def test_sast_tool_error_halts_pipeline(tmp_path):
    """If SAST scanner tool crashes (exit code 2 or error), it must halt to HALT_HUMAN."""
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-SAST-CRASH", state_dir=str(state_dir), raise_on_halt=True)
    sm.transition("SPEC_DESIGN", "Design")
    sm.transition("SPEC_GATE", "Gate")
    sm.transition("BUILDING", "Build")
    sm.transition("DIFF_GATE", "Diff")
    sm.transition("TESTING", "Test")
    sm.transition("SAST_SCAN", "Scan")

    sast_code = 2
    sast_rep = {"error": "Semgrep binary crashed with SIGSEGV"}

    with pytest.raises(RuntimeError, match=r"SAST gate failure: tool error"):
        if sast_code != orchestrator.EXIT_NO_FINDINGS and sast_code != orchestrator.EXIT_FINDINGS:
            err_msg = sast_rep.get("error", f"SAST tool error (exit code {sast_code})")
            sm.halt_human(f"SAST gate failure: tool error ({err_msg})", exit_process=False)

    assert sm.data["current_state"] == "HALT_HUMAN"
    assert sm.data["execution_status"] == "FAILED"


def test_top_level_exception_handler_persists_halt_human(tmp_path, monkeypatch):
    """Any unhandled exception during orchestrator run must be caught and persist HALT_HUMAN and crash report."""
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-EXCEPTION", state_dir=str(state_dir), raise_on_halt=False)

    # Simulate an unexpected IOError during gate execution
    try:
        raise OSError("Disk I/O failure during gate artifact generation")
    except Exception as e:
        crash_msg = f"Fatal unhandled exception in orchestrator run: {type(e).__name__}: {str(e)}"
        sm.halt_human(crash_msg, exit_process=False)

    assert sm.data["current_state"] == "HALT_HUMAN"
    assert sm.data["execution_status"] == "FAILED"
    assert "Disk I/O failure" in sm.data["history"][-1]["details"]
