"""Recognition confidence presets for FaceLens.

Lower L2 distance is more similar. A stricter profile uses a lower threshold and
larger ambiguity margin to reduce the chance of greeting the wrong customer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceProfile:
    key: str
    thai_name: str
    description: str
    recognition_threshold: float
    ambiguity_margin: float


CONFIDENCE_PROFILES: dict[str, ConfidenceProfile] = {
    "strict": ConfidenceProfile(
        key="strict",
        thai_name="ปลอดภัยสูง",
        description="ลดโอกาสทักผิดชื่อ เหมาะกับใช้งานหน้าร้านจริงเมื่อยังมีข้อมูลใบหน้าไม่มาก",
        recognition_threshold=0.62,
        ambiguity_margin=0.12,
    ),
    "balanced": ConfidenceProfile(
        key="balanced",
        thai_name="สมดุล (แนะนำ)",
        description="สมดุลระหว่างการจำได้เร็วและความปลอดภัยในการทักชื่อ",
        recognition_threshold=0.75,
        ambiguity_margin=0.08,
    ),
    "friendly": ConfidenceProfile(
        key="friendly",
        thai_name="ทักง่ายขึ้น",
        description="จำชื่อได้ง่ายขึ้น แต่ควรใช้เมื่อมีภาพใบหน้าลูกค้าหลายมุมและทดสอบแล้วว่าแม่น",
        recognition_threshold=0.82,
        ambiguity_margin=0.06,
    ),
}

DEFAULT_CONFIDENCE_PROFILE_KEY = "balanced"


def get_confidence_profile(key: str | None) -> ConfidenceProfile:
    return CONFIDENCE_PROFILES.get((key or "").strip().lower(), CONFIDENCE_PROFILES[DEFAULT_CONFIDENCE_PROFILE_KEY])
