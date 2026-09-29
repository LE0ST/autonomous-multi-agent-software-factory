"""S3: freeze the other implementations used to produce gate evidence.

Source-byte faults are injected at the read boundary; controller installation
files are never edited. Materialization/scanner/model operations remain doubles.
"""
from pathlib import Path

import pytest

from adapters import LogicAuditOutput
from orchestrator.verification_manifest import VerificationManifest
from ._support import INSTALLATION, make_session, run_prefix


@pytest.mark.parametrize('component', ['suite', 'scanner', 'rules', 'audit-adapter', 'materializer'])
def test_changed_gate_implementation_cannot_append_evidence(tmp_path, monkeypatch, component):
    import orchestrator.gate_controller as gates
    import orchestrator.logic_audit as audit

    fixture = make_session(tmp_path, monkeypatch)
    prior_count = {'suite': 1, 'scanner': 2, 'rules': 2, 'audit-adapter': 3, 'materializer': 1}[component]
    run_prefix(fixture, prior_count)
    before = fixture.sm.data['gate_evidence']
    replaced_calls = []
    if component in ('suite', 'rules'):
        target = INSTALLATION / ('trusted_tests/suite.py' if component == 'suite' else 'scripts/semgrep_rules.yml')
        read_bytes = Path.read_bytes

        def drifted_bytes(path):
            original = read_bytes(path)
            return original + b'\n# injected implementation drift\n' if path.resolve() == target else original

        monkeypatch.setattr(Path, 'read_bytes', drifted_bytes)
    elif component == 'scanner':
        def substitute_scanner(path):
            replaced_calls.append(component)
            return 0, {'engine': 'substituted scanner', 'results': []}

        monkeypatch.setattr(gates, 'run_sast', substitute_scanner)
    elif component == 'audit-adapter':
        class SubstituteAdapter:
            def audit_logic_and_security(self, spec, diff):
                replaced_calls.append(component)
                return LogicAuditOutput(status='PASS', violated_invariants=[], justification='Substituted model adapter')

        monkeypatch.setattr(audit, 'create_security_adapter', lambda *args, **kwargs: SubstituteAdapter())
    else:
        materialize = VerificationManifest.materialize

        def substitute_materializer(manifest, target):
            replaced_calls.append(component)
            return materialize(manifest, target)

        monkeypatch.setattr(VerificationManifest, 'materialize', substitute_materializer)
    operation = {1: fixture.session.run_testing, 2: fixture.session.run_sast, 3: fixture.session.run_audit}[prior_count]
    rejected = False
    try:
        result = operation()
        rejected = result[0] != 0 if prior_count == 2 else result[0] is False
    except RuntimeError:
        rejected = True
    after = fixture.sm.data['gate_evidence']
    assert rejected and after == before, (
        f'S3 {component} substitution: rejected={rejected}, '
        f'replacement_executed={bool(replaced_calls)}, new_evidence={len(after) - len(before)}')
