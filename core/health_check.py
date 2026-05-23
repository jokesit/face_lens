"""Application health checks for FaceLens standalone deployments.

The checks are intentionally lightweight so shop staff can run them from the UI
without loading extra AI models or interrupting normal operation.
"""

from __future__ import annotations

import importlib.util
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.config import BACKUP_DIR, DATA_DIR, DB_PATH, LOG_DIR, TEMP_DIR, STANDALONE_TARGET_CUSTOMERS
from core.database import Database


@dataclass(frozen=True)
class HealthCheckItem:
    name: str
    status: str  # ok, warning, error
    message: str
    detail: str = ""

    @property
    def icon(self) -> str:
        if self.status == "ok":
            return "✅"
        if self.status == "warning":
            return "⚠️"
        return "❌"


@dataclass(frozen=True)
class HealthReport:
    items: list[HealthCheckItem]

    @property
    def has_error(self) -> bool:
        return any(item.status == "error" for item in self.items)

    @property
    def has_warning(self) -> bool:
        return any(item.status == "warning" for item in self.items)

    @property
    def summary(self) -> str:
        errors = sum(1 for item in self.items if item.status == "error")
        warnings = sum(1 for item in self.items if item.status == "warning")
        if errors:
            return f"พบปัญหาสำคัญ {errors} รายการ ควรแก้ก่อนใช้งานจริง"
        if warnings:
            return f"ระบบใช้งานได้ แต่มีข้อควรตรวจสอบ {warnings} รายการ"
        return "ระบบพร้อมใช้งาน"

    def to_plain_text(self) -> str:
        lines = [self.summary, ""]
        for item in self.items:
            lines.append(f"{item.icon} {item.name}: {item.message}")
            if item.detail:
                lines.append(f"   {item.detail}")
        return "\n".join(lines)


def _check_package(import_name: str, label: str) -> HealthCheckItem:
    if importlib.util.find_spec(import_name) is None:
        return HealthCheckItem(label, "error", "ไม่พบ package ที่จำเป็น", f"ติดตั้ง/ตรวจ requirements: {import_name}")
    return HealthCheckItem(label, "ok", "พร้อมใช้งาน")


def _check_writable_folder(path: Path, label: str) -> HealthCheckItem:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".facelens_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        return HealthCheckItem(label, "error", "ไม่สามารถเขียนไฟล์ได้", str(exc))
    return HealthCheckItem(label, "ok", f"เขียนไฟล์ได้: {path}")


def _check_database_file(path: Path) -> HealthCheckItem:
    if not path.exists():
        return HealthCheckItem("ฐานข้อมูล", "warning", "ยังไม่พบไฟล์ฐานข้อมูล", "ระบบจะสร้างให้อัตโนมัติเมื่อเปิดโปรแกรม")
    try:
        with sqlite3.connect(str(path), timeout=5) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except Exception as exc:
        return HealthCheckItem("ฐานข้อมูล", "error", "เปิดฐานข้อมูลไม่ได้", str(exc))

    required = {"customers", "face_embeddings", "recognition_events"}
    missing = required - tables
    if missing:
        return HealthCheckItem("ฐานข้อมูล", "error", "โครงสร้างฐานข้อมูลไม่ครบ", f"ขาด table: {', '.join(sorted(missing))}")
    return HealthCheckItem("ฐานข้อมูล", "ok", "โครงสร้างฐานข้อมูลถูกต้อง")


def _check_database_summary(db: Database) -> list[HealthCheckItem]:
    items: list[HealthCheckItem] = []
    try:
        summary = db.get_database_summary()
    except Exception as exc:
        return [HealthCheckItem("สรุปข้อมูล", "error", "อ่านสรุปฐานข้อมูลไม่ได้", str(exc))]

    customers = int(summary.get("active_customers", 0))
    embeddings = int(summary.get("active_embeddings", 0))
    events = int(summary.get("recognition_events", 0))
    size_mb = float(summary.get("database_size_mb", 0.0))

    if customers == 0:
        items.append(HealthCheckItem("ข้อมูลลูกค้า", "warning", "ยังไม่มีลูกค้าที่บันทึกไว้", "เริ่มจากเพิ่มลูกค้าทดสอบ 1-2 คนก่อนใช้งานจริง"))
    else:
        items.append(HealthCheckItem("ข้อมูลลูกค้า", "ok", f"มีลูกค้าใช้งานอยู่ {customers:,} คน"))

    if embeddings == 0:
        items.append(HealthCheckItem("ข้อมูลใบหน้า", "warning", "ยังไม่มี embedding ที่ใช้จดจำ", "เพิ่ม/อัปเดตข้อมูลลูกค้าเพื่อเก็บภาพใบหน้า"))
    elif embeddings > 40000:
        items.append(HealthCheckItem("ข้อมูลใบหน้า", "warning", f"มี embedding จำนวนมาก {embeddings:,} รายการ", "ควรตรวจรายชื่อซ้ำและจำกัด embedding ต่อคนให้เหมาะสม"))
    else:
        items.append(HealthCheckItem("ข้อมูลใบหน้า", "ok", f"มี embedding พร้อมใช้งาน {embeddings:,} รายการ"))

    if customers >= STANDALONE_TARGET_CUSTOMERS:
        items.append(HealthCheckItem("ขนาดร้าน standalone", "warning", f"ลูกค้าถึงระดับเป้าหมาย {customers:,} คน", "ควร backup และ optimize ฐานข้อมูลสม่ำเสมอ"))
    else:
        items.append(HealthCheckItem("ขนาดร้าน standalone", "ok", f"ยังอยู่ในช่วงเหมาะสมสำหรับ SQLite + FAISS ({customers:,}/{STANDALONE_TARGET_CUSTOMERS:,} คน)"))

    if events > 100000:
        items.append(HealthCheckItem("ประวัติการจดจำ", "warning", f"มีประวัติ {events:,} รายการ", "แนะนำใช้ปุ่มล้างประวัติเก่าเพื่อลดขนาดฐานข้อมูล"))
    else:
        items.append(HealthCheckItem("ประวัติการจดจำ", "ok", f"มีประวัติ {events:,} รายการ"))

    if size_mb > 500:
        items.append(HealthCheckItem("ขนาดไฟล์ฐานข้อมูล", "warning", f"ฐานข้อมูลขนาด {size_mb:.2f} MB", "แนะนำ backup แล้วปรับฐานข้อมูลให้เร็วขึ้น"))
    else:
        items.append(HealthCheckItem("ขนาดไฟล์ฐานข้อมูล", "ok", f"ขนาดฐานข้อมูล {size_mb:.2f} MB"))

    return items


