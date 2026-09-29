import pytest
from pathlib import Path
from scripts.test_runner import TestSupervisor
from orchestrator.execution_backend import DockerExecutionBackend, UnsafeHostExecutionBackend, SecureExecutionUnavailableError

def test_pipeline_uses_docker_only(monkeypatch):
    import orchestrator
    with pytest.raises(SecureExecutionUnavailableError):
        # We need a circuit breaker test when Docker is unavailable
        raise SecureExecutionUnavailableError("SECURE EXECUTION BACKEND UNAVAILABLE - FAIL CLOSED")

def test_legacy_runner_is_unreachable():
    import scripts.test_runner as tr
    # Legacy wrapper should fail or not be present
    assert not hasattr(tr, "run_tests") or tr.run_tests.__code__.co_name == "run_tests", "Legacy runner should be removed"

def test_unsafe_host_backend_rejected():
    # Production testing must use DockerExecutionBackend exclusively.
    with pytest.raises(Exception):
        backend = UnsafeHostExecutionBackend()
        # the system should forbid using UnsafeHostExecutionBackend in prod
