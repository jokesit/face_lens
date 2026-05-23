"""FaceLens main application.

Batch 9 adds a compact modern layout and runtime confidence presets so the
shop can reduce wrong-name greetings without editing code. Batch 10 adds
restore/maintenance tools for standalone pharmacy deployments.
"""

from __future__ import annotations

import ctypes
import sys
import time
from datetime import datetime

from core.frozen_runtime import setup_runtime_environment

setup_runtime_environment()

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplashScreen,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from add_customer_dialog import AddCustomerDialog
from customer_management_dialog import CustomerManagementDialog
from health_check_dialog import HealthCheckDialog
from core.app_logging import install_exception_logger
from core.app_settings import AppSettings
from core.config import (
    APP_WINDOW_HEIGHT,
    APP_WINDOW_WIDTH,
    LOGO_PNG_PATH,
    BACKUP_DIR,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    RECOGNITION_EVENT_MIN_SECONDS,
    SHOW_DEBUG_DISTANCE,
    STANDALONE_TARGET_CUSTOMERS,
)
from core.confidence_profiles import CONFIDENCE_PROFILES, get_confidence_profile
from core.database import Database
from core.performance_profiles import PERFORMANCE_PROFILES, get_performance_profile
from core.recognition_worker import RecognitionWorker
from core.ui_styles import STYLESHEET
from core.video_thread import VideoThread


try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("facelens.pro.store.1.0")
except (ImportError, AttributeError):
    pass


def build_app_icon() -> QIcon:
    """Return the app icon if bundled; otherwise return an empty icon safely."""
    if LOGO_PNG_PATH.exists():
        return QIcon(str(LOGO_PNG_PATH))
    return QIcon()


def build_splash_screen() -> QSplashScreen | None:
    """Create a splash screen only when the logo image is available."""
    if not LOGO_PNG_PATH.exists():
        return None
    pixmap = QPixmap(str(LOGO_PNG_PATH))
    if pixmap.isNull():
        return None
    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint)
    splash.setFont(QFont("Segoe UI", 18, QFont.Bold))
    splash.showMessage("กำลังเริ่มต้น FaceLens...", Qt.AlignCenter | Qt.AlignBottom, Qt.black)
    return splash


