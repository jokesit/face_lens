# file: main.py (The Final, Stable, Smooth & Correct Architecture)

import sys, cv2, numpy as np
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QPushButton, QSplashScreen
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap, QFont, QIcon

from PIL import Image, ImageDraw, ImageFont

# --- 1. เพิ่มโค้ดสำหรับ Windows Taskbar Icon ---
import ctypes
myappid = 'facelens.pro.store.1.0' 
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except (ImportError, AttributeError):
    pass # จะทำงานบน Windows เท่านั้น
# -----------------------------------------------

import faiss
from core.face_recognizer import FaceRecognizer
from add_customer_dialog import AddCustomerDialog
from core.database import Database


STYLESHEET = """
QMainWindow { background-color: #F5F5F5; }
QLabel#TitleLabel { font-size: 32px; font-weight: bold; color: #2980B9; padding-bottom: 10px; }
QLabel#CameraLabel { background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 10px; }
QLabel#NameLabel { font-size: 24px; font-weight: bold; padding: 10px; border-radius: 5px; }
QPushButton { background-color: #3498DB; color: white; font-size: 16px; font-weight: bold; padding: 12px; border-radius: 8px; border: none; }
QPushButton:hover { background-color: #2980B9; }
QPushButton:pressed { background-color: #1F618D; }
"""
# 5555

class RecognitionThread(QThread):
    recognition_result = Signal(str, object)
    snapshot_result = Signal(object)
    verification_result = Signal(str, float)

    def __init__(self):
        super().__init__()
        self.recognizer = None
        self.faiss_index = None
        self.index_to_name_map = {}
        self.RECOGNITION_THRESHOLD = 0.75
        self.is_running = True

    def run(self):
        self.recognizer = FaceRecognizer()
        print("Warming up model...")
        self.recognizer.get_embedding(np.zeros((160, 160, 3), dtype=np.uint8))
        print("Model ready.")
        while self.is_running:
            self.msleep(100)

    @Slot(list)
    def build_faiss_index(self, db_data):
        try:
            if not db_data: self.faiss_index = None; return
            embeddings = np.array([item[2] for item in db_data]).astype('float32')
            self.faiss_index = faiss.IndexFlatL2(embeddings.shape[1])
            self.faiss_index.add(embeddings)
            self.index_to_name_map = {i: item[1] for i, item in enumerate(db_data)}
        except Exception as e:
            print(f"RecognitionThread Error: {e}")

    @Slot(object, object)
    def process_recognition_job(self, face_image, box):
        if self.faiss_index is None or self.recognizer is None: return
        embedding = self.recognizer.get_embedding(face_image)
        if embedding is not None:
            query = np.array([embedding]).astype('float32')
            distances, indices = self.faiss_index.search(query, 1)
            distance, index = distances[0][0], indices[0][0]
            name = "Unknown"
            if distance < self.RECOGNITION_THRESHOLD:
                name = self.index_to_name_map.get(index, "Unknown")
            self.recognition_result.emit(name, box)

    @Slot(object)
    def process_snapshot_job(self, face_image):
        if self.recognizer is None: return
        embedding = self.recognizer.get_embedding(face_image)
        self.snapshot_result.emit(embedding)

    @Slot(list, str)
    def process_verification_job(self, captured_embeddings, name):
        if not captured_embeddings or self.recognizer is None:
            self.verification_result.emit(name, None); return
        new_avg = np.mean(captured_embeddings, axis=0); new_avg /= np.linalg.norm(new_avg)
        db = Database(); existing = db.get_customer_by_name(name); distance = -1.0
        if existing and existing['avg_embedding'] is not None:
            distance = np.linalg.norm(new_avg - existing['avg_embedding'])
        self.verification_result.emit(name, distance)

    def stop(self): self.is_running = False; self.quit(); self.wait()


