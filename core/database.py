import sqlite3
import numpy as np
import io
import os

class Database:
    def __init__(self, db_path='data/facelens.db'):
        """
        คลาสสำหรับจัดการฐานข้อมูล SQLite ทั้งหมด
        """
        # --- 2. เพิ่มโค้ด 2 บรรทัดนี้ ---
        # สร้าง directory ถ้ายังไม่มี
        db_dir = os.path.dirname(db_path)
        os.makedirs(db_dir, exist_ok=True)
        # -----------------------------

        # แปลง numpy array เป็น text และกลับกัน
        sqlite3.register_adapter(np.ndarray, self.adapt_array)
        sqlite3.register_converter("array", self.convert_array)

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        self.create_tables()

    def adapt_array(self, arr):
        """แปลง numpy array เป็น binary เพื่อเก็บใน DB"""
        out = io.BytesIO()
        np.save(out, arr)
        out.seek(0)
        return sqlite3.Binary(out.read())

    def convert_array(self, text):
        """แปลง binary กลับเป็น numpy array"""
        out = io.BytesIO(text)
        out.seek(0)
        return np.load(out)

    def create_tables(self):
        """สร้างตารางถ้ายังไม่มี"""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                embedding array,
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )
        ''')
        self.conn.commit()

    def add_or_update_customer(self, name, embeddings):
        """เพิ่มลูกค้าใหม่ หรืออัปเดต embeddings ของลูกค้าเดิม"""
        cursor = self.conn.cursor()
        # ตรวจสอบว่ามีชื่อนี้อยู่แล้วหรือไม่
        cursor.execute("SELECT id FROM customers WHERE name = ?", (name,))
        result = cursor.fetchone()

        if result:
            # ถ้ามี ให้อัปเดต
            customer_id = result[0]
            print(f"Updating existing customer: {name} (ID: {customer_id})")
        else:
            # ถ้าไม่มี ให้เพิ่มใหม่
            cursor.execute("INSERT INTO customers (name) VALUES (?)", (name,))
            customer_id = cursor.lastrowid
            print(f"Adding new customer: {name} (ID: {customer_id})")

        # เพิ่ม embeddings ทั้งหมดสำหรับลูกค้านี้
        for emb in embeddings:
            cursor.execute("INSERT INTO embeddings (customer_id, embedding) VALUES (?, ?)", (customer_id, emb))
        
        self.conn.commit()
        print(f"Successfully added {len(embeddings)} new embeddings for {name}.")

    def get_all_data_for_faiss(self):
        """ดึงข้อมูลทั้งหมดเพื่อใช้สร้าง Faiss Index"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT e.id, c.name, e.embedding
            FROM embeddings e
            JOIN customers c ON e.customer_id = c.id
        ''')
        # คืนค่าเป็น list ของ (embedding_id, customer_name, embedding_array)
        return cursor.fetchall()

    def __del__(self):
        """ปิดการเชื่อมต่อเมื่อ object ถูกทำลาย"""
        self.conn.close()