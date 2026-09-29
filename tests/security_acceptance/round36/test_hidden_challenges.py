"""Real candidate interpreter; only mount paths are translated for this test boundary."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types
import pytest
from orchestrator.execution_backend import ExecutionResult
from scripts.test_runner import TestSupervisor

ROOT = Path(__file__).resolve().parents[3]
GOOD = 'def validate_password(p):\n return isinstance(p,str) and len(p)>=8 and any(c.isalpha() for c in p) and any(c.isdigit() for c in p)\n'
OLD = "p in ['Valid123!', '1234567a', '1a234567', 'a1aaaaaa']"


class LocalBoundary:
    def __init__(self, fault=None):
        self.requests = []
        self.fault = fault

    def execute(self, command, candidate_dir, scratch_dir, timeout_seconds, env=None):
        req = scratch_dir / 'rpc_request.json'
        if req.exists():
            requests = json.loads(req.read_text())
            assert all(set(r) == {'id', 'value'} for r in requests)
            self.requests.append(requests)
        for script in scratch_dir.glob('*.py'):
            script.write_text(script.read_text().replace('/src/src', (candidate_dir / 'src').as_posix()).replace('/scratch/', scratch_dir.as_posix() + '/'))
        for script in candidate_dir.rglob('*.py'):
            script.write_text(script.read_text().replace('/scratch/', scratch_dir.as_posix() + '/'))
        translated = [sys.executable if i == 0 else x.replace('/scratch/', scratch_dir.as_posix() + '/') for i, x in enumerate(command)]
        proc = subprocess.run(translated, cwd=candidate_dir, capture_output=True, text=True, timeout=timeout_seconds,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        response = scratch_dir / 'rpc_response.json'
        if self.fault and response.exists():
            data = json.loads(response.read_text())
            if self.fault == 'duplicate':
                data['responses'].append(data['responses'][0])
            elif self.fault == 'missing':
                data['responses'].pop()
            elif self.fault == 'type':
                data['responses'][0]['value'] = 1
            elif self.fault == 'replay':
                data['responses'][0]['id'] = 'old-id'
            response.write_text(json.dumps(data))
        return ExecutionResult(proc.returncode, proc.stdout, proc.stderr, False)


def verify(tmp_path, code, fault=None):
    repo, candidate, scratch = (tmp_path / name for name in ('repo', 'candidate', 'scratch'))
    (repo / 'trusted_tests').mkdir(parents=True)
    shutil.copyfile(ROOT / 'trusted_tests/suite.py', repo / 'trusted_tests/suite.py')
    (candidate / 'src/auth').mkdir(parents=True)
    (candidate / 'src/auth/password_validator.py').write_text(code)
    scratch.mkdir()
    boundary = LocalBoundary(fault)
    result = TestSupervisor(boundary, repo).verify_candidate(candidate, scratch)
    return result, boundary


def test_correct_behavior_passes_and_challenges_vary(tmp_path):
    a, first = verify(tmp_path / 'first', GOOD)
    b, second = verify(tmp_path / 'second', GOOD)
    assert a[0] and b[0], (a, b)
    values_a = [r['value'] for r in first.requests[0]]
    values_b = [r['value'] for r in second.requests[0]]
    assert len(values_a) >= 100
    assert values_a != values_b


@pytest.mark.parametrize('code', [
    'def validate_password(p): return False',
    f'def validate_password(p): return {OLD}',
    "import os,json\nr=json.load(open('/scratch/rpc_request.json'))\njson.dump({'responses':[{'id':x['id'],'type':'bool','value':x['value'] in ['Valid123!','1234567a','1a234567','a1aaaaaa']} for x in r]},open('/scratch/rpc_response.json','w'))\nos._exit(0)",
    "import os\nprint('TRUSTED_RESULTS:PASS')\nos._exit(0)",
    "class Lie:\n def __repr__(self): return 'True'\n def __str__(self): return 'True'\ndef validate_password(p): return Lie()",
])
def test_wrong_behavior_and_old_forgery_rejected(tmp_path, code):
    result, _ = verify(tmp_path, code)
    assert result[0] is False


@pytest.mark.parametrize('fault', ['duplicate', 'missing', 'type', 'replay'])
def test_protocol_fault_rejected(tmp_path, fault):
    result, _ = verify(tmp_path, GOOD, fault)
    assert result[0] is False


def test_foreign_module_cache_cannot_supply_verdict(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'suite', types.SimpleNamespace(run_all=lambda *a: (True, 'fake', '')))
    result, _ = verify(tmp_path, 'def validate_password(p): return False')
    assert result[0] is False


def test_alternate_implementation_at_import_is_valid_behavior(tmp_path):
    code = "import os,json\nr=json.load(open('/scratch/rpc_request.json'))\n" + GOOD + "\njson.dump({'responses':[{'id':x['id'],'type':'bool','value':validate_password(x['value'])} for x in r]},open('/scratch/rpc_response.json','w'))\nos._exit(0)"
    result, _ = verify(tmp_path, code)
    assert result[0] is True
