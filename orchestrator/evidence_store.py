"""Controller-only HMAC material, never copied into a candidate materialization."""
import ctypes
import hashlib
import os
import secrets
import stat
from pathlib import Path


def _private(path, directory=False):
    if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
        raise RuntimeError('Evidence key path cannot contain links/reparse points')
    if os.name == 'nt':
        # Protected DACL: only the object's owner and LocalSystem. No inherited grants.
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
        convert.restype = ctypes.c_int
        apply = advapi.SetFileSecurityW
        apply.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
        apply.restype = ctypes.c_int
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        descriptor = ctypes.c_void_p()
        flags = 'OICI' if directory else ''
        sddl = f'D:P(A;{flags};FA;;;OW)(A;{flags};FA;;;SY)'
        if not convert(sddl, 1, ctypes.byref(descriptor), None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not apply(str(path), 0x80000004, descriptor):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.LocalFree(descriptor)
    else:
        if path.stat().st_uid != os.geteuid():
            raise RuntimeError('Controller does not own evidence key path')
        os.chmod(path, 0o700 if directory else 0o600)
        if stat.S_IMODE(path.stat().st_mode) != (0o700 if directory else 0o600):
            raise RuntimeError('Unable to restrict evidence permissions')


class EvidenceKey:
    def __init__(self, state_dir, expected_id=None):
        directory = Path(state_dir) / '.controller-secrets'
        # Check the existing ancestry before touching permissions or creating secrets.
        for parent in (Path(state_dir), *Path(state_dir).parents):
            if parent.is_symlink() or getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400:
                raise RuntimeError('Linked evidence ancestry is forbidden')
        directory.mkdir(mode=0o700, exist_ok=True)
        _private(directory, True)
        self.path = directory / 'evidence.key'
        if not self.path.exists():
            if expected_id:
                raise RuntimeError('Evidence key was deleted; cannot regenerate it')
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(secrets.token_bytes(32))
                stream.flush()
                os.fsync(stream.fileno())
        _private(self.path)
        self.identity = hashlib.sha256(self.read()).hexdigest()
        if expected_id is not None and self.identity != expected_id:
            raise RuntimeError('Evidence key was replaced')

    def read(self):
        _private(self.path)
        value = self.path.read_bytes()
        if len(value) != 32:
            raise RuntimeError('Invalid evidence key length')
        if hasattr(self, 'identity') and hashlib.sha256(value).hexdigest() != self.identity:
            raise RuntimeError('Evidence key was replaced')
        return value
