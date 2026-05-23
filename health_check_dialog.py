"""Health check dialog for FaceLens."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout

from core.database import Database
from core.health_check import run_health_checks


class HealthCheckDialog(QDialog):
    def __init__(self, db: Database, camera_index: int = 0, parent=None):
        super().__init__(parent)
        self.db = db
        self.camera_index = camera_index
        self.setWindowTitle("ตรวจความพร้อมของระบบ")
        self.resize(660, 520)

        title = QLabel("ตรวจความพร้อมของ FaceLens")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))

        subtitle = QLabel("ใช้ตรวจ dependency, ฐานข้อมูล, พื้นที่จัดเก็บ และความพร้อมสำหรับใช้งานในร้านยา")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)

        self.result_box = QTextEdit(self)
        self.result_box.setReadOnly(True)
        self.result_box.setFont(QFont("Consolas", 10))

        self.refresh_button = QPushButton("ตรวจอีกครั้ง")
        self.refresh_button.clicked.connect(self.run_checks)

        close_button = QPushButton("ปิด")
        close_button.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.result_box, stretch=1)
        layout.addLayout(button_layout)

        self.run_checks()

    def run_checks(self) -> None:
        self.refresh_button.setEnabled(False)
        self.result_box.setPlainText("กำลังตรวจระบบ...")
        try:
            report = run_health_checks(self.db, camera_index=self.camera_index, include_camera=False)
            self.result_box.setPlainText(report.to_plain_text())
        except Exception as exc:
            self.result_box.setPlainText(f"ตรวจระบบไม่สำเร็จ:\n{exc}")
        finally:
            self.refresh_button.setEnabled(True)
