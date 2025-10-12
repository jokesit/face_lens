import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # ปิด warning TensorFlow

import cv2
import numpy as np
import mediapipe as mp
import traceback
from deepface import DeepFace


class FaceRecognizer:
    def __init__(self, detector_confidence=0.7, model_name="ArcFace"):
        self.model_name = model_name
        print("FaceRecognizer initializing...")

        # Mediapipe face detection
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detector = self.mp_face_detection.FaceDetection(
            min_detection_confidence=detector_confidence
        )

        self.model = None
        try:
            print(f"Loading {model_name} model (this may take a few seconds)...")
            self.model = DeepFace.build_model(model_name)
            print(f"{model_name} model loaded successfully.")
        except Exception as e:
            print(f"Failed to load {model_name} model:", e)
            traceback.print_exc()
            self.model = None

    def detect_faces(self, image):
        """Detect faces and return cropped BGR faces and bounding boxes."""
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.face_detector.process(rgb_image)
        cropped_faces, bounding_boxes = [], []

        if results and results.detections:
            h, w, _ = image.shape
            for det in results.detections:
                box = det.location_data.relative_bounding_box
                x, y = int(box.xmin * w), int(box.ymin * h)
                bw, bh = int(box.width * w), int(box.height * h)
                x, y = max(0, x), max(0, y)
                x2, y2 = min(w, x + bw), min(h, y + bh)
                face_img = image[y:y2, x:x2]

                if face_img.size > 0:
                    cropped_faces.append(face_img)
                    bounding_boxes.append((x, y, x2 - x, y2 - y))

        return cropped_faces, bounding_boxes

    def _preprocess_for_arcface(self, face_bgr):
        """Resize & preprocess for ArcFace model input."""
        try:
            if face_bgr is None or face_bgr.size == 0:
                return None
            face = cv2.resize(face_bgr, (112, 112), interpolation=cv2.INTER_AREA)
            face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
            face = face.astype('float32')
            face = np.expand_dims(face, axis=0)
            return face
        except Exception as e:
            print("Preprocess error:", e)
            return None

    def get_embedding(self, face_bgr):
        """Return normalized embedding vector using ArcFace (DeepFace 0.0.95)."""
        try:
            if face_bgr is None or face_bgr.size == 0:
                return None

            res = DeepFace.represent(
            img_path=face_bgr,
            model_name="ArcFace",
            enforce_detection=False
        )

            if res and 'embedding' in res[0]:
                emb = np.array(res[0]['embedding'], dtype='float32')
                norm = np.linalg.norm(emb)
                return emb / norm if norm > 0 else None
            return None

        except Exception as e:
            print("Embedding extraction failed:", e)
            traceback.print_exc()
            return None