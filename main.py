# file: main.py (The Final, Logically Correct Version)

import sys, cv2, numpy as np
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QPushButton
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap, QFont

import faiss
from core.face_recognizer import FaceRecognizer
from add_customer_dialog import AddCustomerDialog
from core.database import Database

STYLESHEET = """
QMainWindow { background-color: #F5F5F5; }
QLabel#TitleLabel { font-size: 32px; font-weight: bold; color: #2C3E50; padding-bottom: 10px; }
QLabel#CameraLabel { background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 10px; }
QLabel#NameLabel { font-size: 24px; font-weight: bold; padding: 10px; border-radius: 5px; }
QPushButton { background-color: #3498DB; color: white; font-size: 16px; font-weight: bold; padding: 12px; border-radius: 8px; border: none; }
QPushButton:hover { background-color: #2980B9; }
QPushButton:pressed { background-color: #1F618D; }
"""


   
# single face
class VideoThread(QThread):
    change_pixmap_signal = Signal(np.ndarray)
    raw_frame_signal = Signal(np.ndarray) 
    update_name_signal = Signal(str)
    snapshot_result_signal = Signal(object) 

    def __init__(self):
        super().__init__()
        self.recognizer = FaceRecognizer()
        self.db = Database()
        self.is_running = True
        self.is_busy_processing_snapshot = False
        self.faiss_index = None
        self.index_to_name_map = {}
        self.build_faiss_index()
        self.RECOGNITION_THRESHOLD = 0.8 #morethan 0.8 not show name
        self.frame_counter = 0
        self.last_known_name = "Unknown"
        self.name_display_counter = 0
        self.RECOGNITION_INTERVAL = 20
        self.NAME_DISPLAY_DURATION = 60

    @Slot()
    def build_faiss_index(self):
        print("Building Faiss index...")
        all_data = self.db.get_all_data_for_faiss()
        if not all_data:
            print("Database is empty."); self.faiss_index = None; return
        embeddings = np.array([item[2] for item in all_data]).astype('float32')
        self.faiss_index = faiss.IndexFlatL2(embeddings.shape[1])
        self.faiss_index.add(embeddings)
        self.index_to_name_map = {i: item[1] for i, item in enumerate(all_data)}
        print(f"Faiss index built with {self.faiss_index.ntotal} vectors.")

    @Slot(object)
    def process_snapshot_request(self, frame):
        self.is_busy_processing_snapshot = True
        faces, _ = self.recognizer.detect_faces(frame)
        embedding = None
        if len(faces) == 1: embedding = self.recognizer.get_embedding(faces[0])
        self.snapshot_result_signal.emit(embedding)
        self.is_busy_processing_snapshot = False

    def run(self):
        cap = cv2.VideoCapture(0)
        while self.is_running:
            ret, cv_img = cap.read()
            if not ret: continue
            
            self.raw_frame_signal.emit(cv_img)
            frame_to_display = cv_img.copy()
            faces, boxes = self.recognizer.detect_faces(frame_to_display)

            # --- ตรรกะการจดจำและแสดงผลเวอร์ชันปรับปรุง ---
            if not self.is_busy_processing_snapshot and self.frame_counter % self.RECOGNITION_INTERVAL == 0:
                # ถ้าถึงรอบตรวจจับ ให้ทำการตัดสินใจใหม่เสมอ
                if faces and self.faiss_index is not None:
                    embedding = self.recognizer.get_embedding(faces[0])
                    if embedding is not None:
                        query = np.array([embedding]).astype('float32')
                        distances, indices = self.faiss_index.search(query, 1)
                        distance = distances[0][0]
                        
                        if distance < self.RECOGNITION_THRESHOLD:
                            # ถ้าเจอคนรู้จัก: จำชื่อและเริ่มนับเวลา
                            index = indices[0][0]
                            self.last_known_name = self.index_to_name_map[index]
                            self.name_display_counter = self.NAME_DISPLAY_DURATION
                        else:
                            # ถ้าเจอคนไม่รู้จัก: ล้างความจำทันที
                            self.last_known_name = "Unknown"
                            self.name_display_counter = 0
                else:
                    # ถ้าไม่เจอใบหน้าเลยในรอบตรวจจับ: ล้างความจำทันที
                    self.last_known_name = "Unknown"
                    self.name_display_counter = 0
            
            # ลดตัวนับเวลาแสดงผลลงเรื่อยๆ
            if self.name_display_counter > 0:
                self.name_display_counter -= 1
            else:
                self.last_known_name = "Unknown"
            
            # วาดกรอบและแสดงชื่อล่าสุดเสมอ
            if boxes:
                x, y, w, h = boxes[0]
                color = (0, 255, 0) if self.last_known_name != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame_to_display, (x, y), (x+w, y+h), color, 2)
                cv2.putText(frame_to_display, self.last_known_name, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
            
            self.change_pixmap_signal.emit(frame_to_display)
            self.update_name_signal.emit(self.last_known_name)
            self.frame_counter += 1
        cap.release()

    def stop(self): self.is_running = False; self.quit(); self.wait()

class MainWindow(QMainWindow):
    # (คลาสนี้เหมือนเดิมทุกประการ ไม่ต้องแก้ไข)
    rebuild_index_signal = Signal()
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FaceLens (Pro)"); self.setGeometry(100, 100, 800, 720)
        title_label = QLabel("FaceLens"); title_label.setObjectName("TitleLabel"); title_label.setAlignment(Qt.AlignCenter)
        self.image_label = QLabel(self); self.image_label.setObjectName("CameraLabel"); self.image_label.setAlignment(Qt.AlignCenter); self.image_label.setText("Starting Camera...")
        self.name_label = QLabel(self); self.name_label.setObjectName("NameLabel"); self.name_label.setAlignment(Qt.AlignCenter)
        self.add_customer_button = QPushButton("Add / Update Customer Data", self); self.add_customer_button.clicked.connect(self.open_add_customer_dialog)
        layout = QVBoxLayout(); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)
        layout.addWidget(title_label); layout.addWidget(self.image_label); layout.addWidget(self.name_label); layout.addWidget(self.add_customer_button)
        container = QWidget(); container.setLayout(layout); self.setCentralWidget(container)
        self.thread = VideoThread()
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.update_name_signal.connect(self.update_name)
        self.rebuild_index_signal.connect(self.thread.build_faiss_index)
        self.thread.start()
        self.update_name("Searching...")
    def open_add_customer_dialog(self):
        dialog = AddCustomerDialog(parent=self)
        self.thread.raw_frame_signal.connect(dialog.update_frame)
        dialog.request_snapshot_processing.connect(self.thread.process_snapshot_request)
        self.thread.snapshot_result_signal.connect(dialog.on_snapshot_processed)
        dialog.customer_saved_signal.connect(self.rebuild_index_signal.emit)
        dialog.exec()
        self.thread.raw_frame_signal.disconnect(dialog.update_frame)
        dialog.request_snapshot_processing.disconnect(self.thread.process_snapshot_request)
        self.thread.snapshot_result_signal.disconnect(dialog.on_snapshot_processed)
        dialog.customer_saved_signal.disconnect(self.rebuild_index_signal.emit)
    def closeEvent(self, event): self.thread.stop(); event.accept()
    @Slot(np.ndarray)
    def update_image(self, cv_img): self.image_label.setPixmap(self.convert_cv_qt(cv_img))
    @Slot(str)
    def update_name(self, name):
        if name not in ["Unknown", "Searching..."]: text, color, bg_color = f"Welcome, {name}!", "#2ECC71", "#E8F8F5"
        else: text, color, bg_color = "Unknown Customer", "#E74C3C", "#F9EBEA"
        self.name_label.setStyleSheet(f"background-color: {bg_color}; color: {color}; font-size: 24px; font-weight: bold; padding: 10px; border-radius: 5px;")
        self.name_label.setText(text)
    def convert_cv_qt(self, cv_img):
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        p = QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888))
        return p.scaled(640, 480, Qt.KeepAspectRatio)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())








