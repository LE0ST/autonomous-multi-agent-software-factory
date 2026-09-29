import dataclasses
import subprocess
import pytest


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def repo_fixture(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-b', 'dev')
    git(root, 'config', 'user.name', 'Round36')
    git(root, 'config', 'user.email', 'round36@example.invalid')
    (root / 'specs').mkdir()
    (root / 'orchestrator').mkdir()
    (root / 'specs/R36.md').write_text('frozen spec')
    (root / 'orchestrator/config.json').write_text('{}')
    (root / 'orchestrator/verification_policy.json').write_text('{"require_pytest": false}')
    (root / 'file.py').write_text('base')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'base')
    base = git(root, 'rev-parse', 'HEAD')
    (root / 'file.py').write_text('candidate')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'candidate')
    return root, base, git(root, 'rev-parse', 'HEAD')


def test_selection_race_does_not_rediscover_head(tmp_path):
    from orchestrator.verification_context import VerificationContext
    root, base, candidate = repo_fixture(tmp_path)
    (root / 'file.py').write_text('racing commit')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'race')
    context = VerificationContext.capture(root, 'R36', base, candidate)
    assert context.C == candidate
    assert context.tree == git(root, 'rev-parse', candidate + '^{tree}')
    assert context.tree != git(root, 'rev-parse', 'HEAD^{tree}')
    assert context.rebuild_manifest(root).dump()['candidate_commit_sha'] == candidate
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.C = git(root, 'rev-parse', 'HEAD')


@pytest.mark.parametrize('path', ['specs/R36.md', 'orchestrator/config.json', 'orchestrator/verification_policy.json'])
def test_current_context_change_rejected(tmp_path, path):
    from orchestrator.verification_context import VerificationContext
    root, base, candidate = repo_fixture(tmp_path)
    context = VerificationContext.capture(root, 'R36', base, candidate)
    assert context.verify_current(root, 'R36')
    (root / path).write_text('changed')
    assert not context.verify_current(root, 'R36')


def test_symbolic_manifest_input_is_rejected(tmp_path):
    from orchestrator.verification_manifest import VerificationManifest
    root, base, candidate = repo_fixture(tmp_path)
    with pytest.raises(ValueError):
        VerificationManifest(root, 'HEAD', base, 'a' * 64, 'b' * 64, 'c' * 64)
