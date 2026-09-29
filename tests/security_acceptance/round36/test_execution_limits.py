import io
import subprocess
import pytest
from orchestrator.execution_backend import DockerExecutionBackend


@pytest.mark.parametrize('mode', ['timeout', 'overflow', 'cleanup_failure'])
def test_output_and_cleanup_are_bounded_and_fail_closed(tmp_path, monkeypatch, mode):
    import orchestrator.execution_backend as module
    monkeypatch.setattr(module.shutil, 'which', lambda x: 'docker')
    calls = []
    class Process:
        def __init__(self, *a, **kw):
            self.stdout = io.BytesIO(b'x' * 700000)
            self.stderr = io.BytesIO(b'y' * 700000)
            self.returncode = 0
            self.killed = False
        def communicate(self, timeout=None):
            if mode == 'timeout' and not self.killed:
                raise subprocess.TimeoutExpired('docker', timeout)
            return 'x' * 700000, 'y' * 700000
        def wait(self, timeout=None):
            if mode == 'timeout' and not self.killed:
                raise subprocess.TimeoutExpired('docker', timeout)
            return self.returncode
        def poll(self): return self.returncode
        def kill(self): self.killed = True
    monkeypatch.setattr(module.subprocess, 'Popen', Process)
    def run(command, **kw):
        calls.append((command, kw))
        return subprocess.CompletedProcess(command, 1 if mode == 'cleanup_failure' else 0, '', 'cleanup error')
    monkeypatch.setattr(module.subprocess, 'run', run)
    candidate, scratch = tmp_path / 'candidate', tmp_path / 'scratch'
    candidate.mkdir()
    scratch.mkdir()
    result = DockerExecutionBackend().execute(['python', 'main.py'], candidate, scratch, 0.1)
    assert result.exit_code != 0
    assert len(result.stdout) <= 524288 and len(result.stderr) <= 524288
    assert calls and all(0 < kwargs.get('timeout', 0) <= 10 for command, kwargs in calls)
    assert any(command[1] == 'ps' for command, kwargs in calls)
