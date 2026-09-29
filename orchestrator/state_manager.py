"""Transactional state with a local consistency witness, not an external anchor.

Paired snapshot/witness rollback or deletion is not detected across restarts.
No caller-owned snapshots can be saved.
"""
import copy
import hmac
import json
import hashlib
import inspect
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from adapters.sanitizer import sanitize_secret_text

# Inert compatibility name exercised by the frozen mutable-reference
# counterexample. It is never read by the integration path.
_installed_merge_operation = None

VALID_STATES = ('INIT', 'SPEC_DESIGN', 'SPEC_GATE', 'BUILDING', 'DIFF_GATE', 'TESTING', 'TRIAGING', 'SAST_SCAN', 'SAST_FILTER', 'LOGIC_AUDIT', 'AUTO_MERGE', 'HUMAN_REVIEW', 'HALT_HUMAN')
STATUSES = ('RUNNING', 'INTERRUPTED', 'COMPLETED', 'FAILED', 'NEEDS_HUMAN_REVIEW')
TERMINAL = ('HALT_HUMAN', 'HUMAN_REVIEW')
EDGES = {'INIT': {'SPEC_DESIGN', 'SPEC_GATE'}, 'SPEC_DESIGN': {'SPEC_GATE'}, 'SPEC_GATE': {'BUILDING'}, 'BUILDING': {'DIFF_GATE'}, 'DIFF_GATE': {'TESTING', 'BUILDING'}, 'TESTING': {'TRIAGING', 'SAST_SCAN'}, 'TRIAGING': {'BUILDING'}, 'SAST_SCAN': {'SAST_FILTER', 'LOGIC_AUDIT', 'BUILDING'}, 'SAST_FILTER': {'BUILDING', 'LOGIC_AUDIT'}, 'LOGIC_AUDIT': {'BUILDING', 'AUTO_MERGE'}, 'AUTO_MERGE': set()}

class CorruptStateError(RuntimeError):
    pass
class TerminalStateError(RuntimeError):
    pass
class IllegalStateTransitionError(RuntimeError):
    pass

class StateLock:
    """Thread-owned reentrant mutex and kernel file lock. Lock files are never unlinked."""
    def __init__(self, path, timeout=10.0, poll_interval=0.02):
        self.path = Path(path)
        self.timeout, self.poll_interval = timeout, poll_interval
        self._mutex = threading.RLock()
        self._owner, self._depth, self._file = None, 0, None

    def acquire(self):
        deadline = time.monotonic() + self.timeout
        if not self._mutex.acquire(timeout=self.timeout):
            raise TimeoutError('Timed out acquiring state lock')
        try:
            if self._depth:
                self._depth += 1
                return self
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self.path, 'a+b')
            while True:
                try:
                    self._file.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Timed out acquiring state lock')
                    time.sleep(self.poll_interval)
            self._owner, self._depth = threading.get_ident(), 1
            return self
        except BaseException:
            if self._file:
                self._file.close()
                self._file = None
            self._mutex.release()
            raise

    def owned(self):
        return self._owner == threading.get_ident() and self._depth > 0

    def release(self):
        if not self.owned():
            raise RuntimeError('cannot release lock owned by another thread')
        self._depth -= 1
        if not self._depth:
            self._file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file, self._owner = None, None
        self._mutex.release()
    __enter__ = acquire
    def __exit__(self, *args):
        self.release()

def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate state key')
        result[key] = value
    return result

