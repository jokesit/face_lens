# file: add_customer_dialog.py (Beautiful UI Version)

import cv2
import numpy as np
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QHBoxLayout
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QImage, QPixmap

from core.database import Database
from core.face_recognizer import FaceRecognizer

# --- สไตล์ชีตสำหรับหน้าต่าง Pop-up โดยเฉพาะ ---
DIALOG_STYLESHEET = """
QDialog {
    background-color: #FFFFFF;
}
QLabel {
    font-size: 14px;
    color: #5D6D7E;
}
QLineEdit {
    font-size: 16px;
    padding: 8px;
    border: 1px solid #BDC3C7;
    border-radius: 5px;
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

class AddCustomerDialog(QDialog):
    request_snapshot_processing = Signal(object)
    customer_saved_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Update Customer")
        self.setMinimumSize(400, 550)
        self.setStyleSheet(DIALOG_STYLESHEET)

        self.recognizer = FaceRecognizer()
        self.db = Database()
        self.current_frame = None
        self.is_processing = False
        self.captured_embeddings = []
        self.MAX_SNAPSHOTS = 5

        # --- UI & Layout ที่ปรับปรุงใหม่ ---
        self.name_label = QLabel("Customer's Full Name:")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Somchai Jaidee")

        self.camera_label = QLabel("Align face in the green box")
        self.camera_label.setObjectName("CameraLabel")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setStyleSheet("background-color: #ECF0F1; border-radius: 8px;")
        self.camera_label.setFixedSize(320, 240)
        
        self.capture_button = QPushButton(f"Take Snapshot (0/{self.MAX_SNAPSHOTS})")
        self.capture_button.setObjectName("CaptureButton")
        self.save_button = QPushButton("Save Customer")
        self.save_button.setObjectName("SaveButton")
        
        # จัดปุ่มให้อยู่แนวนอน
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.capture_button)
        button_layout.addWidget(self.save_button)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.camera_label)
        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.capture_button.clicked.connect(self.take_snapshot)
        self.save_button.clicked.connect(self.save_customer)
        self.save_button.setEnabled(False)

    @Slot(np.ndarray)
    def update_frame(self, frame):
        self.current_frame = frame
        frame_to_display = self.current_frame.copy()
        h, w, _ = frame_to_display.shape
        cx, cy = w // 2, h // 2
        rect_w, rect_h = 280, 340
        # วาดกรอบไกด์ไลน์สีขาวให้ดูสบายตา
        cv2.rectangle(frame_to_display, (cx - rect_w//2, cy - rect_h//2), (cx + rect_w//2, cy + rect_h//2), (255, 255, 255), 2)
        qt_img = self.convert_cv_qt(frame_to_display)
        self.camera_label.setPixmap(qt_img)

    def take_snapshot(self):
        if self.is_processing or len(self.captured_embeddings) >= self.MAX_SNAPSHOTS or self.current_frame is None: return
        faces, _ = self.recognizer.detect_faces(self.current_frame)
        if len(faces) == 1:
            self.is_processing = True
            self.capture_button.setEnabled(False)
            self.capture_button.setText("Processing...")
            self.request_snapshot_processing.emit(self.current_frame)
        else:
            QMessageBox.warning(self, "Warning", "No face or multiple faces detected.")

    @Slot(object)
    def on_snapshot_processed(self, embedding):
        if embedding is not None:
            self.captured_embeddings.append(embedding)
            count = len(self.captured_embeddings)
            if count >= 3: self.save_button.setEnabled(True)
        else:
            QMessageBox.warning(self, "Warning", "Could not process face. Please ensure one clear face is in the box.")
        self.is_processing = False
        self.capture_button.setEnabled(True)
        self.capture_button.setText(f"Take Snapshot ({len(self.captured_embeddings)}/{self.MAX_SNAPSHOTS})")

    def save_customer(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Please enter a customer name.")
            return
        try:
            self.db.add_or_update_customer(name, self.captured_embeddings)
            QMessageBox.information(self, "Success", f"Customer '{name}' has been saved/updated.")
            self.customer_saved_signal.emit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save data: {e}"); self.reject()

    def convert_cv_qt(self, cv_img):
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB) # <<< แก้ไขบรรทัดนี้
        h, w, ch = rgb.shape
        p = QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888))
        return p.scaled(320, 240, Qt.KeepAspectRatio)