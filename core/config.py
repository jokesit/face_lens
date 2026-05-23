"""Central configuration for FaceLens.

Keep performance knobs and filesystem paths in one place so the app can be
adjusted for low-spec shop computers without hunting through UI/thread code.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_app_path() -> Path:
    """Return the folder that contains the running app or source project."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_bundle_path() -> Path:
    """Return the PyInstaller internal resource folder when frozen.

    In PyInstaller onedir builds, application data files such as assets/logo.png
    usually live under sys._MEIPASS, which points to dist/FaceLens/_internal.
    Runtime writable data still belongs beside FaceLens.exe, returned by
    get_app_path().
    """
    bundle_path = getattr(sys, "_MEIPASS", None)
    if bundle_path:
        return Path(bundle_path).resolve()
    return get_app_path()


def resolve_resource_path(relative_path: str | Path) -> Path:
    """Find a read-only bundled resource in source or frozen builds."""
    relative = Path(relative_path)
    candidates = [
        get_app_path() / relative,
        get_bundle_path() / relative,
        get_app_path() / "_internal" / relative,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Return the source-style path as a stable fallback. Callers can check exists().
    return get_app_path() / relative


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


APP_PATH = get_app_path()
DATA_DIR = APP_PATH / "data"
TEMP_DIR = APP_PATH / "temp_files"
ASSETS_DIR = resolve_resource_path("assets")
LOGO_PNG_PATH = resolve_resource_path("assets/logo.png")
LOGO_ICO_PATH = resolve_resource_path("assets/logo.ico")
DB_PATH = DATA_DIR / "facelens.db"
LOG_DIR = APP_PATH / "logs"
BACKUP_DIR = APP_PATH / "backups"

for folder in (DATA_DIR, TEMP_DIR, LOG_DIR, BACKUP_DIR):
    folder.mkdir(parents=True, exist_ok=True)

# Camera/display
CAMERA_INDEX = int(os.getenv("FACELENS_CAMERA_INDEX", "0"))
CAMERA_WIDTH = int(os.getenv("FACELENS_CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.getenv("FACELENS_CAMERA_HEIGHT", "480"))
DISPLAY_WIDTH = int(os.getenv("FACELENS_DISPLAY_WIDTH", "640"))
DISPLAY_HEIGHT = int(os.getenv("FACELENS_DISPLAY_HEIGHT", "440"))
APP_WINDOW_WIDTH = int(os.getenv("FACELENS_WINDOW_WIDTH", "860"))
APP_WINDOW_HEIGHT = int(os.getenv("FACELENS_WINDOW_HEIGHT", "800"))
TARGET_FPS = float(os.getenv("FACELENS_TARGET_FPS", "15"))
FACE_DETECTION_INTERVAL_FRAMES = max(1, int(os.getenv("FACELENS_FACE_DETECTION_INTERVAL", "1")))
# Batch 7 adds runtime performance profiles. Environment values above are kept
# as safe defaults/fallbacks, while the UI can change the active profile live.
SHOW_DEBUG_DISTANCE = env_bool("FACELENS_SHOW_DEBUG_DISTANCE", False)

# Face detection / recognition
FACE_DETECTION_CONFIDENCE = float(os.getenv("FACELENS_FACE_CONFIDENCE", "0.70"))
MIN_FACE_SIZE = int(os.getenv("FACELENS_MIN_FACE_SIZE", "80"))
RECOGNITION_INTERVAL_FRAMES = int(os.getenv("FACELENS_RECOGNITION_INTERVAL", "12"))
RECOGNITION_MIN_SECONDS_BETWEEN_JOBS = float(os.getenv("FACELENS_RECOGNITION_MIN_SECONDS", "1.2"))
RECOGNITION_RESULT_TTL_SECONDS = float(os.getenv("FACELENS_RECOGNITION_RESULT_TTL", "3.0"))
RECOGNITION_BOX_REUSE_IOU = float(os.getenv("FACELENS_RECOGNITION_REUSE_IOU", "0.35"))
RECOGNITION_THRESHOLD = float(os.getenv("FACELENS_RECOGNITION_THRESHOLD", "0.75"))
VERIFICATION_THRESHOLD = float(os.getenv("FACELENS_VERIFICATION_THRESHOLD", "0.75"))
RECOGNITION_TOP_K = int(os.getenv("FACELENS_RECOGNITION_TOP_K", "2"))
RECOGNITION_AMBIGUITY_MARGIN = float(os.getenv("FACELENS_RECOGNITION_AMBIGUITY_MARGIN", "0.08"))
MAX_RECOGNITION_FACES = int(os.getenv("FACELENS_MAX_RECOGNITION_FACES", "3"))

# Face quality. These values are intentionally conservative for shop PCs and
# normal webcams. They can be tuned through environment variables later.
FACE_QUALITY_MIN_SIZE = int(os.getenv("FACELENS_QUALITY_MIN_SIZE", "80"))
FACE_QUALITY_MIN_SHARPNESS = float(os.getenv("FACELENS_QUALITY_MIN_SHARPNESS", "25"))
FACE_QUALITY_MIN_BRIGHTNESS = float(os.getenv("FACELENS_QUALITY_MIN_BRIGHTNESS", "45"))
FACE_QUALITY_MAX_BRIGHTNESS = float(os.getenv("FACELENS_QUALITY_MAX_BRIGHTNESS", "220"))
FACE_QUALITY_MIN_SCORE_RECOGNITION = float(os.getenv("FACELENS_QUALITY_MIN_SCORE_RECOGNITION", "45"))
FACE_QUALITY_MIN_SCORE_CAPTURE = float(os.getenv("FACELENS_QUALITY_MIN_SCORE_CAPTURE", "60"))

# Enrollment
MAX_SNAPSHOTS = int(os.getenv("FACELENS_MAX_SNAPSHOTS", "5"))
CAPTURE_COOLDOWN_FRAMES = int(os.getenv("FACELENS_CAPTURE_COOLDOWN", "30"))
MIN_FACE_MOVEMENT = int(os.getenv("FACELENS_MIN_FACE_MOVEMENT", "10"))

# Embedding cache
EMBEDDING_CACHE_SIZE = int(os.getenv("FACELENS_EMBEDDING_CACHE_SIZE", "300"))

# Recognition event logging
RECOGNITION_EVENT_MIN_SECONDS = float(os.getenv("FACELENS_EVENT_MIN_SECONDS", "15"))

# Standalone pharmacy target scale.
# 1,000-5,000 customers is suitable for local SQLite + in-memory FAISS.
STANDALONE_TARGET_CUSTOMERS = int(os.getenv("FACELENS_TARGET_CUSTOMERS", "5000"))
STANDALONE_WARN_EMBEDDINGS = int(os.getenv("FACELENS_WARN_EMBEDDINGS", "30000"))
RECOMMENDED_MAX_EMBEDDINGS_PER_CUSTOMER = int(os.getenv("FACELENS_MAX_EMBEDDINGS_PER_CUSTOMER", "8"))

# Keep event logs useful without allowing the SQLite file to grow forever.
RECOGNITION_EVENTS_RETENTION_DAYS = int(os.getenv("FACELENS_EVENT_RETENTION_DAYS", "90"))

# Enrollment duplicate prevention. These thresholds are intentionally stricter
# than live recognition because saving the same person under two names creates
# long-term confusion when a standalone pharmacy database reaches thousands of customers.
ENROLLMENT_DUPLICATE_WARNING_DISTANCE = float(os.getenv("FACELENS_ENROLLMENT_DUPLICATE_WARNING_DISTANCE", "0.68"))
ENROLLMENT_DUPLICATE_STRICT_DISTANCE = float(os.getenv("FACELENS_ENROLLMENT_DUPLICATE_STRICT_DISTANCE", "0.55"))
ENROLLMENT_NEAREST_MATCH_LIMIT = int(os.getenv("FACELENS_ENROLLMENT_NEAREST_MATCH_LIMIT", "5"))
