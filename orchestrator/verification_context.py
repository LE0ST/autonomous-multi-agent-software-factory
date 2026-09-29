"""One immutable identity shared by verification, evidence, recovery and merge."""
import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from orchestrator.verification_manifest import VerificationManifest

DEFAULT_POLICY = b'{"schema":36,"require_pytest":false,"suite":"password-v36","evidence_ttl_seconds":86400}'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def context_bytes(root, task_id):
    root = Path(root)
    config = root / 'orchestrator/config.json'
    policy = root / 'orchestrator/verification_policy.json'
    return ((root / 'specs' / f'{task_id}.md').read_bytes(),
            config.read_bytes() if config.exists() else b'{}',
            policy.read_bytes() if policy.exists() else DEFAULT_POLICY)


@dataclass(frozen=True)
class VerificationContext:
    B: str
    C: str
    tree: str
    M: str
    spec_digest: str
    config_digest: str
    policy_digest: str

    def __post_init__(self):
        for name in ('B', 'C', 'tree'):
            if not isinstance(getattr(self, name), str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', getattr(self, name)):
                raise ValueError('Exact Git object IDs are required')
        for name in ('M', 'spec_digest', 'config_digest', 'policy_digest'):
            if not isinstance(getattr(self, name), str) or not re.fullmatch(r'[0-9a-f]{64}', getattr(self, name)):
                raise ValueError('Exact SHA256 digest required')

    @classmethod
    def capture(cls, root, task_id, base_sha, candidate_sha):
        spec, config, policy = context_bytes(root, task_id)
        hashes = tuple(map(digest, (spec, config, policy)))
        manifest = VerificationManifest(Path(root), candidate_sha, base_sha, *hashes)
        return cls(base_sha, candidate_sha, manifest.dump()['candidate_tree_sha'], manifest.digest, *hashes)

    def to_dict(self):
        return asdict(self)

    @property
    def identity(self):
        return digest(json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':')).encode())

    def rebuild_manifest(self, root):
        manifest = VerificationManifest(Path(root), self.C, self.B, self.spec_digest, self.config_digest, self.policy_digest)
        if manifest.digest != self.M or manifest.dump()['candidate_tree_sha'] != self.tree:
            raise ValueError('Candidate tree/manifest changed')
        return manifest

    def verify_current(self, root, task_id):
        try:
            return self == self.capture(root, task_id, self.B, self.C)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            return False
