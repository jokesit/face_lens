"""PyInstaller runtime hook for FaceLens.

This hook runs before ``main.py`` in the frozen application. It keeps runtime
folders outside PyInstaller's temporary extraction folder and writes a startup
log even when the release EXE has no console window.

Portable ZIP mode:
    runtime folders live beside FaceLens.exe.

Installed mode:
    ``installed_mode.txt`` exists beside FaceLens.exe, so writable runtime data
    lives in ``C:\\ProgramData\\FaceLens``. This avoids Windows permission
    issues when the app is installed under ``C:\\Program Files\\FaceLens``.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def _runtime_dir(app_dir: Path) -> Path:
    override = os.environ.get("FACELENS_RUNTIME_DIR")
    if override:
        return Path(override).expanduser().resolve()

    if (app_dir / "installed_mode.txt").exists():
        program_data = os.environ.get("PROGRAMDATA") or str(Path.home() / "AppData" / "Local")
        return Path(program_data) / "FaceLens"

    return app_dir


APP_DIR = _app_dir()
RUNTIME_DIR = _runtime_dir(APP_DIR)
LOG_DIR = RUNTIME_DIR / "logs"
DATA_DIR = RUNTIME_DIR / "data"
BACKUP_DIR = RUNTIME_DIR / "backups"
TEMP_DIR = RUNTIME_DIR / "temp_files"
DEEPFACE_HOME = RUNTIME_DIR / ".deepface"
MPLCONFIG_DIR = TEMP_DIR / "matplotlib"

for folder in (LOG_DIR, DATA_DIR, BACKUP_DIR, TEMP_DIR, MPLCONFIG_DIR, DEEPFACE_HOME / "weights"):
    folder.mkdir(parents=True, exist_ok=True)


# Add common PyInstaller/native-library folders to DLL search paths. This is
# especially important for faiss-cpu on Windows, where _swigfaiss.pyd depends
# on DLLs that may live in faiss_cpu.libs or inside PyInstaller's _internal dir.
def _add_dll_search_dir(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        return
    try:
        os.add_dll_directory(str(path))
    except Exception:
        pass
    current_path = os.environ.get("PATH", "")
    path_text = str(path)
    if path_text not in current_path.split(os.pathsep):
        os.environ["PATH"] = path_text + os.pathsep + current_path


_internal_dir = APP_DIR / "_internal"
for candidate in (
    APP_DIR,
    _internal_dir,
    APP_DIR / "faiss",
    _internal_dir / "faiss",
    APP_DIR / "faiss_cpu.libs",
    _internal_dir / "faiss_cpu.libs",
    APP_DIR / "faiss.libs",
    _internal_dir / "faiss.libs",
):
    _add_dll_search_dir(candidate)

# Keep noisy ML startup messages lower for release builds. Users can override
# these from PowerShell if they need deeper debugging.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("DEEPFACE_HOME", str(DEEPFACE_HOME))
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("FACELENS_FROZEN", "1")
os.environ.setdefault("FACELENS_APP_DIR", str(APP_DIR))
os.environ.setdefault("FACELENS_RUNTIME_DIR", str(RUNTIME_DIR))

# Some native packages use cwd for relative files. In frozen mode, prefer the
# executable folder so bundled assets and native files are resolved reliably.
try:
    os.chdir(APP_DIR)
except OSError:
    pass

# Release EXE has console=False, so redirect stdout/stderr to a persistent log.
# This makes startup failures visible to support instead of looking like the app
# did nothing.
log_path = LOG_DIR / "facelens_runtime.log"
try:
    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    log_file.write("\n" + "=" * 80 + "\n")
    log_file.write(time.strftime("%Y-%m-%d %H:%M:%S") + " FaceLens frozen startup\n")
    log_file.write(f"executable={sys.executable}\n")
    log_file.write(f"app_dir={APP_DIR}\n")
    log_file.write(f"runtime_dir={RUNTIME_DIR}\n")
    log_file.write(f"deepface_home={DEEPFACE_HOME}\n")
    sys.stdout = log_file
    sys.stderr = log_file
except Exception:
    # Do not block app startup just because logging cannot be opened.
    pass