# multiface detect
# class VideoThread(QThread):
#     # ... (ส่วน Signal และ __init__ เหมือนเดิม แต่ปรับ Threshold)
#     change_pixmap_signal = Signal(np.ndarray)
#     raw_frame_signal = Signal(np.ndarray) 
#     update_name_signal = Signal(str)
#     snapshot_result_signal = Signal(object) 

#     def __init__(self):
#         super().__init__()
#         self.recognizer = FaceRecognizer()
#         self.db = Database()
#         self.is_running = True
#         self.is_busy_processing_snapshot = False
#         self.faiss_index = None
#         self.index_to_name_map = {}
#         self.build_faiss_index()
        
#         self.RECOGNITION_THRESHOLD = 0.8 # <<-- ปรับให้เข้มงวดขึ้น
        
#         self.frame_counter = 0
#         self.RECOGNITION_INTERVAL = 20
#         # เราจะไม่ใช้ระบบนับถอยหลังอีกต่อไป เพราะจะตัดสินใจทุกเฟรม
#         self.recognition_results = {} # เก็บผลลัพธ์ล่าสุด {box: name}

#     @Slot()
#     def build_faiss_index(self):
#         # (ฟังก์ชันนี้เหมือนเดิม)
#         print("Building Faiss index...")
#         all_data = self.db.get_all_data_for_faiss()
#         if not all_data:
#             print("Database is empty."); self.faiss_index = None; return
#         embeddings = np.array([item[2] for item in all_data]).astype('float32')
#         self.faiss_index = faiss.IndexFlatL2(embeddings.shape[1])
#         self.faiss_index.add(embeddings)
#         self.index_to_name_map = {i: item[1] for i, item in enumerate(all_data)}
#         print(f"Faiss index built with {self.faiss_index.ntotal} vectors.")

