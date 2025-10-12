# file: add_customer_dialog.py (The Final, Correct, and Smart Version)

import cv2
import numpy as np
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QHBoxLayout, QInputDialog
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QImage, QPixmap

from core.database import Database
# ไม่ต้อง import FaceRecognizer ที่นี่อีกต่อไป

DIALOG_STYLESHEET = """
QDialog {
    background-color: #FFFFFF;
}
QLabel {
    font-size: 16px;
    font-weight: bold;
    color: #5D6D7E;
}
QLineEdit {
    font-size: 16px;
    color: #0d0d0d;
    padding: 8px;
    border: 1px solid #BDC3C7;
    border-radius: 5px;
    background-color: #d7f5db;
}
QPushButton#CaptureButton {
    background-color: #2ECC71;
    color: white;
    font-size: 16px;
    font-weight: bold;
    padding: 12px;
    border-radius: 8px;
    border: none;
}
QPushButton#CaptureButton:hover { background-color: #28B463; }
QPushButton#CaptureButton:pressed { background-color: #239B56; }
QPushButton#CaptureButton:disabled { background-color: #B2BABB; }

QPushButton#SaveButton {
    background-color: #3498DB;
    color: white;
    font-size: 16px;
    font-weight: bold;
    padding: 12px;
    border-radius: 8px;
    border: none;
}
QPushButton#SaveButton:hover { background-color: #2980B9; }
QPushButton#SaveButton:pressed { background-color: #1F618D; }
QPushButton#SaveButton:disabled { background-color: #D5D8DC; }
"""
# 555

class AddCustomerDialog(QDialog):
    capture_mode_toggled = Signal(bool)
    request_verification_job = Signal(list, str)
    customer_saved_signal = Signal()
    new_embedding_captured = Signal(object)

    VERIFICATION_THRESHOLD = 0.75

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Update Customer")
        self.setMinimumSize(400, 550)
        self.setStyleSheet(DIALOG_STYLESHEET)
        
        self.db = Database()
        self.is_capture_mode = False
        self.MAX_SNAPSHOTS = 5
        self.captured_embeddings = []
        self.current_frame = None

        self.name_label = QLabel("Customer's Full Name:")
        self.name_input = QLineEdit(); self.name_input.setPlaceholderText("e.g., Somchai Jaidee")
        self.camera_label = QLabel("Enter name and press 'Start Capture'"); self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setStyleSheet("background-color: #ECF0F1; border-radius: 8px; font-size: 14px;"); self.camera_label.setFixedSize(320, 240)
        self.capture_button = QPushButton(f"Start Automatic Capture (0/{self.MAX_SNAPSHOTS})"); self.capture_button.setObjectName("CaptureButton")
        self.save_button = QPushButton("Save Customer"); self.save_button.setObjectName("SaveButton")
        button_layout = QHBoxLayout(); button_layout.addWidget(self.capture_button); button_layout.addWidget(self.save_button)
        layout = QVBoxLayout(); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)
        layout.addWidget(self.name_label); layout.addWidget(self.name_input); layout.addWidget(self.camera_label); layout.addLayout(button_layout)
        self.setLayout(layout)
        
        self.capture_button.clicked.connect(self.toggle_capture_mode)
        self.save_button.clicked.connect(self.save_customer_handler)
        self.save_button.setEnabled(False)

    @Slot(np.ndarray)
    def update_frame(self, frame):
        self.current_frame = frame
        frame_to_display = self.current_frame.copy()
        h, w, _ = frame_to_display.shape; cx, cy = w // 2, h // 2
        rect_w, rect_h = 280, 340
        cv2.rectangle(frame_to_display, (cx - rect_w//2, cy - rect_h//2), (cx + rect_w//2, cy + rect_h//2), (255, 255, 255), 2)
        qt_img = self.convert_cv_qt(frame_to_display)
        self.camera_label.setPixmap(qt_img)

    def toggle_capture_mode(self):
        name = self.name_input.text().strip()
        if not name and not self.is_capture_mode:
            QMessageBox.warning(self, "Warning", "Please enter a customer name first."); return
        self.is_capture_mode = not self.is_capture_mode
        self.capture_mode_toggled.emit(self.is_capture_mode)
        if self.is_capture_mode:
            self.name_input.setEnabled(False); self.capture_button.setText("Stop Capture")
            self.camera_label.setText("Please look at the camera and move your head slightly.")
        else:
            self.name_input.setEnabled(True); self.capture_button.setText(f"Start Automatic Capture (0/{self.MAX_SNAPSHOTS})")

    @Slot(int, int)
    def update_capture_progress(self, count, max_count):
        if self.is_capture_mode:
            if count >= max_count:
                self.is_capture_mode = False; self.camera_label.setText("Capture complete! Thank you.")
                self.capture_button.setText("Finished"); self.capture_button.setEnabled(False); self.save_button.setEnabled(True)
            else:
                self.camera_label.setText(f"{count}/{max_count} captured. Please move your head slightly.")
    
    @Slot(object)
    def add_captured_embedding(self, embedding):
        if embedding is not None: self.captured_embeddings.append(embedding)

    def save_customer_handler(self):
        name_to_save = self.name_input.text().strip()
        if not name_to_save:
            QMessageBox.warning(self, "Warning", "Please enter a customer name."); return
        if not self.captured_embeddings:
            QMessageBox.warning(self, "Warning", "No snapshots to save."); return
            
        self.save_button.setEnabled(False); self.save_button.setText("Verifying...")
        self.request_verification_job.emit(self.captured_embeddings, name_to_save)

    @Slot(str, float)
    def on_verification_finished(self, name, distance):
        self.save_button.setEnabled(True); self.save_button.setText("Save Customer")
        if distance < 0: # ใช้ค่าติดลบเป็นตัวบ่งชี้ "ลูกค้าใหม่"
            self.perform_save(name, self.captured_embeddings)
        elif distance < self.VERIFICATION_THRESHOLD:
            reply = QMessageBox.question(self, "Confirm Update", f"A customer named '{name}' already exists, and the face seems to match.\n\nDo you want to add the new snapshots to their profile?", QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes: self.perform_save(name, self.captured_embeddings)
        else:
            new_name, ok = QInputDialog.getText(self, "Duplicate Name Detected", f"A customer named '{name}' already exists, but the face does not match.\n\nPlease provide a more specific name (e.g., '{name} (Hat Yai)'):")
            if ok and new_name.strip(): self.perform_save(new_name.strip(), self.captured_embeddings)

    def perform_save(self, name, embeddings):
        try:
            self.db.add_or_update_customer(name, embeddings)
            QMessageBox.information(self, "Success", f"Customer '{name}' has been saved/updated.")
            self.customer_saved_signal.emit(); self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save data: {e}"); self.reject()
            
    def convert_cv_qt(self, cv_img):
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB); h, w, ch = rgb.shape
        p = QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888))
        return p.scaled(320, 240, Qt.KeepAspectRatio)
