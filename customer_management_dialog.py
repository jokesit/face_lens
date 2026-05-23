"""Customer management dialog for FaceLens.

Batch 5 adds a production-style management screen so operators can review,
rename, pause, and deactivate customer profiles without editing SQLite directly.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.database import Database


MANAGEMENT_STYLESHEET = """
QDialog { background-color: #FFFFFF; }
QLabel#DialogTitle { font-size: 22px; font-weight: bold; color: #1F618D; }
QLabel#SummaryLabel { font-size: 14px; color: #566573; }
QTableWidget { font-size: 13px; gridline-color: #EAECEE; selection-background-color: #D6EAF8; }
QHeaderView::section { background-color: #EBF5FB; color: #1B4F72; padding: 6px; font-weight: bold; border: 1px solid #D6EAF8; }
QPushButton { background-color: #3498DB; color: white; font-size: 14px; font-weight: bold; padding: 9px; border-radius: 7px; border: none; }
QPushButton:hover { background-color: #2980B9; }
QPushButton#DangerButton { background-color: #E74C3C; }
QPushButton#DangerButton:hover { background-color: #C0392B; }
QPushButton#NeutralButton { background-color: #7F8C8D; }
QPushButton#NeutralButton:hover { background-color: #707B7C; }
"""


class CustomerManagementDialog(QDialog):
    customers_changed = Signal()

    COL_ID = 0
    COL_NAME = 1
    COL_EMBEDDINGS = 2
    COL_CONSENT = 3
    COL_LAST_SEEN = 4
    COL_UPDATED = 5
    COL_NOTES = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("จัดการข้อมูลลูกค้า")
        self.setMinimumSize(980, 560)
        self.setStyleSheet(MANAGEMENT_STYLESHEET)
        self.db = Database()

        self.title_label = QLabel("จัดการข้อมูลลูกค้า")
        self.title_label.setObjectName("DialogTitle")
        self.summary_label = QLabel("กำลังโหลดข้อมูล...")
        self.summary_label.setObjectName("SummaryLabel")

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "ชื่อลูกค้า",
            "จำนวนใบหน้า",
            "สถานะการจดจำ",
            "พบล่าสุด",
            "อัปเดตล่าสุด",
            "หมายเหตุ",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_NOTES, QHeaderView.Stretch)
        for col in (self.COL_ID, self.COL_EMBEDDINGS, self.COL_CONSENT, self.COL_LAST_SEEN, self.COL_UPDATED):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        self.refresh_button = QPushButton("รีเฟรช")
        self.rename_button = QPushButton("แก้ชื่อ")
        self.notes_button = QPushButton("แก้หมายเหตุ")
        self.toggle_consent_button = QPushButton("พัก/เปิดการจดจำ")
        self.delete_button = QPushButton("ลบข้อมูลลูกค้า")
        self.delete_button.setObjectName("DangerButton")
        self.close_button = QPushButton("ปิด")
        self.close_button.setObjectName("NeutralButton")

        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.rename_button)
        buttons.addWidget(self.notes_button)
        buttons.addWidget(self.toggle_consent_button)
        buttons.addStretch(1)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.close_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self.setLayout(layout)

        self.refresh_button.clicked.connect(self.load_customers)
        self.rename_button.clicked.connect(self.rename_selected_customer)
        self.notes_button.clicked.connect(self.edit_selected_notes)
        self.toggle_consent_button.clicked.connect(self.toggle_selected_consent)
        self.delete_button.clicked.connect(self.delete_selected_customer)
        self.close_button.clicked.connect(self.accept)

        self.load_customers()

    def closeEvent(self, event) -> None:
        self.db.close()
        event.accept()

    def load_customers(self) -> None:
        customers = self.db.list_active_customers()
        summary = self.db.get_database_summary()
        self.summary_label.setText(
            "ลูกค้าที่ใช้งานอยู่: {customers} คน | ใบหน้าที่ใช้จดจำ: {embeddings} รายการ | ประวัติการจดจำ: {events} รายการ".format(
                customers=summary["active_customers"],
                embeddings=summary["active_embeddings"],
                events=summary["recognition_events"],
            )
        )
        self.table.setRowCount(len(customers))
        for row_index, customer in enumerate(customers):
            consent_text = "เปิดใช้งาน" if customer.get("consent_status") == "granted" else "พักการจดจำ"
            values = [
                str(customer.get("id", "")),
                str(customer.get("name", "")),
                str(customer.get("active_embedding_count", 0)),
                consent_text,
                self._format_datetime(customer.get("last_seen_at")),
                self._format_datetime(customer.get("updated_at")),
                str(customer.get("notes", "") or ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in {self.COL_ID, self.COL_EMBEDDINGS}:
                    item.setTextAlignment(Qt.AlignCenter)
                item.setData(Qt.UserRole, customer.get("id"))
                self.table.setItem(row_index, col, item)

    @staticmethod
    def _format_datetime(value: str | None) -> str:
        if not value:
            return "-"
        return value.replace("T", " ").replace("+00:00", "")

    def _selected_customer_id(self) -> int | None:
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "ยังไม่ได้เลือกลูกค้า", "กรุณาเลือกลูกค้าจากตารางก่อน")
            return None
        item = self.table.item(selected[0].row(), self.COL_ID)
        if item is None:
            return None
        return int(item.text())

    def _selected_customer_name(self) -> str:
        selected = self.table.selectedItems()
        if not selected:
            return ""
        item = self.table.item(selected[0].row(), self.COL_NAME)
        return item.text() if item else ""

    def rename_selected_customer(self) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            return
        current_name = self._selected_customer_name()
        new_name, ok = QInputDialog.getText(self, "แก้ชื่อลูกค้า", "ชื่อใหม่:", text=current_name)
        if not ok:
            return
        try:
            self.db.rename_customer(customer_id, new_name)
            self.customers_changed.emit()
            self.load_customers()
        except Exception as exc:
            QMessageBox.critical(self, "แก้ชื่อไม่สำเร็จ", f"ไม่สามารถแก้ชื่อได้:\n{exc}")

    def edit_selected_notes(self) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            return
        row = self.table.currentRow()
        current_notes = self.table.item(row, self.COL_NOTES).text() if row >= 0 and self.table.item(row, self.COL_NOTES) else ""
        notes, ok = QInputDialog.getMultiLineText(self, "แก้หมายเหตุ", "หมายเหตุสำหรับใช้งานภายในร้าน:", current_notes)
        if not ok:
            return
        try:
            self.db.update_customer_notes(customer_id, notes)
            self.load_customers()
        except Exception as exc:
            QMessageBox.critical(self, "บันทึกหมายเหตุไม่สำเร็จ", f"ไม่สามารถบันทึกหมายเหตุได้:\n{exc}")

    def toggle_selected_consent(self) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            return
        row = self.table.currentRow()
        current_text = self.table.item(row, self.COL_CONSENT).text() if row >= 0 and self.table.item(row, self.COL_CONSENT) else "เปิดใช้งาน"
        new_status = "paused" if current_text == "เปิดใช้งาน" else "granted"
        new_text = "พักการจดจำ" if new_status == "paused" else "เปิดใช้งาน"
        reply = QMessageBox.question(
            self,
            "ยืนยันการเปลี่ยนสถานะ",
            f"ต้องการเปลี่ยนสถานะเป็น '{new_text}' หรือไม่?\n\nถ้าพักการจดจำ ระบบจะไม่ทักชื่อลูกค้าคนนี้จนกว่าจะเปิดใช้งานอีกครั้ง",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self.db.set_customer_consent(customer_id, new_status)
            self.customers_changed.emit()
            self.load_customers()
        except Exception as exc:
            QMessageBox.critical(self, "เปลี่ยนสถานะไม่สำเร็จ", f"ไม่สามารถเปลี่ยนสถานะได้:\n{exc}")

    def delete_selected_customer(self) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            return
        name = self._selected_customer_name()
        reply = QMessageBox.warning(
            self,
            "ยืนยันการลบข้อมูลลูกค้า",
            f"ต้องการลบข้อมูลของ '{name}' หรือไม่?\n\nระบบจะปิดใช้งานใบหน้าของลูกค้าคนนี้ แต่ยังเก็บประวัติบางส่วนไว้เพื่อ audit/debug ภายในระบบ",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if self.db.soft_delete_customer_by_id(customer_id):
                self.customers_changed.emit()
                self.load_customers()
            else:
                QMessageBox.information(self, "ไม่พบข้อมูล", "ไม่พบลูกค้าที่ต้องการลบ หรือถูกลบไปแล้ว")
        except Exception as exc:
            QMessageBox.critical(self, "ลบข้อมูลไม่สำเร็จ", f"ไม่สามารถลบข้อมูลได้:\n{exc}")
