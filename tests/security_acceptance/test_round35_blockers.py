import pytest
import os
import sys
import json
import hashlib
import shutil
import subprocess
from pathlib import Path

def get_python():
    return sys._base_executable if hasattr(sys, '_base_executable') else sys.executable

# BLOCKER 1: AUTHORITATIVE TRUSTED VERDICT
def test_authoritative_trusted_verdict_rejects_repr_spoof(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "dev"], cwd=repo_dir, check=True)

    trusted_dir = repo_dir / "trusted_tests"
    trusted_dir.mkdir()
    shutil.copy("trusted_tests/suite.py", trusted_dir / "suite.py")

    cand = tmp_path / "candidate"
    (cand / "src" / "auth").mkdir(parents=True)

    # Malicious repr spoof
    (cand / "src" / "auth" / "password_validator.py").write_text(
        "class Lie:\n def __init__(self,p): self.p=p\n def __repr__(self): return 'True' if self.p=='Valid123!' else 'False'\ndef validate_password(p): return Lie(p)\n"
    )

    scratch = tmp_path / "scratch"
    scratch.mkdir()

    from scripts.test_runner import TestSupervisor
    from orchestrator.execution_backend import ExecutionResult
    class LocalBoundary:
        def execute(self, command, candidate_dir, scratch_dir, timeout_seconds, env=None):
            translated = [str(x).replace('/src/src', str(candidate_dir/'src')).replace('/scratch/', str(scratch_dir)+os.sep) for x in command]
            if translated[0] == "python": translated[0] = get_python()
            p = subprocess.run(translated, cwd=candidate_dir, capture_output=True, text=True, timeout=timeout_seconds, env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONPATH': str(candidate_dir / 'src')})
            return ExecutionResult(p.returncode, p.stdout, p.stderr, False)

    if "suite" in sys.modules: del sys.modules["suite"]
    supervisor = TestSupervisor(LocalBoundary(), repo_dir)
    passed, stdout, stderr, code, evidence = supervisor.verify_candidate(cand, scratch)

    assert passed is False, f"Vulnerability: Candidate bypassed the check using a spoofed repr. Output: {stdout}"

# BLOCKER 2: AUTHENTIC GATE EVIDENCE / RECOVERY PROVENANCE
def test_authentic_gate_evidence_rejects_synthetic_claims(tmp_path):
    from orchestrator.state_manager import StateManager
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "dev"], cwd=repo_dir, check=True)

    state_dir = repo_dir / "orchestrator" / "state"
    state_dir.mkdir(parents=True)
    sm = StateManager("T", state_dir=str(state_dir), raise_on_halt=False)
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"

    (repo_dir / "specs").mkdir()
    (repo_dir / "specs" / "T.md").write_text("spec")
    (repo_dir / "orchestrator").mkdir(exist_ok=True)
    (repo_dir / "orchestrator" / "config.json").write_text("{}")

    (repo_dir / "file").write_text("base")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo_dir, check=True)
    b = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True).stdout.strip()

    wt = repo_dir / ".worktrees" / "wt_T"
    subprocess.run(["git", "worktree", "add", "-b", "task/T", str(wt), "dev"], cwd=repo_dir, check=True)
    (wt / "file").write_text("candidate")
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "cand"], cwd=wt, check=True)
    c = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt, capture_output=True, text=True).stdout.strip()
    c_tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=wt, capture_output=True, text=True).stdout.strip()

    sm.data["verification_candidate"] = {
        "candidate_commit": c,
        "base_commit": b,
        "candidate_tree": c_tree,
        "canonical_manifest_digest": "fake_digest",
        "spec_digest": "fake_spec",
        "config_digest": "fake_config",
        "policy_digest": "fake_policy"
    }

    sm.data["gate_evidence"] = [
        {"schema_version": "3.0", "gate_name": g, "candidate_commit_sha": c, "candidate_tree_sha": c_tree, "canonical_manifest_digest": "fake_digest", "expected_base_sha": b, "spec_digest": "fake_spec", "config_digest": "fake_config", "policy_digest": "fake_policy", "result": "PASS", "verifier_or_scanner_name": "Fake", "verifier_or_scanner_version": "1.0", "backend_identity": "Fake", "backend_security_profile_digest": "fake", "trusted_suite_identity": "trusted_tests", "trusted_suite_version": "1.0", "timestamp": "2026-09-18T00:00:00Z"} for g in ["DIFF_GATE", "TESTING", "SAST", "LOGIC_AUDIT"]
    ]

    import json
    temp_file = Path(sm.state_file).with_suffix('.tmp')
    temp_file.write_text(json.dumps(sm.data, indent=2), encoding='utf-8')
    temp_file.replace(sm.state_file)

    import importlib.util
    spec = importlib.util.spec_from_file_location("orchestrator_script", "orchestrator.py")
    orchestrator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(orchestrator)

    res = orchestrator.resume_merge("T", base_branch="dev", repo_root=repo_dir)
    assert res is False, "Vulnerability: Fake evidence accepted"