class StateManager:
    def __init__(self, task_id, config_path='orchestrator/config.json', state_dir='orchestrator/state', raise_on_halt=False, lock_timeout=10.0):
        if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', task_id):
            raise ValueError('Invalid task identifier')
        self.task_id, self.raise_on_halt = task_id, raise_on_halt
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / f'state_{task_id}.json'
        self._lock = StateLock(self.state_file.with_suffix('.lock'), timeout=lock_timeout)
        self._tx_depth, self._generation = 0, -1
        self._recovery_caps = {}
        self._active_recovery_cap = None
        cfg = Path(config_path)
        # Existing authoritative state must remain loadable when current config is
        # damaged: gates reject the changed digest, and the controller can persist HALT.
        self.config = json.loads(cfg.read_bytes()) if cfg.exists() and not self.state_file.exists() else {}
        with self._lock:
            self._lock._file.seek(0)
            initialized = bool(self._lock._file.read())
            if self.state_file.exists():
                self._reload()
            elif initialized:
                raise CorruptStateError('Authoritative state was deleted after initialization')
            else:
                self._data = self._init_state()
                self._tx_depth = 1
                try:
                    self._persist()
                finally:
                    self._tx_depth = 0

    def _init_state(self):
        limits, budgets = self.config.get('budgets', {}), {}
        for counter, limit, default in (
            ('logic_replans_used', 'max_logic_replans', 2),
            ('security_replans_used', 'max_security_replans', 1),
            ('spec_syntax_retries_used', 'max_spec_syntax_retries', 1),
            ('worker_attempts_in_epoch', 'max_worker_per_epoch', 2),
            ('total_cumulative_worker_runs', 'max_cumulative_worker_runs', 5)):
            budgets[counter], budgets[limit] = 0, limits.get(limit, default)
        return dict(schema_version=36, generation=0, task_id=self.task_id, epoch=1, current_state='INIT', execution_status='RUNNING', budgets=budgets, audit_model_used=None, history=[], verification_context=None, gate_evidence=[], attempt=None, integration_pending=None, integration_receipt=None)

    def _validate(self, data):
        # Older active snapshots can acquire the S4 fields on their next write.
        # An older COMPLETED snapshot has no receipt and must fail closed.
        required = set(self._init_state()) - {'integration_pending', 'integration_receipt'}
        if not isinstance(data, dict) or not required <= data.keys():
            raise CorruptStateError('State missing required schema fields; legacy state requires explicit migration')
        if (data['schema_version'] != 36 or data['task_id'] != self.task_id
                or type(data['generation']) is not int or data['generation'] < 0
                or data['current_state'] not in VALID_STATES or data['execution_status'] not in STATUSES
                or type(data['epoch']) is not int or data['epoch'] < 1
                or not isinstance(data['history'], list) or not isinstance(data['gate_evidence'], list)):
            raise CorruptStateError('Invalid authoritative state schema')
        if set(data['budgets']) != set(self._init_state()['budgets']) or any(type(v) is not int or v < 0 for v in data['budgets'].values()):
            raise CorruptStateError('Invalid budgets')
        if (data['current_state'] == 'HALT_HUMAN' and data['execution_status'] != 'FAILED'
                or data['current_state'] == 'HUMAN_REVIEW' and data['execution_status'] != 'NEEDS_HUMAN_REVIEW'):
            raise CorruptStateError('Inconsistent terminal state/status')
        self._validate_integration(data)

    @staticmethod
    def _integration_bytes(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')

    def _integration_key(self, data):
        from orchestrator.evidence_store import EvidenceKey
        key_id = data.get('evidence_key_id')
        if not isinstance(key_id, str):
            raise CorruptStateError('Integration evidence key is missing')
        return EvidenceKey(self.state_dir, key_id).read()

    def _validate_integration(self, data):
        pending, receipt = data.get('integration_pending'), data.get('integration_receipt')
        status, state, history = data['execution_status'], data['current_state'], data['history']
        try:
            completion_rows = [i for i, row in enumerate(history)
                if isinstance(row, dict) and row.get('to') == 'COMPLETED']
            if status == 'COMPLETED':
                if (state != 'AUTO_MERGE' or pending is not None or not isinstance(receipt, dict)
                        or completion_rows != [len(history) - 1] or len(history) < 2
                        or history[-1].get('from') != 'AUTO_MERGE'
                        or history[-2].get('to') != 'AUTO_MERGE'):
                    raise CorruptStateError('Completion state, history and receipt disagree')
                metadata = receipt
            else:
                if receipt is not None or completion_rows:
                    raise CorruptStateError('Completion claim without terminal integration')
                if pending is None:
                    return
                if (state, status) not in (('AUTO_MERGE', 'RUNNING'),
                        ('AUTO_MERGE', 'INTERRUPTED'), ('HALT_HUMAN', 'FAILED')):
                    raise CorruptStateError('Pending integration has invalid state/status')
                metadata = pending
            if not isinstance(metadata, dict):
                raise CorruptStateError('Integration metadata is missing')
            common = {'schema', 'phase', 'task', 'repository', 'base_branch', 'B', 'C',
                'tree', 'M', 'context', 'attempt', 'gate_signatures', 'key_id', 'nonce',
                'generation', 'cas', 'candidate_ref_at_freeze', 'signature'}
            expected_keys = common | ({'integrated_at', 'history_digest'} if receipt is not None else set())
            if set(metadata) != expected_keys:
                raise CorruptStateError('Integration metadata fields are invalid')
            context, records = data['verification_context'], data['gate_evidence']
            from orchestrator.gate_controller import GATES
            if (metadata['schema'] != 37
                    or metadata['phase'] != ('completed' if receipt is not None else 'pending')
                    or metadata['task'] != self.task_id
                    or not isinstance(metadata['repository'], str)
                    or not Path(metadata['repository']).is_absolute()
                    or not isinstance(metadata['base_branch'], str)
                    or not metadata['base_branch']
                    or metadata['cas'] != 'exact-ref B-to-C'
                    or not isinstance(context, dict)
                    or metadata['context'] != context
                    or metadata['B'] != context['B'] or metadata['C'] != context['C']
                    or metadata['tree'] != context['tree'] or metadata['M'] != context['M']
                    or metadata['attempt'] != data['attempt']
                    or not isinstance(metadata['candidate_ref_at_freeze'], str)
                    or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',
                        metadata['candidate_ref_at_freeze'])
                    or metadata['key_id'] != data.get('evidence_key_id')
                    or not isinstance(metadata['nonce'], str)
                    or not re.fullmatch(r'[0-9a-f]{64}', metadata['nonce'])
                    or type(metadata['generation']) is not int
                    or metadata['generation'] < 1
                    or metadata['generation'] > data['generation']
                    or (receipt is not None and metadata['generation'] != data['generation'])
                    or not isinstance(records, list) or len(records) != 4
                    or metadata['gate_signatures'] != [r['signature'] for r in records]
                    or not all(r['gate'] == gate and r['sequence'] == index
                        and r['task'] == self.task_id
                        and r['repository'] == metadata['repository']
                        and r['context'] == context and r['attempt'] == data['attempt']
                        and r['key_id'] == metadata['key_id'] and r['result'] == 'PASS'
                        for index, (gate, r) in enumerate(zip(GATES, records), 1))):
                raise CorruptStateError('Integration binding does not match current task and evidence')
            key = self._integration_key(data)
            previous = ''
            for record in records:
                body = dict(record)
                signature = body.pop('signature')
                if (record['previous'] != previous
                        or not hmac.compare_digest(signature,
                            hmac.new(key, self._integration_bytes(body), hashlib.sha256).hexdigest())):
                    raise CorruptStateError('Integration gate evidence is not authentic and ordered')
                previous = signature
            body = dict(metadata)
            signature = body.pop('signature')
            if (not isinstance(signature, str)
                    or not hmac.compare_digest(signature,
                        hmac.new(key, self._integration_bytes(body), hashlib.sha256).hexdigest())):
                raise CorruptStateError('Integration metadata signature is invalid')
            if receipt is not None and (type(receipt['integrated_at']) not in (int, float)
                    or receipt['integrated_at'] <= 0
                    or receipt['history_digest'] != hashlib.sha256(
                        self._integration_bytes(history)).hexdigest()):
                raise CorruptStateError('Invalid integration completion time')
        except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
            if isinstance(exc, CorruptStateError):
                raise
            raise CorruptStateError('Invalid integration state or evidence') from exc

    def _reload(self):
        if not self._lock.owned():
            raise RuntimeError('Reload requires lock ownership')
        try:
            raw = self.state_file.read_bytes()
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (OSError, ValueError) as exc:
            raise CorruptStateError(f'Authoritative state file {self.state_file} is corrupt or missing') from exc
        self._validate(data)
        self._lock._file.seek(0)
        try:
            witness = json.loads(self._lock._file.read(), object_pairs_hook=_unique_object)
            # Equality alone accepts bool/float generations as integers. Reject
            # ambiguous encodings before comparing this local consistency record.
            if (not isinstance(witness, dict) or set(witness) != {'generation', 'digest'}
                    or type(witness['generation']) is not int or witness['generation'] < 0
                    or not isinstance(witness['digest'], str)
                    or not re.fullmatch(r'[0-9a-f]{64}', witness['digest'])):
                raise ValueError('Invalid local consistency witness schema')
            if witness != {'generation': data['generation'], 'digest': hashlib.sha256(raw).hexdigest()}:
                raise ValueError('Snapshot does not match local consistency witness')
        except (ValueError, TypeError) as exc:
            raise CorruptStateError('Authoritative state freshness witness is missing or mismatched') from exc
        if data['generation'] < self._generation:
            raise CorruptStateError('Authoritative generation rolled back')
        self._data, self._generation = data, data['generation']

    @property
    def data(self):
        with self._lock:
            if not self._tx_depth:
                self._reload()
            return copy.deepcopy(self._data)

    def _persist(self):
        """The sole persistence primitive, callable only by an owning transaction."""
        if not self._lock.owned() or self._tx_depth != 1:
            raise RuntimeError('Persistence requires an owning transaction')
        # The immediate caller must be the installed integration code. An
        # arbitrary callback deeper under that frame has no persistence grant.
        # Validate the complete state delta against the durable snapshot too:
        # callbacks may mutate _data and return before this direct call.
        if self.state_file.exists():
            durable = json.loads(self.state_file.read_bytes(), object_pairs_hook=_unique_object)
            integration_changed = (durable.get('integration_pending') != self._data.get('integration_pending')
                or durable.get('integration_receipt') != self._data.get('integration_receipt')
                or (durable.get('execution_status') == 'COMPLETED') !=
                    (self._data.get('execution_status') == 'COMPLETED')
                or [r for r in durable.get('history', []) if isinstance(r, dict) and r.get('to') == 'COMPLETED'] !=
                    [r for r in self._data.get('history', []) if isinstance(r, dict) and r.get('to') == 'COMPLETED'])
            if integration_changed:
                frame = sys._getframe(1)
                direct_integration = (frame.f_code is StateManager._integrate.__code__
                    and frame.f_locals.get('self') is self)
                completion_boundary = (frame.f_code is StateManager._persist_completion.__code__
                    and frame.f_locals.get('self') is self
                    and frame.f_back is not None
                    and frame.f_back.f_code is StateManager._integrate.__code__
                    and frame.f_back.f_locals.get('self') is self)
                if not (direct_integration or completion_boundary):
                    raise TerminalStateError('Only the installed exact-ref integration operation may persist integration')
                candidate = copy.deepcopy(self._data)
                expected = copy.deepcopy(durable)
                expected['generation'] += 1
                if durable.get('integration_pending') is None and candidate.get('integration_pending') is not None:
                    if not direct_integration:
                        raise TerminalStateError('Only integration may persist pre-CAS intent')
                    # The only pre-CAS delta is the durable signed intent.
                    expected['integration_pending'] = candidate['integration_pending']
                elif durable.get('integration_pending') is not None and candidate.get('integration_pending') is None:
                    if candidate.get('execution_status') == 'COMPLETED':
                        if not completion_boundary:
                            raise TerminalStateError('Completion requires the trusted post-CAS persistence boundary')
                        # Completion may add exactly one row and one receipt.
                        # A ref read is a second check; the trusted merge helper
                        # must also have returned from its exact B-to-C CAS.
                        pending = durable['integration_pending']
                        if (self._exact_ref(Path(pending['repository']),
                                    f"refs/heads/{pending['base_branch']}") != pending['C']):
                            raise TerminalStateError('Actual exact-ref CAS required before completion persistence')
                        expected['history'].append(candidate['history'][-1])
                        expected['integration_receipt'] = candidate['integration_receipt']
                        expected['execution_status'] = 'COMPLETED'
                    else:
                        if not direct_integration:
                            raise TerminalStateError('Only integration may roll back pre-CAS intent')
                        # A failed CAS can clear intent only while B remains B.
                        pending = durable['integration_pending']
                        if self._exact_ref(Path(pending['repository']),
                                f"refs/heads/{pending['base_branch']}") != pending['B']:
                            raise TerminalStateError('Cannot clear intent after a moved or uncertain ref')
                    expected['integration_pending'] = None
                else:
                    raise TerminalStateError('Invalid integration persistence transition')
                if candidate != expected:
                    raise TerminalStateError('Integration persistence contains a callback-owned state change')
        self._validate(self._data)
        raw = json.dumps(self._data, sort_keys=True, indent=2).encode('utf-8')
        fd, name = tempfile.mkstemp(prefix=f'.{self.state_file.name}.tmp.', dir=self.state_dir)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.state_file)
            # A crash between replace and witness update fails closed on next load.
            self._lock._file.seek(0)
            self._lock._file.truncate()
            self._lock._file.write(json.dumps({'generation': self._data['generation'],
                'digest': hashlib.sha256(raw).hexdigest()}).encode())
            self._lock._file.flush()
            os.fsync(self._lock._file.fileno())
            self._generation = self._data['generation']
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _persist_completion(self):
        """Narrow post-CAS write site; callback calls cannot enter through it."""
        caller = sys._getframe(1)
        if caller.f_code is not StateManager._integrate.__code__ or caller.f_locals.get('self') is not self:
            raise TerminalStateError('Completion persistence requires the installed integration operation')
        self._persist()

    def _transaction(self, mutate, *, _authorization=None, _integration_authorization=None):
        with self._lock:
            if self._tx_depth:
                raise RuntimeError('Nested mutations are forbidden')
            self._reload()
            before = copy.deepcopy(self._data)
            self._tx_depth = 1
            try:
                result = mutate()
                terminal = before['current_state'] in TERMINAL or before['execution_status'] in ('FAILED', 'NEEDS_HUMAN_REVIEW', 'COMPLETED')
                changed = (before['current_state'], before['execution_status']) != (self._data['current_state'], self._data['execution_status'])
                if before['execution_status'] == 'COMPLETED':
                    raise TerminalStateError('Completed integration is immutable')
                pending_changed = before.get('integration_pending') != self._data.get('integration_pending')
                completing = self._data['execution_status'] == 'COMPLETED'
                if (pending_changed or completing or
                        before.get('integration_receipt') != self._data.get('integration_receipt')):
                    raise TerminalStateError('General transactions cannot persist integration authority')
                if completing and (before.get('integration_pending') is None
                        or before['current_state'] != 'AUTO_MERGE'):
                    raise TerminalStateError('Completion requires a durable pending integration')
                if terminal and changed:
                    caller = sys._getframe(1)
                    if (self._active_recovery_cap is not _authorization
                            or caller.f_code is not StateManager._recover.__code__
                            or caller.f_locals.get('self') is not self):
                        raise TerminalStateError('Terminal mutation requires a fresh recovery capability')
                self._data['generation'] = before['generation'] + 1
                self._persist()
                return result
            except BaseException:
                self._data = before
                raise
            finally:
                self._tx_depth = 0

    def _assert_active(self):
        if (self._data.get('integration_pending') is not None or self._data['current_state'] in TERMINAL
                or self._data['execution_status'] in ('FAILED', 'NEEDS_HUMAN_REVIEW', 'COMPLETED')):
            raise TerminalStateError('Cannot transition out of terminal state without dedicated authorization')

    def _transition(self, state, details):
        old = self._data['current_state']
        self._data['current_state'] = state
        self._data['history'].append(dict(timestamp=datetime.now(timezone.utc).isoformat(), **{'from': old, 'to': state}, details=sanitize_secret_text(str(details)), epoch=self._data['epoch']))

    def transition(self, new_state, details=''):
        if new_state not in VALID_STATES:
            raise ValueError(f"Invalid state '{new_state}'")
        def change():
            self._assert_active()
            old = self._data['current_state']
            if new_state in TERMINAL:
                raise TerminalStateError('Use atomic halt/review methods')
            if new_state != old and new_state not in EDGES.get(old, set()):
                raise IllegalStateTransitionError(f"Illegal FSM transition from '{old}' to '{new_state}'")
            self._transition(new_state, details)
        self._transaction(change)

    def set_execution_status(self, status):
        if status not in STATUSES:
            raise ValueError('Invalid execution status')
        if status == 'COMPLETED':
            raise TerminalStateError('Only an authorized exact-ref integration can complete a task')
        def change():
            self._assert_active()
            if status in ('FAILED', 'NEEDS_HUMAN_REVIEW'):
                raise TerminalStateError('Use atomic halt/review methods')
            self._data['execution_status'] = status
        self._transaction(change)

    def mark_interrupted(self):
        self.set_execution_status('INTERRUPTED')

    def register_worker_run(self):
        def change():
            self._assert_active()
            b = self._data['budgets']
            if b['worker_attempts_in_epoch'] >= b['max_worker_per_epoch']:
                return 'Worker attempt limit per epoch exceeded'
            if b['total_cumulative_worker_runs'] >= b['max_cumulative_worker_runs']:
                return 'Global cumulative worker build budget exceeded'
            b['worker_attempts_in_epoch'] += 1
            b['total_cumulative_worker_runs'] += 1
        reason = self._transaction(change)
        if reason:
            self.halt_human(reason)
            return False
        return True

    def can_worker_retry_in_epoch(self):
        b = self.data['budgets']
        return b['worker_attempts_in_epoch'] < b['max_worker_per_epoch']

    def _consume(self, counter, limit, reason, new_epoch=False):
        def change():
            self._assert_active()
            b = self._data['budgets']
            b[counter] += 1
            if b[counter] > b[limit]:
                return False
            if new_epoch:
                self._data['epoch'] += 1
                b['worker_attempts_in_epoch'] = 0
            return True
        if not self._transaction(change):
            self.halt_human(f'{counter} budget exhausted: {reason}')
            return False
        return True
    def consume_logic_replan(self, reason):
        return self._consume('logic_replans_used', 'max_logic_replans', reason, True)
    def consume_security_replan(self, reason):
        return self._consume('security_replans_used', 'max_security_replans', reason, True)
    def consume_spec_syntax_retry(self, reason):
        return self._consume('spec_syntax_retries_used', 'max_spec_syntax_retries', reason)

    def halt_human(self, reason, exit_process=True):
        safe = sanitize_secret_text(str(reason))
        def change():
            if self._data['execution_status'] == 'COMPLETED':
                raise TerminalStateError('Completed task cannot be rewritten')
            self._transition('HALT_HUMAN', safe)
            self._data['execution_status'] = 'FAILED'
        self._transaction(change)
        Path(f'CRASH_REPORT_{self.task_id}.md').write_text(f'# CIRCUIT BREAKER TRIGGERED - {self.task_id}\n\n{safe}\n', encoding='utf-8')
        if self.raise_on_halt:
            raise RuntimeError(f'Circuit Breaker triggered: {safe}')
        if exit_process:
            sys.exit(1)

    def request_human_review(self, reason, gate='LOGIC_AUDIT', exit_process=True):
        safe = sanitize_secret_text(str(reason))
        def change():
            self._assert_active()
            self._transition('HUMAN_REVIEW', safe)
            self._data['execution_status'] = 'NEEDS_HUMAN_REVIEW'
            self._data['blocked_reason'] = dict(gate=gate, reason=safe)
        self._transaction(change)
        Path(f'HUMAN_REVIEW_{self.task_id}.md').write_text(f'# HUMAN REVIEW REQUIRED - {self.task_id}\n\n{safe}\n', encoding='utf-8')
        if self.raise_on_halt:
            raise RuntimeError(f'Human review required ({gate}): {safe}')
        if exit_process:
            sys.exit(0)

    def record_audit_model(self, provider, model):
        def change():
            self._assert_active()
            self._data['audit_model_used'] = dict(provider=sanitize_secret_text(provider).strip().lower(), model=sanitize_secret_text(model).strip())
        self._transaction(change)

    def validate_strict_recovery(self, repo_root=None, base_branch='dev', *, mode='merge'):
        try:
            self._recovery_session(repo_root, base_branch, mode)
            return True, 'Strict current context and authentic evidence verified'
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            return False, str(exc)

    def _recovery_session(self, repo_root, base_branch, mode):
        import subprocess
        from orchestrator.gate_controller import VerificationSession, GATES
        from orchestrator.verification_context import VerificationContext
        if repo_root is None or mode not in ('merge', 'audit'):
            raise TerminalStateError('Explicit repository and recovery mode required')
        root = Path(repo_root).resolve()
        data = self.data
        if data.get('integration_pending') is not None or data.get('integration_receipt') is not None:
            raise TerminalStateError('Integration intent or receipt forbids ordinary recovery')
        history = data['history']
        expected = ('HALT_HUMAN', 'FAILED', 'AUTO_MERGE') if mode == 'merge' else ('HUMAN_REVIEW', 'NEEDS_HUMAN_REVIEW', 'LOGIC_AUDIT')
        if (data['current_state'] != expected[0] or data['execution_status'] != expected[1]
                or not history or history[-1].get('from') != expected[2]
                or history[-1].get('to') != expected[0]):
            raise TerminalStateError('Terminal state/history does not authorize this recovery')
        if mode == 'audit' and data.get('blocked_reason', {}).get('gate') != 'LOGIC_AUDIT':
            raise TerminalStateError('Review was not blocked at LOGIC_AUDIT')
        context = VerificationContext(**data['verification_context'])
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=root, text=True, stderr=subprocess.PIPE, timeout=30).strip()
        try:
            if git('rev-parse', f'refs/heads/{base_branch}') != context.B:
                raise TerminalStateError('Base reference drifted')
            if git('rev-parse', f'refs/heads/task/{self.task_id}') != context.C:
                raise TerminalStateError('Candidate branch drifted')
            if subprocess.run(['git', 'merge-base', '--is-ancestor', context.B, context.C], cwd=root, capture_output=True, timeout=30).returncode:
                raise TerminalStateError('Candidate is not a descendant of base')
            worktree = root / '.worktrees' / f'wt_{self.task_id}'
            if worktree.exists():
                status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=worktree, text=True, timeout=30)
                head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=worktree, text=True, timeout=30).strip()
                if status.strip() or head != context.C:
                    raise TerminalStateError('Preserved worktree drifted')
        except subprocess.SubprocessError as exc:
            raise TerminalStateError('Cannot validate current recovery Git objects') from exc
        session = VerificationSession(root, self, context, resume=True)
        required = GATES if mode == 'merge' else GATES[:3]
        if not session.verify_evidence(required=required):
            raise TerminalStateError('Authentic current gate evidence required')
        return session

    def authorize_recovery(self, repo_root, base_branch='dev', *, mode='merge'):
        with self._lock:
            session = self._recovery_session(repo_root, base_branch, mode)
            capability = object()
            # Keep the issued object alive while its identity keys this authority.
            self._recovery_caps[id(capability)] = (
                capability, self.data['generation'], Path(repo_root).resolve(), base_branch, mode)
            return capability, session

    @staticmethod
    def _exact_ref(root, ref):
        try:
            return subprocess.check_output(['git', 'rev-parse', '--verify', ref],
                cwd=root, text=True, encoding='utf-8', stderr=subprocess.PIPE, timeout=30).strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise TerminalStateError(f'Cannot read integration reference {ref}') from exc

    def _integrate(self, session, base_branch):
        """The sole completion issuer; CAS and state persistence remain separate."""
        from orchestrator.gate_controller import VerificationSession
        from scripts.merge_gate import execute_fast_forward_merge
        if type(session) is not VerificationSession or session.sm is not self:
            raise TerminalStateError('Current controller verification session required')
        root = Path(session.root).resolve()
        context = session.context
        base_ref = f'refs/heads/{base_branch}'
        candidate_ref = f'refs/heads/task/{self.task_id}'
        with self._lock:
            if self._tx_depth:
                raise RuntimeError('Nested integration is forbidden')
            snapshot = self.data
            if snapshot.get('integration_pending') is not None:
                raise TerminalStateError('Integration requires explicit reconciliation before retry')
            if snapshot['execution_status'] == 'COMPLETED':
                raise TerminalStateError('Task already completed')
            if (snapshot['current_state'] not in ('LOGIC_AUDIT', 'AUTO_MERGE')
                    or snapshot['execution_status'] not in ('RUNNING', 'INTERRUPTED')
                    or snapshot['verification_context'] != context.to_dict()
                    or snapshot['attempt'] != session.attempt):
                raise TerminalStateError('Current attempt and merge state required')
            if not session.verify_evidence():
                raise TerminalStateError('Complete authentic evidence required immediately before merge')
            if (session._candidate_ref_at_freeze is None
                    or self._exact_ref(root, candidate_ref) != session._candidate_ref_at_freeze):
                raise TerminalStateError('Candidate reference drifted before integration')
            if snapshot['current_state'] == 'LOGIC_AUDIT':
                self.transition('AUTO_MERGE')
            session._current()
            if not session.verify_evidence():
                raise TerminalStateError('Merge authorization changed')
            current = self.data
            body = dict(schema=37, phase='pending', task=self.task_id,
                repository=str(root), base_branch=base_branch, B=context.B, C=context.C,
                tree=context.tree, M=context.M, context=context.to_dict(),
                attempt=session.attempt,
                candidate_ref_at_freeze=session._candidate_ref_at_freeze,
                gate_signatures=[r['signature'] for r in current['gate_evidence']],
                key_id=current['evidence_key_id'], nonce=secrets.token_hex(32),
                generation=current['generation'] + 1, cas='exact-ref B-to-C')
            pending = dict(body, signature=hmac.new(self._integration_key(current),
                self._integration_bytes(body), hashlib.sha256).hexdigest())
            before = copy.deepcopy(self._data)
            self._tx_depth = 1
            try:
                if self._data.get('integration_pending') is not None:
                    raise TerminalStateError('Integration already pending')
                self._data['integration_pending'] = pending
                self._data['generation'] = before['generation'] + 1
                StateManager._persist(self)
            except BaseException:
                self._data = before
                raise
            finally:
                self._tx_depth = 0
            # The intent is durable before Git is touched. A crash after this
            # point leaves an explicit nonterminal state for reconciliation.
            if (self._exact_ref(root, candidate_ref) != session._candidate_ref_at_freeze
                    or not session.verify_evidence()):
                raise TerminalStateError('Integration context drifted after durable intent')
            passed, reason = execute_fast_forward_merge(root, context.B, context.C, base_branch)
            if not passed:
                # Only a still-unchanged B proves that no CAS took effect.
                try:
                    unchanged = self._exact_ref(root, base_ref) == context.B
                except TerminalStateError:
                    unchanged = False
                if unchanged:
                    before = copy.deepcopy(self._data)
                    self._tx_depth = 1
                    try:
                        self._data['integration_pending'] = None
                        self._data['generation'] = before['generation'] + 1
                        StateManager._persist(self)
                    except BaseException:
                        self._data = before
                        raise
                    finally:
                        self._tx_depth = 0
                return False, reason
            # A callback may return success and move the ref without conditional
            # CAS. Check the loaded implementation against installed build
            # literals, not against a writable module-level reference.
            from orchestrator.gate_controller import loaded_code_identity
            try:
                trusted_merge = (execute_fast_forward_merge.__module__ == 'scripts.merge_gate'
                    and loaded_code_identity(execute_fast_forward_merge.__code__) ==
                        '0c651a10f4d6f2a5730217fe84b889b047b7c040da89fbbb51c312c42f82cfe0'
                    and hashlib.sha256(inspect.getsource(execute_fast_forward_merge).encode()).hexdigest() ==
                        'e0ff668ab8c4e198bac0411fb0f21d192f5ff32a265a469a20583beab5b4d427')
            except (AttributeError, OSError, TypeError):
                trusted_merge = False
            if not trusted_merge:
                raise TerminalStateError('Substituted merge helper cannot attest exact-ref CAS')
            if (self._exact_ref(root, base_ref) != context.C
                    or self._exact_ref(root, candidate_ref) != session._candidate_ref_at_freeze
                    or not session.verify_evidence()):
                raise TerminalStateError('Claimed CAS success lacks exact current integration')
            before = copy.deepcopy(self._data)
            self._tx_depth = 1
            try:
                if self._data.get('integration_pending') != pending:
                    raise TerminalStateError('Durable integration intent changed')
                self._data['history'].append(dict(timestamp=datetime.now(timezone.utc).isoformat(),
                    **{'from': 'AUTO_MERGE', 'to': 'COMPLETED'},
                    details=f'Exact-ref CAS {base_ref}: {context.B} -> {context.C}',
                    epoch=self._data['epoch']))
                receipt = dict(body, phase='completed',
                    generation=self._data['generation'] + 1,
                    integrated_at=time.time(),
                    history_digest=hashlib.sha256(self._integration_bytes(
                        self._data['history'])).hexdigest())
                receipt['signature'] = hmac.new(self._integration_key(self._data),
                    self._integration_bytes(receipt), hashlib.sha256).hexdigest()
                self._data['integration_pending'] = None
                self._data['integration_receipt'] = receipt
                self._data['execution_status'] = 'COMPLETED'
                self._data['generation'] = before['generation'] + 1
                StateManager._persist_completion(self)
            except BaseException:
                self._data = before
                raise
            finally:
                self._tx_depth = 0
            return True, reason

    def reconcile_integration(self, repo_root):
        """Read-only crash reconciliation. Never infer completion from a moved ref."""
        with self._lock:
            data = self.data
            pending = data.get('integration_pending')
            if pending is None:
                return False, 'No unresolved durable integration intent'
            root = Path(repo_root).resolve()
            if str(root) != pending['repository']:
                return False, 'Pending integration belongs to a different repository'
            try:
                current = self._exact_ref(root, f"refs/heads/{pending['base_branch']}")
            except TerminalStateError as exc:
                return False, str(exc)
            if current == pending['C']:
                return False, 'Exact candidate is integrated; durable completion is absent. Administrative reconciliation required.'
            if current == pending['B']:
                return False, 'Base is unchanged; interrupted intent requires administrative reconciliation.'
            return False, 'Base reference diverged; administrative reconciliation required.'

    def _begin_verification(self, context, attempt, key_id, implementations):
        from orchestrator.verification_context import VerificationContext
        if not isinstance(context, VerificationContext):
            raise TypeError('VerificationContext required')
        def change():
            self._assert_active()
            if self._data['current_state'] != 'BUILDING':
                raise IllegalStateTransitionError('Verification must begin after BUILDING')
            self._data['verification_context'] = context.to_dict()
            self._data['attempt'] = attempt
            self._data['evidence_key_id'] = key_id
            self._data['implementations'] = implementations
            self._data['gate_evidence'] = []
        self._transaction(change)
    def can_resume_merge(self, repo_root=None, base_branch='dev'):
        return self.validate_strict_recovery(repo_root, base_branch, mode='merge')
    def can_resume_audit(self, repo_root=None, base_branch='dev'):
        return self.validate_strict_recovery(repo_root, base_branch, mode='audit')
    def execute_merge_recovery_transition(self, authorization, details=''):
        self._recover(authorization, 'merge', details)
    def execute_audit_recovery_transition(self, authorization, details=''):
        self._recover(authorization, 'audit', details)
    def _recover(self, authorization, mode, details):
        with self._lock:
            # id() and `is` never invoke caller-defined hash/equality. The stored
            # object is held strongly until this exact object is presented.
            key = id(authorization)
            entry = self._recovery_caps.get(key)
            if entry is not None and entry[0] is authorization:
                del self._recovery_caps[key]
            else:
                entry = None
            if entry is None:
                raise TerminalStateError('Dedicated fresh recovery authorization required')
            if self._active_recovery_cap is not None:
                raise TerminalStateError('Concurrent recovery attempt is forbidden')
            self._active_recovery_cap = authorization
            try:
                if entry[1] != self.data['generation'] or entry[4] != mode:
                    raise TerminalStateError('Dedicated fresh recovery authorization required')
                self._recovery_session(entry[2], entry[3], mode)
                def change():
                    if self._data['generation'] != entry[1]:
                        raise TerminalStateError('Recovery capability is stale')
                    self._transition('AUTO_MERGE' if mode == 'merge' else 'LOGIC_AUDIT', details)
                    self._data['execution_status'] = 'RUNNING'
                self._transaction(change, _authorization=authorization)
            finally:
                self._active_recovery_cap = None
    def issue_gate_evidence(self, *args, **kwargs):
        raise RuntimeError('Generic evidence issuance is forbidden; run a controller gate')
    def verify_all_evidence(self, repo_root=None):
        from orchestrator.gate_controller import VerificationSession
        from orchestrator.verification_context import VerificationContext
        try:
            root = Path(repo_root) if repo_root is not None else self.state_dir.parent.parent
            context = VerificationContext(**self.data['verification_context'])
            return VerificationSession(root, self, context, resume=True).verify_evidence()
        except (OSError, RuntimeError, ValueError, TypeError, KeyError):
            return False
