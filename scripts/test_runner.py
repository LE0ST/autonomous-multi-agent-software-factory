import sys
import json
import re
import hashlib
import types
from pathlib import Path
from typing import Tuple, Dict, Any

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from orchestrator.execution_backend import ExecutionBackend
except ImportError:
    pass

def load_config(repo_root: Path) -> dict:
    for candidate in [repo_root / "orchestrator" / "config.json", repo_root / ".orchestrator" / "config.json"]:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {
        "coverage_threshold": 85.0,
        "test_command": "python -m pytest --cov=src --cov-fail-under=85 -q"
    }

class TestSupervisor:
    def __init__(self, backend, repo_root: Path):
        self.backend = backend
        self.repo_root = repo_root

    def verify_candidate(self, candidate_dir: Path, scratch_dir: Path, *, policy_bytes=None) -> Tuple[bool, str, str, int, dict]:
        cfg = load_config(self.repo_root)

        trusted_dir = self.repo_root / "trusted_tests"
        if not trusted_dir.exists():
            return False, "", "No trusted verifier tests found. Autonomous verification requires an authoritative trusted test suite.", 1, {}

        # Execute exactly the bytes whose digest is reported; never import generic cached 'suite'.
        # The controller installation owns this directory, never the candidate materialization.
        evidence = {"trusted_verifier_result": "FAIL"}
        try:
            suite_bytes = (trusted_dir / 'suite.py').read_bytes()
            suite_hash = hashlib.sha256(suite_bytes).hexdigest()
            suite = types.ModuleType('_controller_suite_' + suite_hash)
            suite.__file__ = str(trusted_dir / 'suite.py')
            exec(compile(suite_bytes, suite.__file__, 'exec'), suite.__dict__)
            from orchestrator.verification_context import DEFAULT_POLICY
            policy_path = self.repo_root / 'orchestrator/verification_policy.json'
            policy = json.loads(policy_bytes if policy_bytes is not None else
                                (policy_path.read_bytes() if policy_path.exists() else DEFAULT_POLICY))
            if policy.get('require_pytest', False):
                return False, '', 'Required independent pytest completion is unsupported by this backend; FAIL CLOSED', 1, evidence
            if policy.get('suite', 'password-v36') != 'password-v36':
                return False, '', 'Unsupported trusted behavior suite', 1, evidence
        except Exception as exc:
            return False, '', f'Failed to load trusted suite/policy: {exc}', 1, evidence

        # Run assertions outside candidate interpreter
        try:
            passed, stdout, stderr = suite.run_all(self.backend, candidate_dir, scratch_dir)
            exit_code = 0 if passed else 1
        except Exception as e:
            passed, stdout, stderr, exit_code = False, "", f"Trusted suite error: {e}", 1

        evidence = {
            "execution_backend_identity": self.backend.__class__.__name__,
            "trusted_verifier_result": "PASS" if passed else "FAIL",
            "verifier_implementation": "TrustedSuiteSupervisor",
            "trusted_suite_identity": "trusted_tests",
            "trusted_suite_version": suite_hash,
        }

        return passed, stdout, stderr, exit_code, evidence

def run_tests(worktree_dir: Path, repo_root: Path) -> tuple[bool, str, str, int]:
    # Production MUST NOT use this legacy host test runner.
    raise NotImplementedError("Legacy host execution is strictly forbidden in production.")

TestSupervisor.__test__ = False

if __name__ == "__main__":
    from orchestrator.execution_backend import DockerExecutionBackend, SecureExecutionUnavailableError
    worktree_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    repo_root_path = Path.cwd()
    scratch_dir = repo_root_path / ".audit-tmp" / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    try:
        backend = DockerExecutionBackend()
    except Exception:
        print("[CIRCUIT BREAKER] Forced halt. SECURE EXECUTION BACKEND UNAVAILABLE - FAIL CLOSED")
        sys.exit(1)

    supervisor = TestSupervisor(backend=backend, repo_root=repo_root_path)
    passed, stdout, stderr, code, evidence = supervisor.verify_candidate(worktree_path, scratch_dir)

    payloads_dir = repo_root_path / "orchestrator" / "payloads"
    payloads_dir.mkdir(parents=True, exist_ok=True)

    if not passed:
        payload = {
            "exit_code": code,
            "stdout": stdout,
            "stderr": stderr,
            "evidence": evidence
        }
        failure_file = payloads_dir / "raw_test_failure.json"
        failure_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("[FAIL] Test Gate: FAILED")
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        sys.exit(1)

    success_file = payloads_dir / "raw_test_success.json"
    success_file.write_text(json.dumps({"evidence": evidence}, indent=2), encoding="utf-8")
    print("[PASS] Test Gate: controller behavioral challenges passed (pytest/coverage supplementary)")
    sys.exit(0)
