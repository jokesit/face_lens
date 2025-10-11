# file: add_customer_dialog.py (Final, UI-Only Version)

import cv2
import numpy as np
import json
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QImage, QPixmap

class AddCustomerDialog(QDialog):
    # Signal สำหรับส่ง "คำร้อง" ขอให้ประมวลผลภาพทั้งเฟรม
    request_snapshot_processing = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Customer")
        self.setMinimumSize(400, 500)
        
        self.db_path = 'data/customer_data.json'
        self.current_frame = None
        self.is_processing = False
        self.captured_embeddings = []

        # --- UI & Layout ---
        self.name_label = QLabel("Customer Name:")
        self.name_input = QLineEdit()
        self.camera_label = QLabel("Align face in the green box")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setStyleSheet("background-color: black; border: 1px solid #555;")
        self.camera_label.setFixedSize(320, 240)
        self.snapshot_button = QPushButton("Take Snapshot (0/5)")
        self.save_button = QPushButton("Save Customer")
        layout = QVBoxLayout()
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.camera_label)
        layout.addWidget(self.snapshot_button)
        layout.addWidget(self.save_button)
        self.setLayout(layout)

        self.snapshot_button.clicked.connect(self.take_snapshot)
        self.save_button.clicked.connect(self.save_customer)
        self.save_button.setEnabled(False)

    @Slot(np.ndarray)
    def update_frame(self, frame):
        self.current_frame = frame
        frame_to_display = self.current_frame.copy()
        h, w, _ = frame_to_display.shape
        cx, cy = w // 2, h // 2
        rect_w, rect_h = 280, 340
        cv2.rectangle(frame_to_display, (cx - rect_w//2, cy - rect_h//2), (cx + rect_w//2, cy + rect_h//2), (0, 255, 0), 2)
        qt_img = self.convert_cv_qt(frame_to_display)
        self.camera_label.setPixmap(qt_img)

    def take_snapshot(self):
        if self.is_processing or len(self.captured_embeddings) >= 5 or self.current_frame is None: return
        
        self.is_processing = True
        self.snapshot_button.setEnabled(False)
        self.snapshot_button.setText("Processing...")
        # ส่ง "คำร้อง" พร้อมกับภาพทั้งเฟรมออกไปให้ศูนย์บัญชาการ
        self.request_snapshot_processing.emit(self.current_frame)

    @Slot(object)
    def on_snapshot_processed(self, embedding):
        """รับผลลัพธ์สุดท้าย (Embedding) กลับมาจากศูนย์บัญชาการ"""
        if embedding is not None:
            self.captured_embeddings.append(embedding)
            count = len(self.captured_embeddings)
            if count >= 3: self.save_button.setEnabled(True)
        else:
            QMessageBox.warning(self, "Warning", "Could not process face. Please ensure one clear face is in the box.")

        self.is_processing = False
        self.snapshot_button.setEnabled(True)
        self.snapshot_button.setText(f"Take Snapshot ({len(self.captured_embeddings)}/5)")

    def save_customer(self):
        name = self.name_input.text().strip()
        if not name: return
        try:
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f: data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError): data = {"customers": []}
            
            customer_found = False
            for c in data['customers']:
                if c['name'] == name: c['embeddings'].extend([e.tolist() for e in self.captured_embeddings]); customer_found = True; break
            if not customer_found: data['customers'].append({"name": name, "embeddings": [e.tolist() for e in self.captured_embeddings]})
            
            with open(self.db_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
            
            QMessageBox.information(self, "Success", f"Customer '{name}' has been saved/updated.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save data: {e}"); self.reject()

    def convert_cv_qt(self, cv_img):
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        p = QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888))
        return p.scaled(320, 240, Qt.KeepAspectRatio)