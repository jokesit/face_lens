"""Runtime performance presets for FaceLens.

The expensive part of FaceLens is not drawing the camera frame; it is creating
DeepFace embeddings. These presets tune recognition frequency and result reuse
without changing the database or AI model.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceProfile:
    key: str
    thai_name: str
    description: str
    target_fps: float
    face_detection_interval_frames: int
    recognition_interval_frames: int
    recognition_min_seconds_between_jobs: float
    recognition_result_ttl_seconds: float
    recognition_box_reuse_iou: float
    max_recognition_faces: int


PERFORMANCE_PROFILES: dict[str, PerformanceProfile] = {
    "fast": PerformanceProfile(
        key="fast",
        thai_name="เบาและเร็ว",
        description="เหมาะกับคอมสเปกไม่สูง ลดการเรียก AI เพื่อให้เครื่องลื่นและร้อนน้อยลง",
        target_fps=15.0,
        face_detection_interval_frames=1,
        recognition_interval_frames=18,
        recognition_min_seconds_between_jobs=1.8,
        recognition_result_ttl_seconds=3.5,
        recognition_box_reuse_iou=0.32,
        max_recognition_faces=2,
    ),
    "balanced": PerformanceProfile(
        key="balanced",
        thai_name="สมดุล (แนะนำ)",
        description="เหมาะกับการใช้งานหน้าร้านจริง ภาพลื่น กรอบตามทัน และจำหน้าได้รวดเร็วพอเหมาะ",
        target_fps=15.0,
        face_detection_interval_frames=1,
        recognition_interval_frames=12,
        recognition_min_seconds_between_jobs=1.2,
        recognition_result_ttl_seconds=3.0,
        recognition_box_reuse_iou=0.35,
        max_recognition_faces=3,
    ),
    "accurate": PerformanceProfile(
        key="accurate",
        thai_name="แม่นยำขึ้น",
        description="เหมาะกับเครื่องแรงขึ้นหรือช่วงทดสอบ เรียก AI บ่อยขึ้นเพื่ออัปเดตชื่อไวกว่าเดิม",
        target_fps=15.0,
        face_detection_interval_frames=1,
        recognition_interval_frames=8,
        recognition_min_seconds_between_jobs=0.8,
        recognition_result_ttl_seconds=2.2,
        recognition_box_reuse_iou=0.42,
        max_recognition_faces=3,
    ),
}

DEFAULT_PROFILE_KEY = "balanced"


def get_performance_profile(key: str | None) -> PerformanceProfile:
    return PERFORMANCE_PROFILES.get((key or "").strip().lower(), PERFORMANCE_PROFILES[DEFAULT_PROFILE_KEY])
