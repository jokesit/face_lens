# file: main.py (The Final, Smoothed & Stable Version)

import sys, cv2, numpy as np, json
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QPushButton
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from core.face_recognizer import FaceRecognizer
from add_customer_dialog import AddCustomerDialog

class VideoThread(QThread):
    change_pixmap_signal = Signal(np.ndarray)
    raw_frame_signal = Signal(np.ndarray) 
    update_name_signal = Signal(str)
    snapshot_result_signal = Signal(object) 

    def __init__(self):
        super().__init__()
        self.recognizer = FaceRecognizer()
        self.db_path = 'data/customer_data.json'
        self.known_faces = self.load_known_faces()
        self.RECOGNITION_THRESHOLD = 0.8
        self.is_running = True
        self.is_busy_processing_snapshot = False

        # --- ตัวแปรใหม่สำหรับทำให้การแสดงผลนุ่มนวล ---
        self.frame_counter = 0
        self.last_known_name = "Unknown"
        self.name_display_counter = 0 # ตัวนับเวลาที่จะแสดงชื่อค้างไว้
        self.RECOGNITION_INTERVAL = 20 # ทำการจดจำทุก 20 เฟรม
        self.NAME_DISPLAY_DURATION = 60 # แสดงชื่อค้างไว้ 60 เฟรม (~2-3 วินาที)
        # ---------------------------------------------

    @Slot()
    def reload_database(self): 
        print("Reloading database...")
        self.known_faces = self.load_known_faces()

    @Slot(object)
    def process_snapshot_request(self, frame):
        self.is_busy_processing_snapshot = True
        print("AI Thread: LOCKED for snapshot.")
        faces, _ = self.recognizer.detect_faces(frame)
        embedding = None
        if len(faces) == 1: embedding = self.recognizer.get_embedding(faces[0])
        self.snapshot_result_signal.emit(embedding)
        print("AI Thread: UNLOCKED from snapshot.")
        self.is_busy_processing_snapshot = False

    def load_known_faces(self):
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for c in data['customers']: c['embeddings'] = [np.array(e) for e in c['embeddings']]
                print(f"Loaded {len(data['customers'])} known customers.")
                return data['customers']
        except (FileNotFoundError, json.JSONDecodeError):
            with open(self.db_path, 'w', encoding='utf-8') as f: json.dump({"customers": []}, f)
            return []
        except Exception as e: print(f"Error loading DB: {e}"); return []

    def run(self):
        cap = cv2.VideoCapture(0)
        while self.is_running:
            ret, cv_img = cap.read()
            if not ret: continue
            
            self.raw_frame_signal.emit(cv_img)
            
            frame_to_display = cv_img.copy()
            faces, boxes = self.recognizer.detect_faces(frame_to_display)

            # --- ตรรกะการจดจำและแสดงผลเวอร์ชันใหม่ ---
            if not self.is_busy_processing_snapshot and self.frame_counter % self.RECOGNITION_INTERVAL == 0 and faces:
                embedding = self.recognizer.get_embedding(faces[0])
                if embedding is not None:
                    smallest_dist = float('inf')
                    best_name = "Unknown"
                    for c in self.known_faces:
                        for known_emb in c['embeddings']:
                            dist = np.linalg.norm(embedding - known_emb)
                            if dist < smallest_dist: smallest_dist, best_name = dist, c['name']
                    
                    if smallest_dist < self.RECOGNITION_THRESHOLD:
                        self.last_known_name = best_name
                        self.name_display_counter = self.NAME_DISPLAY_DURATION # เริ่มนับถอยหลัง
                    else:
                        self.last_known_name = "Unknown"
            
            # ลดตัวนับลงเรื่อยๆ
            if self.name_display_counter > 0:
                self.name_display_counter -= 1
            else:
                self.last_known_name = "Unknown" # เมื่อนับครบ ให้กลับเป็น Unknown
            
            # วาดกรอบและแสดงชื่อล่าสุดเสมอ
            if boxes:
                x, y, w, h = boxes[0]
                color = (0, 255, 0) if self.last_known_name != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame_to_display, (x, y), (x+w, y+h), color, 2)
                cv2.putText(frame_to_display, self.last_known_name, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
            
            self.change_pixmap_signal.emit(frame_to_display)
            self.update_name_signal.emit(self.last_known_name)
            self.frame_counter += 1
            # ---------------------------------------------

        cap.release()

    def stop(self): self.is_running = False; self.quit(); self.wait()

class MainWindow(QMainWindow):
    reload_db_signal = Signal()
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FaceLens"); self.setGeometry(100, 100, 800, 650)
        self.image_label = QLabel(self); self.image_label.setStyleSheet("background-color: black;"); self.image_label.setAlignment(Qt.AlignCenter)
        self.name_label = QLabel(self); self.name_label.setAlignment(Qt.AlignCenter)
        self.add_customer_button = QPushButton("Add/Update Customer", self); self.add_customer_button.setStyleSheet("font-size: 16px; padding: 10px;")
        self.add_customer_button.clicked.connect(self.open_add_customer_dialog)
        layout = QVBoxLayout(); layout.addWidget(self.image_label); layout.addWidget(self.name_label); layout.addWidget(self.add_customer_button)
        container = QWidget(); container.setLayout(layout); self.setCentralWidget(container)
        
        self.thread = VideoThread()
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.update_name_signal.connect(self.update_name)
        self.reload_db_signal.connect(self.thread.reload_database)
        self.thread.start()
        self.update_name("Searching...")

    def open_add_customer_dialog(self):
        dialog = AddCustomerDialog(parent=self)
        self.thread.raw_frame_signal.connect(dialog.update_frame)
        dialog.request_snapshot_processing.connect(self.thread.process_snapshot_request)
        self.thread.snapshot_result_signal.connect(dialog.on_snapshot_processed)
        if dialog.exec(): self.reload_db_signal.emit()
        self.thread.raw_frame_signal.disconnect(dialog.update_frame)
        dialog.request_snapshot_processing.disconnect(self.thread.process_snapshot_request)
        self.thread.snapshot_result_signal.disconnect(dialog.on_snapshot_processed)

    def closeEvent(self, event): self.thread.stop(); event.accept()
    @Slot(np.ndarray)
    def update_image(self, cv_img): self.image_label.setPixmap(self.convert_cv_qt(cv_img))
    @Slot(str)
    def update_name(self, name):
        if name not in ["Unknown", "Searching..."]: text, color = f"Welcome, {name}!", "#2ecc71"
        else: text, color = "Unknown Customer", "#e74c3c"
        self.name_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color};")
        self.name_label.setText(text)
    def convert_cv_qt(self, cv_img):
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        p = QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888))
        return p.scaled(640, 480, Qt.KeepAspectRatio)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())