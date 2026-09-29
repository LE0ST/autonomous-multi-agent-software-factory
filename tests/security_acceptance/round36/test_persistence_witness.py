"""Replaying an entire older state snapshot must fail even in a fresh process."""
import pytest
from orchestrator.state_manager import StateManager


def test_full_snapshot_rollback_is_detected_by_fresh_instance(tmp_path):
    directory = tmp_path / 'state'
    sm = StateManager('R36', state_dir=str(directory))
    old = sm.state_file.read_bytes()
    sm.register_worker_run()
    sm.state_file.write_bytes(old)
    with pytest.raises(RuntimeError):
        StateManager('R36', state_dir=str(directory))


def test_private_transaction_cannot_resurrect_terminal_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sm = StateManager('R36', state_dir=str(tmp_path / 'state'))
    sm.halt_human('failed', exit_process=False)
    def resurrect():
        sm._data['current_state'] = 'AUTO_MERGE'
        sm._data['execution_status'] = 'RUNNING'
    with pytest.raises(RuntimeError):
        sm._transaction(resurrect)
    assert sm.data['current_state'] == 'HALT_HUMAN'