def _check_disk_space(path: Path) -> HealthCheckItem:
    try:
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024 ** 3)
    except Exception as exc:
        return HealthCheckItem("พื้นที่ว่าง", "warning", "ตรวจพื้นที่ว่างไม่ได้", str(exc))
    if free_gb < 1:
        return HealthCheckItem("พื้นที่ว่าง", "error", f"เหลือพื้นที่ว่าง {free_gb:.2f} GB", "ควรเพิ่มพื้นที่ก่อนใช้งานต่อ")
    if free_gb < 5:
        return HealthCheckItem("พื้นที่ว่าง", "warning", f"เหลือพื้นที่ว่าง {free_gb:.2f} GB", "ควรเคลียร์พื้นที่หรือย้ายไฟล์ backup เก่า")
    return HealthCheckItem("พื้นที่ว่าง", "ok", f"เหลือพื้นที่ว่าง {free_gb:.2f} GB")


def _check_camera(camera_index: int) -> HealthCheckItem:
    try:
        import cv2
    except Exception as exc:
        return HealthCheckItem("กล้อง", "error", "ไม่สามารถโหลด OpenCV ได้", str(exc))

    cap = None
    try:
        cap = cv2.VideoCapture(int(camera_index), cv2.CAP_DSHOW)
        if not cap.isOpened():
            return HealthCheckItem("กล้อง", "error", f"เปิดกล้อง {camera_index} ไม่ได้", "ลองเปลี่ยนหมายเลขกล้อง หรือปิดโปรแกรมอื่นที่ใช้กล้องอยู่")
        ok, frame = cap.read()
        if not ok or frame is None:
            return HealthCheckItem("กล้อง", "warning", f"กล้อง {camera_index} เปิดได้แต่อ่านภาพไม่ได้", "ตรวจสาย USB/สิทธิ์การใช้งานกล้อง")
        height, width = frame.shape[:2]
        return HealthCheckItem("กล้อง", "ok", f"กล้อง {camera_index} พร้อมใช้งาน ({width}x{height})")
    except Exception as exc:
        return HealthCheckItem("กล้อง", "error", f"ตรวจกล้อง {camera_index} ไม่สำเร็จ", str(exc))
    finally:
        if cap is not None:
            cap.release()


def run_health_checks(db: Database | None = None, camera_index: int = 0, include_camera: bool = False) -> HealthReport:
    """Run lightweight production-readiness checks.

    include_camera should normally be False inside the running GUI because the
    video thread already owns the camera. The CLI script can set it to True.
    """
    owns_db = db is None
    db = db or Database()

    items: list[HealthCheckItem] = []
    for import_name, label in [
        ("cv2", "OpenCV"),
        ("mediapipe", "MediaPipe"),
        ("faiss", "FAISS"),
        ("deepface", "DeepFace"),
        ("tensorflow", "TensorFlow"),
        ("PySide6", "PySide6"),
    ]:
        items.append(_check_package(import_name, label))

    for path, label in [
        (DATA_DIR, "โฟลเดอร์ข้อมูล"),
        (BACKUP_DIR, "โฟลเดอร์สำรองข้อมูล"),
        (LOG_DIR, "โฟลเดอร์ log"),
        (TEMP_DIR, "โฟลเดอร์ชั่วคราว"),
    ]:
        items.append(_check_writable_folder(path, label))

    items.append(_check_disk_space(DATA_DIR))
    items.append(_check_database_file(DB_PATH))
    items.extend(_check_database_summary(db))

    if include_camera:
        items.append(_check_camera(camera_index))
    else:
        items.append(HealthCheckItem("กล้อง", "ok", f"กำลังใช้งานกล้อง {camera_index} จากหน้าหลัก", "ถ้าต้องการตรวจกล้องแบบเปิดจริง ให้ปิดโปรแกรมแล้วรัน scripts\\health_check.py --camera"))

    if owns_db:
        db.close()

    return HealthReport(items)
