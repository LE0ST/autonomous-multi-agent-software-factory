"""S1: a state-directory writer cannot reset durable authority in a fresh process."""
import json
import os
import subprocess
import sys

import pytest

from orchestrator.state_manager import StateManager
from ._support import INSTALLATION

PROBE = '''
import json, sys
sys.path.insert(0, sys.argv[1])
from orchestrator.state_manager import StateManager, CorruptStateError
try:
    sm = StateManager('S1', state_dir=sys.argv[2])
    state = sm.data
except CorruptStateError:
    print(json.dumps({'outcome': 'rejected'}))
else:
    print(json.dumps({'outcome': 'accepted', 'generation': state['generation'],
        'state': state['current_state'], 'status': state['execution_status'],
        'worker_runs': state['budgets']['total_cumulative_worker_runs']}))
'''


def probe(directory):
    proc = subprocess.run(
        [sys.executable, '-I', '-B', '-c', PROBE, str(INSTALLATION), str(directory)],
        cwd=directory.parent, capture_output=True, text=True, encoding='utf-8', timeout=30,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    # Import/process/permission failures are NOT secure-behavior evidence.
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    return json.loads(proc.stdout)


def files(directory):
    return {p.relative_to(directory): p.read_bytes() for p in directory.rglob('*') if p.is_file()}


@pytest.mark.parametrize('terminal', [False, True], ids=['spent-budget', 'terminal'])
def test_restoring_all_colocated_files_is_rejected_by_fresh_process(tmp_path, monkeypatch, terminal):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / 'state'
    sm = StateManager('S1', state_dir=str(directory))
    old = files(directory)
    assert sm.register_worker_run()
    if terminal:
        sm.halt_human('terminal fixture', exit_process=False)
    latest = probe(directory)
    assert latest['outcome'] == 'accepted' and latest['worker_runs'] == 1
    assert latest['generation'] > 0
    assert latest['state'] == ('HALT_HUMAN' if terminal else 'INIT')
    # Restore EVERY colocated file, not just today's JSON and lock witness.
    for path in directory.rglob('*'):
        if path.is_file():
            path.unlink()
    for relative, content in old.items():
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    observed = probe(directory)
    assert observed['outcome'] == 'rejected', f'S1 rollback accepted by fresh process: {observed}'


@pytest.mark.parametrize('terminal', [False, True], ids=['spent-budget', 'terminal'])
def test_deleting_all_colocated_files_is_rejected_by_fresh_process(tmp_path, monkeypatch, terminal):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / 'state'
    sm = StateManager('S1', state_dir=str(directory))
    assert sm.register_worker_run()
    if terminal:
        sm.halt_human('terminal fixture', exit_process=False)
    latest = probe(directory)
    assert latest['outcome'] == 'accepted' and latest['worker_runs'] == 1
    assert latest['state'] == ('HALT_HUMAN' if terminal else 'INIT')
    for path in directory.rglob('*'):
        if path.is_file():
            path.unlink()
    assert files(directory) == {}
    observed = probe(directory)
    assert observed['outcome'] == 'rejected', f'S1 deletion recreated initialized task: {observed}'


def test_untampered_terminal_state_survives_a_fresh_process(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / 'state'
    sm = StateManager('S1', state_dir=str(directory))
    assert sm.register_worker_run()
    sm.halt_human('terminal fixture', exit_process=False)
    observed = probe(directory)
    assert observed == dict(outcome='accepted', generation=sm.data['generation'],
                            state='HALT_HUMAN', status='FAILED', worker_runs=1)
