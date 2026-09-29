"""S3 adversarial execution bindings; doubles are installed before identity freeze."""
import types
from pathlib import Path

from .round37._support import INSTALLATION, TrackedBackend, make_session, run_prefix


def test_suite_bytes_changed_only_for_execution_cannot_sign(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 1)
    before = fixture.sm.data['gate_evidence']
    suite_path = INSTALLATION / 'trusted_tests/suite.py'
    original_read = Path.read_bytes
    reads = []

    def read_with_execution_only_drift(path):
        data = original_read(path)
        if path.resolve() == suite_path:
            import inspect
            executing = inspect.currentframe().f_back.f_code.co_name == 'verify_candidate'
            reads.append(executing)
            if executing:
                return data + b'\n# execution-only substitution\n'
        return data

    monkeypatch.setattr(Path, 'read_bytes', read_with_execution_only_drift)
    try:
        result = fixture.session.run_testing()
        rejected = result[0] is False
    except RuntimeError:
        rejected = True
    assert any(reads), 'The altered bytes must reach the suite execution read'
    assert rejected and fixture.sm.data['gate_evidence'] == before


def test_backend_method_changed_during_materialization_cannot_execute(tmp_path, monkeypatch):
    backend = TrackedBackend()
    fixture = make_session(tmp_path, monkeypatch, backend=backend)
    run_prefix(fixture, 1)
    before = fixture.sm.data['gate_evidence']
    original_materialize = fixture.session._materialize
    replacement = TrackedBackend()
    reached = []

    def materialize_then_swap(parent, name):
        path = original_materialize(parent, name)
        reached.append(name)
        backend.execute = types.MethodType(
            lambda self, *args, **kwargs: replacement.execute(*args, **kwargs), backend)
        return path

    monkeypatch.setattr(fixture.session, '_materialize', materialize_then_swap)
    try:
        result = fixture.session.run_testing()
        rejected = result[0] is False
    except RuntimeError:
        rejected = True
    assert reached == ['candidate'], 'The substitution must follow materialization'
    assert rejected and replacement.calls == 0 and fixture.sm.data['gate_evidence'] == before


def test_scanner_substituted_then_restored_during_call_cannot_sign(tmp_path, monkeypatch):
    import orchestrator.gate_controller as gates

    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 2)
    before = fixture.sm.data['gate_evidence']
    original_materialize = fixture.session._materialize
    original_scanner = gates.run_sast
    calls = []

    def substituted_scanner(path):
        calls.append('substituted')
        gates.run_sast = original_scanner
        return 0, {'engine': 'substituted scanner', 'results': []}

    def materialize_then_swap(parent, name):
        path = original_materialize(parent, name)
        gates.run_sast = substituted_scanner
        return path

    monkeypatch.setattr(fixture.session, '_materialize', materialize_then_swap)
    try:
        result = fixture.session.run_sast()
        rejected = result[0] != 0
    except RuntimeError:
        rejected = True
    assert rejected and calls == [] and fixture.sm.data['gate_evidence'] == before


def test_manifest_instance_override_cannot_materialize_for_gate(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 1)
    before = fixture.sm.data['gate_evidence']
    original = fixture.session.manifest.materialize
    calls = []

    def substituted(target):
        calls.append('substituted')
        return original(target)

    fixture.session.manifest.materialize = substituted
    try:
        result = fixture.session.run_testing()
        rejected = result[0] is False
    except RuntimeError:
        rejected = True
    assert rejected and calls == [] and fixture.sm.data['gate_evidence'] == before
