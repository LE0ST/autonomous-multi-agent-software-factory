import pytest
import shutil
from unittest.mock import patch, MagicMock
from pathlib import Path
from orchestrator.execution_backend import DockerExecutionBackend, SecureExecutionUnavailableError, ExecutionResult

def test_secure_execution_backend_fails_closed_when_unavailable():
    with patch('shutil.which', return_value=None):
        with pytest.raises(SecureExecutionUnavailableError) as exc_info:
            backend = DockerExecutionBackend()
        assert 'SECURE EXECUTION BACKEND UNAVAILABLE - FAIL CLOSED' in str(exc_info.value)

def test_docker_backend_exact_profile_construction():
    with patch('shutil.which', return_value='/usr/bin/docker'):
        backend = DockerExecutionBackend()

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ('stdout_data', 'stderr_data')
        mock_proc.returncode = 0

        with patch('subprocess.Popen', return_value=mock_proc) as mock_popen:
            res = backend.execute(
                command=['python', 'script.py'],
                candidate_dir=Path('/candidate'),
                scratch_dir=Path('/scratch'),
                timeout_seconds=5.0,
                env={'MY_VAR': '1'}
            )

            assert res.exit_code == 0
            assert res.stdout == 'stdout_data'

            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]

            assert cmd[0:2] == ['docker', 'run']
            assert '--rm' in cmd
            assert '--network=none' in cmd or ('--network' in cmd and cmd[cmd.index('--network') + 1] == 'none')
            assert '--read-only' in cmd
            assert '--cap-drop=ALL' in cmd or ('--cap-drop' in cmd and cmd[cmd.index('--cap-drop') + 1] == 'ALL')
            assert '--security-opt=no-new-privileges' in cmd or ('--security-opt' in cmd and cmd[cmd.index('--security-opt') + 1] == 'no-new-privileges')
            assert '--tmpfs' in cmd and '/tmp' in cmd[cmd.index('--tmpfs') + 1]

            image_idx = -1
            for i, arg in enumerate(cmd):
                if '@sha256:' in arg:
                    image_idx = i
                    break

            assert image_idx != -1, 'Image with sha256 digest not found in docker command'
            assert cmd[image_idx + 1:] == ['python', 'script.py'], 'Command must appear immediately after image'

def test_docker_backend_container_lifecycle_on_timeout():
    with patch('shutil.which', return_value='/usr/bin/docker'):
        backend = DockerExecutionBackend()

        mock_proc = MagicMock()
        import subprocess
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd='docker', timeout=5.0)

        with patch('subprocess.Popen', return_value=mock_proc) as mock_popen,              patch('subprocess.run') as mock_run:

            mock_proc.communicate.side_effect = [subprocess.TimeoutExpired(cmd='docker', timeout=5.0), ('stdout_data', 'stderr_data')]

            res = backend.execute(
                command=['python', 'script.py'],
                candidate_dir=Path('/candidate'),
                scratch_dir=Path('/scratch'),
                timeout_seconds=5.0
            )

            assert res.timed_out is True
            assert res.exit_code == 124

            mock_run.assert_called()
            killed_cmd = mock_run.call_args_list[0][0][0]
            assert 'docker' in killed_cmd
            assert 'rm' in killed_cmd or 'stop' in killed_cmd or 'kill' in killed_cmd