class VideoThread(QThread):
    change_pixmap_signal = Signal(QPixmap)
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
        self.RECOGNITION_INTERVAL = 20
        self.last_known_results = {}
        self.is_capture_mode = False
        self.capture_count = 0
        self.last_face_box = None
        self.capture_cooldown = 0
        self.COOLDOWN_FRAMES = 30
        self.MIN_FACE_MOVEMENT = 10
        self.MAX_SNAPSHOTS = 5

        # --- 2. โหลดฟอนต์ภาษาไทย ---
        try:
            self.font = ImageFont.truetype("assets/tahoma.ttf", 24)
        except IOError:
            print("Font file not found in assets/tahoma.ttf. Using default font.")
            self.font = ImageFont.load_default()
        # -----------------------------

    @Slot(str, object)
    def update_recognition_results(self, name, box):
        self.last_known_results[box] = name

    @Slot(bool)
    def set_capture_mode(self, is_active):
        self.is_capture_mode = is_active
        if is_active:
            self.capture_count = 0
            self.last_face_box = None
        else:
            self.last_face_box = None

    def run(self):
        cap = cv2.VideoCapture(0)
        while self.is_running:
            ret, cv_img = cap.read()
            if not ret: continue
            
            self.raw_frame_signal.emit(cv_img)
            frame_to_display = cv_img.copy()
            faces, boxes = self.detector.detect_faces(frame_to_display)

            if self.is_capture_mode:
                if self.capture_cooldown > 0: self.capture_cooldown -= 1
                if self.capture_cooldown == 0 and len(faces) == 1 and self.capture_count < self.MAX_SNAPSHOTS:
                    face_img, face_box = faces[0], boxes[0]
                    h, w, _ = face_img.shape; is_good = h >= 64 and w >= 64; has_moved = True
                    if self.last_face_box is not None:
                        dx = abs(face_box[0] - self.last_face_box[0]); dy = abs(face_box[1] - self.last_face_box[1])
                        if dx < self.MIN_FACE_MOVEMENT and dy < self.MIN_FACE_MOVEMENT: has_moved = False
                    if is_good and has_moved:
                        self.snapshot_job_signal.emit(face_img)
                        self.capture_count += 1
                        self.last_face_box = face_box; self.capture_cooldown = self.COOLDOWN_FRAMES
                        self.capture_progress_signal.emit(self.capture_count, self.MAX_SNAPSHOTS)
            else:
                if self.frame_counter % self.RECOGNITION_INTERVAL == 0:
                    self.last_known_results = {}
                    if faces:
                        self.recognition_job_signal.emit(faces[0], boxes[0])
                    else:
                        self.update_display_name_signal.emit("Unknown")

            # --- 3. อัปเกรดการวาดข้อความด้วย Pillow ---
            if self.last_known_results:
                pil_img = Image.fromarray(cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB))
                draw = ImageDraw.Draw(pil_img)
                for box, name in self.last_known_results.items():
                    x, y, w, h = box
                    color = (0, 255, 0) if name != "Unknown" else (255, 0, 0)
                    draw.rectangle([(x, y), (x + w, y + h)], outline=color, width=3)
                    draw.text((x, y - 30), name, font=self.font, fill=color)
                frame_to_display = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            # ---------------------------------------------
            
            rgb = cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            pixmap = QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888))
            self.change_pixmap_signal.emit(pixmap.scaled(640, 480, Qt.KeepAspectRatio))
            
            self.frame_counter += 1
        cap.release()

    def stop(self):
        self.is_running = False
        self.quit()
        self.wait()


