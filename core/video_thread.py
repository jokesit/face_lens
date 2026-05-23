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
    FACE_DETECTION_INTERVAL_FRAMES,
    MAX_RECOGNITION_FACES,
    MAX_SNAPSHOTS,
    MIN_FACE_MOVEMENT,
    RECOGNITION_BOX_REUSE_IOU,
    RECOGNITION_INTERVAL_FRAMES,
    RECOGNITION_MIN_SECONDS_BETWEEN_JOBS,
    RECOGNITION_RESULT_TTL_SECONDS,
    TARGET_FPS,
    SHOW_DEBUG_DISTANCE,
)
from core.face_quality import evaluate_face_quality
from core.face_recognizer import FaceRecognizer
from core.performance import box_iou
from core.performance_profiles import DEFAULT_PROFILE_KEY, get_performance_profile
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

    def __init__(self, camera_index: int | None = None):
        super().__init__()
        self.detector = FaceRecognizer()
        self.is_running = True
        self.camera_index = CAMERA_INDEX if camera_index is None else int(camera_index)
        self._camera_restart_requested = False
        self.frame_counter = 0
        self.recognition_job_pending = False
        self.last_known_results: dict[FaceBox, tuple[str, float | None, str]] = {}
        self.last_result_at = 0.0
        self.last_recognition_request_at = 0.0
        self.cached_observations: list[FaceObservation] = []
        self.is_capture_mode = False
        self.capture_count = 0
        self.last_face_box: FaceBox | None = None
        self.capture_cooldown = 0
        self.show_debug_distance = SHOW_DEBUG_DISTANCE
        self.active_profile_key = DEFAULT_PROFILE_KEY

        self.target_fps = TARGET_FPS
        self.face_detection_interval_frames = FACE_DETECTION_INTERVAL_FRAMES
        self.recognition_interval_frames = RECOGNITION_INTERVAL_FRAMES
        self.recognition_min_seconds_between_jobs = RECOGNITION_MIN_SECONDS_BETWEEN_JOBS
        self.recognition_result_ttl_seconds = RECOGNITION_RESULT_TTL_SECONDS
        self.recognition_box_reuse_iou = RECOGNITION_BOX_REUSE_IOU
        self.max_recognition_faces = MAX_RECOGNITION_FACES

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
            self.last_result_at = time.monotonic()
            self.update_display_name_signal.emit(best_name)

    @Slot(bool)
    def set_show_debug_distance(self, enabled: bool) -> None:
        self.show_debug_distance = bool(enabled)

    @Slot(str)
    def set_performance_profile(self, profile_key: str) -> None:
        """Apply a runtime performance profile without restarting the app."""
        profile = get_performance_profile(profile_key)
        self.active_profile_key = profile.key
        self.target_fps = max(1.0, profile.target_fps)
        self.face_detection_interval_frames = max(1, int(profile.face_detection_interval_frames))
        self.recognition_interval_frames = max(1, int(profile.recognition_interval_frames))
        self.recognition_min_seconds_between_jobs = max(0.1, float(profile.recognition_min_seconds_between_jobs))
        self.recognition_result_ttl_seconds = max(0.5, float(profile.recognition_result_ttl_seconds))
        self.recognition_box_reuse_iou = max(0.0, min(1.0, float(profile.recognition_box_reuse_iou)))
        self.max_recognition_faces = max(1, int(profile.max_recognition_faces))
        self.last_known_results = {}
        self.last_result_at = 0.0
        self.recognition_job_pending = False
        print(f"Performance profile applied: {profile.thai_name}")

    @Slot(int)
    def set_camera_index(self, camera_index: int) -> None:
        camera_index = max(0, min(9, int(camera_index)))
        if camera_index == self.camera_index:
            return
        self.camera_index = camera_index
        self._camera_restart_requested = True
        self.recognition_job_pending = False
        self.last_known_results = {}
        self.cached_observations = []
        self.last_result_at = 0.0
        self.update_display_name_signal.emit("Switching Camera")

    @Slot(bool)
    def set_capture_mode(self, is_active: bool) -> None:
        self.is_capture_mode = is_active
        self.capture_count = 0 if is_active else self.capture_count
        self.last_face_box = None
        self.capture_cooldown = 0
        if is_active:
            self.recognition_job_pending = False
            self.last_known_results = {}
            self.cached_observations = []
            self.last_result_at = 0.0

    def run(self) -> None:
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else 0

        while self.is_running:
            self._camera_restart_requested = False
            cap = cv2.VideoCapture(self.camera_index, backend)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                self.update_display_name_signal.emit("Camera Error")
                cap.release()
                # Keep the thread alive briefly so the operator can choose another camera.
                while self.is_running and not self._camera_restart_requested:
                    self.msleep(200)
                continue

            try:
                while self.is_running and not self._camera_restart_requested:
                    min_frame_seconds = 1.0 / self.target_fps if self.target_fps > 0 else 0.0
                    frame_started_at = time.perf_counter()
                    ret, cv_img = cap.read()
                    if not ret:
                        self.msleep(30)
                        continue

                    self.raw_frame_signal.emit(cv_img)
                    frame_to_display = cv_img.copy()

                    should_detect = (
                        self.is_capture_mode
                        or self.frame_counter % self.face_detection_interval_frames == 0
                        or not self.cached_observations
                    )
                    if should_detect:
                        faces, boxes = self.detector.detect_faces(frame_to_display)
                        observations = self._build_observations(faces, boxes)
                        self.cached_observations = observations
                    else:
                        observations = self.cached_observations

                    if self.is_capture_mode:
                        self._handle_capture_mode(observations)
                    else:
                        self._handle_recognition_mode(observations)

                    self._emit_display_frame(frame_to_display, observations)

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
                self.capture_hint_signal.emit("กรุณาให้มีใบหน้าเพียง 1 คนในกล้อง")
            return

        if self.capture_cooldown != 0:
            return

        observation = observations[0]
        quality = evaluate_face_quality(observation.face_image)
        if not quality.is_good_for_capture:
            self.capture_hint_signal.emit(f"ภาพยังไม่เหมาะสม: {self._quality_reason_to_thai(quality.reason)}")
            return

        has_moved = True
        if self.last_face_box is not None:
            dx = abs(observation.box[0] - self.last_face_box[0])
            dy = abs(observation.box[1] - self.last_face_box[1])
            has_moved = dx >= MIN_FACE_MOVEMENT or dy >= MIN_FACE_MOVEMENT

        if not has_moved:
            self.capture_hint_signal.emit("กรุณาขยับหรือหันหน้าเล็กน้อย เพื่อเก็บมุมใบหน้าที่หลากหลาย")
            return

        self.snapshot_job_signal.emit(observation.face_image)
        self.capture_count += 1
        self.last_face_box = observation.box
        self.capture_cooldown = CAPTURE_COOLDOWN_FRAMES
        self.capture_progress_signal.emit(self.capture_count, MAX_SNAPSHOTS)


    @staticmethod
    def _quality_reason_to_thai(reason: str) -> str:
        translations = {
            "empty": "ไม่พบภาพใบหน้า",
            "invalid-size": "ขนาดภาพไม่ถูกต้อง",
            "face-too-small": "ใบหน้าเล็กเกินไป กรุณาเข้าใกล้กล้องอีกเล็กน้อย",
            "blurry": "ภาพเบลอ กรุณาอยู่นิ่งสักครู่",
            "too-dark": "แสงน้อยเกินไป กรุณาเพิ่มแสงบริเวณใบหน้า",
            "too-bright": "แสงสว่างเกินไป กรุณาลดแสงสะท้อนบริเวณใบหน้า",
            "ok": "ภาพพร้อมใช้งาน",
        }
        parts = [part.strip() for part in reason.split(",") if part.strip()]
        if not parts:
            return translations.get(reason, reason)
        return " / ".join(translations.get(part, part) for part in parts)

    def _handle_recognition_mode(self, observations: list[FaceObservation]) -> None:
        now = time.monotonic()
        if not observations:
            self.recognition_job_pending = False
            self.last_known_results = {}
            self.cached_observations = []
            self.last_result_at = 0.0
            self.update_display_name_signal.emit("Unknown")
            return

        if self.frame_counter % self.recognition_interval_frames != 0:
            return

        if self.recognition_job_pending:
            return

        if now - self.last_recognition_request_at < self.recognition_min_seconds_between_jobs:
            return

        if self._can_reuse_recent_results(observations, now):
            return

        self.recognition_job_pending = True
        self.last_recognition_request_at = now
        self.recognition_job_signal.emit(observations[:self.max_recognition_faces])

    def _can_reuse_recent_results(self, observations: list[FaceObservation], now: float) -> bool:
        """Avoid calling DeepFace again when the same face is still in place.

        DeepFace is the expensive step. For a shop greeting screen, it is fine to
        reuse a confident result for a few seconds while the customer's face box
        stays close to the previous box.
        """
        if not self.last_known_results:
            return False
        if now - self.last_result_at > self.recognition_result_ttl_seconds:
            self.last_known_results = {}
            return False

        known_boxes = list(self.last_known_results.keys())
        for observation in observations[:self.max_recognition_faces]:
            if not any(box_iou(observation.box, old_box) >= self.recognition_box_reuse_iou for old_box in known_boxes):
                return False
        return True

    def _emit_display_frame(self, frame_to_display: np.ndarray, observations: list[FaceObservation]) -> None:
        """Draw face boxes on the latest detected positions.

        Recognition is intentionally throttled because DeepFace is expensive, but
        the display box should still follow the face immediately. Therefore this
        method matches the latest recognition result to the latest face box and
        draws on the current box instead of drawing the old recognized box.
        """
        if self.last_known_results and time.monotonic() - self.last_result_at > self.recognition_result_ttl_seconds:
            self.last_known_results = {}

        if observations:
            pil_img = Image.fromarray(cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            used_result_boxes: set[FaceBox] = set()

            for observation in observations[:self.max_recognition_faces]:
                result = self._match_result_for_current_box(observation.box, used_result_boxes)
                if result is None:
                    name, distance, note = "Unknown", None, "pending"
                else:
                    result_box, name, distance, note = result
                    used_result_boxes.add(result_box)

                x, y, w, h = observation.box
                color = (0, 255, 0) if name != "Unknown" else (255, 0, 0)
                label = name if name != "Unknown" else "ไม่รู้จัก"
                if distance is not None and name != "Unknown" and self.show_debug_distance:
                    label = f"{name} {distance:.2f}"
                if note == "ambiguous-match":
                    label = "ยังไม่มั่นใจ"

                draw.rectangle([(x, y), (x + w, y + h)], outline=color, width=3)
                draw.text((x, max(0, y - 30)), label, font=self.font, fill=color)
            frame_to_display = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        rgb = cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        self.change_image_signal.emit(q_img)

    def _match_result_for_current_box(
        self,
        current_box: FaceBox,
        used_result_boxes: set[FaceBox],
    ) -> tuple[FaceBox, str, float | None, str] | None:
        """Find the best recent recognition result for a live face box."""
        if not self.last_known_results:
            return None

        best_box: FaceBox | None = None
        best_payload: tuple[str, float | None, str] | None = None
        best_score = 0.0
        for result_box, payload in self.last_known_results.items():
            if result_box in used_result_boxes:
                continue
            score = box_iou(current_box, result_box)
            if score > best_score:
                best_score = score
                best_box = result_box
                best_payload = payload

        if best_box is None or best_payload is None:
            return None
        if best_score < self.recognition_box_reuse_iou:
            return None

        name, distance, note = best_payload
        return best_box, name, distance, note

    def stop(self) -> None:
        self.is_running = False
        self.quit()
        self.wait(3000)
