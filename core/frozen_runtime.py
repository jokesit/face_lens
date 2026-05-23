"""Runtime support for source and frozen FaceLens builds."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from core.config import APP_PATH, LOG_DIR


_RUNTIME_READY = False


def setup_runtime_environment() -> None:
    """Prepare a stable runtime environment before heavy AI imports.

    This is intentionally safe to call in source mode and frozen mode. The
    PyInstaller runtime hook does most of the work for the EXE, but calling this
    in source mode keeps behavior consistent during development.
    """
    global _RUNTIME_READY
    if _RUNTIME_READY:
        return
    _RUNTIME_READY = True

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    os.environ.setdefault("DEEPFACE_HOME", str(APP_PATH / ".deepface"))

    for folder in (LOG_DIR, APP_PATH / ".deepface" / "weights"):
        folder.mkdir(parents=True, exist_ok=True)

    if getattr(sys, "frozen", False):
        try:
            os.chdir(APP_PATH)
        except OSError:
            pass
        _write_startup_marker()


def _write_startup_marker() -> None:
    try:
        log_path = LOG_DIR / "facelens_startup.log"
        with open(log_path, "a", encoding="utf-8") as file:
            file.write("\n" + "=" * 80 + "\n")
            file.write(time.strftime("%Y-%m-%d %H:%M:%S") + " FaceLens startup marker\n")
            file.write(f"python={sys.version}\n")
            file.write(f"frozen={getattr(sys, 'frozen', False)}\n")
            file.write(f"executable={sys.executable}\n")
            file.write(f"app_path={APP_PATH}\n")
            file.write(f"deepface_home={os.environ.get('DEEPFACE_HOME')}\n")
    except Exception:
        pass
