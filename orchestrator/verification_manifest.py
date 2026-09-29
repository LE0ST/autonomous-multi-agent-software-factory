import os
import sys
import json
import hashlib
import stat
import re
import subprocess
from pathlib import Path
from typing import Dict, Any
from scripts.file_policy import normalize_relative_path


def get_git_output(cmd: list[str], repo_root: Path) -> bytes:
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, check=True)
    return proc.stdout

class CanonicalManifestError(RuntimeError):
    pass

class VerificationManifest:
    """
    Constructs and materializes canonical gate inputs directly from Git objects,
    preventing export-ignore and export-subst tampering.
    """

    def __init__(self, repo_root: Path, candidate_sha: str, expected_base_sha: str, spec_digest: str, config_digest: str, policy_digest: str):
        for value in (candidate_sha, expected_base_sha):
            if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', value):
                raise ValueError('Manifest requires explicit Git commit IDs; symbolic references are forbidden')
        self._repo_root = repo_root
        self._candidate_sha = candidate_sha
        self._expected_base_sha = expected_base_sha
        self._spec_digest = spec_digest
        self._config_digest = config_digest
        self._policy_digest = policy_digest
        self._manifest_data = {}
        self._manifest_digest = ""
        self._build_manifest()

    def _build_manifest(self):
        try:
            tree_out = get_git_output(["git", "rev-parse", f"{self._candidate_sha}^{{tree}}"], self._repo_root)
            tree_sha = tree_out.decode('utf-8').strip()
        except subprocess.CalledProcessError as e:
            raise CanonicalManifestError(f"Failed to get tree SHA for candidate {self._candidate_sha}: {e}")

        try:
            ls_tree_out = get_git_output(["git", "ls-tree", "-r", "-z", tree_sha], self._repo_root)
        except subprocess.CalledProcessError as e:
            raise CanonicalManifestError(f"Failed to read tree {tree_sha}: {e}")

        entries = {}
        seen_lower = set()

        for entry in ls_tree_out.split(b'\0'):
            if not entry:
                continue

            metadata, path = entry.split(b'\t', 1)
            mode, obj_type, obj_sha = metadata.split(b' ')

            path = path.decode('utf-8')
            mode = mode.decode('utf-8')
            obj_type = obj_type.decode('utf-8')
            obj_sha = obj_sha.decode('utf-8')
            try:
                canonical_path = normalize_relative_path(path)
                if canonical_path != path or any(part in ('.controller-secrets', '.evidence_key', 'evidence.key', '.git') for part in path.split('/')):
                    raise ValueError('Controller secrets and path aliases are forbidden')
            except ValueError as exc:
                raise CanonicalManifestError(str(exc)) from exc

            if obj_type == "commit":
                raise CanonicalManifestError(f"Git submodules are not supported for canonical verification: {path}")

            if obj_type != "blob":
                continue

            # Windows canonicalization: lowercase and normalize slashes
            path_normalized = path.replace("\\", "/").lower()
            if path_normalized in seen_lower:
                raise CanonicalManifestError(f"Canonical path collision detected, failing closed: {path}")
            seen_lower.add(path_normalized)

            if ".." in path or path.startswith("/") or path.startswith("\\") or ":" in path or Path(path).is_absolute():
                raise CanonicalManifestError(f"Invalid path traversal or absolute path in Git tree: {path}")

            try:
                size_out = get_git_output(["git", "cat-file", "-s", obj_sha], self._repo_root)
                size = int(size_out.decode('utf-8').strip())
            except subprocess.CalledProcessError:
                raise CanonicalManifestError(f"Failed to get object size for {obj_sha}")

            try:
                content = get_git_output(["git", "cat-file", "-p", obj_sha], self._repo_root)
                content_hash = hashlib.sha256(content).hexdigest()
            except subprocess.CalledProcessError:
                raise CanonicalManifestError(f"Failed to read blob {obj_sha}")

            entries[path] = {
                "normalized_relative_path": path.replace("\\", "/"),
                "git_mode": mode,
                "blob_identity": obj_sha,
                "exact_content_hash": content_hash,
                "exact_byte_size": size
            }

        sorted_entries = dict(sorted(entries.items()))

        self._manifest_data = {
            "candidate_commit_sha": self._candidate_sha,
            "candidate_tree_sha": tree_sha,
            "expected_base_commit_sha": self._expected_base_sha,
            "spec_digest": self._spec_digest,
            "config_digest": self._config_digest,
            "policy_digest": self._policy_digest,
            "verifier_implementation": "ManifestVerifier/1.0",
            "scanner_policy": "DefaultScanner/1.0",
            "entries": sorted_entries
        }

        serialized = json.dumps(self._manifest_data, separators=(',', ':'), sort_keys=True).encode('utf-8')
        self._manifest_digest = hashlib.sha256(serialized).hexdigest()
        self._manifest_data["canonical_manifest_digest"] = self._manifest_digest

        # Capture the immutable serialized bytes so that mutation of self._manifest_data does not affect materialization
        self._immutable_snapshot_bytes = json.dumps(self._manifest_data, separators=(',', ':'), sort_keys=True).encode('utf-8')

    @property
    def digest(self) -> str:
        return self._manifest_digest

    def dump(self) -> Dict[str, Any]:
        import copy
        return copy.deepcopy(self._manifest_data)

    def materialize(self, target_dir: Path):
        """POSIX descriptor-relative writes; unsupported native Windows fails closed."""
        if os.name == 'nt' or not hasattr(os, 'O_NOFOLLOW') or os.open not in os.supports_dir_fd:
            raise CanonicalManifestError('Secure materialization not available on this platform. Fail closed.')
        target = Path(target_dir).absolute()
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent_fd = os.open(target.anchor, flags)
        root_fd = None
        try:
            # Traverse each existing ancestor with no-follow handles, without resolve/check/write races.
            for part in target.parent.parts[1:]:
                child = os.open(part, flags, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = child
            os.mkdir(target.name, mode=0o700, dir_fd=parent_fd)
            root_fd = os.open(target.name, flags, dir_fd=parent_fd)
            snapshot = json.loads(self._immutable_snapshot_bytes)
            for path, info in snapshot['entries'].items():
                clean = normalize_relative_path(path)
                if clean != path or info['git_mode'] not in ('100644', '100755'):
                    raise CanonicalManifestError('Only canonical regular files can be materialized')
                content = get_git_output(['git', 'cat-file', '-p', info['blob_identity']], self._repo_root)
                if len(content) != info['exact_byte_size'] or hashlib.sha256(content).hexdigest() != info['exact_content_hash']:
                    raise CanonicalManifestError(f'Canonical blob mismatch: {path}')
                current_fd = os.dup(root_fd)
                try:
                    parts = path.split('/')
                    for part in parts[:-1]:
                        try:
                            os.mkdir(part, mode=0o755, dir_fd=current_fd)
                        except FileExistsError:
                            pass
                        child = os.open(part, flags, dir_fd=current_fd)
                        os.close(current_fd)
                        current_fd = child
                    fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=current_fd)
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                        os.fchmod(stream.fileno(), 0o555 if info['git_mode'] == '100755' else 0o444)
                finally:
                    os.close(current_fd)
            os.fchmod(root_fd, 0o755)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise CanonicalManifestError(f'Secure materialization failed: {exc}') from exc
        finally:
            if root_fd is not None:
                os.close(root_fd)
            os.close(parent_fd)

def create_canonical_manifest(repo_root: Path, candidate_sha=None, expected_base_sha=None,
                              spec_digest=None, config_digest=None, policy_digest=None) -> str:
    """Deprecated adapter: all identities must be explicit; never rediscover refs."""
    if any(v is None for v in (candidate_sha, expected_base_sha, spec_digest, config_digest, policy_digest)):
        raise ValueError('Explicit candidate, base and context digests are required')
    return VerificationManifest(repo_root, candidate_sha, expected_base_sha,
                                spec_digest, config_digest, policy_digest).digest
