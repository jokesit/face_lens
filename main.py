# file: main.py
"""FaceLens main application.

Batch 2 focuses on correct Qt threading:
- VideoThread owns only camera capture, face detection, and display frame creation.
- RecognitionWorker is a QObject moved to a dedicated QThread for DeepFace/FAISS work.
- Heavy embedding jobs no longer live on a QThread subclass object in the GUI thread.
"""

from __future__ import annotations

import ctypes
import platform
import sys
import time
import traceback

import cv2
import faiss
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QSplashScreen, QVBoxLayout, QWidget

from add_customer_dialog import AddCustomerDialog
from core.config import (
    ASSETS_DIR,
    CAMERA_HEIGHT,
    CAMERA_INDEX,
    CAMERA_WIDTH,
    CAPTURE_COOLDOWN_FRAMES,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    LOG_DIR,
    MAX_SNAPSHOTS,
    MIN_FACE_MOVEMENT,
    RECOGNITION_INTERVAL_FRAMES,
    RECOGNITION_THRESHOLD,
    TARGET_FPS,
)
from core.database import Database
from core.face_recognizer import FaceRecognizer


# Windows taskbar icon/app grouping.
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("facelens.pro.store.1.0")
except (ImportError, AttributeError):
    pass


STYLESHEET = """
QMainWindow { background-color: #F5F5F5; }
QLabel#TitleLabel { font-size: 32px; font-weight: bold; color: #2980B9; padding-bottom: 10px; }
QLabel#CameraLabel { background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 10px; }
QLabel#NameLabel { font-size: 24px; font-weight: bold; padding: 10px; border-radius: 5px; }
QPushButton { background-color: #3498DB; color: white; font-size: 16px; font-weight: bold; padding: 12px; border-radius: 8px; border: none; }
QPushButton:hover { background-color: #2980B9; }
QPushButton:pressed { background-color: #1F618D; }
"""


class RecognitionWorker(QObject):
    """Runs expensive recognition jobs inside a dedicated QThread.

    Important Qt rule: this is a QObject moved to a QThread. Slots on this object
    run in the worker thread when called through queued signal connections.
    """

    recognition_result = Signal(str, object)
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

    @Slot(object, object)
    def process_recognition_job(self, face_image, box) -> None:
        try:
            if self.faiss_index is None or self.recognizer is None:
                self.recognition_result.emit("Unknown", box)
                return

            embedding = self.recognizer.get_embedding(face_image)
            if embedding is None:
                self.recognition_result.emit("Unknown", box)
                return

            query = np.asarray([embedding], dtype=np.float32)
            distances, indices = self.faiss_index.search(query, 1)
            distance = float(distances[0][0])
            index = int(indices[0][0])

            name = "Unknown"
            if distance < self.recognition_threshold:
                name = self.index_to_name_map.get(index, "Unknown")
            self.recognition_result.emit(name, box)
        except Exception as exc:
            print(f"Recognition job failed: {exc}")
            self.recognition_result.emit("Unknown", box)

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


