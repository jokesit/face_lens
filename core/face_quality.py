"""Face quality scoring utilities.

FaceLens should prefer being quiet over greeting the wrong person. This module
filters blurry, tiny, too-dark, or over-exposed face crops before they reach the
expensive embedding model or the enrollment database.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from core.config import (
    FACE_QUALITY_MAX_BRIGHTNESS,
    FACE_QUALITY_MIN_BRIGHTNESS,
    FACE_QUALITY_MIN_SCORE_CAPTURE,
    FACE_QUALITY_MIN_SCORE_RECOGNITION,
    FACE_QUALITY_MIN_SHARPNESS,
    FACE_QUALITY_MIN_SIZE,
)


@dataclass(frozen=True)
class FaceQualityResult:
    score: float
    is_good_for_recognition: bool
    is_good_for_capture: bool
    reason: str
    width: int
    height: int
    brightness: float
    sharpness: float


def evaluate_face_quality(face_image: np.ndarray) -> FaceQualityResult:
    """Return a lightweight quality score for one cropped face image.

    Score is 0-100. It is deliberately simple and CPU-friendly:
    - size score rewards larger crops
    - sharpness uses Laplacian variance
    - brightness penalizes under/over-exposure
    """
    if face_image is None or face_image.size == 0:
        return FaceQualityResult(0.0, False, False, "empty", 0, 0, 0.0, 0.0)

    height, width = face_image.shape[:2]
    if width <= 0 or height <= 0:
        return FaceQualityResult(0.0, False, False, "invalid-size", width, height, 0.0, 0.0)

    gray = cv2.cvtColor(face_image, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    min_side = min(width, height)
    size_score = min(100.0, (min_side / max(1, FACE_QUALITY_MIN_SIZE)) * 70.0)
    sharpness_score = min(100.0, (sharpness / max(1.0, FACE_QUALITY_MIN_SHARPNESS)) * 60.0)

    if FACE_QUALITY_MIN_BRIGHTNESS <= brightness <= FACE_QUALITY_MAX_BRIGHTNESS:
        brightness_score = 100.0
    else:
        # Soft penalty instead of a hard fail, so recognition still works in a
        # slightly imperfect shop environment.
        if brightness < FACE_QUALITY_MIN_BRIGHTNESS:
            distance = FACE_QUALITY_MIN_BRIGHTNESS - brightness
        else:
            distance = brightness - FACE_QUALITY_MAX_BRIGHTNESS
        brightness_score = max(0.0, 100.0 - distance * 2.0)

    score = round((size_score * 0.35) + (sharpness_score * 0.40) + (brightness_score * 0.25), 2)

    reasons: list[str] = []
    if min_side < FACE_QUALITY_MIN_SIZE:
        reasons.append("face-too-small")
    if sharpness < FACE_QUALITY_MIN_SHARPNESS:
        reasons.append("blurry")
    if brightness < FACE_QUALITY_MIN_BRIGHTNESS:
        reasons.append("too-dark")
    if brightness > FACE_QUALITY_MAX_BRIGHTNESS:
        reasons.append("too-bright")

    reason = ", ".join(reasons) if reasons else "ok"
    return FaceQualityResult(
        score=score,
        is_good_for_recognition=score >= FACE_QUALITY_MIN_SCORE_RECOGNITION,
        is_good_for_capture=score >= FACE_QUALITY_MIN_SCORE_CAPTURE and not reasons,
        reason=reason,
        width=width,
        height=height,
        brightness=brightness,
        sharpness=sharpness,
    )
