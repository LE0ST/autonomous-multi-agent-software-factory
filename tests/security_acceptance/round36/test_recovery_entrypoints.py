"""Recovery exercises the actual entrypoints with evidence from real controller gates."""
import pytest
from adapters import LogicAuditOutput
from orchestrator.state_manager import StateManager
from .test_pipeline_trace import prepare
from .test_context_binding import git


def test_authentic_audit_recovery_preserves_budgets(tmp_path, monkeypatch):
    import orchestrator.logic_audit as audit
    mod, root, base, trace = prepare(tmp_path, monkeypatch)
    normal_factory = audit.create_security_adapter
    class Unavailable:
        def audit_logic_and_security(self, spec, diff):
            return LogicAuditOutput(status='UNCERTAIN', violated_invariants=[], justification='Temporary review')
    monkeypatch.setattr(audit, 'create_security_adapter', lambda *a, **kw: Unavailable())
    assert mod.run_pipeline('R36') is False
    sm = StateManager('R36', state_dir=str(root / 'orchestrator/state'))
    before = sm.data
    assert before['current_state'] == 'HUMAN_REVIEW'
    assert len(before['gate_evidence']) == 3
    monkeypatch.setattr(audit, 'create_security_adapter', normal_factory)
    assert mod.resume_audit('R36', repo_root=root) is True
    after = sm.data
    assert after['execution_status'] == 'COMPLETED'
    assert after['budgets'] == before['budgets'] and after['epoch'] == before['epoch']
    assert git(root, 'rev-parse', 'dev') == after['verification_context']['C']


def test_authentic_merge_entrypoint_succeeds(tmp_path, monkeypatch):
    import scripts.merge_gate as merge
    mod, root, base, trace = prepare(tmp_path, monkeypatch)
    real_merge = merge.execute_fast_forward_merge
    monkeypatch.setattr(merge, 'execute_fast_forward_merge', lambda *a: (False, 'merge unavailable'))
    with pytest.raises(SystemExit):
        mod.run_pipeline('R36')
    sm = StateManager('R36', state_dir=str(root / 'orchestrator/state'))
    before = sm.data
    assert len(before['gate_evidence']) == 4
    monkeypatch.setattr(merge, 'execute_fast_forward_merge', real_merge)
    assert mod.resume_merge('R36', repo_root=root) is True
    assert sm.data['budgets'] == before['budgets']
    assert sm.data['execution_status'] == 'COMPLETED'


def test_required_pytest_policy_fails_closed(tmp_path):
    from scripts.test_runner import TestSupervisor
    from .test_hidden_challenges import ROOT
    class NeverExecute:
        def execute(self, *a, **kw):
            pytest.fail('Unsupported required pytest policy must reject before sandbox execution')
    result = TestSupervisor(NeverExecute(), ROOT).verify_candidate(tmp_path, tmp_path,
        policy_bytes=b'{"require_pytest":true}')
    assert result[0] is False and result[3] != 0
