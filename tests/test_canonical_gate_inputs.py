import os
import json
import pytest
import subprocess
from pathlib import Path
from orchestrator.verification_manifest import VerificationManifest, CanonicalManifestError

def test_canonical_manifest_prevents_export_and_mutation_tampering(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    # Initialize a git repo
    subprocess.run(["git", "init"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root)

    # Create files, including some that export-ignore would target
    (repo_root / "normal.py").write_text("print('normal')")
    (repo_root / "secret.txt").write_text("secret_data")
    (repo_root / ".gitattributes").write_text("secret.txt export-ignore\\n")

    subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=repo_root, check=True)
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    # Create candidate
    (repo_root / "normal.py").write_text("print('candidate')")
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "Candidate commit"], cwd=repo_root, check=True)
    candidate_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    # 1. Build canonical manifest
    manifest = VerificationManifest(
        repo_root=repo_root,
        candidate_sha=candidate_sha,
        expected_base_sha=base_sha,
        spec_digest="spec123",
        config_digest="cfg123",
        policy_digest="pol123"
    )

    data = manifest.dump()

    # Ensure export-ignore did not hide secret.txt from the manifest
    assert "secret.txt" in data["entries"]
    assert "normal.py" in data["entries"]

    # 2. Materialize to a fresh gate directory
    gate1_dir = tmp_path / "gate1"
    manifest.materialize(gate1_dir)

    # Ensure secret.txt was materialized (bypassing export-ignore)
    assert (gate1_dir / "secret.txt").read_text() == "secret_data"

    # 3. Simulate mutation during TESTING gate
    (gate1_dir / "normal.py").write_text("mutated_by_testing")
    (gate1_dir / "new_file.py").write_text("new")
    (gate1_dir / "secret.txt").unlink()

    # 4. Materialize SAST gate independently
    gate2_dir = tmp_path / "gate2"
    manifest.materialize(gate2_dir)

    # Ensure SAST gate is completely unaffected by TESTING gate mutations
    assert (gate2_dir / "normal.py").read_text() == "print('candidate')"
    assert not (gate2_dir / "new_file.py").exists()
    assert (gate2_dir / "secret.txt").read_text() == "secret_data"

    # 5. Manifest mismatch detection (simulating altered hash)
    manifest._manifest_data["entries"]["normal.py"]["exact_byte_size"] = 999

    gate3_dir = tmp_path / "gate3"
    with pytest.raises(CanonicalManifestError) as exc:
        manifest.materialize(gate3_dir)
    assert "Manifest integrity check failed" in str(exc.value)
