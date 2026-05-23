# file: add_customer_dialog.py

"""Dialog for enrolling or updating a customer face profile.

Batch 11 adds duplicate-customer prevention. This is important for pharmacy
standalone deployments with 1,000-5,000 customers, where accidentally saving the
same face under two names hurts recognition quality over time.
"""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.config import (
    ENROLLMENT_DUPLICATE_STRICT_DISTANCE,
    ENROLLMENT_DUPLICATE_WARNING_DISTANCE,
    MAX_SNAPSHOTS,
    RECOMMENDED_MAX_EMBEDDINGS_PER_CUSTOMER,
    VERIFICATION_THRESHOLD,
)
from core.database import Database


DIALOG_STYLESHEET = """
QDialog { background-color: #FFFFFF; }
QLabel { font-size: 14px; font-weight: bold; color: #5D6D7E; }
QLabel#HintLabel { font-size: 13px; font-weight: normal; color: #1F618D; background-color: #EBF5FB; padding: 7px; border-radius: 6px; }
QLineEdit { font-size: 14px; color: #0d0d0d; padding: 7px; border: 1px solid #BDC3C7; border-radius: 5px; background-color: #F8F9F9; }
QPushButton#CaptureButton { background-color: #2ECC71; color: white; font-size: 14px; font-weight: bold; padding: 9px; border-radius: 8px; border: none; }
QPushButton#CaptureButton:hover { background-color: #28B463; }
QPushButton#CaptureButton:pressed { background-color: #239B56; }
QPushButton#CaptureButton:disabled { background-color: #B2BABB; }
QPushButton#SaveButton { background-color: #3498DB; color: white; font-size: 14px; font-weight: bold; padding: 9px; border-radius: 8px; border: none; }
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
        self.setMinimumSize(430, 560)
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
        self.camera_label.setStyleSheet("background-color: #ECF0F1; border-radius: 8px; font-size: 13px;")
        self.camera_label.setFixedSize(320, 230)

        self.hint_label = QLabel(
            "คำแนะนำ: ให้ลูกค้าหันหน้าเข้ากล้อง แสงพอดี และอยู่นิ่งชั่วครู่\n"
            "ระบบจะตรวจว่าข้อมูลนี้อาจซ้ำกับลูกค้าเดิมหรือไม่ก่อนบันทึก"
        )
        self.hint_label.setObjectName("HintLabel")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setWordWrap(True)

        self.capture_button = QPushButton(f"เริ่มบันทึกใบหน้า (0/{self.MAX_SNAPSHOTS})")
        self.capture_button.setObjectName("CaptureButton")
        self.save_button = QPushButton("ตรวจสอบและบันทึก")
        self.save_button.setObjectName("SaveButton")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.capture_button)
        button_layout.addWidget(self.save_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(11)
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
        rect_w, rect_h = 280, 330
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
            self.capture_button.setEnabled(True)
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
                self.hint_label.setText(
                    "พร้อมตรวจสอบข้อมูลซ้ำและบันทึก ระบบจะเก็บใบหน้าที่ใช้งานต่อคนไม่เกิน "
                    f"{RECOMMENDED_MAX_EMBEDDINGS_PER_CUSTOMER} รายการ เพื่อให้โปรแกรมเร็วและแม่น"
                )
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
        self.save_button.setText("กำลังตรวจสอบข้อมูลซ้ำ...")
        self.request_verification_job.emit(self.captured_embeddings, name_to_save)

    @Slot(object)
    def on_verification_finished(self, payload):
        self.save_button.setEnabled(True)
        self.save_button.setText("ตรวจสอบและบันทึก")

        # Backward-compatible handling if an older worker emits the old tuple.
        if isinstance(payload, tuple) and len(payload) == 2:
            name, distance = payload
            payload = {"requested_name": name, "same_name_distance": distance, "nearest_matches": [], "error": None}

        if not isinstance(payload, dict):
            QMessageBox.warning(self, "ตรวจสอบไม่สำเร็จ", "ไม่สามารถอ่านผลการตรวจสอบข้อมูลซ้ำได้")
            return

        requested_name = str(payload.get("requested_name") or self.name_input.text().strip()).strip()
        error = payload.get("error")
        if error:
            reply = QMessageBox.question(
                self,
                "ตรวจสอบข้อมูลซ้ำไม่สำเร็จ",
                f"ระบบตรวจสอบข้อมูลซ้ำไม่สำเร็จ:\n{error}\n\nต้องการบันทึกต่อหรือไม่?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.perform_save(requested_name, self.captured_embeddings)
            return

        same_name_distance = payload.get("same_name_distance")
        nearest_matches = list(payload.get("nearest_matches") or [])

        if isinstance(same_name_distance, (float, int)) and same_name_distance >= 0:
            if same_name_distance < self.VERIFICATION_THRESHOLD:
                reply = QMessageBox.question(
                    self,
                    "ยืนยันการอัปเดตข้อมูล",
                    f"พบชื่อลูกค้า '{requested_name}' อยู่แล้ว และใบหน้าดูตรงกับข้อมูลเดิม\n"
                    f"ค่าความใกล้เคียง: {same_name_distance:.3f}\n\n"
                    "ต้องการเพิ่มภาพชุดใหม่นี้เข้าโปรไฟล์เดิมหรือไม่?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    self.perform_save(requested_name, self.captured_embeddings)
                return

            QMessageBox.warning(
                self,
                "ชื่อซ้ำแต่ใบหน้าไม่ตรงกัน",
                f"มีชื่อลูกค้า '{requested_name}' อยู่แล้ว แต่ใบหน้าชุดใหม่นี้ไม่ค่อยตรงกับข้อมูลเดิม\n"
                f"ค่าความใกล้เคียง: {same_name_distance:.3f}\n\n"
                "กรุณาใช้ชื่อให้เฉพาะเจาะจงขึ้น หรือกลับไปตรวจสอบว่ากำลังบันทึกคนถูกต้อง",
            )
            return

        warning_match = self._best_duplicate_warning(nearest_matches, requested_name)
        if warning_match:
            self._handle_possible_duplicate(requested_name, warning_match)
            return

        self.perform_save(requested_name, self.captured_embeddings)

    def _best_duplicate_warning(self, nearest_matches: list[dict], requested_name: str) -> dict | None:
        requested_lower = requested_name.casefold()
        for match in nearest_matches:
            match_name = str(match.get("name") or "")
            if match_name.casefold() == requested_lower:
                continue
            distance = match.get("distance")
            if isinstance(distance, (float, int)) and distance <= ENROLLMENT_DUPLICATE_WARNING_DISTANCE:
                return match
        return None

    def _handle_possible_duplicate(self, requested_name: str, match: dict) -> None:
        matched_name = str(match.get("name") or "ลูกค้าเดิม")
        distance = float(match.get("distance", 999.0))
        is_strict = distance <= ENROLLMENT_DUPLICATE_STRICT_DISTANCE

        message = (
            "ระบบพบว่าใบหน้าชุดนี้คล้ายกับลูกค้าที่มีอยู่แล้วมาก\n\n"
            f"ลูกค้าที่ใกล้เคียง: {matched_name}\n"
            f"ชื่อที่กำลังจะบันทึก: {requested_name}\n"
            f"ค่าความใกล้เคียง: {distance:.3f}\n\n"
        )
        if is_strict:
            message += "คำแนะนำ: มีโอกาสสูงว่าเป็นคนเดียวกัน ควรอัปเดตข้อมูลลูกค้าเดิมแทนการสร้างชื่อใหม่"
        else:
            message += "คำแนะนำ: กรุณาตรวจสอบกับลูกค้าหรือพนักงานก่อนบันทึก เพื่อป้องกันชื่อซ้ำในฐานข้อมูล"

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("อาจเป็นลูกค้าคนเดิม")
        box.setText(message)
        update_button = box.addButton(f"อัปเดต '{matched_name}'", QMessageBox.AcceptRole)
        save_new_button = box.addButton("บันทึกเป็นชื่อใหม่", QMessageBox.DestructiveRole)
        cancel_button = box.addButton("ยกเลิก", QMessageBox.RejectRole)
        box.setDefaultButton(update_button if is_strict else cancel_button)
        box.exec()

        clicked = box.clickedButton()
        if clicked == update_button:
            self.perform_save(matched_name, self.captured_embeddings)
        elif clicked == save_new_button:
            self.perform_save(requested_name, self.captured_embeddings)

    def perform_save(self, name, embeddings):
        try:
            self.db.add_or_update_customer(name, embeddings)
            QMessageBox.information(
                self,
                "บันทึกสำเร็จ",
                f"บันทึก/อัปเดตข้อมูลของ '{name}' เรียบร้อยแล้ว\n\n"
                f"ระบบจะเก็บใบหน้าที่ใช้งานล่าสุดไม่เกิน {RECOMMENDED_MAX_EMBEDDINGS_PER_CUSTOMER} รายการต่อคน เพื่อให้ค้นหาเร็วและฐานข้อมูลไม่โตเกินจำเป็น",
            )
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
        bytes_per_line = ch * w
        convert_to_Qt_format = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
        return QPixmap.fromImage(convert_to_Qt_format).scaled(320, 230, Qt.KeepAspectRatio)
