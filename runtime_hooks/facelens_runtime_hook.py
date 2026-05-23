"""PyInstaller runtime hook for FaceLens.

This hook runs before ``main.py`` in the frozen application. It keeps runtime
folders outside PyInstaller's temporary extraction folder and writes a startup
log even when the release EXE has no console window.
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


APP_DIR = _app_dir()
LOG_DIR = APP_DIR / "logs"
DATA_DIR = APP_DIR / "data"
BACKUP_DIR = APP_DIR / "backups"
TEMP_DIR = APP_DIR / "temp_files"
DEEPFACE_HOME = APP_DIR / ".deepface"

for folder in (LOG_DIR, DATA_DIR, BACKUP_DIR, TEMP_DIR, DEEPFACE_HOME / "weights"):
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
os.environ.setdefault("FACELENS_FROZEN", "1")

# Some native packages use cwd for relative files. In frozen mode, prefer the
# executable folder so data/backups/logs are created beside FaceLens.exe.
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
    log_file.write(f"deepface_home={DEEPFACE_HOME}\n")
    sys.stdout = log_file
    sys.stderr = log_file
except Exception:
    # Do not block app startup just because logging cannot be opened.
    pass