class VideoThread(QThread):
    """Camera capture + face detection thread.

    This thread emits QImage, not QPixmap. QPixmap must be created in the GUI thread.
    """

    change_image_signal = Signal(QImage)
    recognition_job_signal = Signal(object, object)
    raw_frame_signal = Signal(np.ndarray)
    capture_progress_signal = Signal(int, int)
    snapshot_job_signal = Signal(object)
    update_display_name_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.detector = FaceRecognizer()
        self.is_running = True
        self.frame_counter = 0
        self.recognition_job_pending = False
        self.last_known_results: dict[tuple[int, int, int, int], str] = {}
        self.is_capture_mode = False
        self.capture_count = 0
        self.last_face_box = None
        self.capture_cooldown = 0

        try:
            self.font = ImageFont.truetype(str(ASSETS_DIR / "tahoma.ttf"), 24)
        except IOError:
            print("Font file not found in assets/tahoma.ttf. Using default font.")
            self.font = ImageFont.load_default()

    @Slot(str, object)
    def update_recognition_results(self, name: str, box) -> None:
        self.recognition_job_pending = False
        if box is not None:
            self.last_known_results[box] = name

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

                if self.is_capture_mode:
                    self._handle_capture_mode(faces, boxes)
                else:
                    self._handle_recognition_mode(faces, boxes)

                self._emit_display_frame(frame_to_display)

                self.frame_counter += 1
                elapsed = time.perf_counter() - frame_started_at
                sleep_ms = int(max(0.0, min_frame_seconds - elapsed) * 1000)
                if sleep_ms > 0:
                    self.msleep(sleep_ms)
        finally:
            cap.release()

    def _handle_capture_mode(self, faces, boxes) -> None:
        if self.capture_cooldown > 0:
            self.capture_cooldown -= 1

        if self.capture_cooldown != 0 or len(faces) != 1 or self.capture_count >= MAX_SNAPSHOTS:
            return

        face_img, face_box = faces[0], boxes[0]
        face_h, face_w = face_img.shape[:2]
        is_good = face_h >= 64 and face_w >= 64
        has_moved = True

        if self.last_face_box is not None:
            dx = abs(face_box[0] - self.last_face_box[0])
            dy = abs(face_box[1] - self.last_face_box[1])
            has_moved = dx >= MIN_FACE_MOVEMENT or dy >= MIN_FACE_MOVEMENT

        if is_good and has_moved:
            self.snapshot_job_signal.emit(face_img)
            self.capture_count += 1
            self.last_face_box = face_box
            self.capture_cooldown = CAPTURE_COOLDOWN_FRAMES
            self.capture_progress_signal.emit(self.capture_count, MAX_SNAPSHOTS)

    def _handle_recognition_mode(self, faces, boxes) -> None:
        if self.frame_counter % RECOGNITION_INTERVAL_FRAMES != 0:
            return

        self.last_known_results = {}
        if faces and not self.recognition_job_pending:
            self.recognition_job_pending = True
            self.recognition_job_signal.emit(faces[0], boxes[0])
        elif not faces:
            self.recognition_job_pending = False
            self.update_display_name_signal.emit("Unknown")

    def _emit_display_frame(self, frame_to_display: np.ndarray) -> None:
        if self.last_known_results:
            pil_img = Image.fromarray(cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            for box, name in self.last_known_results.items():
                x, y, w, h = box
                color = (0, 255, 0) if name != "Unknown" else (255, 0, 0)
                draw.rectangle([(x, y), (x + w, y + h)], outline=color, width=3)
                draw.text((x, max(0, y - 30)), name, font=self.font, fill=color)
            frame_to_display = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        rgb = cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        self.change_image_signal.emit(q_img)

    def stop(self) -> None:
        self.is_running = False
        self.quit()
        self.wait(3000)


class MainWindow(QMainWindow):
    rebuild_index_signal = Signal(list)
    verification_job_signal = Signal(list, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FaceLens (Professional Thread Architecture)")
        self.setGeometry(100, 100, 800, 720)
        self.setWindowIcon(QIcon(str(ASSETS_DIR / "logo.png")))
        self.db = Database()

        title_label = QLabel("FaceLens AI")
        title_label.setObjectName("TitleLabel")
        title_label.setAlignment(Qt.AlignCenter)

        self.image_label = QLabel(self)
        self.image_label.setObjectName("CameraLabel")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setText("Starting Camera...")

        self.name_label = QLabel(self)
        self.name_label.setObjectName("NameLabel")
        self.name_label.setAlignment(Qt.AlignCenter)

        self.add_customer_button = QPushButton("Add / Update Customer Data", self)
        self.add_customer_button.clicked.connect(self.open_add_customer_dialog)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        layout.addWidget(title_label)
        layout.addWidget(self.image_label)
        layout.addWidget(self.name_label)
        layout.addWidget(self.add_customer_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.video_thread = VideoThread()
        self.recognition_thread = QThread(self)
        self.recognition_worker = RecognitionWorker()
        self.recognition_worker.moveToThread(self.recognition_thread)

        self._connect_threads()
        self._start_threads()

    def _connect_threads(self) -> None:
        self.recognition_thread.started.connect(self.recognition_worker.initialize)
        self.recognition_thread.finished.connect(self.recognition_worker.deleteLater)

        self.video_thread.change_image_signal.connect(self.update_image)
        self.video_thread.recognition_job_signal.connect(self.recognition_worker.process_recognition_job)
        self.video_thread.update_display_name_signal.connect(self.update_name_from_result)

        self.recognition_worker.recognition_result.connect(self.video_thread.update_recognition_results)
        self.recognition_worker.recognition_result.connect(self.update_name_from_result)
        self.recognition_worker.worker_ready.connect(self.update_name_from_result)
        self.recognition_worker.worker_error.connect(self.show_worker_error)

        self.rebuild_index_signal.connect(self.recognition_worker.build_faiss_index)
        self.verification_job_signal.connect(self.recognition_worker.process_verification_job)

    def _start_threads(self) -> None:
        self.update_name_from_result("Loading AI model...", None)
        self.recognition_thread.start()
        self.video_thread.start()
        self.rebuild_index_signal.emit(self.db.get_all_data_for_faiss())

    def open_add_customer_dialog(self) -> None:
        dialog = AddCustomerDialog(parent=self)

        self.video_thread.raw_frame_signal.connect(dialog.update_frame)
        dialog.capture_mode_toggled.connect(self.video_thread.set_capture_mode)
        self.video_thread.snapshot_job_signal.connect(self.recognition_worker.process_snapshot_job)
        self.recognition_worker.snapshot_result.connect(dialog.add_captured_embedding)
        self.video_thread.capture_progress_signal.connect(dialog.update_capture_progress)
        dialog.request_verification_job.connect(self.verification_job_signal.emit)
        self.recognition_worker.verification_result.connect(dialog.on_verification_finished)
        dialog.customer_saved_signal.connect(self.on_customer_saved)

        dialog.exec()

        self.video_thread.raw_frame_signal.disconnect(dialog.update_frame)
        dialog.capture_mode_toggled.disconnect(self.video_thread.set_capture_mode)
        self.video_thread.snapshot_job_signal.disconnect(self.recognition_worker.process_snapshot_job)
        self.recognition_worker.snapshot_result.disconnect(dialog.add_captured_embedding)
        self.video_thread.capture_progress_signal.disconnect(dialog.update_capture_progress)
        dialog.request_verification_job.disconnect(self.verification_job_signal.emit)
        self.recognition_worker.verification_result.disconnect(dialog.on_verification_finished)
        dialog.customer_saved_signal.disconnect(self.on_customer_saved)
        self.video_thread.set_capture_mode(False)

    @Slot()
    def on_customer_saved(self) -> None:
        self.rebuild_index_signal.emit(self.db.get_all_data_for_faiss())

    def closeEvent(self, event) -> None:
        self.video_thread.stop()
        self.recognition_thread.quit()
        self.recognition_thread.wait(5000)
        self.db.close()
        event.accept()

    @Slot(QImage)
    def update_image(self, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image)
        self.image_label.setPixmap(pixmap.scaled(DISPLAY_WIDTH, DISPLAY_HEIGHT, Qt.KeepAspectRatio))

    @Slot(str)
    def show_worker_error(self, message: str) -> None:
        self.update_name_from_result("Unknown", None)
        print(message)

    @Slot(str, object)
    def update_name_from_result(self, name: str, box=None) -> None:
        if name == "Camera Error":
            text, color, bg_color = "Camera Error", "#E74C3C", "#F9EBEA"
        elif name in {"Loading AI model...", "Searching..."}:
            text, color, bg_color = name, "#2980B9", "#EBF5FB"
        elif name != "Unknown":
            text, color, bg_color = f"Welcome, {name}!", "#2ECC71", "#E8F8F5"
        else:
            text, color, bg_color = "Unknown Customer", "#E74C3C", "#F9EBEA"

        self.name_label.setStyleSheet(
            f"background-color: {bg_color}; color: {color}; font-size: 24px; "
            "font-weight: bold; padding: 10px; border-radius: 5px;"
        )
        self.name_label.setText(text)


def install_exception_logger() -> None:
    """Write uncaught Python exceptions to logs/facelens_crash.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "facelens_crash.log"

    def _hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open(log_path, "a", encoding="utf-8") as file:
                file.write("\n" + "=" * 80 + "\n")
                file.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                file.write(text)
        finally:
            print(text)
            sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


if __name__ == "__main__":
    install_exception_logger()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ASSETS_DIR / "logo.png")))
    app.setStyleSheet(STYLESHEET)
    app.setFont(QFont("Segoe UI", 10))

    pixmap = QPixmap(str(ASSETS_DIR / "logo.png"))
    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint)
    splash.setFont(QFont("Segoe UI", 20, QFont.Bold))
    splash.showMessage("Initializing FaceLens, please wait...", Qt.AlignCenter | Qt.AlignBottom, Qt.black)
    splash.show()

    window = MainWindow()
    splash.finish(window)
    window.show()
    sys.exit(app.exec())
