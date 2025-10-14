import cv2
import numpy as np
import mediapipe as mp
from deepface import DeepFace
import os
import hashlib
from collections import OrderedDict
import sys


# --- โค้ดเวทมนตร์สำหรับหา Path หลัก ---
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ------------------------------------

# --- สร้าง Path ไปยังโฟลเดอร์ Temp ---
temp_folder_path = os.path.join(application_path, 'temp_files')
os.makedirs(temp_folder_path, exist_ok=True)
# -----------------------------------

class FaceRecognizer:
    def __init__(self):
        print("FaceRecognizer initializing...")
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detector = self.mp_face_detection.FaceDetection(min_detection_confidence=0.7)
        self.embedding_cache = OrderedDict()
        self.CACHE_SIZE = 200

    def detect_faces(self, image):
        # (ฟังก์ชันนี้สมบูรณ์แล้ว ไม่ต้องแก้ไข)
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.face_detector.process(rgb_image)
        cropped_faces, bounding_boxes = [], []
        if results.detections:
            h, w, _ = image.shape
            for detection in results.detections:
                box = detection.location_data.relative_bounding_box
                x, y, width, height = int(box.xmin * w), int(box.ymin * h), int(box.width * w), int(box.height * h)
                x, y = max(0, x), max(0, y)
                face_img = image[y:y+height, x:x+width]
                if face_img.size > 0:
                    cropped_faces.append(face_img)
                    bounding_boxes.append((x, y, width, height))
        return cropped_faces, bounding_boxes
        
    def get_embedding(self, face_image):
        """
        ฟังก์ชันเวอร์ชันสมบูรณ์: ใช้ Cache + ไฟล์ชั่วคราวเพื่อความเร็วและความเสถียร
        """
        image_bytes = face_image.tobytes()
        image_hash = hashlib.sha256(image_bytes).hexdigest()

        if image_hash in self.embedding_cache:
            self.embedding_cache.move_to_end(image_hash)
            return self.embedding_cache[image_hash]
        
        # --- ถ้าไม่เจอในแคช ให้ใช้วิธีไฟล์ชั่วคราวที่เสถียร ---
        # temp_file_path = f"temp_face_{image_hash}.jpg" 
        temp_file_path = os.path.join(temp_folder_path, f"temp_face_{image_hash}.jpg")
        embedding = None
        try:
            cv2.imwrite(temp_file_path, face_image)
            result = DeepFace.represent(
                img_path=temp_file_path,
                model_name='ArcFace',
                enforce_detection=False,
                detector_backend='skip'
            )
            
            if result and 'embedding' in result[0]:
                embedding_vector = np.array(result[0]['embedding'])
                normalized_embedding = embedding_vector / np.linalg.norm(embedding_vector)
                embedding = normalized_embedding

        except Exception as e:
            print(f"DeepFace Error in get_embedding: {e}")
            embedding = None
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        # ----------------------------------------------------

        if embedding is not None:
            self.embedding_cache[image_hash] = embedding
            if len(self.embedding_cache) > self.CACHE_SIZE:
                self.embedding_cache.popitem(last=False)
        
        return embedding