# file: core/face_recognizer.py (ArcFace Version)

import cv2
import numpy as np
import mediapipe as mp
from deepface import DeepFace
import os

class FaceRecognizer:
    def __init__(self):
        print("FaceRecognizer initialized. Model will be built on first use.")
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detector = self.mp_face_detection.FaceDetection(min_detection_confidence=0.7)

    def detect_faces(self, image):
        # (ฟังก์ชันนี้เหมือนเดิม ไม่มีการเปลี่ยนแปลง)
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.face_detector.process(rgb_image)
        cropped_faces = []
        bounding_boxes = []
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
        temp_file_path = "temp_face.jpg"
        embedding = None
        try:
            cv2.imwrite(temp_file_path, face_image)

            # --- ส่วนที่อัปเกรด ---
            result = DeepFace.represent(
                img_path=temp_file_path,
                model_name='ArcFace',       # 1. เปลี่ยนไปใช้ ArcFace
                enforce_detection=False,
                detector_backend='skip'     # บอกว่าไม่ต้องตรวจจับซ้ำ
            )
            # ---------------------
            
            if result and 'embedding' in result[0]:
                embedding_vector = np.array(result[0]['embedding'])
                # 2. ทำ Normalization
                normalized_embedding = embedding_vector / np.linalg.norm(embedding_vector)
                embedding = normalized_embedding

        except Exception as e:
            print(f"DeepFace Error: Could not get embedding. Reason: {e}")
            embedding = None
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        
        return embedding