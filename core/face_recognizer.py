# file: core/face_recognizer.py (The Final Confirmed & Working Version)

import cv2
import numpy as np
import mediapipe as mp
from deepface import DeepFace
import os # Import 'os' สำหรับจัดการไฟล์

class FaceRecognizer:
    def __init__(self):
        print("FaceRecognizer initialized. Model will be built on first use.")
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detector = self.mp_face_detection.FaceDetection(min_detection_confidence=0.7)

    def detect_faces(self, image):
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
        # --- นี่คือส่วนที่แก้ไขใหม่ทั้งหมด ---
        
        # 1. กำหนดชื่อไฟล์ชั่วคราว
        temp_file_path = "temp_face.jpg"
        embedding = None

        try:
            # 2. บันทึกภาพใบหน้าที่ตัดแล้วลงเป็นไฟล์ชั่วคราว
            cv2.imwrite(temp_file_path, face_image)

            # 3. เรียกใช้ DeepFace โดยส่ง "ที่อยู่ไฟล์" เข้าไป
            result = DeepFace.represent(
                img_path=temp_file_path,
                model_name='Facenet',
                enforce_detection=False
            )
            
            if result and 'embedding' in result[0]:
                embedding = np.array(result[0]['embedding'])

        except Exception as e:
            print(f"DeepFace Error: Could not get embedding. Reason: {e}")
            embedding = None
        finally:
            # 4. ไม่ว่าจะสำเร็จหรือล้มเหลว ให้ลบไฟล์ชั่วคราวทิ้งเสมอ
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        
        return embedding