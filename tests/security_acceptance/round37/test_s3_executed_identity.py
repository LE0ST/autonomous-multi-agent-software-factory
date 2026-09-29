"""S3: backend substitution and loaded implementation changes cannot issue TESTING."""
import types

import pytest

from ._support import ClaimedBackend, TrackedBackend, make_session, run_prefix


@pytest.mark.parametrize('kind', ['different-class', 'same-class-instance', 'instance-method'])
def test_backend_substitution_is_rejected_without_testing_evidence(tmp_path, monkeypatch, kind):
    original = ClaimedBackend() if kind == 'different-class' else TrackedBackend()
    fixture = make_session(tmp_path, monkeypatch, backend=original)
    run_prefix(fixture, 1)
    before = fixture.sm.data['gate_evidence']
    replacement = TrackedBackend()
    result = None
    rejected = False
    try:
        if kind == 'instance-method':
            def substituted(self, *args, **kwargs):
                return replacement.execute(*args, **kwargs)
            original.execute = types.MethodType(substituted, original)
        else:
            fixture.session.backend = replacement
        result = fixture.session.run_testing()
        rejected = result[0] is False
    except (RuntimeError, AttributeError, TypeError):
        rejected = True
    records = fixture.sm.data['gate_evidence']
    assert rejected and records == before, (
        f'S3 {kind}: rejected={rejected}, replacement_calls={replacement.calls}, '
        f'TESTING_appended={len(records) > len(before)}, '
        f'signed_backend={records[-1]["implementations"]["backend"]}')


def test_backend_class_implementation_change_is_rejected(tmp_path, monkeypatch):
    backend = TrackedBackend()
    fixture = make_session(tmp_path, monkeypatch, backend=backend)
    run_prefix(fixture, 1)
    before = fixture.sm.data['gate_evidence']

    def changed(self, *args, **kwargs):
        pytest.fail('Changed implementation must be rejected before execution')

    monkeypatch.setattr(TrackedBackend, 'execute', changed)
    with pytest.raises(RuntimeError, match='implementation changed'):
        fixture.session.run_testing()
    assert fixture.sm.data['gate_evidence'] == before


def test_valid_testing_names_the_backend_that_executed(tmp_path, monkeypatch):
    backend = TrackedBackend()
    fixture = make_session(tmp_path, monkeypatch, backend=backend)
    run_prefix(fixture, 2)
    assert backend.calls == 1
    record = fixture.sm.data['gate_evidence'][-1]
    assert record['gate'] == 'TESTING'
    assert record['implementations']['backend'] == type(backend).__module__ + '.' + type(backend).__qualname__
    assert fixture.session.backend is backend
