import os
import sys
import threading
import tempfile
import time
from pathlib import Path
from orchestrator.verification_manifest import VerificationManifest, CanonicalManifestError
import pytest
import subprocess
import hashlib

def get_blob_hash_size(repo_root, content):
    # write content as blob
    proc = subprocess.run(["git", "hash-object", "-w", "--stdin"], input=content, cwd=repo_root, capture_output=True)
    return proc.stdout.decode().strip(), len(content), hashlib.sha256(content).hexdigest()

def test_manifest_post_digest_mutation(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, check=True)

    (repo_root / "a.txt").write_text("initial")
    subprocess.run(["git", "add", "a.txt"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    manifest = VerificationManifest(repo_root, head, "base", "spec", "config", "policy")
    original_digest = manifest.digest

    # "Valid blob/hash/size substituted after digest check -> accepted under unchanged digest"
    # Wait, the only way an unchanged digest accepts a mutated dictionary is if the mutation bypassed the digest check.
    # Ah! The integrity check in materialize is:
    # current_digest = hashlib.sha256(serialized).hexdigest()
    # if current_digest != self._manifest_digest: raise
    # What if the attacker mutates self._manifest_data AND self._manifest_digest?
    # The caller stored `original_digest`.
    # `materialize` doesn't take the `expected_digest` as an argument! It just checks `self._manifest_digest`.

    new_blob, new_size, new_hash = get_blob_hash_size(repo_root, b"hacked")
    manifest._manifest_data["entries"]["a.txt"]["blob_identity"] = new_blob
    manifest._manifest_data["entries"]["a.txt"]["exact_byte_size"] = new_size
    manifest._manifest_data["entries"]["a.txt"]["exact_content_hash"] = new_hash

    # Fix the manifest's internal digest so the internal check passes
    import json
    serialized = json.dumps({k: v for k, v in manifest._manifest_data.items() if k != "canonical_manifest_digest"}, separators=(',', ':'), sort_keys=True).encode('utf-8')
    manifest._manifest_digest = hashlib.sha256(serialized).hexdigest()

    target_dir = tmp_path / "target"
    try:
        manifest.materialize(target_dir)
        # If we reach here, it must not be Windows, so assert the bytes are NOT hacked
        assert (target_dir / "a.txt").read_text() == "initial", "Post-digest mutation wrote changed bytes!"
    except CanonicalManifestError as e:
        assert "fail closed" in str(e).lower()

def test_manifest_alias_collision(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "core.protectNTFS", "false"], cwd=repo_root, check=True)

    # Create an alias collision manually in git index
    blob_a, _, _ = get_blob_hash_size(repo_root, b"A")
    blob_b, _, _ = get_blob_hash_size(repo_root, b"B")

    # We will use git update-index to add nested/a.txt and nested\a.txt
    subprocess.run(["git", "update-index", "--add", "--cacheinfo", f"100644,{blob_a},nested/a.txt"], cwd=repo_root, check=True)
    subprocess.run(["git", "update-index", "--add", "--cacheinfo", f"100644,{blob_b},nested\\a.txt"], cwd=repo_root, check=True)

    tree_sha = subprocess.run(["git", "write-tree"], cwd=repo_root, capture_output=True, text=True).stdout.strip()
    commit_sha = subprocess.run(["git", "commit-tree", tree_sha, "-m", "col"], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    try:
        manifest = VerificationManifest(repo_root, commit_sha, "base", "spec", "config", "policy")
        target_dir = tmp_path / "target"
        manifest.materialize(target_dir)
        # If it gets here without failing, it means it wrote both and one overwrote the other.
        pytest.fail("Alias collision was accepted and materialized!")
    except CanonicalManifestError as e:
        assert "collision" in str(e).lower() or "fail closed" in str(e).lower()

def test_manifest_junction_race(tmp_path):
    # The requirement says: "If safe handle-relative materialization cannot be implemented on the platform, fail closed rather than materialize insecurely."
    # We can test if the materialize method is race-resistant by using a mock.
    # But since the instructions say "fail closed", we can just ensure that on Windows, materialize fails with CanonicalManifestError, OR it successfully prevents junctions.

    # I'll just check if the code has native race-resistant handles. It doesn't.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, check=True)

    (repo_root / "safe").mkdir()
    (repo_root / "safe" / "file.txt").write_text("content")
    subprocess.run(["git", "add", "safe/file.txt"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    manifest = VerificationManifest(repo_root, head, "base", "spec", "config", "policy")
    target_dir = tmp_path / "target"

    # Start materialization in a thread, but hook the directory creation to insert a junction.
    # Since python's `open` on Windows follows junctions by default, and `mkdir` also follows,
    # the code in `materialize` that does:
    # full_path.parent.mkdir(...)
    # full_path.write_bytes(...)
    # is inherently vulnerable to junction replacement.

    # For now, just test if it's Windows and it throws an error or not.
    # To fix this, we will raise CanonicalManifestError("Secure materialization not available on this platform") in `materialize()`.
    # If it fails closed, the test passes.
    try:
        manifest.materialize(target_dir)
        pytest.fail("Native Windows materialization is NOT race-resistant and MUST fail closed.")
    except CanonicalManifestError as e:
        assert "fail closed" in str(e).lower() or "not available" in str(e).lower() or "secure materialization" in str(e).lower(), str(e)
