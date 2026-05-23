"""Warm up/download FaceLens AI model files before PyInstaller packaging.

Run this before building the EXE so DeepFace weights are available on the build
machine and can be bundled into the onedir release.
"""

from __future__ import annotations

import numpy as np

from core.frozen_runtime import setup_runtime_environment
from core.face_recognizer import FaceRecognizer


def main() -> int:
    setup_runtime_environment()
    print("Initializing FaceRecognizer...")
    recognizer = FaceRecognizer()
    # A simple bright face-like crop is enough to force DeepFace model creation.
    # DeepFace may fail to extract a real face from it, but the model download and
    # TensorFlow initialization path is still exercised by get_embedding fallback.
    sample = np.full((160, 160, 3), 180, dtype=np.uint8)
    try:
        recognizer.get_embedding(sample)
    except Exception as exc:
        # Model warmup can reject the synthetic crop. That is acceptable as long
        # as imports/model initialization completed far enough to prepare files.
        print(f"Warmup completed with a non-fatal synthetic-image warning: {exc}")
    print("Model warmup step finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
