"""Customer management dialog for FaceLens.

Batch 5 adds a production-style management screen so operators can review,
rename, pause, and deactivate customer profiles without editing SQLite directly.
Batch 10 adds privacy-delete and database maintenance tools for real shops.
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

from core.config import ENROLLMENT_DUPLICATE_WARNING_DISTANCE, RECOGNITION_EVENTS_RETENTION_DAYS, RECOMMENDED_MAX_EMBEDDINGS_PER_CUSTOMER
from core.database import Database


MANAGEMENT_STYLESHEET = """
QDialog { background-color: #FFFFFF; }
QLabel#DialogTitle { font-size: 22px; font-weight: bold; color: #1F618D; }
QLabel#SummaryLabel { font-size: 14px; color: #566573; }
QTableWidget {
    font-size: 13px;
    gridline-color: #EAECEE;
    selection-background-color: #1F618D;
    selection-color: #FFFFFF;
    alternate-background-color: #F8FBFD;
}
QTableWidget::item:selected {
    background-color: #1F618D;
    color: #FFFFFF;
    font-weight: bold;
}
QHeaderView::section { background-color: #EBF5FB; color: #1B4F72; padding: 6px; font-weight: bold; border: 1px solid #D6EAF8; }
QPushButton { background-color: #3498DB; color: white; font-size: 14px; font-weight: bold; padding: 9px; border-radius: 7px; border: none; }
QPushButton:hover { background-color: #2980B9; }
QPushButton#DangerButton { background-color: #E74C3C; }
QPushButton#DangerButton:hover { background-color: #C0392B; }
QPushButton#HardDeleteButton { background-color: #922B21; }
QPushButton#HardDeleteButton:hover { background-color: #7B241C; }
QPushButton#MaintenanceButton { background-color: #5D6D7E; }
QPushButton#MaintenanceButton:hover { background-color: #4D5656; }
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
        self.selected_customer_label = QLabel("ยังไม่ได้เลือกรายชื่อลูกค้า")
        self.selected_customer_label.setObjectName("SummaryLabel")

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
        self.table.setAlternatingRowColors(True)
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
        self.delete_button = QPushButton("ลบออกจากการจดจำ")
        self.delete_button.setObjectName("DangerButton")
        self.hard_delete_button = QPushButton("ลบถาวรตามคำขอลูกค้า")
        self.hard_delete_button.setObjectName("HardDeleteButton")
        self.prune_events_button = QPushButton("ล้างประวัติเก่า")
        self.prune_events_button.setObjectName("MaintenanceButton")
        self.optimize_button = QPushButton("ปรับฐานข้อมูลให้เร็วขึ้น")
        self.optimize_button.setObjectName("MaintenanceButton")
        self.duplicates_button = QPushButton("ตรวจรายชื่อซ้ำ")
        self.duplicates_button.setObjectName("MaintenanceButton")
        self.close_button = QPushButton("ปิด")
        self.close_button.setObjectName("NeutralButton")

        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.rename_button)
        buttons.addWidget(self.notes_button)
        buttons.addWidget(self.toggle_consent_button)
        buttons.addStretch(1)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.hard_delete_button)
        buttons.addWidget(self.close_button)

        maintenance_buttons = QHBoxLayout()
        maintenance_buttons.addStretch(1)
        maintenance_buttons.addWidget(self.duplicates_button)
        maintenance_buttons.addWidget(self.prune_events_button)
        maintenance_buttons.addWidget(self.optimize_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.selected_customer_label)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        layout.addLayout(maintenance_buttons)
        self.setLayout(layout)

        self.refresh_button.clicked.connect(self.load_customers)
        self.rename_button.clicked.connect(self.rename_selected_customer)
        self.notes_button.clicked.connect(self.edit_selected_notes)
        self.toggle_consent_button.clicked.connect(self.toggle_selected_consent)
        self.delete_button.clicked.connect(self.delete_selected_customer)
        self.hard_delete_button.clicked.connect(self.hard_delete_selected_customer)
        self.prune_events_button.clicked.connect(self.prune_old_events)
        self.optimize_button.clicked.connect(self.optimize_database)
        self.duplicates_button.clicked.connect(self.check_possible_duplicates)
        self.close_button.clicked.connect(self.accept)
        self.table.itemSelectionChanged.connect(self.update_selected_customer_label)
        self.table.itemDoubleClicked.connect(lambda _item: self.rename_selected_customer())

        self.load_customers()

    def closeEvent(self, event) -> None:
        self.db.close()
        event.accept()

    def load_customers(self) -> None:
        customers = self.db.list_active_customers()
        summary = self.db.get_database_summary()
        self.summary_label.setText(
            "ลูกค้าที่ใช้งานอยู่: {customers} คน | ใบหน้าที่ใช้จดจำ: {embeddings} รายการ | ประวัติการจดจำ: {events} รายการ | ขนาดฐานข้อมูล: {size:.2f} MB".format(
                customers=summary["active_customers"],
                embeddings=summary["active_embeddings"],
                events=summary["recognition_events"],
                size=summary.get("database_size_mb", 0.0),
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

    def update_selected_customer_label(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            self.selected_customer_label.setText("ยังไม่ได้เลือกรายชื่อลูกค้า")
            return

        name_item = self.table.item(row, self.COL_NAME)
        status_item = self.table.item(row, self.COL_CONSENT)
        embeddings_item = self.table.item(row, self.COL_EMBEDDINGS)
        name = name_item.text() if name_item else "-"
        status = status_item.text() if status_item else "-"
        embeddings = embeddings_item.text() if embeddings_item else "0"
        max_hint = f" / แนะนำไม่เกิน {RECOMMENDED_MAX_EMBEDDINGS_PER_CUSTOMER}"
        self.selected_customer_label.setText(
            f"กำลังเลือก: {name} | สถานะ: {status} | ใบหน้าที่ใช้จดจำ: {embeddings} รายการ{max_hint}"
        )

    def _selected_customer_id(self) -> int | None:
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "ยังไม่ได้เลือกลูกค้า", "กรุณาคลิกเลือกรายชื่อลูกค้าจากตารางก่อน รายชื่อที่เลือกจะเป็นแถบสีน้ำเงินเข้ม")
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


    def hard_delete_selected_customer(self) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            return
        name = self._selected_customer_name()
        reply = QMessageBox.warning(
            self,
            "ยืนยันการลบถาวร",
            f"ต้องการลบข้อมูลใบหน้าของ '{name}' แบบถาวรหรือไม่?\n\n"
            "การลบแบบนี้จะลบ customer, face embeddings และประวัติที่ผูกกับลูกค้าคนนี้ออกจากฐานข้อมูลจริง ๆ "
            "เหมาะสำหรับกรณีลูกค้าขอให้ลบข้อมูลส่วนบุคคล/ข้อมูลใบหน้า และไม่สามารถย้อนกลับได้ถ้าไม่มีไฟล์สำรอง",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if self.db.hard_delete_customer_by_id(customer_id):
                self.customers_changed.emit()
                self.load_customers()
                QMessageBox.information(self, "ลบถาวรแล้ว", f"ลบข้อมูลใบหน้าของ '{name}' แบบถาวรเรียบร้อยแล้ว")
            else:
                QMessageBox.information(self, "ไม่พบข้อมูล", "ไม่พบลูกค้าที่ต้องการลบ")
        except Exception as exc:
            QMessageBox.critical(self, "ลบถาวรไม่สำเร็จ", f"ไม่สามารถลบข้อมูลถาวรได้:\n{exc}")

    def prune_old_events(self) -> None:
        reply = QMessageBox.question(
            self,
            "ยืนยันการล้างประวัติเก่า",
            f"ต้องการลบประวัติการจดจำที่เก่ากว่า {RECOGNITION_EVENTS_RETENTION_DAYS} วันหรือไม่?\n\n"
            "ข้อมูลลูกค้าและใบหน้าจะไม่ถูกลบ การล้างนี้ช่วยให้ฐานข้อมูลเล็กและเร็วขึ้นเมื่อใช้งานไปนาน ๆ",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            removed = self.db.prune_recognition_events(RECOGNITION_EVENTS_RETENTION_DAYS)
            self.load_customers()
            QMessageBox.information(self, "ล้างประวัติเก่าแล้ว", f"ลบประวัติการจดจำเก่าออกแล้ว {removed} รายการ")
        except Exception as exc:
            QMessageBox.critical(self, "ล้างประวัติไม่สำเร็จ", f"ไม่สามารถล้างประวัติเก่าได้:\n{exc}")

    def check_possible_duplicates(self) -> None:
        """Show likely duplicate customer records based on average embeddings."""
        try:
            duplicates = self.db.find_possible_duplicate_customers(ENROLLMENT_DUPLICATE_WARNING_DISTANCE)
        except Exception as exc:
            QMessageBox.critical(self, "ตรวจรายชื่อซ้ำไม่สำเร็จ", f"ไม่สามารถตรวจรายชื่อซ้ำได้:\n{exc}")
            return

        if not duplicates:
            QMessageBox.information(
                self,
                "ไม่พบรายชื่อที่น่าจะซ้ำ",
                "ยังไม่พบลูกค้าที่ใบหน้าใกล้เคียงกันมากในระดับที่ควรตรวจสอบ\n\n"
                "ระบบจะตรวจซ้ำให้อีกครั้งทุกครั้งที่บันทึกลูกค้าใหม่",
            )
            return

        lines = []
        for item in duplicates[:15]:
            lines.append(
                f"- {item['left_name']} ↔ {item['right_name']} | ระยะ {item['distance']:.3f}"
            )
        if len(duplicates) > 15:
            lines.append(f"... และอีก {len(duplicates) - 15} คู่")

        QMessageBox.warning(
            self,
            "พบรายชื่อที่ควรตรวจสอบ",
            "ระบบพบลูกค้าบางรายที่ใบหน้าคล้ายกันมาก อาจเป็นคนเดียวกันที่ถูกบันทึกซ้ำ\n\n"
            + "\n".join(lines)
            + "\n\nคำแนะนำ: ตรวจสอบจากข้อมูลจริงก่อนลบหรือรวมข้อมูล เพื่อป้องกันการลบผิดคน",
        )

    def optimize_database(self) -> None:
        reply = QMessageBox.question(
            self,
            "ยืนยันการปรับฐานข้อมูล",
            "ต้องการปรับฐานข้อมูลให้กระชับและเร็วขึ้นหรือไม่?\n\n"
            "ระบบจะ checkpoint WAL, วิเคราะห์ index และ compact ไฟล์ฐานข้อมูล อาจใช้เวลาสั้น ๆ ตามขนาดข้อมูล",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self.db.optimize_database()
            self.load_customers()
            QMessageBox.information(self, "ปรับฐานข้อมูลแล้ว", "ปรับฐานข้อมูลเรียบร้อยแล้ว")
        except Exception as exc:
            QMessageBox.critical(self, "ปรับฐานข้อมูลไม่สำเร็จ", f"ไม่สามารถปรับฐานข้อมูลได้:\n{exc}")
