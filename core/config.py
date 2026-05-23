# file: core/config.py
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


APP_PATH = get_app_path()
DATA_DIR = APP_PATH / "data"
TEMP_DIR = APP_PATH / "temp_files"
ASSETS_DIR = APP_PATH / "assets"
DB_PATH = DATA_DIR / "facelens.db"
LOG_DIR = APP_PATH / "logs"

for folder in (DATA_DIR, TEMP_DIR, LOG_DIR):
    folder.mkdir(parents=True, exist_ok=True)

# Camera/display
CAMERA_INDEX = int(os.getenv("FACELENS_CAMERA_INDEX", "0"))
CAMERA_WIDTH = int(os.getenv("FACELENS_CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.getenv("FACELENS_CAMERA_HEIGHT", "480"))
DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 480
TARGET_FPS = float(os.getenv("FACELENS_TARGET_FPS", "15"))

# Face detection / recognition
FACE_DETECTION_CONFIDENCE = float(os.getenv("FACELENS_FACE_CONFIDENCE", "0.70"))
MIN_FACE_SIZE = int(os.getenv("FACELENS_MIN_FACE_SIZE", "80"))
RECOGNITION_INTERVAL_FRAMES = int(os.getenv("FACELENS_RECOGNITION_INTERVAL", "12"))
RECOGNITION_THRESHOLD = float(os.getenv("FACELENS_RECOGNITION_THRESHOLD", "0.75"))
VERIFICATION_THRESHOLD = float(os.getenv("FACELENS_VERIFICATION_THRESHOLD", "0.75"))

# Enrollment
MAX_SNAPSHOTS = int(os.getenv("FACELENS_MAX_SNAPSHOTS", "5"))
CAPTURE_COOLDOWN_FRAMES = int(os.getenv("FACELENS_CAPTURE_COOLDOWN", "30"))
MIN_FACE_MOVEMENT = int(os.getenv("FACELENS_MIN_FACE_MOVEMENT", "10"))

# Embedding cache
EMBEDDING_CACHE_SIZE = int(os.getenv("FACELENS_EMBEDDING_CACHE_SIZE", "300"))
