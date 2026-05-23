# file: core/face_recognizer.py

from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from deepface import DeepFace

from core.config import (
    EMBEDDING_CACHE_SIZE,
    FACE_DETECTION_CONFIDENCE,
    MIN_FACE_SIZE,
    TEMP_DIR,
)


class FaceRecognizer:
    def __init__(self):
        print("FaceRecognizer initializing...")
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detector = self.mp_face_detection.FaceDetection(
            model_selection=0,
            min_detection_confidence=FACE_DETECTION_CONFIDENCE,
        )
        self.embedding_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.cache_size = EMBEDDING_CACHE_SIZE

    def detect_faces(self, image: np.ndarray) -> tuple[list[np.ndarray], list[tuple[int, int, int, int]]]:
        if image is None or image.size == 0:
            return [], []

        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.face_detector.process(rgb_image)
        cropped_faces: list[np.ndarray] = []
        bounding_boxes: list[tuple[int, int, int, int]] = []

        if not results.detections:
            return cropped_faces, bounding_boxes

        frame_h, frame_w = image.shape[:2]
        for detection in results.detections:
            rel_box = detection.location_data.relative_bounding_box
            x = max(0, int(rel_box.xmin * frame_w))
            y = max(0, int(rel_box.ymin * frame_h))
            w = int(rel_box.width * frame_w)
            h = int(rel_box.height * frame_h)

            # Add a small margin so ArcFace receives the full face region.
            margin_x = int(w * 0.15)
            margin_y = int(h * 0.20)
            x1 = max(0, x - margin_x)
            y1 = max(0, y - margin_y)
            x2 = min(frame_w, x + w + margin_x)
            y2 = min(frame_h, y + h + margin_y)

            crop_w = x2 - x1
            crop_h = y2 - y1
            if crop_w < MIN_FACE_SIZE or crop_h < MIN_FACE_SIZE:
                continue

            face_img = image[y1:y2, x1:x2]
            if face_img.size > 0:
                cropped_faces.append(face_img.copy())
                bounding_boxes.append((x1, y1, crop_w, crop_h))

        return cropped_faces, bounding_boxes

    def get_embedding(self, face_image: np.ndarray) -> np.ndarray | None:
        if face_image is None or face_image.size == 0:
            return None

        image_hash = self._hash_image(face_image)
        cached = self.embedding_cache.get(image_hash)
        if cached is not None:
            self.embedding_cache.move_to_end(image_hash)
            return cached

        embedding = self._represent_direct(face_image)
        if embedding is None:
            # Keep a fallback for DeepFace/OpenCV edge cases on some Windows builds.
            embedding = self._represent_via_temp_file(face_image, image_hash)

        if embedding is not None:
            self.embedding_cache[image_hash] = embedding
            if len(self.embedding_cache) > self.cache_size:
                self.embedding_cache.popitem(last=False)

        return embedding

    @staticmethod
    def _hash_image(face_image: np.ndarray) -> str:
        hasher = hashlib.sha256()
        hasher.update(str(face_image.shape).encode("utf-8"))
        hasher.update(face_image.tobytes())
        return hasher.hexdigest()

    def _represent_direct(self, face_image: np.ndarray) -> np.ndarray | None:
        try:
            result = DeepFace.represent(
                img_path=face_image,
                model_name="ArcFace",
                enforce_detection=False,
                detector_backend="skip",
            )
            return self._extract_normalized_embedding(result)
        except Exception as exc:
            print(f"DeepFace direct embedding failed: {exc}")
            return None

    def _represent_via_temp_file(self, face_image: np.ndarray, image_hash: str) -> np.ndarray | None:
        temp_file_path = Path(TEMP_DIR) / f"temp_face_{image_hash}.jpg"
        try:
            cv2.imwrite(str(temp_file_path), face_image)
            result = DeepFace.represent(
                img_path=str(temp_file_path),
                model_name="ArcFace",
                enforce_detection=False,
                detector_backend="skip",
            )
            return self._extract_normalized_embedding(result)
        except Exception as exc:
            print(f"DeepFace temp-file embedding failed: {exc}")
            return None
        finally:
            try:
                temp_file_path.unlink(missing_ok=True)
            except Exception:
                pass

    @staticmethod
    def _extract_normalized_embedding(result) -> np.ndarray | None:
        if not result or "embedding" not in result[0]:
            return None
        vector = np.asarray(result[0]["embedding"], dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return None
        return (vector / norm).astype(np.float32)
