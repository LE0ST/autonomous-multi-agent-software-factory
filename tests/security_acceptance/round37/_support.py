"""Real Git/context/FSM/evidence; explicit execution/materialization/model doubles.

Only known fixture candidate code executes on the host via the frozen Round 3.6
LocalBoundary. This does not establish native Docker or POSIX containment.
No generic evidence issuer or snapshot writer is used to prepare authentic gates.
"""
import subprocess
from pathlib import Path
from types import SimpleNamespace

from adapters import LogicAuditOutput
from orchestrator.execution_backend import DockerExecutionBackend
from orchestrator.gate_controller import VerificationSession
from orchestrator.state_manager import StateManager
from orchestrator.verification_context import VerificationContext
from orchestrator.verification_manifest import VerificationManifest
from tests.security_acceptance.round36.test_hidden_challenges import GOOD, LocalBoundary

TASK = 'R37'
INSTALLATION = Path(__file__).resolve().parents[3]
GATES = ('DIFF_GATE', 'TESTING', 'SAST', 'LOGIC_AUDIT')
STATES = ('DIFF_GATE', 'TESTING', 'SAST_SCAN', 'LOGIC_AUDIT')
SPEC = '''## 1. Scope and Boundaries
- Allowed files:
  - `src/auth/password_validator.py`
- Strictly forbidden files:
  - `.env`
## 2. Acceptance Criteria
[AC-01] Passwords need at least eight characters, one letter and one digit.
## 3. Security Invariants
[SEC-01] Reject invalid inputs.
## 4. Test Matrix
[TEST-01] Covers [AC-01] and [SEC-01].
'''


def git(root, *args):
    return subprocess.check_output(
        ['git', *args], cwd=root, text=True, encoding='utf-8',
        stderr=subprocess.PIPE, timeout=30).strip()


class TrackedBackend:
    def __init__(self):
        self.calls = 0
        self.boundary = LocalBoundary()

    def execute(self, *args, **kwargs):
        self.calls += 1
        return self.boundary.execute(*args, **kwargs)


class ClaimedBackend(TrackedBackend):
    def execute(self, *args, **kwargs):
        raise AssertionError('The nonexecuting claimed backend was invoked')


def make_session(tmp_path, monkeypatch, *, backend=None):
    import orchestrator.gate_controller as gates
    import orchestrator.logic_audit as audit

    root = tmp_path / 'repo'
    root.mkdir()
    monkeypatch.chdir(root)
    git(root, 'init', '-b', 'dev')
    git(root, 'config', 'user.name', 'Round37 Acceptance')
    git(root, 'config', 'user.email', 'round37@example.invalid')
    (root / 'src/auth').mkdir(parents=True)
    (root / 'specs').mkdir()
    (root / 'orchestrator').mkdir()
    (root / '.gitignore').write_text(
        'orchestrator/state/\nCRASH_REPORT*\nHUMAN_REVIEW*\n', encoding='utf-8')
    (root / 'specs/R37.md').write_text(SPEC, encoding='utf-8')
    (root / 'orchestrator/config.json').write_text('{}', encoding='utf-8')
    (root / 'orchestrator/verification_policy.json').write_text(
        '{"schema":36,"suite":"password-v36","require_pytest":false,"evidence_ttl_seconds":86400}',
        encoding='utf-8')
    candidate_file = root / 'src/auth/password_validator.py'
    candidate_file.write_text('def validate_password(p): return False\n', encoding='utf-8')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'base')
    base = git(root, 'rev-parse', 'HEAD')
    git(root, 'switch', '-c', 'task/R37')
    candidate_file.write_text(GOOD, encoding='utf-8')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'candidate')
    candidate = git(root, 'rev-parse', 'HEAD')
    git(root, 'switch', 'dev')

    # Install boundary doubles BEFORE implementation identities are frozen.
    trace = []
    boundary = TrackedBackend()
    monkeypatch.setattr(DockerExecutionBackend, '__init__', lambda self: None)

    def execute(self, *args, **kwargs):
        trace.append('TESTING')
        return boundary.execute(*args, **kwargs)

    monkeypatch.setattr(DockerExecutionBackend, 'execute', execute)

    def materialize(manifest, target):
        trace.append('MATERIALIZE')
        target.mkdir()
        for name, entry in manifest.dump()['entries'].items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(
                ['git', 'cat-file', '-p', entry['blob_identity']], cwd=root, timeout=30))

    monkeypatch.setattr(VerificationManifest, 'materialize', materialize)

    def scanner(path):
        trace.append('SAST')
        assert (path / 'src/auth/password_validator.py').read_text(encoding='utf-8') == GOOD
        return 0, {'engine': 'round37-scanner-boundary', 'results': []}

    monkeypatch.setattr(gates, 'run_sast', scanner)

    class Adapter:
        def audit_logic_and_security(self, spec, diff):
            trace.append('LOGIC_AUDIT')
            assert spec == SPEC and 'validate_password' in diff
            return LogicAuditOutput(status='PASS', violated_invariants=[], justification='Boundary control')

    monkeypatch.setattr(audit, 'create_security_adapter', lambda *args, **kwargs: Adapter())
    sm = StateManager(TASK, state_dir=str(root / 'orchestrator/state'))
    sm.transition('SPEC_GATE')
    sm.transition('BUILDING')
    context = VerificationContext.capture(root, TASK, base, candidate)
    session = VerificationSession(root, sm, context, backend=backend)
    return SimpleNamespace(root=root, base=base, candidate=candidate, sm=sm,
                           session=session, trace=trace, boundary=boundary)


def run_prefix(fixture, count):
    session, sm = fixture.session, fixture.sm
    calls = (session.run_diff, session.run_testing, session.run_sast, session.run_audit)
    for index, call in enumerate(calls[:count]):
        before = sm.data['gate_evidence']
        assert len(before) == index, 'Fixture must use exactly the authentic prior gates'
        result = call()
        assert (result[0] == 0 if index == 2 else result[0] is True), result
        after = sm.data['gate_evidence']
        assert after[:-1] == before and len(after) == index + 1
        assert after[-1]['gate'] == GATES[index] and after[-1]['sequence'] == index + 1
        assert session.verify_evidence(required=GATES[:index + 1])


def halted_merge(tmp_path, monkeypatch):
    import scripts.merge_gate as merge

    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    with monkeypatch.context() as fault:
        fault.setattr(merge, 'execute_fast_forward_merge', lambda *args: (False, 'injected CAS failure'))
        assert fixture.session.merge('dev')[0] is False
    fixture.sm.halt_human('CAS unavailable', exit_process=False)
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base
    assert fixture.sm.data['history'][-1]['from'] == 'AUTO_MERGE'
    assert fixture.sm.validate_strict_recovery(fixture.root, mode='merge')[0]
    return fixture
