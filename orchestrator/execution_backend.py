"""Bounded Docker execution. No automatic or constructible unsafe-host fallback."""
import abc
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

IMAGE = 'python@sha256:4d752c0337b587da481dfbe2b1a5e171b3152d19213db6fbba4ff31d51abf192'
OUTPUT_LIMIT = 512 * 1024
CLEANUP_TIMEOUT = 5.0

class SecureExecutionUnavailableError(RuntimeError):
    pass

@dataclass(frozen=True)
class ExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool

class ExecutionBackend(abc.ABC):
    @abc.abstractmethod
    def execute(self, command, candidate_dir, scratch_dir, timeout_seconds, env=None):
        raise NotImplementedError

class DockerExecutionBackend(ExecutionBackend):
    def __init__(self):
        if not shutil.which('docker'):
            raise SecureExecutionUnavailableError('SECURE EXECUTION BACKEND UNAVAILABLE - FAIL CLOSED')

    def execute(self, command, candidate_dir, scratch_dir, timeout_seconds, env=None):
        candidate, scratch = Path(candidate_dir).resolve(), Path(scratch_dir).resolve()
        if (not candidate.is_dir() or not scratch.is_dir() or candidate == scratch
                or candidate.is_relative_to(scratch) or scratch.is_relative_to(candidate)):
            return ExecutionResult(2, '', 'Invalid isolation mounts', False)
        name = 'verify_' + uuid.uuid4().hex
        args = ['docker', 'run', '--rm', '--name', name, '--network=none', '--read-only',
                '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=64m',
                '-v', f'{candidate}:/src:ro', '-v', f'{scratch}:/scratch:rw',
                '--workdir', '/src', '--user', '1000:1000', '--cap-drop=ALL',
                '--security-opt=no-new-privileges', '--pids-limit=64', '--memory=512m', '--cpus=1.0']
        for key, value in (env or {}).items():
            args.extend(['-e', f'{key}={value}'])
        args.extend([IMAGE, *command])
        buffers = [bytearray(), bytearray()]
        overflow = threading.Event()
        timed_out, failure, code, process = False, '', 2, None
        readers = []
        def drain(stream, buffer):
            try:
                while True:
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    remaining = OUTPUT_LIMIT - len(buffer)
                    buffer.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        overflow.set()
                        process.kill()
            except (OSError, ValueError):
                overflow.set()
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for stream, buffer in zip((process.stdout, process.stderr), buffers):
                reader = threading.Thread(target=drain, args=(stream, buffer), daemon=True)
                reader.start()
                readers.append(reader)
            try:
                code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out, code = True, 124
                process.kill()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    failure = 'Docker client failed to terminate'
            for reader in readers:
                reader.join(timeout=2.0)
            if any(reader.is_alive() for reader in readers):
                failure = 'Output drains did not terminate'
            if overflow.is_set():
                code = 2
                failure = 'Candidate output exceeded limit'
        except (OSError, ValueError) as exc:
            failure = str(exc)
        finally:
            # A removal failure is never ignored: independently verify disappearance.
            deadline = time.monotonic() + CLEANUP_TIMEOUT
            try:
                subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=max(0.1, deadline - time.monotonic()))
                gone = subprocess.run(['docker', 'ps', '-a', '-q', '--filter', f'name=^/{name}$'],
                    capture_output=True, text=True, timeout=max(0.1, deadline - time.monotonic()))
                if gone.returncode != 0 or gone.stdout.strip():
                    failure = 'Container disappearance could not be verified'
            except (OSError, subprocess.TimeoutExpired):
                failure = 'Container cleanup exceeded deadline or failed'
        stdout, stderr = (bytes(buffer).decode('utf-8', errors='replace')[:OUTPUT_LIMIT] for buffer in buffers)
        if failure:
            return ExecutionResult(124 if timed_out else 2, stdout, (failure + '\n' + stderr)[:OUTPUT_LIMIT], timed_out)
        return ExecutionResult(code, stdout, stderr, timed_out)

class UnsafeHostExecutionBackend(ExecutionBackend):
    def __init__(self):
        raise SecureExecutionUnavailableError('UnsafeHostExecutionBackend is strictly forbidden in production')
    def execute(self, *args, **kwargs):
        raise SecureExecutionUnavailableError('Unsafe host execution is forbidden')
