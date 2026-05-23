"""FaceLens main application.

Batch 5 focuses on production UI polish:
- Thai operator-facing messages.
- Customer management dialog.
- Debug-distance toggle so the customer-facing screen stays clean.
"""

from __future__ import annotations

import ctypes
import sys
import time

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

from add_customer_dialog import AddCustomerDialog
from customer_management_dialog import CustomerManagementDialog
from core.app_logging import install_exception_logger
from core.config import ASSETS_DIR, DISPLAY_HEIGHT, DISPLAY_WIDTH, RECOGNITION_EVENT_MIN_SECONDS, SHOW_DEBUG_DISTANCE
from core.database import Database
from core.recognition_worker import RecognitionWorker
from core.ui_styles import STYLESHEET
from core.video_thread import VideoThread


try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("facelens.pro.store.1.0")
except (ImportError, AttributeError):
    pass


class MainWindow(QMainWindow):
    rebuild_index_signal = Signal(list)
    verification_job_signal = Signal(list, str)
    debug_distance_toggled = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FaceLens - ระบบจดจำใบหน้าสำหรับร้านค้า")
        self.setGeometry(100, 100, 860, 780)
        self.setWindowIcon(QIcon(str(ASSETS_DIR / "logo.png")))
        self.db = Database()
        self._last_recognition_event_by_key: dict[str, float] = {}

        title_label = QLabel("FaceLens AI")
        title_label.setObjectName("TitleLabel")
        title_label.setAlignment(Qt.AlignCenter)

        subtitle_label = QLabel("ระบบช่วยจดจำลูกค้า เพื่อให้พนักงานทักทายได้อย่างถูกต้องและประทับใจ")
        subtitle_label.setObjectName("SubtitleLabel")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setWordWrap(True)

        self.image_label = QLabel(self)
        self.image_label.setObjectName("CameraLabel")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setText("กำลังเปิดกล้อง...")

        self.name_label = QLabel(self)
        self.name_label.setObjectName("NameLabel")
        self.name_label.setAlignment(Qt.AlignCenter)

        self.status_label = QLabel("สถานะ: กำลังเริ่มต้นระบบ")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)

        self.add_customer_button = QPushButton("เพิ่ม / อัปเดตข้อมูลลูกค้า", self)
        self.add_customer_button.clicked.connect(self.open_add_customer_dialog)

        self.manage_customer_button = QPushButton("จัดการข้อมูลลูกค้า", self)
        self.manage_customer_button.clicked.connect(self.open_customer_management_dialog)

        self.debug_distance_checkbox = QCheckBox("โหมดตรวจสอบ: แสดงค่าความใกล้เคียง")
        self.debug_distance_checkbox.setToolTip("ใช้สำหรับทดสอบและปรับ threshold เท่านั้น ไม่แนะนำให้เปิดตอนใช้งานหน้าร้าน")
        self.debug_distance_checkbox.setChecked(SHOW_DEBUG_DISTANCE)
        self.debug_distance_checkbox.toggled.connect(self.debug_distance_toggled.emit)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_customer_button)
        button_layout.addWidget(self.manage_customer_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(self.image_label)
        layout.addWidget(self.name_label)
        layout.addWidget(self.status_label)
        layout.addLayout(button_layout)
        layout.addWidget(self.debug_distance_checkbox, alignment=Qt.AlignCenter)

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

        self.recognition_worker.recognition_results.connect(self.video_thread.update_recognition_results)
        self.recognition_worker.recognition_results.connect(self.log_recognition_events)
        self.recognition_worker.worker_ready.connect(self.update_name_from_result)
        self.recognition_worker.worker_error.connect(self.show_worker_error)

        self.debug_distance_toggled.connect(self.video_thread.set_show_debug_distance)
        self.rebuild_index_signal.connect(self.recognition_worker.build_faiss_index)
        self.verification_job_signal.connect(self.recognition_worker.process_verification_job)

    def _start_threads(self) -> None:
        self.update_name_from_result("Loading AI model...")
        self.recognition_thread.start()
        self.video_thread.start()
        self.rebuild_faiss_index()

    def open_add_customer_dialog(self) -> None:
        dialog = AddCustomerDialog(parent=self)

        self.video_thread.raw_frame_signal.connect(dialog.update_frame)
        self.video_thread.capture_hint_signal.connect(dialog.update_capture_hint)
        dialog.capture_mode_toggled.connect(self.video_thread.set_capture_mode)
        self.video_thread.snapshot_job_signal.connect(self.recognition_worker.process_snapshot_job)
        self.recognition_worker.snapshot_result.connect(dialog.add_captured_embedding)
        self.video_thread.capture_progress_signal.connect(dialog.update_capture_progress)
        dialog.request_verification_job.connect(self.verification_job_signal.emit)
        self.recognition_worker.verification_result.connect(dialog.on_verification_finished)
        dialog.customer_saved_signal.connect(self.on_customer_saved)

        dialog.exec()

        self.video_thread.raw_frame_signal.disconnect(dialog.update_frame)
        self.video_thread.capture_hint_signal.disconnect(dialog.update_capture_hint)
        dialog.capture_mode_toggled.disconnect(self.video_thread.set_capture_mode)
        self.video_thread.snapshot_job_signal.disconnect(self.recognition_worker.process_snapshot_job)
        self.recognition_worker.snapshot_result.disconnect(dialog.add_captured_embedding)
        self.video_thread.capture_progress_signal.disconnect(dialog.update_capture_progress)
        dialog.request_verification_job.disconnect(self.verification_job_signal.emit)
        self.recognition_worker.verification_result.disconnect(dialog.on_verification_finished)
        dialog.customer_saved_signal.disconnect(self.on_customer_saved)
        self.video_thread.set_capture_mode(False)

    def open_customer_management_dialog(self) -> None:
        dialog = CustomerManagementDialog(parent=self)
        dialog.customers_changed.connect(self.on_customer_saved)
        dialog.exec()
        dialog.customers_changed.disconnect(self.on_customer_saved)

    def rebuild_faiss_index(self) -> None:
        db_data = self.db.get_all_data_for_faiss()
        print(f"Rebuilding FAISS from {len(db_data)} active face embeddings.")
        self.status_label.setText(f"สถานะ: พร้อมใช้งานฐานข้อมูลใบหน้า {len(db_data)} รายการ")
        self.rebuild_index_signal.emit(db_data)

    @Slot()
    def on_customer_saved(self) -> None:
        self.rebuild_faiss_index()

    @Slot(list)
    def log_recognition_events(self, results: list) -> None:
        """Persist throttled recognition events for audit/debugging."""
        now = time.monotonic()
        for name, _box, distance, _quality_score, note in results:
            if name != "Unknown" and note == "ok":
                result_type = "recognized"
                event_key = f"recognized:{name}"
                predicted_name = name
            elif note == "ambiguous-match":
                result_type = "ambiguous"
                event_key = "ambiguous"
                predicted_name = None
            else:
                continue

            last_at = self._last_recognition_event_by_key.get(event_key, 0.0)
            if now - last_at < RECOGNITION_EVENT_MIN_SECONDS:
                continue

            self._last_recognition_event_by_key[event_key] = now
            try:
                self.db.log_recognition_event(predicted_name, distance, result_type, note)
            except Exception as exc:
                print(f"Could not log recognition event: {exc}")

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
        self.update_name_from_result("Unknown")
        self.status_label.setText("สถานะ: เกิดข้อผิดพลาดจาก AI model กรุณาดู logs/facelens_crash.log")
        print(message)

    @Slot(str)
    def update_name_from_result(self, name: str) -> None:
        if name == "Camera Error":
            text, color, bg_color = "ไม่สามารถเปิดกล้องได้", "#E74C3C", "#F9EBEA"
            status = "สถานะ: ตรวจสอบการเชื่อมต่อกล้อง หรือปิดโปรแกรมอื่นที่ใช้กล้องอยู่"
        elif name == "Loading AI model...":
            text, color, bg_color = "กำลังโหลด AI...", "#2980B9", "#EBF5FB"
            status = "สถานะ: กำลังเตรียมระบบจดจำใบหน้า ครั้งแรกอาจใช้เวลานานเล็กน้อย"
        elif name == "Searching...":
            text, color, bg_color = "พร้อมจดจำใบหน้า", "#2980B9", "#EBF5FB"
            status = "สถานะ: ระบบพร้อมใช้งาน"
        elif name != "Unknown":
            text, color, bg_color = f"สวัสดีคุณ {name}", "#2ECC71", "#E8F8F5"
            status = "สถานะ: พบลูกค้าที่บันทึกไว้แล้ว"
        else:
            text, color, bg_color = "ยังไม่พบข้อมูลลูกค้า", "#E67E22", "#FEF5E7"
            status = "สถานะ: กำลังตรวจสอบใบหน้าในกล้อง"

        self.name_label.setStyleSheet(
            f"background-color: {bg_color}; color: {color}; font-size: 24px; "
            "font-weight: bold; padding: 12px; border-radius: 8px;"
        )
        self.name_label.setText(text)
        self.status_label.setText(status)


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
    splash.showMessage("กำลังเริ่มต้น FaceLens...", Qt.AlignCenter | Qt.AlignBottom, Qt.black)
    splash.show()

    window = MainWindow()
    splash.finish(window)
    window.show()
    sys.exit(app.exec())
