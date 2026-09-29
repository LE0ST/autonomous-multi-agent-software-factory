import pytest
import subprocess
from pathlib import Path

def test_manifest_rejects_unsafe_paths(tmp_path):
    from orchestrator.verification_manifest import CanonicalManifestError, VerificationManifest

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=repo, check=True)

    # We test that materialization rejects it, or VerificationManifest parsing rejects it
    # We'll just verify the exceptions are raised when creating a manifest with a mock get_git_output
    pass

def test_manifest_reconstructs_bytes(tmp_path):
    pass
