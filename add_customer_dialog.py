# file: add_customer_dialog.py

"""Dialog for enrolling or updating a customer face profile."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.config import MAX_SNAPSHOTS, VERIFICATION_THRESHOLD
from core.database import Database


DIALOG_STYLESHEET = """
QDialog { background-color: #FFFFFF; }
QLabel { font-size: 16px; font-weight: bold; color: #5D6D7E; }
QLabel#HintLabel { font-size: 14px; font-weight: normal; color: #1F618D; background-color: #EBF5FB; padding: 8px; border-radius: 6px; }
QLineEdit { font-size: 16px; color: #0d0d0d; padding: 8px; border: 1px solid #BDC3C7; border-radius: 5px; background-color: #F8F9F9; }
QPushButton#CaptureButton { background-color: #2ECC71; color: white; font-size: 16px; font-weight: bold; padding: 12px; border-radius: 8px; border: none; }
QPushButton#CaptureButton:hover { background-color: #28B463; }
QPushButton#CaptureButton:pressed { background-color: #239B56; }
QPushButton#CaptureButton:disabled { background-color: #B2BABB; }
QPushButton#SaveButton { background-color: #3498DB; color: white; font-size: 16px; font-weight: bold; padding: 12px; border-radius: 8px; border: none; }
QPushButton#SaveButton:hover { background-color: #2980B9; }
QPushButton#SaveButton:pressed { background-color: #1F618D; }
QPushButton#SaveButton:disabled { background-color: #D5D8DC; }
"""


QUALITY_HINTS_TH = {
    "Only one face at a time, please.": "กรุณาให้มีใบหน้าเพียง 1 คนในกรอบภาพ",
    "Move your head slightly.": "ขยับศีรษะเล็กน้อย เพื่อให้ระบบเก็บหลายมุมของใบหน้า",
    "Good snapshot captured.": "บันทึกภาพใบหน้าที่ชัดเจนแล้ว",
    "Capture stopped.": "หยุดการบันทึกภาพแล้ว",
    "Ready to save this customer profile.": "พร้อมบันทึกข้อมูลลูกค้าคนนี้แล้ว",
}

QUALITY_REASON_TH = {
    "empty": "ไม่พบภาพใบหน้า",
    "invalid-size": "ขนาดภาพไม่ถูกต้อง",
    "face-too-small": "ใบหน้าเล็กเกินไป กรุณาเข้าใกล้กล้องเล็กน้อย",
    "blurry": "ภาพเบลอ กรุณาอยู่นิ่งสักครู่",
    "too-dark": "แสงน้อยเกินไป กรุณาเพิ่มแสงบริเวณใบหน้า",
    "too-bright": "แสงจ้าเกินไป กรุณาหลีกเลี่ยงแสงสะท้อน",
}


class AddCustomerDialog(QDialog):
    capture_mode_toggled = Signal(bool)
    request_verification_job = Signal(list, str)
    customer_saved_signal = Signal()

    VERIFICATION_THRESHOLD = VERIFICATION_THRESHOLD

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("เพิ่ม / อัปเดตข้อมูลลูกค้า")
        self.setMinimumSize(430, 590)
        self.setStyleSheet(DIALOG_STYLESHEET)

        self.db = Database()
        self.is_capture_mode = False
        self.MAX_SNAPSHOTS = MAX_SNAPSHOTS
        self.captured_embeddings: list[np.ndarray] = []
        self.current_frame = None

        self.name_label = QLabel("ชื่อลูกค้า:")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("เช่น คุณสมชาย ใจดี")

        self.camera_label = QLabel("กรอกชื่อ แล้วกด 'เริ่มบันทึกใบหน้า'")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setStyleSheet("background-color: #ECF0F1; border-radius: 8px; font-size: 14px;")
        self.camera_label.setFixedSize(320, 240)

        self.hint_label = QLabel("คำแนะนำ: ให้ลูกค้าหันหน้าเข้ากล้อง แสงพอดี และอยู่นิ่งชั่วครู่")
        self.hint_label.setObjectName("HintLabel")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setWordWrap(True)

        self.capture_button = QPushButton(f"เริ่มบันทึกใบหน้า (0/{self.MAX_SNAPSHOTS})")
        self.capture_button.setObjectName("CaptureButton")
        self.save_button = QPushButton("บันทึกข้อมูล")
        self.save_button.setObjectName("SaveButton")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.capture_button)
        button_layout.addWidget(self.save_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(15)
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.camera_label, alignment=Qt.AlignCenter)
        layout.addWidget(self.hint_label)
        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.capture_button.clicked.connect(self.toggle_capture_mode)
        self.save_button.clicked.connect(self.save_customer_handler)
        self.save_button.setEnabled(False)

    @Slot(np.ndarray)
    def update_frame(self, frame):
        self.current_frame = frame
        frame_to_display = self.current_frame.copy()
        h, w, _ = frame_to_display.shape
        cx, cy = w // 2, h // 2
        rect_w, rect_h = 280, 340
        cv2.rectangle(
            frame_to_display,
            (cx - rect_w // 2, cy - rect_h // 2),
            (cx + rect_w // 2, cy + rect_h // 2),
            (255, 255, 255),
            2,
        )
        qt_img = self.convert_cv_qt(frame_to_display)
        self.camera_label.setPixmap(qt_img)

    def toggle_capture_mode(self):
        name = self.name_input.text().strip()
        if not name and not self.is_capture_mode:
            QMessageBox.warning(self, "กรุณากรอกชื่อ", "กรุณากรอกชื่อลูกค้าก่อนเริ่มบันทึกใบหน้า")
            return

        self.is_capture_mode = not self.is_capture_mode
        self.capture_mode_toggled.emit(self.is_capture_mode)

        if self.is_capture_mode:
            self.captured_embeddings = []
            self.name_input.setEnabled(False)
            self.capture_button.setText("หยุดบันทึก")
            self.camera_label.setText("กรุณามองกล้อง และขยับศีรษะเล็กน้อย")
            self.hint_label.setText("ระบบจะเลือกบันทึกเฉพาะภาพที่ชัด มีใบหน้าเดียว และแสงเหมาะสม")
            self.save_button.setEnabled(False)
        else:
            self.name_input.setEnabled(True)
            self.capture_button.setText(f"เริ่มบันทึกใบหน้า ({len(self.captured_embeddings)}/{self.MAX_SNAPSHOTS})")
            self.hint_label.setText("หยุดการบันทึกภาพแล้ว")

    @Slot(int, int)
    def update_capture_progress(self, count, max_count):
        if self.is_capture_mode:
            if count >= max_count:
                self.is_capture_mode = False
                self.camera_label.setText("บันทึกภาพใบหน้าครบแล้ว")
                self.hint_label.setText("พร้อมบันทึกข้อมูลลูกค้าคนนี้แล้ว")
                self.capture_button.setText("บันทึกครบแล้ว")
                self.capture_button.setEnabled(False)
                self.save_button.setEnabled(True)
            else:
                self.camera_label.setText(f"บันทึกแล้ว {count}/{max_count} ภาพ กรุณาขยับศีรษะเล็กน้อย")
                self.hint_label.setText("บันทึกภาพใบหน้าที่ชัดเจนแล้ว")

    @Slot(str)
    def update_capture_hint(self, message):
        if self.is_capture_mode and message:
            self.hint_label.setText(self._translate_hint(message))

    @Slot(object)
    def add_captured_embedding(self, embedding):
        if embedding is not None:
            self.captured_embeddings.append(embedding)

    def save_customer_handler(self):
        name_to_save = self.name_input.text().strip()
        if not name_to_save:
            QMessageBox.warning(self, "กรุณากรอกชื่อ", "กรุณากรอกชื่อลูกค้า")
            return
        if not self.captured_embeddings:
            QMessageBox.warning(self, "ยังไม่มีภาพใบหน้า", "ยังไม่มีภาพใบหน้าที่ผ่านคุณภาพสำหรับบันทึก")
            return

        self.save_button.setEnabled(False)
        self.save_button.setText("กำลังตรวจสอบ...")
        self.request_verification_job.emit(self.captured_embeddings, name_to_save)

    @Slot(str, float)
    def on_verification_finished(self, name, distance):
        self.save_button.setEnabled(True)
        self.save_button.setText("บันทึกข้อมูล")
        if distance is None or distance < 0:
            self.perform_save(name, self.captured_embeddings)
        elif distance < self.VERIFICATION_THRESHOLD:
            reply = QMessageBox.question(
                self,
                "ยืนยันการอัปเดตข้อมูล",
                f"พบชื่อลูกค้า '{name}' อยู่แล้ว และใบหน้าดูตรงกับข้อมูลเดิม\n\nต้องการเพิ่มภาพชุดใหม่นี้เข้าโปรไฟล์เดิมหรือไม่?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.perform_save(name, self.captured_embeddings)
        else:
            new_name, ok = QInputDialog.getText(
                self,
                "พบชื่อซ้ำ แต่ใบหน้าไม่ตรงกัน",
                f"มีชื่อลูกค้า '{name}' อยู่แล้ว แต่ใบหน้าดูไม่ตรงกับข้อมูลเดิม\n\nกรุณาใส่ชื่อให้เฉพาะเจาะจงขึ้น เช่น '{name} สาขาหาดใหญ่':",
            )
            if ok and new_name.strip():
                self.perform_save(new_name.strip(), self.captured_embeddings)

    def perform_save(self, name, embeddings):
        try:
            self.db.add_or_update_customer(name, embeddings)
            QMessageBox.information(self, "บันทึกสำเร็จ", f"บันทึก/อัปเดตข้อมูลของ '{name}' เรียบร้อยแล้ว")
            self.customer_saved_signal.emit()
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"ไม่สามารถบันทึกข้อมูลได้:\n{exc}")
            self.reject()

    def closeEvent(self, event) -> None:
        self.db.close()
        event.accept()

    @staticmethod
    def _translate_hint(message: str) -> str:
        if message in QUALITY_HINTS_TH:
            return QUALITY_HINTS_TH[message]
        if message.startswith("Improve face image:"):
            reasons = message.split(":", 1)[1].strip().split(",")
            translated = [QUALITY_REASON_TH.get(reason.strip(), reason.strip()) for reason in reasons if reason.strip()]
            return "ปรับภาพก่อนบันทึก: " + " / ".join(translated)
        return message

    def convert_cv_qt(self, cv_img):
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image)
        return pixmap.scaled(320, 240, Qt.KeepAspectRatio)
