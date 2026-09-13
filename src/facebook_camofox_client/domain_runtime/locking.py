"""Single-flight OS file lock — Camoufox profiles cannot be shared.

One browser-driving process at a time: if the lock is held (e.g. an
active POST /api/listings creation), the holder proceeds and the
latecomer skips its tick (exit 0, not a failure). Cross-platform:
msvcrt on Windows, fcntl on POSIX. Stale locks die with the process
(locks are fd-bound, never files left behind).
"""
from __future__ import annotations

import os
from pathlib import Path


class SingleFlight:
    def __init__(self, name: str = "camofox_marketplace") -> None:
        import tempfile
        from typing import Any

        self.path = Path(tempfile.gettempdir()) / f"{name}.lock"
        self._fh: Any = None

    def acquire(self) -> bool:
        self._fh = open(self.path, "w")
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl  # type: ignore[import-not-found]

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
            return True
        except (OSError, IOError):
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
            return False

    def release(self) -> None:
        try:
            if self._fh is not None:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl  # type: ignore[import-not-found]

                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
                self._fh.close()
        except Exception:
            pass
        finally:
            self._fh = None

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()
