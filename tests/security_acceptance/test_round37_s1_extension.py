"""S1 extension: strict local consistency and native process controls.

No protected authority is modeled by these tests. Original paired attacks remain
mandatory. Subprocess failures and unavailable facilities never count as PASS.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.state_manager import StateManager

INSTALLATION = Path(__file__).resolve().parents[2]
PROBE = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from orchestrator.state_manager import StateManager, CorruptStateError
try:
    sm = StateManager('S1X', state_dir=sys.argv[2])
    data = sm.data
except CorruptStateError:
    print(json.dumps({'outcome': 'rejected'}))
else:
    print(json.dumps({'outcome': 'accepted', 'data': data}))
'''


def command(script, directory, *args):
    return [sys.executable, '-I', '-B', '-c', script, str(INSTALLATION),
            str(directory), *args]


def run(script, directory, *args):
    return subprocess.run(command(script, directory, *args), cwd=directory.parent,
                          capture_output=True, text=True, encoding='utf-8', timeout=30)


def probe(directory):
    result = run(PROBE, directory)
    assert result.returncode == 0, (result.stdout, result.stderr)
    return json.loads(result.stdout)


def witness(directory):
    return directory / 'state_S1X.lock'


@pytest.mark.parametrize('fault', [
    'duplicate-generation', 'duplicate-digest', 'boolean-generation',
    'float-generation', 'missing', 'empty', 'truncated', 'non-object',
    'extra-field', 'wrong-generation', 'wrong-digest', 'invalid-utf8',
])
def test_ambiguous_or_corrupt_local_witness_is_rejected(tmp_path, fault):
    directory = tmp_path / 'state'
    sm = StateManager('S1X', state_dir=directory)
    assert sm.register_worker_run()
    before = sm.state_file.read_bytes()
    record = json.loads(witness(directory).read_bytes())
    digest = json.dumps(record['digest'])
    if fault == 'duplicate-generation':
        raw = ('{"generation":999,"generation":1,"digest":' + digest + '}').encode()
    elif fault == 'duplicate-digest':
        raw = ('{"generation":1,"digest":"' + '0' * 64 + '","digest":' + digest + '}').encode()
    elif fault == 'boolean-generation':
        raw = ('{"generation":true,"digest":' + digest + '}').encode()
    elif fault == 'float-generation':
        raw = ('{"generation":1.0,"digest":' + digest + '}').encode()
    elif fault == 'missing':
        witness(directory).unlink()
        raw = None
    elif fault == 'empty':
        raw = b''
    elif fault == 'truncated':
        raw = b'{"generation":'
    elif fault == 'non-object':
        raw = b'[]'
    elif fault == 'extra-field':
        raw = json.dumps({**record, 'reset': True}).encode()
    elif fault == 'wrong-generation':
        raw = json.dumps({**record, 'generation': 0}).encode()
    elif fault == 'wrong-digest':
        raw = json.dumps({**record, 'digest': '0' * 64}).encode()
    else:
        raw = b'\xff'
    if raw is not None:
        witness(directory).write_bytes(raw)
    observed = probe(directory)
    assert observed['outcome'] == 'rejected', f'S1 ambiguous witness accepted: {fault}'
    assert sm.state_file.read_bytes() == before, 'Corruption must not trigger repair/reset'


@pytest.mark.parametrize('terminal', [False, True], ids=['spent-budget', 'terminal'])
def test_schema36_local_reopen_preserves_exact_snapshot(tmp_path, monkeypatch, terminal):
    """Compatibility control, NOT authenticated migration or enrollment evidence."""
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / 'state'
    sm = StateManager('S1X', state_dir=directory)
    assert sm.register_worker_run()
    if terminal:
        sm.halt_human('fixture', exit_process=False)
    before = sm.state_file.read_bytes()
    expected = sm.data
    assert expected['schema_version'] == 36
    assert probe(directory) == {'outcome': 'accepted', 'data': expected}
    assert sm.state_file.read_bytes() == before


def test_missing_state_with_surviving_witness_is_not_enrolled_again(tmp_path):
    directory = tmp_path / 'state'
    sm = StateManager('S1X', state_dir=directory)
    assert sm.register_worker_run()
    marker = witness(directory).read_bytes()
    sm.state_file.unlink()
    assert probe(directory) == {'outcome': 'rejected'}
    assert not sm.state_file.exists()
    assert witness(directory).read_bytes() == marker


CRASH_WRITER = r'''
import builtins, json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import orchestrator.state_manager as module
directory, point, action = Path(sys.argv[2]), sys.argv[3], sys.argv[4]
real_replace, real_fsync = module.os.replace, module.os.fsync
witness_fd = None
def die():
    print('REACHED:' + point, flush=True)
    os._exit(73)
class InterruptedWitness:
    def __init__(self, stream): self.stream = stream
    def __getattr__(self, name): return getattr(self.stream, name)
    def truncate(self, *args):
        result = self.stream.truncate(*args)
        if point == 'witness-truncated':
            self.stream.flush()
            real_fsync(self.stream.fileno())
            die()
        return result
    def write(self, raw):
        if point == 'witness-partial':
            self.stream.write(raw[:len(raw)//2])
            self.stream.flush()
            real_fsync(self.stream.fileno())
            die()
        return self.stream.write(raw)
def opened(path, *args, **kwargs):
    global witness_fd
    stream = builtins.open(path, *args, **kwargs)
    if Path(path) == directory / 'state_S1X.lock':
        witness_fd = stream.fileno()
        return InterruptedWitness(stream)
    return stream
def replace(source, destination):
    if point == 'before-replace': die()
    result = real_replace(source, destination)
    if point == 'after-replace': die()
    return result
def fsync(fd):
    kind = 'witness' if fd == witness_fd else 'snapshot'
    if point == kind + '-before-sync': die()
    result = real_fsync(fd)
    if point == kind + '-after-sync': die()
    return result
module.open, module.os.replace, module.os.fsync = opened, replace, fsync
sm = module.StateManager('S1X', state_dir=directory)
if action == 'update':
    sm.register_worker_run()
elif action == 'terminal':
    sm.halt_human('interrupted terminal transition', exit_process=False)
else:
    assert action == 'initialize'
raise AssertionError('Fault boundary was never reached: ' + point)
'''


@pytest.mark.parametrize('action', ['initialize', 'update', 'terminal'])
@pytest.mark.parametrize('point', [
    'snapshot-before-sync', 'snapshot-after-sync', 'before-replace', 'after-replace',
    'witness-truncated', 'witness-partial', 'witness-before-sync', 'witness-after-sync',
])
def test_process_crash_at_local_commit_boundary(tmp_path, action, point):
    directory = tmp_path / 'state'
    old = None
    if action != 'initialize':
        sm = StateManager('S1X', state_dir=directory)
        assert sm.register_worker_run()
        old = sm.data
    child = run(CRASH_WRITER, directory, point, action)
    assert child.returncode == 73, (child.stdout, child.stderr)
    assert child.stdout.strip() == 'REACHED:' + point
    observed = probe(directory)
    # Crashes before replacement may preserve the previous completed transaction.
    if point in ('snapshot-before-sync', 'snapshot-after-sync', 'before-replace'):
        if old is not None:
            assert observed == {'outcome': 'accepted', 'data': old}
        else:
            # Initialization never committed. This is only a local first-use control.
            assert observed['outcome'] in ('accepted', 'rejected')
            if observed['outcome'] == 'accepted':
                assert observed['data']['generation'] == 0
                assert observed['data']['budgets']['total_cumulative_worker_runs'] == 0
                assert observed['data']['current_state'] == 'INIT'
    elif point in ('after-replace', 'witness-truncated', 'witness-partial'):
        assert observed == {'outcome': 'rejected'}, 'Mixed local commit must fail closed'
    else:
        # Flush completed before the witness fsync hook; process death is NOT power loss.
        assert observed['outcome'] == 'accepted'
        data = observed['data']
        assert data['generation'] == (0 if old is None else old['generation'] + 1)
        assert data['budgets']['total_cumulative_worker_runs'] == (
            0 if action == 'initialize' else 2 if action == 'update' else 1)
        assert data['current_state'] == ('HALT_HUMAN' if action == 'terminal' else 'INIT')
        assert data['execution_status'] == ('FAILED' if action == 'terminal' else 'RUNNING')


CONCURRENT_WRITER = r'''
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from orchestrator.state_manager import StateManager
directory = Path(sys.argv[2])
name = sys.argv[3]
(directory.parent / ('ready-' + name)).write_text('ready')
deadline = time.monotonic() + 20
while not (directory.parent / 'go').exists():
    if time.monotonic() > deadline: raise RuntimeError('start barrier timed out')
    time.sleep(0.01)
sm = StateManager('S1X', state_dir=directory, lock_timeout=10)
assert sm.register_worker_run()
print(json.dumps({'generation': sm.data['generation']}))
'''


@pytest.mark.parametrize('preexisting', [False, True], ids=['first-use', 'existing'])
def test_independent_controller_processes_preserve_both_commits(tmp_path, preexisting):
    """Real OS locks; no claim about hostile lock deletion/replacement."""
    import time
    directory = tmp_path / 'state'
    if preexisting:
        StateManager('S1X', state_dir=directory)
    children = []
    try:
        for name in ('a', 'b'):
            children.append(subprocess.Popen(command(CONCURRENT_WRITER, directory, name),
                cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8'))
        deadline = time.monotonic() + 20
        while not all((tmp_path / ('ready-' + name)).exists() for name in ('a', 'b')):
            assert time.monotonic() < deadline, 'Children did not reach start barrier'
            assert all(p.poll() is None for p in children), 'Child exited before barrier'
            time.sleep(0.01)
        (tmp_path / 'go').write_text('go')
        for child in children:
            out, err = child.communicate(timeout=30)
            assert child.returncode == 0, (out, err)
            assert json.loads(out)['generation'] in (1, 2)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)
    observed = probe(directory)
    assert observed['outcome'] == 'accepted'
    data = observed['data']
    assert data['generation'] == 2
    assert data['budgets']['total_cumulative_worker_runs'] == 2
    assert data['budgets']['worker_attempts_in_epoch'] == 2
    assert data['current_state'] == 'INIT' and data['execution_status'] == 'RUNNING'