#     @Slot(object)
#     def process_snapshot_request(self, frame):
#         # (ฟังก์ชันนี้เหมือนเดิม)
#         self.is_busy_processing_snapshot = True
#         faces, _ = self.recognizer.detect_faces(frame)
#         embedding = None
#         if len(faces) == 1: embedding = self.recognizer.get_embedding(faces[0])
#         self.snapshot_result_signal.emit(embedding)
#         self.is_busy_processing_snapshot = False

#     def run(self):
#         cap = cv2.VideoCapture(0)
#         while self.is_running:
#             ret, cv_img = cap.read()
#             if not ret: continue
            
#             self.raw_frame_signal.emit(cv_img)
#             frame_to_display = cv_img.copy()
#             faces, boxes = self.recognizer.detect_faces(frame_to_display)
#             display_name = "Unknown"

#             # --- ตรรกะการจดจำหลายใบหน้า ---
#             if not self.is_busy_processing_snapshot and self.frame_counter % self.RECOGNITION_INTERVAL == 0:
#                 self.recognition_results = {} # ล้างผลลัพธ์เก่าทุกรอบการตรวจจับ
#                 if faces and self.faiss_index is not None:
#                     for i, face_img in enumerate(faces):
#                         embedding = self.recognizer.get_embedding(face_img)
#                         if embedding is not None:
#                             query = np.array([embedding]).astype('float32')
#                             distances, indices = self.faiss_index.search(query, 1)
#                             distance = distances[0][0]
                            
#                             name = "Unknown"
#                             if distance < self.RECOGNITION_THRESHOLD:
#                                 index = indices[0][0]
#                                 name = self.index_to_name_map.get(index, "Unknown")
                            
#                             self.recognition_results[boxes[i]] = name
            
#             # วาดกรอบและแสดงชื่อทั้งหมดจากผลลัพธ์ล่าสุดเสมอ
#             for box, name in self.recognition_results.items():
#                 x, y, w, h = box
#                 color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
#                 cv2.rectangle(frame_to_display, (x, y), (x+w, y+h), color, 2)
#                 cv2.putText(frame_to_display, name, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
            
