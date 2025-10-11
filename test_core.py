# file: test_core.py

import cv2
from core.face_recognizer import FaceRecognizer


def main():
    # สร้าง instance ของ FaceRecognizer โดยไม่ต้องส่ง path เข้าไป
    recognizer = FaceRecognizer()

    # เปิดเว็บแคม (ส่วนที่เหลือเหมือนเดิมทั้งหมด)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: ไม่สามารถเปิดกล้องได้")
        return
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cropped_faces, boxes = recognizer.detect_faces(frame)
        for i, box in enumerate(boxes):
            x, y, w, h = box
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            cv2.putText(frame, f'Face {i+1}', (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        cv2.imshow('Face Detection Test', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()