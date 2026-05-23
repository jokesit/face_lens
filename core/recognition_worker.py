"""Background recognition worker for DeepFace/FAISS jobs."""

from __future__ import annotations

import faiss
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot

from core.config import RECOGNITION_AMBIGUITY_MARGIN, RECOGNITION_THRESHOLD, RECOGNITION_TOP_K
from core.confidence_profiles import DEFAULT_CONFIDENCE_PROFILE_KEY, get_confidence_profile
from core.database import Database
from core.face_recognizer import FaceRecognizer
from core.recognition_types import FaceObservation, RecognitionResult


class RecognitionWorker(QObject):
    """Runs expensive recognition jobs inside a dedicated QThread.

    Important Qt rule: this is a QObject moved to a QThread. Slots on this object
    run in the worker thread when called through queued signal connections.
    """

    recognition_results = Signal(list)
    snapshot_result = Signal(object)
    verification_result = Signal(str, float)
    worker_ready = Signal(str)
    worker_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.recognizer: FaceRecognizer | None = None
        self.faiss_index = None
        self.index_to_name_map: dict[int, str] = {}
        self.recognition_threshold = RECOGNITION_THRESHOLD
        self.ambiguity_margin = RECOGNITION_AMBIGUITY_MARGIN
        self.confidence_profile_key = DEFAULT_CONFIDENCE_PROFILE_KEY
        self.top_k = max(1, RECOGNITION_TOP_K)

    @Slot()
    def initialize(self) -> None:
        """Load and warm up DeepFace in the recognition worker thread."""
        try:
            print("RecognitionWorker initializing...")
            self.recognizer = FaceRecognizer()
            print("Warming up model...")
            self.recognizer.get_embedding(np.zeros((160, 160, 3), dtype=np.uint8))
            print("Model ready.")
            self.worker_ready.emit("Searching...")
        except Exception as exc:
            message = f"Recognition initialization failed: {exc}"
            print(message)
            self.worker_error.emit(message)

    @Slot(list)
    def build_faiss_index(self, db_data: list[tuple[int, str, np.ndarray]]) -> None:
        try:
            if not db_data:
                self.faiss_index = None
                self.index_to_name_map = {}
                print("FAISS index cleared: no customers in database.")
                return

            embeddings = np.asarray([item[2] for item in db_data], dtype=np.float32)
            if embeddings.ndim != 2 or embeddings.shape[0] == 0:
                self.faiss_index = None
                self.index_to_name_map = {}
                return

            index = faiss.IndexFlatL2(embeddings.shape[1])
            index.add(embeddings)
            self.faiss_index = index
            self.index_to_name_map = {i: item[1] for i, item in enumerate(db_data)}
            print(f"FAISS index rebuilt: {len(self.index_to_name_map)} customer vectors.")
        except Exception as exc:
            message = f"FAISS index build failed: {exc}"
            print(message)
            self.worker_error.emit(message)

    @Slot(list)
    def process_recognition_job(self, observations: list[FaceObservation]) -> None:
        """Recognize one or more faces from a camera frame."""
        results: list[tuple[str, tuple[int, int, int, int], float | None, float | None, str]] = []
        try:
            if not observations:
                self.recognition_results.emit([])
                return

            if self.faiss_index is None or self.recognizer is None:
                for obs in observations:
                    results.append(RecognitionResult("Unknown", obs.box, None, obs.quality_score, "index-not-ready").as_tuple())
                self.recognition_results.emit(results)
                return

            for obs in observations:
                embedding = self.recognizer.get_embedding(obs.face_image)
                if embedding is None:
                    results.append(RecognitionResult("Unknown", obs.box, None, obs.quality_score, "embedding-failed").as_tuple())
                    continue

                name, distance, note = self._search_name(embedding)
                results.append(RecognitionResult(name, obs.box, distance, obs.quality_score, note).as_tuple())

            self.recognition_results.emit(results)
        except Exception as exc:
            print(f"Recognition job failed: {exc}")
            fallback = [RecognitionResult("Unknown", obs.box, None, obs.quality_score, "job-failed").as_tuple() for obs in observations]
            self.recognition_results.emit(fallback)

    def _search_name(self, embedding: np.ndarray) -> tuple[str, float | None, str]:
        if self.faiss_index is None:
            return "Unknown", None, "index-not-ready"

        query = np.asarray([embedding], dtype=np.float32)
        k = min(self.top_k, max(1, int(self.faiss_index.ntotal)))
        distances, indices = self.faiss_index.search(query, k)
        best_distance = float(distances[0][0])
        best_index = int(indices[0][0])

        if best_index < 0 or best_distance >= self.recognition_threshold:
            return "Unknown", best_distance, "below-threshold"

        best_name = self.index_to_name_map.get(best_index, "Unknown")
        if k >= 2:
            second_distance = float(distances[0][1])
            second_index = int(indices[0][1])
            second_name = self.index_to_name_map.get(second_index, "Unknown")
            # If two different customers are almost equally close, do not greet by name.
            if second_index >= 0 and second_name != best_name:
                margin = second_distance - best_distance
                if margin < self.ambiguity_margin:
                    return "Unknown", best_distance, "ambiguous-match"

        return best_name, best_distance, "ok"


    @Slot(str)
    def set_confidence_profile(self, profile_key: str) -> None:
        """Apply recognition confidence settings at runtime.

        Lower threshold means stricter matching. Larger ambiguity margin means the
        app is more careful when two customers look similarly close.
        """
        profile = get_confidence_profile(profile_key)
        self.confidence_profile_key = profile.key
        self.recognition_threshold = float(profile.recognition_threshold)
        self.ambiguity_margin = float(profile.ambiguity_margin)
        print(
            f"Confidence profile applied: {profile.thai_name} "
            f"(threshold={self.recognition_threshold:.2f}, margin={self.ambiguity_margin:.2f})"
        )

    @Slot(object)
    def process_snapshot_job(self, face_image) -> None:
        try:
            if self.recognizer is None:
                self.snapshot_result.emit(None)
                return
            embedding = self.recognizer.get_embedding(face_image)
            self.snapshot_result.emit(embedding)
        except Exception as exc:
            print(f"Snapshot embedding failed: {exc}")
            self.snapshot_result.emit(None)

    @Slot(list, str)
    def process_verification_job(self, captured_embeddings: list[np.ndarray], name: str) -> None:
        try:
            valid_embeddings = [np.asarray(e, dtype=np.float32) for e in captured_embeddings if e is not None]
            if not valid_embeddings:
                self.verification_result.emit(name, -1.0)
                return

            new_avg = np.mean(valid_embeddings, axis=0).astype(np.float32)
            norm = np.linalg.norm(new_avg)
            if norm == 0:
                self.verification_result.emit(name, -1.0)
                return
            new_avg = new_avg / norm

            db = Database()
            try:
                existing = db.get_customer_by_name(name)
            finally:
                db.close()

            distance = -1.0
            if existing and isinstance(existing.get("avg_embedding"), np.ndarray):
                distance = float(np.linalg.norm(new_avg - existing["avg_embedding"]))
            self.verification_result.emit(name, distance)
        except Exception as exc:
            print(f"Verification job failed: {exc}")
            self.verification_result.emit(name, -1.0)