#             # หาชื่อที่แสดงใน Label (เลือกคนแรกที่รู้จัก)
#             known_names = [name for name in self.recognition_results.values() if name != "Unknown"]
#             if known_names:
#                 display_name = known_names[0]
            
#             self.change_pixmap_signal.emit(frame_to_display)
#             self.update_name_signal.emit(display_name)
#             self.frame_counter += 1
#         cap.release()

#     def stop(self): self.is_running = False; self.quit(); self.wait()

# class MainWindow(QMainWindow):
#     # (คลาสนี้เหมือนเดิมทุกประการ ไม่ต้องแก้ไข)
#     rebuild_index_signal = Signal()
#     # ... (โค้ดส่วนที่เหลือของ MainWindow และส่วน main เหมือนเดิม)
#     def __init__(self):
#         super().__init__()
#         self.setWindowTitle("FaceLens (Pro)"); self.setGeometry(100, 100, 800, 720)
#         title_label = QLabel("FaceLens"); title_label.setObjectName("TitleLabel"); title_label.setAlignment(Qt.AlignCenter)
#         self.image_label = QLabel(self); self.image_label.setObjectName("CameraLabel"); self.image_label.setAlignment(Qt.AlignCenter); self.image_label.setText("Starting Camera...")
#         self.name_label = QLabel(self); self.name_label.setObjectName("NameLabel"); self.name_label.setAlignment(Qt.AlignCenter)
#         self.add_customer_button = QPushButton("Add / Update Customer Data", self); self.add_customer_button.clicked.connect(self.open_add_customer_dialog)
#         layout = QVBoxLayout(); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)
#         layout.addWidget(title_label); layout.addWidget(self.image_label); layout.addWidget(self.name_label); layout.addWidget(self.add_customer_button)
#         container = QWidget(); container.setLayout(layout); self.setCentralWidget(container)
#         self.thread = VideoThread()
#         self.thread.change_pixmap_signal.connect(self.update_image)
#         self.thread.update_name_signal.connect(self.update_name)
#         self.rebuild_index_signal.connect(self.thread.build_faiss_index)
#         self.thread.start()
#         self.update_name("Searching...")
#     def open_add_customer_dialog(self):
#         dialog = AddCustomerDialog(parent=self)
#         self.thread.raw_frame_signal.connect(dialog.update_frame)
#         dialog.request_snapshot_processing.connect(self.thread.process_snapshot_request)
#         self.thread.snapshot_result_signal.connect(dialog.on_snapshot_processed)
#         dialog.customer_saved_signal.connect(self.rebuild_index_signal.emit)
#         dialog.exec()
#         self.thread.raw_frame_signal.disconnect(dialog.update_frame)
#         dialog.request_snapshot_processing.disconnect(self.thread.process_snapshot_request)
#         self.thread.snapshot_result_signal.disconnect(dialog.on_snapshot_processed)
#         dialog.customer_saved_signal.disconnect(self.rebuild_index_signal.emit)
#     def closeEvent(self, event): self.thread.stop(); event.accept()
#     @Slot(np.ndarray)
#     def update_image(self, cv_img): self.image_label.setPixmap(self.convert_cv_qt(cv_img))
#     @Slot(str)
#     def update_name(self, name):
#         if name not in ["Unknown", "Searching..."]: text, color, bg_color = f"Welcome, {name}!", "#2ECC71", "#E8F8F5"
#         else: text, color, bg_color = "Unknown Customer", "#E74C3C", "#F9EBEA"
#         self.name_label.setStyleSheet(f"background-color: {bg_color}; color: {color}; font-size: 24px; font-weight: bold; padding: 10px; border-radius: 5px;")
#         self.name_label.setText(text)
#     def convert_cv_qt(self, cv_img):
#         rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
#         h, w, ch = rgb.shape
#         p = QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888))
#         return p.scaled(640, 480, Qt.KeepAspectRatio)

# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     app.setStyleSheet(STYLESHEET)
#     app.setFont(QFont("Segoe UI", 10))
#     window = MainWindow()
#     window.show()
#     sys.exit(app.exec())
    
    
 