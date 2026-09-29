"""Round 3.6: public state APIs must preserve authoritative terminal state."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from orchestrator.state_manager import StateManager


def manager(tmp_path):
    return StateManager('R36', state_dir=str(tmp_path / 'state'))


@pytest.mark.parametrize('target', ['AUTO_MERGE', 'LOGIC_AUDIT'])
def test_terminal_transition_rejected(tmp_path, monkeypatch, target):
    monkeypatch.chdir(tmp_path)
    sm = manager(tmp_path)
    sm.halt_human('merge failed', exit_process=False)
    with pytest.raises(RuntimeError):
        sm.transition(target)
    assert manager(tmp_path).data['current_state'] == 'HALT_HUMAN'


def test_terminal_status_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sm = manager(tmp_path)
    sm.halt_human('merge failed', exit_process=False)
    with pytest.raises(RuntimeError):
        sm.set_execution_status('RUNNING')


def test_stale_snapshot_cannot_erase_terminal_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stale, active = manager(tmp_path), manager(tmp_path)
    active.halt_human('merge failed', exit_process=False)
    with pytest.raises((RuntimeError, AttributeError)):
        stale.save()
    assert manager(tmp_path).data['current_state'] == 'HALT_HUMAN'


def test_delete_authoritative_state_fails_closed(tmp_path):
    sm = manager(tmp_path)
    sm.state_file.unlink()
    with pytest.raises(RuntimeError):
        sm.register_worker_run()
    with pytest.raises(RuntimeError):
        manager(tmp_path)


def test_data_is_observation_not_mutation_api(tmp_path):
    sm = manager(tmp_path)
    sm.data['current_state'] = 'AUTO_MERGE'
    assert sm.data['current_state'] == 'INIT'


def test_generation_advances_and_concurrent_updates_survive(tmp_path):
    sm = manager(tmp_path)
    generation = sm.data.get('generation', -1)
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(lambda _: manager(tmp_path).register_worker_run(), range(2))) == [True, True]
    current = manager(tmp_path).data
    assert current['budgets']['total_cumulative_worker_runs'] == 2
    assert current['generation'] == generation + 2


@pytest.mark.parametrize('method', ['execute_merge_recovery_transition', 'execute_audit_recovery_transition'])
def test_recovery_requires_capability(tmp_path, monkeypatch, method):
    monkeypatch.chdir(tmp_path)
    sm = manager(tmp_path)
    sm.halt_human('merge failed', exit_process=False)
    with pytest.raises((RuntimeError, TypeError)):
        getattr(sm, method)('forged authorization')


def test_persistence_primitive_rejects_unlocked_call(tmp_path):
    sm = manager(tmp_path)
    with pytest.raises(RuntimeError):
        sm._persist()


def test_failed_atomic_replace_preserves_prior_state(tmp_path, monkeypatch):
    import orchestrator.state_manager as module
    sm = manager(tmp_path)
    before = sm.state_file.read_bytes()
    def broken(*args):
        raise OSError('injected replace failure')
    monkeypatch.setattr(module.os, 'replace', broken)
    with pytest.raises(OSError):
        sm.register_worker_run()
    assert sm.state_file.read_bytes() == before
    assert json.loads(before)['budgets']['total_cumulative_worker_runs'] == 0