class MainWindow(QMainWindow):
    rebuild_index_signal = Signal(list)
    verification_job_signal = Signal(list, str)
    snapshot_job_signal = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FaceLens (Pro Architecture)")
        self.setGeometry(100, 100, 800, 720)
        self.setWindowIcon(QIcon("assets/logo.png"))
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
        self.recognition_thread = RecognitionThread()

        # Connect signals
        self.video_thread.change_pixmap_signal.connect(self.update_image)
        self.video_thread.recognition_job_signal.connect(self.recognition_thread.process_recognition_job)
        self.recognition_thread.recognition_result.connect(self.video_thread.update_recognition_results)
        self.recognition_thread.recognition_result.connect(self.update_name_from_result)
        self.rebuild_index_signal.connect(self.recognition_thread.build_faiss_index)
        self.verification_job_signal.connect(self.recognition_thread.process_verification_job)
        self.video_thread.update_display_name_signal.connect(self.update_name_from_result)

        self.recognition_thread.start()
        self.video_thread.start()
        
        self.rebuild_index_signal.emit(self.db.get_all_data_for_faiss())
        self.update_name_from_result("Searching...", None)

    def open_add_customer_dialog(self):
        dialog = AddCustomerDialog(parent=self)
        
        self.video_thread.raw_frame_signal.connect(dialog.update_frame)
        dialog.capture_mode_toggled.connect(self.video_thread.set_capture_mode)
        self.video_thread.snapshot_job_signal.connect(self.recognition_thread.process_snapshot_job)
        self.recognition_thread.snapshot_result.connect(dialog.add_captured_embedding)
        self.video_thread.capture_progress_signal.connect(dialog.update_capture_progress)
        dialog.request_verification_job.connect(self.verification_job_signal.emit)
        self.recognition_thread.verification_result.connect(dialog.on_verification_finished)
        dialog.customer_saved_signal.connect(self.on_customer_saved)
        
        dialog.exec()
        
        self.video_thread.raw_frame_signal.disconnect(dialog.update_frame)
        dialog.capture_mode_toggled.disconnect(self.video_thread.set_capture_mode)
        self.video_thread.snapshot_job_signal.disconnect(self.recognition_thread.process_snapshot_job)
        self.recognition_thread.snapshot_result.disconnect(dialog.add_captured_embedding)
        self.video_thread.capture_progress_signal.disconnect(dialog.update_capture_progress)
        dialog.request_verification_job.disconnect(self.verification_job_signal.emit)
        self.recognition_thread.verification_result.disconnect(dialog.on_verification_finished)
        dialog.customer_saved_signal.disconnect(self.on_customer_saved)
        self.video_thread.set_capture_mode(False)

    @Slot()
    def on_customer_saved(self):
        self.rebuild_index_signal.emit(self.db.get_all_data_for_faiss())

    def closeEvent(self, event):
        self.video_thread.stop()
        self.recognition_thread.stop()
        event.accept()

    @Slot(QPixmap)
    def update_image(self, pixmap):
        self.image_label.setPixmap(pixmap)
    
    @Slot(str, object)
    def update_name_from_result(self, name, box=None):
        if name not in ["Unknown", "Searching..."]:
            text, color, bg_color = f"Welcome, {name}!", "#2ECC71", "#E8F8F5"
        else:
            text, color, bg_color = "Unknown Customer", "#E74C3C", "#F9EBEA"
        self.name_label.setStyleSheet(f"background-color: {bg_color}; color: {color}; font-size: 24px; font-weight: bold; padding: 10px; border-radius: 5px;")
        self.name_label.setText(text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("assets/logo.png"))
    app.setStyleSheet(STYLESHEET)
    app.setFont(QFont("Segoe UI", 10))
    
    # --- เริ่มส่วนของ Splash Screen ---
    # 1. โหลดรูปภาพที่จะใช้เป็น Splash Screen
    pixmap = QPixmap("assets/logo.png")
    # 2. สร้าง Splash Screen จากรูปภาพ
    splash = QSplashScreen(pixmap)
    
    splash.setWindowFlag(Qt.WindowStaysOnTopHint)
    splash_font = QFont("Segoe UI", 20, QFont.Bold)
    splash.setFont(splash_font)
    splash.showMessage("Initializing FaceLens, please wait...", Qt.AlignCenter | Qt.AlignBottom, Qt.black)
    # 3. แสดง Splash Screen ทันที!
    splash.show()
    
    window = MainWindow()
    
    # 4. เมื่อ MainWindow โหลดเสร็จแล้ว ให้ปิด Splash Screen
    splash.finish(window)
    # 5. แสดงหน้าต่างหลักของโปรแกรม
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
    
    
 