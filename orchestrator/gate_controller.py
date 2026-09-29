"""Closed gate runner: only successful concrete operations issue evidence.

Python controller code and its installation are trusted. Candidate code runs only
behind the execution backend; candidate JSON and serialized state are untrusted.
"""
import hashlib
import hmac
import importlib.metadata
import inspect
import json
import types
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from orchestrator.evidence_store import EvidenceKey
from orchestrator.execution_backend import DockerExecutionBackend
from orchestrator.verification_context import VerificationContext, context_bytes, digest
from scripts.diff_gate import validate_diff
from scripts.sast_runner import run_sast
from scripts.test_runner import TestSupervisor

GATES = ('DIFF_GATE', 'TESTING', 'SAST', 'LOGIC_AUDIT')
AUDIT_ADAPTER_KEYS = frozenset(('adapter_factory_loaded', 'gemini_adapter_loaded',
    'deepseek_adapter_loaded', 'glm_adapter_loaded', 'qwen_adapter_loaded'))
INSTALLATION = Path(__file__).resolve().parents[1]
IMPLEMENTATION_FILES = ('orchestrator.py', 'orchestrator/state_manager.py',
    'orchestrator/gate_controller.py', 'orchestrator/evidence_store.py',
    'orchestrator/verification_context.py', 'orchestrator/verification_manifest.py',
    'orchestrator/execution_backend.py', 'trusted_tests/suite.py', 'scripts/test_runner.py',
    'scripts/sast_runner.py', 'scripts/diff_gate.py', 'scripts/file_policy.py',
    'scripts/merge_gate.py', 'scripts/semgrep_rules.yml', 'orchestrator/logic_audit.py')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def loaded_code_identity(code):
    # marshal encodes reference/interning details that can change after execution.
    # Hash semantic code fields and recursively canonical constants instead.
    def constant(value):
        if isinstance(value, types.CodeType):
            return loaded_code_identity(value)
        if isinstance(value, bytes):
            return {'bytes': value.hex()}
        if isinstance(value, slice):
            return {'slice': [constant(value.start), constant(value.stop), constant(value.step)]}
        if isinstance(value, (tuple, frozenset)):
            values = [constant(v) for v in value]
            return {'tuple' if isinstance(value, tuple) else 'set':
                    values if isinstance(value, tuple) else sorted(values, key=lambda v: canonical(v))}
        if value is Ellipsis:
            return {'ellipsis': True}
        if isinstance(value, complex):
            return {'complex': [value.real, value.imag]}
        return value
    return digest(canonical({'bytecode': code.co_code.hex(),
        'constants': [constant(v) for v in code.co_consts], 'names': code.co_names,
        'varnames': code.co_varnames, 'freevars': code.co_freevars, 'cellvars': code.co_cellvars,
        'args': [code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount],
        'flags': code.co_flags, 'exceptions': getattr(code, 'co_exceptiontable', b'').hex()}))


def implementation_identities(backend_type=DockerExecutionBackend):
    identities = {p: digest((INSTALLATION / p).read_bytes()) for p in IMPLEMENTATION_FILES}
    identities['backend'] = backend_type.__module__ + '.' + backend_type.__qualname__
    identities['backend_source'] = digest(Path(inspect.getsourcefile(backend_type)).read_bytes())
    identities['python'] = sys.version
    # Bind loaded code too: a cached implementation cannot claim only a different
    # on-disk source digest. Recovery under newly loaded code will reject it.
    from orchestrator.state_manager import StateManager
    from orchestrator.logic_audit import execute_logic_security_audit, create_security_adapter
    from orchestrator.verification_manifest import VerificationManifest
    from adapters import GeminiAdapter, DeepSeekAdapter, GLMAdapter, QwenAdapter
    for name, function in {'diff_loaded': validate_diff, 'sast_loaded': run_sast,
            'verifier_loaded': TestSupervisor.verify_candidate, 'backend_loaded': backend_type.execute,
            'audit_loaded': execute_logic_security_audit,
            'adapter_factory_loaded': create_security_adapter,
            'gemini_adapter_loaded': GeminiAdapter.audit_logic_and_security,
            'deepseek_adapter_loaded': DeepSeekAdapter.audit_logic_and_security,
            'glm_adapter_loaded': GLMAdapter.audit_logic_and_security,
            'qwen_adapter_loaded': QwenAdapter.audit_logic_and_security,
            'materializer_loaded': VerificationManifest.materialize,
            'transaction_loaded': StateManager._transaction}.items():
        identities[name] = loaded_code_identity(function.__code__)
    for package in ('bandit', 'semgrep'):
        try:
            distribution = importlib.metadata.distribution(package)
            # Bind the installed distribution version and its installation manifest.
            # Scanners execute from the controller installation, outside candidate mounts.
            identities[package] = distribution.version + ':' + digest(
                (distribution.read_text('RECORD') or distribution.read_text('METADATA') or '').encode())
        except importlib.metadata.PackageNotFoundError:
            identities[package] = 'unavailable'
    return identities