class MainWindow(QMainWindow):
    rebuild_index_signal = Signal(list)
    verification_job_signal = Signal(list, str)
    debug_distance_toggled = Signal(bool)
    performance_profile_changed = Signal(str)
    confidence_profile_changed = Signal(str)
    camera_index_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FaceLens - ระบบจดจำใบหน้าสำหรับร้านค้า")
        self.resize(APP_WINDOW_WIDTH, APP_WINDOW_HEIGHT)
        self.setMinimumSize(800, 720)
        self.setWindowIcon(build_app_icon())
        self.db = Database()
        self.settings = AppSettings()
        self._last_recognition_event_by_key: dict[str, float] = {}
        self._closing = False

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
        self.image_label.setMinimumSize(DISPLAY_WIDTH, DISPLAY_HEIGHT)
        self.image_label.setMinimumHeight(DISPLAY_HEIGHT)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.name_label = QLabel(self)
        self.name_label.setObjectName("NameLabel")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setMinimumHeight(48)
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.status_label = QLabel("สถานะ: กำลังเริ่มต้นระบบ")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)

        self.add_customer_button = QPushButton("เพิ่ม / อัปเดตข้อมูลลูกค้า", self)
        self.add_customer_button.clicked.connect(self.open_add_customer_dialog)

        self.manage_customer_button = QPushButton("จัดการข้อมูลลูกค้า", self)
        self.manage_customer_button.clicked.connect(self.open_customer_management_dialog)

        self.backup_button = QPushButton("สำรองฐานข้อมูล", self)
        self.backup_button.setToolTip("สำรองข้อมูลลูกค้าและใบหน้าทั้งหมดเป็นไฟล์ .db")
        self.backup_button.clicked.connect(self.backup_database)

        self.restore_button = QPushButton("กู้คืนฐานข้อมูล", self)
        self.restore_button.setToolTip("กู้คืนข้อมูลจากไฟล์สำรอง .db ใช้เมื่อย้ายเครื่องหรือกู้ข้อมูล")
        self.restore_button.clicked.connect(self.restore_database)

        self.health_check_button = QPushButton("ตรวจระบบ", self)
        self.health_check_button.setToolTip("ตรวจ dependency, ฐานข้อมูล, พื้นที่จัดเก็บ และความพร้อมของโปรแกรม")
        self.health_check_button.clicked.connect(self.open_health_check_dialog)

        self.performance_combo = QComboBox(self)
        for key, profile in PERFORMANCE_PROFILES.items():
            self.performance_combo.addItem(profile.thai_name, key)
        saved_profile_key = self.settings.get_performance_profile_key()
        saved_index = self.performance_combo.findData(saved_profile_key)
        self.performance_combo.setCurrentIndex(saved_index if saved_index >= 0 else 0)
        self.performance_combo.currentIndexChanged.connect(self.on_performance_profile_selected)

        self.performance_hint_label = QLabel(self)
        self.performance_hint_label.setObjectName("PerformanceHintLabel")
        self.performance_hint_label.setAlignment(Qt.AlignCenter)
        self.performance_hint_label.setWordWrap(True)
        self._update_performance_hint(saved_profile_key)

        self.confidence_combo = QComboBox(self)
        for key, profile in CONFIDENCE_PROFILES.items():
            self.confidence_combo.addItem(profile.thai_name, key)
        saved_confidence_key = self.settings.get_confidence_profile_key()
        saved_confidence_index = self.confidence_combo.findData(saved_confidence_key)
        self.confidence_combo.setCurrentIndex(saved_confidence_index if saved_confidence_index >= 0 else 0)
        self.confidence_combo.currentIndexChanged.connect(self.on_confidence_profile_selected)

        self.confidence_hint_label = QLabel(self)
        self.confidence_hint_label.setObjectName("ConfidenceHintLabel")
        self.confidence_hint_label.setAlignment(Qt.AlignCenter)
        self.confidence_hint_label.setWordWrap(True)
        self._update_confidence_hint(saved_confidence_key)

        self.camera_combo = QComboBox(self)
        self.camera_combo.setToolTip("เลือกกล้องที่ต้องการใช้ หากกล้องไม่ขึ้นให้ลองเปลี่ยนเป็นหมายเลขถัดไป")
        for index in range(5):
            self.camera_combo.addItem(f"กล้อง {index}", index)
        saved_camera_index = self.settings.get_camera_index()
        camera_combo_index = self.camera_combo.findData(saved_camera_index)
        self.camera_combo.setCurrentIndex(camera_combo_index if camera_combo_index >= 0 else 0)
        self.camera_combo.currentIndexChanged.connect(self.on_camera_selected)

        self.debug_distance_checkbox = QCheckBox("โหมดตรวจสอบ: แสดงค่าความใกล้เคียง")
        self.debug_distance_checkbox.setToolTip("ใช้สำหรับทดสอบและปรับ threshold เท่านั้น ไม่แนะนำให้เปิดตอนใช้งานหน้าร้าน")
        self.debug_distance_checkbox.setChecked(SHOW_DEBUG_DISTANCE)
        self.debug_distance_checkbox.toggled.connect(self.debug_distance_toggled.emit)

        self.controls_toggle_button = QToolButton(self)
        self.controls_toggle_button.setObjectName("ControlsToggleButton")
        self.controls_toggle_button.setCheckable(True)
        self.controls_toggle_button.setChecked(self.settings.get_controls_collapsed())
        self.controls_toggle_button.clicked.connect(self.toggle_controls_panel)

        tuning_layout = QHBoxLayout()
        tuning_layout.setSpacing(8)
        performance_label = QLabel("โหมดความเร็ว:")
        performance_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        confidence_label = QLabel("ความมั่นใจ:")
        confidence_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tuning_layout.addWidget(performance_label)
        tuning_layout.addWidget(self.performance_combo)
        tuning_layout.addSpacing(8)
        tuning_layout.addWidget(confidence_label)
        tuning_layout.addWidget(self.confidence_combo)
        tuning_layout.addSpacing(8)
        camera_label = QLabel("กล้อง:")
        camera_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tuning_layout.addWidget(camera_label)
        tuning_layout.addWidget(self.camera_combo)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_customer_button)
        button_layout.addWidget(self.manage_customer_button)
        button_layout.addWidget(self.backup_button)
        button_layout.addWidget(self.restore_button)
        button_layout.addWidget(self.health_check_button)

        self.controls_panel = QWidget(self)
        self.controls_panel.setObjectName("ControlsPanel")
        controls_layout = QVBoxLayout(self.controls_panel)
        controls_layout.setContentsMargins(10, 8, 10, 8)
        controls_layout.setSpacing(6)
        controls_layout.addWidget(self.status_label)
        controls_layout.addLayout(tuning_layout)
        controls_layout.addWidget(self.performance_hint_label)
        controls_layout.addWidget(self.confidence_hint_label)
        controls_layout.addLayout(button_layout)
        controls_layout.addWidget(self.debug_distance_checkbox, alignment=Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(7)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(self.image_label, stretch=1)
        layout.addSpacing(4)
        layout.addWidget(self.name_label)
        layout.addWidget(self.controls_toggle_button, alignment=Qt.AlignCenter)
        layout.addWidget(self.controls_panel)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.statusBar().showMessage("กำลังเริ่มต้นระบบ")
        self.apply_controls_collapsed(self.settings.get_controls_collapsed())

        self.video_thread = VideoThread(camera_index=self.settings.get_camera_index())
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
        self.performance_profile_changed.connect(self.video_thread.set_performance_profile)
        self.confidence_profile_changed.connect(self.recognition_worker.set_confidence_profile)
        self.camera_index_changed.connect(self.video_thread.set_camera_index)
        self.rebuild_index_signal.connect(self.recognition_worker.build_faiss_index)
        self.verification_job_signal.connect(self.recognition_worker.process_verification_job)

    def _start_threads(self) -> None:
        self.update_name_from_result("Loading AI model...")
        self.recognition_thread.start()
        self.video_thread.start()
        self.rebuild_faiss_index()
        self.performance_profile_changed.emit(self.settings.get_performance_profile_key())
        self.confidence_profile_changed.emit(self.settings.get_confidence_profile_key())
        self.camera_index_changed.emit(self.settings.get_camera_index())
        QTimer.singleShot(700, self.show_first_run_tip_if_needed)

    @Slot(int)
    def on_performance_profile_selected(self, _index: int) -> None:
        profile_key = self.performance_combo.currentData()
        if not profile_key:
            return
        self.settings.set_performance_profile_key(str(profile_key))
        self._update_performance_hint(str(profile_key))
        self.performance_profile_changed.emit(str(profile_key))

    def _update_performance_hint(self, profile_key: str) -> None:
        profile = get_performance_profile(profile_key)
        self.performance_hint_label.setText(f"ความเร็ว: {profile.description}")

    @Slot(int)
    def on_confidence_profile_selected(self, _index: int) -> None:
        profile_key = self.confidence_combo.currentData()
        if not profile_key:
            return
        self.settings.set_confidence_profile_key(str(profile_key))
        self._update_confidence_hint(str(profile_key))
        self.confidence_profile_changed.emit(str(profile_key))

    def _update_confidence_hint(self, profile_key: str) -> None:
        profile = get_confidence_profile(profile_key)
        self.confidence_hint_label.setText(f"ความมั่นใจ: {profile.description}")

    @Slot(int)
    def on_camera_selected(self, _index: int) -> None:
        camera_index = int(self.camera_combo.currentData())
        self.settings.set_camera_index(camera_index)
        self.camera_index_changed.emit(camera_index)
        self.set_status(f"สถานะ: กำลังสลับไปใช้กล้อง {camera_index}")

    def show_first_run_tip_if_needed(self) -> None:
        if self.settings.get_first_run_done():
            return
        self.settings.set_first_run_done(True)
        QMessageBox.information(
            self,
            "เริ่มต้นใช้งาน FaceLens",
            "คำแนะนำการใช้งาน:\n\n"
            "1. วางกล้องให้เห็นหน้าลูกค้าชัด แสงไม่ย้อนมากเกินไป\n"
            "2. เริ่มจากโหมดความเร็ว: สมดุล และความมั่นใจ: ปลอดภัยสูง\n"
            "3. หากกล้องไม่ขึ้น ให้เปลี่ยนหมายเลขในช่อง 'กล้อง'\n"
            "4. สำรองฐานข้อมูลเป็นประจำ เพื่อป้องกันข้อมูลลูกค้าหาย",
        )

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

    def open_health_check_dialog(self) -> None:
        camera_index = int(self.camera_combo.currentData() or 0)
        dialog = HealthCheckDialog(self.db, camera_index=camera_index, parent=self)
        dialog.exec()

    def rebuild_faiss_index(self) -> None:
        db_data = self.db.get_all_data_for_faiss()
        print(f"Rebuilding FAISS from {len(db_data)} active face embeddings.")
        summary = self.db.get_database_summary()
        customer_count = summary.get("active_customers", 0)
        scale_hint = ""
        if customer_count >= STANDALONE_TARGET_CUSTOMERS:
            scale_hint = " | ถึงระดับเป้าหมายร้านเดี่ยวแล้ว ควรดูแล backup/maintenance สม่ำเสมอ"
        self.set_status(f"สถานะ: พร้อมใช้งานฐานข้อมูลใบหน้า {len(db_data)} รายการ จากลูกค้า {customer_count} คน{scale_hint}")
        self.rebuild_index_signal.emit(db_data)

    @Slot()
    def on_customer_saved(self) -> None:
        self.rebuild_faiss_index()

    @Slot(list)
    def log_recognition_events(self, results: list) -> None:
        """Persist throttled recognition events for audit/debugging."""
        if self._closing:
            return
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
        self._closing = True
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
        self.set_status("สถานะ: เกิดข้อผิดพลาดจาก AI model กรุณาดู logs/facelens_crash.log")
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
        elif name == "Switching Camera":
            text, color, bg_color = "กำลังสลับกล้อง...", "#2980B9", "#EBF5FB"
            status = "สถานะ: กำลังเปิดกล้องที่เลือก กรุณารอสักครู่"
        elif name != "Unknown":
            text, color, bg_color = f"สวัสดีคุณ {name}", "#2ECC71", "#E8F8F5"
            status = "สถานะ: พบลูกค้าที่บันทึกไว้แล้ว"
        else:
            text, color, bg_color = "ยังไม่พบข้อมูลลูกค้า", "#E67E22", "#FEF5E7"
            status = "สถานะ: กำลังตรวจสอบใบหน้าในกล้อง"

        self.name_label.setStyleSheet(
            f"background-color: {bg_color}; color: {color}; font-size: 20px; "
            "font-weight: 800; padding: 10px 8px; border-radius: 8px;"
        )
        self.name_label.setText(text)
        self.set_status(status)

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.statusBar().showMessage(message.replace("สถานะ: ", ""))

    @Slot()
    def toggle_controls_panel(self) -> None:
        self.apply_controls_collapsed(self.controls_toggle_button.isChecked())

    def apply_controls_collapsed(self, collapsed: bool) -> None:
        self.controls_panel.setVisible(not collapsed)
        self.controls_toggle_button.setText("แสดงส่วนควบคุม ▼" if collapsed else "ซ่อนส่วนควบคุม ▲")
        self.controls_toggle_button.setToolTip(
            "กดเพื่อแสดงสถานะและปุ่มจัดการระบบ" if collapsed else "กดเพื่อซ่อนสถานะและปุ่มจัดการ เพื่อเพิ่มพื้นที่กล้อง"
        )
        self.settings.set_controls_collapsed(collapsed)

    def backup_database(self) -> None:
        default_name = f"facelens_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        default_path = BACKUP_DIR / default_name
        file_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "สำรองฐานข้อมูล FaceLens",
            str(default_path),
            "SQLite Database (*.db);;All Files (*)",
        )
        if not file_path:
            return

        try:
            backup_path = self.db.backup_to(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "สำรองฐานข้อมูลไม่สำเร็จ", f"ไม่สามารถสำรองฐานข้อมูลได้:\n{exc}")
            return

        QMessageBox.information(
            self,
            "สำรองฐานข้อมูลสำเร็จ",
            f"บันทึกไฟล์สำรองเรียบร้อยแล้ว:\n{backup_path}",
        )
        self.set_status("สถานะ: สำรองฐานข้อมูลเรียบร้อยแล้ว")

    def restore_database(self) -> None:
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "เลือกไฟล์สำรอง FaceLens เพื่อกู้คืน",
            str(BACKUP_DIR),
            "SQLite Database (*.db);;All Files (*)",
        )
        if not file_path:
            return

        reply = QMessageBox.warning(
            self,
            "ยืนยันการกู้คืนฐานข้อมูล",
            "การกู้คืนจะเขียนทับฐานข้อมูลปัจจุบันด้วยไฟล์สำรองที่เลือก\n\n"
            "แนะนำให้สำรองฐานข้อมูลปัจจุบันก่อนเสมอ ต้องการดำเนินการต่อหรือไม่?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            restored_path = self.db.restore_from_backup(file_path)
            self.rebuild_faiss_index()
        except Exception as exc:
            QMessageBox.critical(self, "กู้คืนฐานข้อมูลไม่สำเร็จ", f"ไม่สามารถกู้คืนฐานข้อมูลได้:\n{exc}")
            return

        QMessageBox.information(
            self,
            "กู้คืนฐานข้อมูลสำเร็จ",
            f"กู้คืนข้อมูลจากไฟล์นี้เรียบร้อยแล้ว:\n{restored_path}\n\nระบบได้สร้างดัชนีใบหน้าใหม่แล้ว",
        )
        self.set_status("สถานะ: กู้คืนฐานข้อมูลและสร้างดัชนีใบหน้าใหม่เรียบร้อยแล้ว")


def run_cli_health_check() -> int:
    """Run a non-GUI health check for source and frozen support diagnostics."""
    from core.health_check import run_health_checks

    db = Database()
    report = run_health_checks(db, include_camera="--camera" in sys.argv)
    print(report.summary)
    print()
    for row in report.items:
        symbol = "✅" if row.status == "ok" else "⚠️" if row.status == "warning" else "❌"
        print(f"{symbol} {row.name}: {row.message}")
        if row.detail:
            print(f"   {row.detail}")
    return 1 if report.has_error else 0


def main() -> int:
    install_exception_logger()

    if "--version" in sys.argv:
        print("FaceLens 0.14")
        return 0

    if "--health-check" in sys.argv:
        return run_cli_health_check()

    app = QApplication(sys.argv)
    app.setWindowIcon(build_app_icon())
    app.setStyleSheet(STYLESHEET)
    app.setFont(QFont("Segoe UI", 9))

    splash = build_splash_screen()
    if splash is not None:
        splash.show()

    window = MainWindow()
    window.show()

    # Important for PyInstaller/Windows: QSplashScreen.finish(widget) can wait
    # for the target widget to become visible. Calling finish() before
    # window.show() may leave the app stuck on the logo screen even though
    # the main window was created successfully. Close it shortly after the
    # main window is shown so the splash never blocks startup.
    if splash is not None:
        QTimer.singleShot(250, lambda: splash.finish(window))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
