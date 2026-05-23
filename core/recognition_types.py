"""Small immutable data types shared between worker and video layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

FaceBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class FaceObservation:
    face_image: np.ndarray
    box: FaceBox
    quality_score: float
    quality_reason: str


@dataclass(frozen=True)
class RecognitionResult:
    name: str
    box: FaceBox
    distance: float | None = None
    quality_score: float | None = None
    note: str = ""

    def as_tuple(self) -> tuple[str, FaceBox, float | None, float | None, str]:
        return self.name, self.box, self.distance, self.quality_score, self.note