# BLOCKER 3: FREEZE AND PERSIST THE ACTUAL B/C/M/CONTEXT USED BY GATES
def test_frozen_context_fails_closed_on_change(tmp_path):
    from orchestrator.state_manager import StateManager
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "dev"], cwd=repo_dir, check=True)

    state_dir = repo_dir / "orchestrator" / "state"
    state_dir.mkdir(parents=True)
    sm = StateManager("T", state_dir=str(state_dir), raise_on_halt=False)
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"

    (repo_dir / "specs").mkdir()
    (repo_dir / "specs" / "T.md").write_text("spec_changed")
    (repo_dir / "orchestrator").mkdir(exist_ok=True)
    (repo_dir / "orchestrator" / "config.json").write_text("{}")

    (repo_dir / "file").write_text("base")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo_dir, check=True)
    b = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True).stdout.strip()

    wt = repo_dir / ".worktrees" / "wt_T"
    subprocess.run(["git", "worktree", "add", "-b", "task/T", str(wt), "dev"], cwd=repo_dir, check=True)
    (wt / "file").write_text("candidate")
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "cand"], cwd=wt, check=True)
    c = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt, capture_output=True, text=True).stdout.strip()
    c_tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=wt, capture_output=True, text=True).stdout.strip()

    sm.data["verification_candidate"] = {
        "candidate_commit": c,
        "base_commit": b,
        "candidate_tree": c_tree,
        "canonical_manifest_digest": "fake_digest",
        "spec_digest": "old_spec_digest",
        "config_digest": "fake_config",
        "policy_digest": "fake_policy"
    }

    sm.data["gate_evidence"] = [
        {"schema_version": "3.0", "gate_name": g, "candidate_commit_sha": c, "candidate_tree_sha": c_tree, "canonical_manifest_digest": "fake_digest", "expected_base_sha": b, "spec_digest": "old_spec_digest", "config_digest": "fake_config", "policy_digest": "fake_policy", "result": "PASS", "verifier_or_scanner_name": "Fake", "verifier_or_scanner_version": "1.0", "backend_identity": "Fake", "backend_security_profile_digest": "fake", "trusted_suite_identity": "trusted_tests", "trusted_suite_version": "1.0", "timestamp": "2026-09-18T00:00:00Z"} for g in ["DIFF_GATE", "TESTING", "SAST", "LOGIC_AUDIT"]
    ]

    import json
    temp_file = Path(sm.state_file).with_suffix('.tmp')
    temp_file.write_text(json.dumps(sm.data, indent=2), encoding='utf-8')
    temp_file.replace(sm.state_file)

    import importlib.util
    spec = importlib.util.spec_from_file_location("orchestrator_script", "orchestrator.py")
    orchestrator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(orchestrator)

    res = orchestrator.resume_merge("T", base_branch="dev", repo_root=repo_dir)
    assert res is False, "Vulnerability: Context change not detected"

# BLOCKER 4: TERMINAL AUTHORIZATION MUST HAVE NO ESCAPE HATCH
def test_terminal_authorization_rejects_unauthorized_state_change(tmp_path):
    from orchestrator.state_manager import StateManager
    repo_dir = tmp_path / "repo"
    state_dir = repo_dir / "orchestrator" / "state"
    state_dir.mkdir(parents=True)

    sm = StateManager("T", state_dir=str(state_dir), raise_on_halt=False)
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    import json
    temp_file = Path(sm.state_file).with_suffix('.tmp')
    temp_file.write_text(json.dumps(sm.data, indent=2), encoding='utf-8')
    temp_file.replace(sm.state_file)

    with pytest.raises(Exception, match=r"terminal|authoriz"):
        sm.set_execution_status("RUNNING")
