"""Real pipeline/Git/context/evidence with explicit external execution boundary doubles.

Windows cannot securely materialize yet. The test materializer reads immutable Git
blobs into a disposable directory; this is not evidence of native containment.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import pytest
from adapters import LogicAuditOutput
from orchestrator.state_manager import StateManager
from .test_context_binding import git
from .test_hidden_challenges import GOOD, LocalBoundary, ROOT

SPEC = '''## 1. Scope and Boundaries
- Allowed files:
  - `src/auth/password_validator.py`
- Strictly forbidden files:
  - `.env`
## 2. Acceptance Criteria
[AC-01] Validate passwords of length at least eight with a letter and a digit.
## 3. Security Invariants
[SEC-01] Reject invalid inputs.
## 4. Test Matrix
[TEST-01] Covers [AC-01] and [SEC-01].
'''


def prepare(tmp_path, monkeypatch, schedule='clean'):
    import orchestrator.gate_controller as gates
    import orchestrator.logic_audit as audit
    from orchestrator.execution_backend import DockerExecutionBackend
    from orchestrator.verification_manifest import VerificationManifest
    from orchestrator.verification_context import VerificationContext
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-b', 'dev')
    git(root, 'config', 'user.name', 'Round36')
    git(root, 'config', 'user.email', 'round36@example.invalid')
    (root / 'orchestrator').mkdir()
    (root / 'specs').mkdir()
    (root / 'src/auth').mkdir(parents=True)
    (root / '.gitignore').write_text('.worktrees/\norchestrator/state/\nCRASH_REPORT*\nHUMAN_REVIEW*\n')
    (root / 'orchestrator/config.json').write_text('{}')
    (root / 'orchestrator/verification_policy.json').write_text('{"require_pytest":false}')
    (root / 'specs/R36.md').write_text(SPEC)
    (root / 'src/auth/password_validator.py').write_text('def validate_password(p): return False\n')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'base')
    base = git(root, 'rev-parse', 'HEAD')
    spec = importlib.util.spec_from_file_location('round36_pipeline', ROOT / 'orchestrator.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.chdir(root)
    monkeypatch.setattr(mod, 'run_discovery', lambda *a: (True, []))
    monkeypatch.setattr(mod, 'load_api_keys', lambda *a: None)
    class Adapter:
        def __init__(self, **kw): pass
        def generate_code_and_tests(self, *, worktree_path, **kw):
            (worktree_path / 'src/auth/password_validator.py').write_text(GOOD)
        def audit_logic_and_security(self, spec, diff):
            trace.append({'gate': 'LOGIC_AUDIT', 'diff': diff, 'spec': spec})
            return LogicAuditOutput(status='PASS', violated_invariants=[], justification='External model boundary test')
    monkeypatch.setattr(mod, 'GeminiAdapter', Adapter)
    monkeypatch.setattr(mod, 'DeepSeekAdapter', Adapter)
    monkeypatch.setattr(audit, 'create_security_adapter', lambda *a, **kw: Adapter())
    boundary = LocalBoundary()
    monkeypatch.setattr(DockerExecutionBackend, '__init__', lambda self: None)
    monkeypatch.setattr(DockerExecutionBackend, 'execute', lambda self, *a, **kw: boundary.execute(*a, **kw))
    trace = []
    def materialize(self, target):
        trace.append({'gate': 'MATERIALIZE', 'manifest': self.digest, 'C': self.dump()['candidate_commit_sha']})
        target.mkdir()
        for name, info in self.dump()['entries'].items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(['git', 'cat-file', '-p', info['blob_identity']], cwd=root))
    monkeypatch.setattr(VerificationManifest, 'materialize', materialize)
    def scanner(path):
        trace.append({'gate': 'SAST', 'bytes': (path / 'src/auth/password_validator.py').read_text()})
        return (2, {'error': 'injected tool error'}) if schedule == 'sast_exit2' else (0, {'engine': 'scanner-boundary', 'results': []})
    monkeypatch.setattr(gates, 'run_sast', scanner)
    original_testing = gates.VerificationSession.run_testing
    def after_testing(self):
        result = original_testing(self)
        trace.append({'gate': 'TESTING', 'context': self.context.to_dict(), 'passed': result[0]})
        if schedule == 'worktree':
            (root / '.worktrees/wt_R36/src/auth/password_validator.py').write_text('MUTATED')
        elif schedule in ('spec', 'config', 'policy'):
            name = {'spec': 'specs/R36.md', 'config': 'orchestrator/config.json', 'policy': 'orchestrator/verification_policy.json'}[schedule]
            (root / name).write_text('MUTATED')
        return result
    monkeypatch.setattr(gates.VerificationSession, 'run_testing', after_testing)
    if schedule == 'selection':
        capture = VerificationContext.capture.__func__
        raced = False
        def racing(cls, repo, task_id, b, c):
            nonlocal raced
            if not raced:
                raced = True
                wt = root / '.worktrees/wt_R36'
                (wt / 'src/auth/password_validator.py').write_text('RACING COMMIT')
                git(wt, 'add', '.')
                git(wt, 'commit', '-m', 'racing commit')
                trace.append({'gate': 'SELECTION_RACE', 'selected': c, 'racing': git(wt, 'rev-parse', 'HEAD')})
            return capture(cls, repo, task_id, b, c)
        monkeypatch.setattr(VerificationContext, 'capture', classmethod(racing))
    return mod, root, base, trace


@pytest.mark.parametrize('schedule', ['clean', 'worktree', 'selection', 'spec', 'config', 'policy', 'sast_exit2'])
def test_real_pipeline_schedules(tmp_path, monkeypatch, schedule):
    mod, root, base, trace = prepare(tmp_path, monkeypatch, schedule)
    try:
        mod.run_pipeline('R36')
    except SystemExit:
        pass
    sm = StateManager('R36', state_dir=str(root / 'orchestrator/state'))
    state = sm.data
    record = {'schedule': schedule, 'base': base, 'final_ref': git(root, 'rev-parse', 'dev'), 'state': state, 'trace': trace}
    (tmp_path / 'trace.json').write_text(json.dumps(record, indent=2))
    assert any(row['gate'] == 'TESTING' and row['passed'] for row in trace), record
    if schedule in ('clean', 'worktree', 'selection'):
        assert state['execution_status'] == 'COMPLETED', record
        context = state['verification_context']
        assert context['B'] == base
        assert record['final_ref'] == context['C']
        assert context['tree'] == git(root, 'rev-parse', context['C'] + '^{tree}')
        assert [ev['gate'] for ev in state['gate_evidence']] == ['DIFF_GATE', 'TESTING', 'SAST', 'LOGIC_AUDIT']
        assert all(ev['context'] == context for ev in state['gate_evidence'])
        materials = [t for t in trace if t['gate'] == 'MATERIALIZE']
        assert len(materials) == 2 and all(t['C'] == context['C'] and t['manifest'] == context['M'] for t in materials)
        if schedule == 'selection':
            race = next(t for t in trace if t['gate'] == 'SELECTION_RACE')
            assert record['final_ref'] == race['selected'] != race['racing']
    else:
        assert state['current_state'] == 'HALT_HUMAN' and state['execution_status'] == 'FAILED', record
        assert record['final_ref'] == base
        assert not any(t['gate'] == 'LOGIC_AUDIT' for t in trace)
        if schedule == 'sast_exit2':
            assert any(t['gate'] == 'SAST' for t in trace)
        else:
            assert not any(t['gate'] == 'SAST' for t in trace)


def test_authentic_merge_recovery_and_capability_replay(tmp_path, monkeypatch):
    import scripts.merge_gate as merge
    mod, root, base, trace = prepare(tmp_path, monkeypatch)
    real_merge = merge.execute_fast_forward_merge
    monkeypatch.setattr(merge, 'execute_fast_forward_merge', lambda *a: (False, 'injected merge failure'))
    try:
        mod.run_pipeline('R36')
    except SystemExit:
        pass
    sm = StateManager('R36', state_dir=str(root / 'orchestrator/state'))
    assert sm.data['current_state'] == 'HALT_HUMAN'
    cap, session = sm.authorize_recovery(root, mode='merge')
    sm.execute_merge_recovery_transition(cap)
    with pytest.raises(RuntimeError):
        sm.execute_merge_recovery_transition(cap)
    monkeypatch.setattr(merge, 'execute_fast_forward_merge', real_merge)
    assert session.merge()[0]
    assert git(root, 'rev-parse', 'dev') == session.context.C
