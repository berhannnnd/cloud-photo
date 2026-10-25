"""Serialize public provider calls across processes sharing a local profile.

Provider reads also issue references and may update shared state. OS locks are
released on process exit; no provider credential or ledger file is inspected.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import time


@contextmanager
def provider_lock(provider, profile, timeout=120):
    identity = hashlib.sha256((provider + '\0' + profile).encode()).hexdigest()
    directory = Path.home() / '.cache' / 'cloud-photo' / 'provider-locks'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / (identity + '.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(fd).st_size == 0:
                os.write(fd, b'\0')
            def acquire():
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            def release():
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(fd, fcntl.LOCK_UN)
        deadline = time.monotonic() + timeout
        while not acquired:
            try:
                acquire()
                acquired = True
            except (BlockingIOError, OSError) as exc:
                import errno
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError('provider profile is busy') from None
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            release()
        os.close(fd)