class VerificationSession:
    def __init__(self, root, state, context, *, backend=None, resume=False):
        self.root, self.sm, self.context = Path(root).resolve(), state, context
        if not isinstance(context, VerificationContext) or not context.verify_current(self.root, state.task_id):
            raise RuntimeError('Verification context is not current')
        # A selection race may move the symbolic task ref during context capture.
        # Freeze its observed value now; C itself remains the immutable commit
        # selected for all gates and the eventual exact B-to-C CAS.
        try:
            self._candidate_ref_at_freeze = subprocess.check_output(
                ['git', 'rev-parse', '--verify', f'refs/heads/task/{state.task_id}'],
                cwd=self.root, text=True, encoding='utf-8', stderr=subprocess.PIPE,
                timeout=30).strip()
        except (OSError, subprocess.SubprocessError):
            self._candidate_ref_at_freeze = None
        self.backend = backend
        self.backend_type = type(backend) if backend is not None else DockerExecutionBackend
        self._bound_backend = backend
        self._bound_backend_type = self.backend_type
        self._bound_backend_execute = self.backend_type.execute
        self._backend_object_token = secrets.token_hex(32)
        self.identities = implementation_identities(self.backend_type)
        import orchestrator.logic_audit as audit_module
        from adapters import GeminiAdapter, DeepSeekAdapter, GLMAdapter, QwenAdapter
        self._bound_gate_functions = {'DIFF_GATE': validate_diff,
            'TESTING': TestSupervisor.verify_candidate, 'SAST': run_sast,
            'LOGIC_AUDIT': audit_module.execute_logic_security_audit}
        self._bound_adapter_factory = audit_module.create_security_adapter
        self._bound_adapter_methods = tuple((adapter, adapter.audit_logic_and_security)
            for adapter in (GeminiAdapter, DeepSeekAdapter, GLMAdapter, QwenAdapter))
        self.spec_bytes, self.config_bytes, self.policy_bytes = context_bytes(self.root, state.task_id)
        if tuple(map(digest, (self.spec_bytes, self.config_bytes, self.policy_bytes))) != (
                context.spec_digest, context.config_digest, context.policy_digest):
            raise RuntimeError('Context bytes changed while freezing gate inputs')
        self.policy = json.loads(self.policy_bytes)
        self.manifest = context.rebuild_manifest(self.root)
        self._bound_manifest = self.manifest
        self._bound_materialize = type(self.manifest).materialize
        # Key creation and attempt creation share the state lock; no racing bootstrap.
        with state._lock:
            snapshot = state.data
            self._key = EvidenceKey(state.state_dir, snapshot.get('evidence_key_id'))
            self.key_path = self._key.path
            if resume:
                if snapshot['verification_context'] != context.to_dict():
                    raise RuntimeError('Recovery context mismatch')
                self.attempt = snapshot['attempt']
            else:
                self.attempt = secrets.token_hex(32)
                state._begin_verification(context, self.attempt, self._key.identity, self.identities)

    def _current(self):
        if not self.context.verify_current(self.root, self.sm.task_id):
            raise RuntimeError('Context changed after verification candidate freeze - FAIL CLOSED')
        if self.backend is not self._bound_backend or self.backend_type is not self._bound_backend_type:
            raise RuntimeError('Gate backend object changed after freeze')
        if self._bound_backend_type.execute is not self._bound_backend_execute:
            raise RuntimeError('Gate backend implementation changed after freeze')
        if self.backend is not None:
            method = self.backend.execute
            if (type(self.backend) is not self._bound_backend_type
                    or getattr(method, '__self__', None) is not self.backend
                    or getattr(method, '__func__', None) is not self._bound_backend_execute):
                raise RuntimeError('Gate backend implementation changed after freeze')
        if self.manifest is not self._bound_manifest:
            raise RuntimeError('Gate materializer object changed after freeze')
        materialize = self.manifest.materialize
        if (type(self.manifest).materialize is not self._bound_materialize
                or getattr(materialize, '__self__', None) is not self.manifest
                or getattr(materialize, '__func__', None) is not self._bound_materialize):
            raise RuntimeError('Gate materializer implementation changed after freeze')
        import orchestrator.logic_audit as audit_module
        if audit_module.create_security_adapter is not self._bound_adapter_factory:
            raise RuntimeError('Gate audit adapter factory changed after freeze')
        if any(adapter.audit_logic_and_security is not method
                for adapter, method in self._bound_adapter_methods):
            raise RuntimeError('Gate audit adapter implementation changed after freeze')
        current = implementation_identities(self.backend_type)
        if self.identities != current:
            changed = sorted(k for k in self.identities.keys() | current.keys() if self.identities.get(k) != current.get(k))
            raise RuntimeError('Gate implementation changed after freeze: ' + ', '.join(changed))
        data = self.sm.data
        if (data['verification_context'] != self.context.to_dict() or data['attempt'] != self.attempt
                or data.get('evidence_key_id') != self._key.identity):
            raise RuntimeError('Attempt, context or key changed')
        self._key.read()

    def _before(self, gate):
        self._current()
        prior = GATES[:GATES.index(gate)]
        if not self.verify_evidence(required=prior):
            raise RuntimeError('Prior evidence missing, stale or out of order')

    def _run_gate(self, gate, *, simulate=False):
        # A gate name selects an execution path, never a standalone PASS issuer.
        if gate not in GATES:
            raise ValueError('Unknown verification gate')
        self._before(gate)
        detail = ''
        if gate == 'DIFF_GATE':
            self.sm.transition('DIFF_GATE')
            with tempfile.TemporaryDirectory(prefix='controller-spec-') as directory:
                spec = Path(directory) / 'spec.md'
                spec.write_bytes(self.spec_bytes)
                operation = validate_diff
                result = operation(self.root, self.context.B, self.context.C, spec)
            eligible = (type(result[0]) is bool and result[0]
                and isinstance(result[1], dict) and result[1].get('status') == 'PASS')
        elif gate == 'TESTING':
            self.sm.transition('TESTING')
            if self.backend is None:
                self.backend = self._bound_backend = self._bound_backend_type()
            with tempfile.TemporaryDirectory(prefix='controller-tests-') as parent:
                candidate = self._materialize(parent, 'candidate')
                scratch = Path(parent) / 'scratch'
                scratch.mkdir()
                self._current()
                supervisor = TestSupervisor(self.backend, INSTALLATION)
                operation = TestSupervisor.verify_candidate
                result = operation(supervisor, candidate, scratch, policy_bytes=self.policy_bytes)
            if (result[0] is True and isinstance(result[4], dict)
                    and result[4].get('trusted_suite_version') != self.identities['trusted_tests/suite.py']):
                raise RuntimeError('Trusted suite bytes changed during execution')
            eligible = (type(result[0]) is bool and result[0]
                and type(result[3]) is int and result[3] == 0
                and isinstance(result[4], dict)
                and result[4].get('trusted_verifier_result') == 'PASS'
                and result[4].get('trusted_suite_version') == self.identities['trusted_tests/suite.py'])
        elif gate == 'SAST':
            self.sm.transition('SAST_SCAN')
            with tempfile.TemporaryDirectory(prefix='controller-sast-') as parent:
                candidate = self._materialize(parent, 'candidate')
                self._current()
                operation = run_sast
                result = operation(candidate)
            eligible = (type(result[0]) is int and result[0] == 0
                and isinstance(result[1], dict) and result[1].get('results') == []
                and not result[1].get('error'))
            if eligible:
                detail = result[1].get('engine', '')
        else:
            from orchestrator.logic_audit import execute_logic_security_audit
            self.sm.transition('LOGIC_AUDIT')
            diff = subprocess.check_output(['git', 'diff', '--no-ext-diff', '--no-textconv',
                self.context.B, self.context.C], cwd=self.root, text=True, timeout=30)
            with tempfile.TemporaryDirectory(prefix='controller-audit-') as parent:
                spec = Path(parent) / 'spec.md'
                spec.write_bytes(self.spec_bytes)
                operation = execute_logic_security_audit
                result = operation(self.sm, spec, diff,
                    json.loads(self.config_bytes).get('roles', {}).get('logic_security', {}),
                    simulate=simulate, exit_process=False)
            eligible = (type(result[0]) is bool and result[0]
                and result[1] is not None and result[1].status == 'PASS'
                and isinstance(result[2], dict) and not simulate)
            if result[0] and simulate:
                raise RuntimeError('Simulation cannot authorize integration')
            if eligible:
                detail = json.dumps(result[2])
        if not eligible:
            return result

        # The result is captured before signing. No caller-supplied result or
        # reusable success capability crosses this execution-to-signing path.
        result_body = (result[0], result[1].model_dump(mode='json'), result[2]) if gate == 'LOGIC_AUDIT' else result
        result_hash = digest(canonical(result_body))
        with self.sm._lock:
            self._current()
            if operation is not self._bound_gate_functions[gate]:
                raise RuntimeError('Gate executable callable changed after freeze')
            def append():
                self.sm._assert_active()
                data = self.sm._data
                sequence = len(data['gate_evidence'])
                if sequence >= len(GATES) or GATES[sequence] != gate:
                    raise RuntimeError('Duplicate or out-of-order gate')
                if data['attempt'] != self.attempt or data['verification_context'] != self.context.to_dict():
                    raise RuntimeError('Concurrent verification attempt replaced')
                record = dict(schema=36, task=self.sm.task_id, repository=str(self.root),
                    gate=gate, context=self.context.to_dict(), result='PASS',
                    implementations=self.identities, attempt=self.attempt, sequence=sequence + 1,
                    generation=data['generation'] + 1, issued_at=time.time(), key_id=self._key.identity,
                    previous=data['gate_evidence'][-1]['signature'] if sequence else '',
                    supplemental={'detail': str(detail)[:1024],
                                  'execution_result_sha256': result_hash,
                                  **({'backend_object_token': self._backend_object_token}
                                     if gate == 'TESTING' else {})})
                record['signature'] = hmac.new(self._key.read(), canonical(record), hashlib.sha256).hexdigest()
                data['gate_evidence'].append(record)
            self.sm._transaction(append)
        return result

    def verify_evidence(self, required=GATES):
        try:
            self._current()
            data = self.sm.data
            records = data['gate_evidence']
            if tuple(required) != GATES[:len(required)] or len(records) != len(required):
                return False
            previous, generation, issued = '', 0, 0
            ttl = self.policy.get('evidence_ttl_seconds', 86400)
            if type(ttl) is not int or not 0 < ttl <= 86400:
                return False
            for sequence, (gate, record) in enumerate(zip(required, records), 1):
                body = dict(record)
                signature = body.pop('signature', None)
                expected = hmac.new(self._key.read(), canonical(body), hashlib.sha256).hexdigest()
                if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
                    return False
                recorded_impl = body['implementations']
                if not isinstance(recorded_impl, dict):
                    return False
                # A failed audit issues no audit record. Recovery may select a new
                # adapter; the three earlier gates did not execute that adapter.
                if gate == 'LOGIC_AUDIT':
                    implementations_match = recorded_impl == self.identities
                else:
                    implementations_match = ({k: v for k, v in recorded_impl.items()
                        if k not in AUDIT_ADAPTER_KEYS} ==
                        {k: v for k, v in self.identities.items()
                        if k not in AUDIT_ADAPTER_KEYS})
                if (body['schema'] != 36 or body['result'] != 'PASS' or body['gate'] != gate
                        or body['task'] != self.sm.task_id or body['repository'] != str(self.root)
                        or body['context'] != self.context.to_dict() or not implementations_match
                        or body['attempt'] != self.attempt or body['key_id'] != self._key.identity
                        or body['sequence'] != sequence or body['previous'] != previous
                        or not generation < body['generation'] <= data['generation']
                        or not issued <= body['issued_at'] <= time.time()
                        or time.time() - body['issued_at'] > ttl):
                    return False
                previous, generation, issued = signature, body['generation'], body['issued_at']
            return True
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
            return False

    def run_diff(self):
        return self._run_gate('DIFF_GATE')

    def _materialize(self, parent, name):
        self._current()
        path = Path(parent) / name
        self.manifest.materialize(path)
        self._current()
        if self.key_path.resolve().is_relative_to(path.resolve()):
            raise RuntimeError('Evidence key cannot be mounted in the sandbox')
        return path

    def run_testing(self):
        return self._run_gate('TESTING')

    def run_sast(self):
        return self._run_gate('SAST')

    def run_audit(self, *, simulate=False):
        return self._run_gate('LOGIC_AUDIT', simulate=simulate)

    def merge(self, base_branch='dev'):
        return self.sm._integrate(self, base_branch)
