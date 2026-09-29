import pytest
from pathlib import Path
from orchestrator.state_manager import StateManager
from orchestrator.verification_manifest import create_canonical_manifest
import json
import subprocess
import shutil

def setup_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "file").write_text("v1")
    subprocess.run(["git", "add", "file"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
    subprocess.run(["git", "branch", "dev"], cwd=repo, check=True)

    subprocess.run(["git", "checkout", "-b", "task/TASK-001"], cwd=repo, check=True)
    (repo / "file").write_text("v2")
    subprocess.run(["git", "add", "file"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "task"], cwd=repo, check=True)

    base_sha = subprocess.run(["git", "rev-parse", "dev"], cwd=repo, capture_output=True, text=True).stdout.strip()
    cand_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()

    (repo / "orchestrator").mkdir()
    (repo / "orchestrator" / "state").mkdir()
    (repo / "specs").mkdir()
    (repo / "specs" / "TASK-001.md").write_text("spec")
    (repo / "orchestrator" / "config.json").write_text("{}")
    subprocess.run(["git", "add", "orchestrator", "specs"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "add meta"], cwd=repo, check=True)

    return repo, base_sha, cand_sha

def create_valid_state(repo, base_sha, cand_sha):
    sm = StateManager("TASK-001", state_dir=str(repo / "orchestrator" / "state"))
    sm.data["current_state"] = "HALT_HUMAN"
    sm.data["execution_status"] = "FAILED"
    sm.data["history"] = [
        {"from": "AUTO_MERGE", "to": "HALT_HUMAN", "details": "merge failed"}
    ]
    manifest_digest = create_canonical_manifest(repo)
    sm.data["verification_candidate"] = {
        "base_commit": base_sha,
        "candidate_commit": cand_sha,
        "canonical_manifest_digest": manifest_digest,
        "spec_digest": "dummy",
        "config_digest": "dummy",
        "policy_digest": "dummy"
    }

    # We must use a list for gate_evidence to pass the current validate_strict_recovery
    def make_ev(name):
        return {
            "schema_version": "3.0",
            "gate_name": name,
            "candidate_commit_sha": cand_sha,
            "candidate_tree_sha": "dummy",
            "canonical_manifest_digest": manifest_digest,
            "expected_base_sha": base_sha,
            "spec_digest": "dummy",
            "config_digest": "dummy",
            "policy_digest": "dummy",
            "verifier_or_scanner_name": "dummy",
            "verifier_or_scanner_version": "dummy",
            "backend_identity": "dummy",
            "backend_security_profile_digest": "dummy",
            "result": "PASS",
            "timestamp": "now",
            "trusted_suite_identity": "dummy",
            "trusted_suite_version": "dummy"
        }

    sm.data["gate_evidence"] = [
        make_ev("DIFF_GATE"),
        make_ev("TESTING"),
        make_ev("SAST"),
        make_ev("LOGIC_AUDIT")
    ]
    sm._save_unlocked()
    return sm

def get_orchestrator_mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("orchestrator_module", "orchestrator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_recovery_accepts_changed_context(tmp_path, monkeypatch):
    mod = get_orchestrator_mod()
    monkeypatch.setattr(mod, "is_repo_clean", lambda root: (True, ""))

    repo, base_sha, cand_sha = setup_repo(tmp_path)
    sm = create_valid_state(repo, base_sha, cand_sha)

    (repo / "specs" / "TASK-001.md").write_text("hacked spec")

    success = mod.resume_merge("TASK-001", base_branch="dev", repo_root=repo)
    if success:
        pytest.fail("FAIL-BEFORE: Recovery accepted state despite changed context (spec_digest mismatch)")

def test_recovery_accepts_incomplete_gates(tmp_path, monkeypatch):
    mod = get_orchestrator_mod()
    monkeypatch.setattr(mod, "is_repo_clean", lambda root: (True, ""))

    repo, base_sha, cand_sha = setup_repo(tmp_path)
    sm = create_valid_state(repo, base_sha, cand_sha)

    sm.data["gate_evidence"] = [sm.data["gate_evidence"][0]]
    sm._save_unlocked()

    success = mod.resume_merge("TASK-001", base_branch="dev", repo_root=repo)
    if success:
        pytest.fail("FAIL-BEFORE: Recovery accepted state with incomplete gate evidence")
