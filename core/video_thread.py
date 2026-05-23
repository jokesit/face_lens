"""Camera capture, face detection, display rendering, and enrollment capture."""

from __future__ import annotations

import platform
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtGui import QImage

from core.config import (
    ASSETS_DIR,
    CAMERA_HEIGHT,
    CAMERA_INDEX,
    CAMERA_WIDTH,
    CAPTURE_COOLDOWN_FRAMES,
    MAX_RECOGNITION_FACES,
    MAX_SNAPSHOTS,
    MIN_FACE_MOVEMENT,
    RECOGNITION_INTERVAL_FRAMES,
    TARGET_FPS,
    SHOW_DEBUG_DISTANCE,
)
from core.face_quality import evaluate_face_quality
from core.face_recognizer import FaceRecognizer
from core.recognition_types import FaceBox, FaceObservation


class VideoThread(QThread):
    """Camera capture + face detection thread.

    This thread emits QImage, not QPixmap. QPixmap must be created in the GUI thread.
    """

    change_image_signal = Signal(QImage)
    recognition_job_signal = Signal(list)
    raw_frame_signal = Signal(np.ndarray)
    capture_progress_signal = Signal(int, int)
    snapshot_job_signal = Signal(object)
    update_display_name_signal = Signal(str)
    capture_hint_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.detector = FaceRecognizer()
        self.is_running = True
        self.frame_counter = 0
        self.recognition_job_pending = False
        self.last_known_results: dict[FaceBox, tuple[str, float | None, str]] = {}
        self.is_capture_mode = False
        self.capture_count = 0
        self.last_face_box: FaceBox | None = None
        self.capture_cooldown = 0
        self.show_debug_distance = SHOW_DEBUG_DISTANCE

        try:
            self.font = ImageFont.truetype(str(ASSETS_DIR / "tahoma.ttf"), 24)
        except IOError:
            print("Font file not found in assets/tahoma.ttf. Using default font.")
            self.font = ImageFont.load_default()

    @Slot(list)
    def update_recognition_results(self, results: list[tuple[str, FaceBox, float | None, float | None, str]]) -> None:
        self.recognition_job_pending = False
        self.last_known_results = {}

        best_name = "Unknown"
        best_distance: float | None = None
        for name, box, distance, _quality_score, note in results:
            self.last_known_results[box] = (name, distance, note)
            if name != "Unknown" and (best_distance is None or (distance is not None and distance < best_distance)):
                best_name = name
                best_distance = distance

        if results:
            self.update_display_name_signal.emit(best_name)

    @Slot(bool)
    def set_show_debug_distance(self, enabled: bool) -> None:
        self.show_debug_distance = bool(enabled)

    @Slot(bool)
    def set_capture_mode(self, is_active: bool) -> None:
        self.is_capture_mode = is_active
        self.capture_count = 0 if is_active else self.capture_count
        self.last_face_box = None
        self.capture_cooldown = 0
        if is_active:
            self.recognition_job_pending = False
            self.last_known_results = {}

    def run(self) -> None:
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else 0
        cap = cv2.VideoCapture(CAMERA_INDEX, backend)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            self.update_display_name_signal.emit("Camera Error")
            return

        min_frame_seconds = 1.0 / TARGET_FPS if TARGET_FPS > 0 else 0.0
        try:
            while self.is_running:
                frame_started_at = time.perf_counter()
                ret, cv_img = cap.read()
                if not ret:
                    self.msleep(30)
                    continue

                self.raw_frame_signal.emit(cv_img)
                frame_to_display = cv_img.copy()
                faces, boxes = self.detector.detect_faces(frame_to_display)
                observations = self._build_observations(faces, boxes)

                if self.is_capture_mode:
                    self._handle_capture_mode(observations)
                else:
                    self._handle_recognition_mode(observations)

                self._emit_display_frame(frame_to_display)

                self.frame_counter += 1
                elapsed = time.perf_counter() - frame_started_at
                sleep_ms = int(max(0.0, min_frame_seconds - elapsed) * 1000)
                if sleep_ms > 0:
                    self.msleep(sleep_ms)
        finally:
            cap.release()

    def _build_observations(self, faces, boxes) -> list[FaceObservation]:
        observations: list[FaceObservation] = []
        for face_img, face_box in zip(faces, boxes):
            quality = evaluate_face_quality(face_img)
            if not quality.is_good_for_recognition:
                continue
            observations.append(
                FaceObservation(
                    face_image=face_img,
                    box=face_box,
                    quality_score=quality.score,
                    quality_reason=quality.reason,
                )
            )

        observations.sort(key=lambda obs: (obs.quality_score, obs.box[2] * obs.box[3]), reverse=True)
        return observations

    def _handle_capture_mode(self, observations: list[FaceObservation]) -> None:
        if self.capture_cooldown > 0:
            self.capture_cooldown -= 1

        if self.capture_count >= MAX_SNAPSHOTS:
            return

        if len(observations) != 1:
            if len(observations) > 1:
                self.capture_hint_signal.emit("Only one face at a time, please.")
            return

        if self.capture_cooldown != 0:
            return

        observation = observations[0]
        quality = evaluate_face_quality(observation.face_image)
        if not quality.is_good_for_capture:
            self.capture_hint_signal.emit(f"Improve face image: {quality.reason}")
            return

        has_moved = True
        if self.last_face_box is not None:
            dx = abs(observation.box[0] - self.last_face_box[0])
            dy = abs(observation.box[1] - self.last_face_box[1])
            has_moved = dx >= MIN_FACE_MOVEMENT or dy >= MIN_FACE_MOVEMENT

        if not has_moved:
            self.capture_hint_signal.emit("Move your head slightly.")
            return

        self.snapshot_job_signal.emit(observation.face_image)
        self.capture_count += 1
        self.last_face_box = observation.box
        self.capture_cooldown = CAPTURE_COOLDOWN_FRAMES
        self.capture_progress_signal.emit(self.capture_count, MAX_SNAPSHOTS)

    def _handle_recognition_mode(self, observations: list[FaceObservation]) -> None:
        if self.frame_counter % RECOGNITION_INTERVAL_FRAMES != 0:
            return

        if observations and not self.recognition_job_pending:
            self.recognition_job_pending = True
            self.recognition_job_signal.emit(observations[:MAX_RECOGNITION_FACES])
        elif not observations:
            self.recognition_job_pending = False
            self.last_known_results = {}
            self.update_display_name_signal.emit("Unknown")

    def _emit_display_frame(self, frame_to_display: np.ndarray) -> None:
        if self.last_known_results:
            pil_img = Image.fromarray(cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            for box, (name, distance, note) in self.last_known_results.items():
                x, y, w, h = box
                color = (0, 255, 0) if name != "Unknown" else (255, 0, 0)
                label = name if name != "Unknown" else "ไม่รู้จัก"
                if distance is not None:
                    label = f"{name} {distance:.2f}" if (name != "Unknown" and self.show_debug_distance) else (name if name != "Unknown" else "ไม่รู้จัก")
                if note == "ambiguous-match":
                    label = "ยังไม่มั่นใจ"
                draw.rectangle([(x, y), (x + w, y + h)], outline=color, width=3)
                draw.text((x, max(0, y - 30)), label, font=self.font, fill=color)
            frame_to_display = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        rgb = cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        self.change_image_signal.emit(q_img)

    def stop(self) -> None:
        self.is_running = False
        self.quit()
        self.wait(3000)
