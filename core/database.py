# file: core/database.py (Robust Version)

import sqlite3
import numpy as np
import io
import os

class Database:
    def __init__(self, db_path='data/facelens.db'):
        db_dir = os.path.dirname(db_path)
        os.makedirs(db_dir, exist_ok=True)
        sqlite3.register_adapter(np.ndarray, self.adapt_array)
        sqlite3.register_converter("array", self.convert_array)
        self.conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        self.create_tables()

    def adapt_array(self, arr):
        out = io.BytesIO(); np.save(out, arr); out.seek(0)
        return sqlite3.Binary(out.read())

    def convert_array(self, text):
        out = io.BytesIO(text); out.seek(0)
        # เพิ่ม try-except เพื่อป้องกันข้อมูลเสียหาย
        try:
            return np.load(out)
        except:
            return None

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                avg_embedding array,
                image_count INTEGER NOT NULL
            )
        ''')
        self.conn.commit()

    def add_or_update_customer(self, name, new_embeddings):
        # 1. กรองค่า None ออกตั้งแต่ต้นทาง
        valid_embeddings = [emb for emb in new_embeddings if emb is not None]
        if not valid_embeddings:
            print("Warning: No valid embeddings to save.")
            return

        cursor = self.conn.cursor()
        cursor.execute("SELECT id, avg_embedding, image_count FROM customers WHERE name = ?", (name,))
        result = cursor.fetchone()
        
        new_avg_embedding = np.mean(valid_embeddings, axis=0)
        num_new_images = len(valid_embeddings)

        if result:
            customer_id, old_avg_embedding, old_image_count = result
            if old_avg_embedding is None: # กรณีข้อมูลเก่าเสียหาย
                old_avg_embedding = np.zeros_like(new_avg_embedding)
                old_image_count = 0
            
            total_images = old_image_count + num_new_images
            updated_avg_embedding = ((old_avg_embedding * old_image_count) + (new_avg_embedding * num_new_images)) / total_images
            updated_avg_embedding /= np.linalg.norm(updated_avg_embedding)

            cursor.execute("UPDATE customers SET avg_embedding = ?, image_count = ? WHERE id = ?", (updated_avg_embedding, total_images, customer_id))
            print(f"Updating customer {name}. Total images: {total_images}")
        else:
            new_avg_embedding /= np.linalg.norm(new_avg_embedding)
            cursor.execute("INSERT INTO customers (name, avg_embedding, image_count) VALUES (?, ?, ?)", (name, new_avg_embedding, num_new_images))
            print(f"Adding new customer {name} with {num_new_images} images.")
        
        self.conn.commit()

    def get_all_data_for_faiss(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, avg_embedding FROM customers")
        
        # 2. กรองข้อมูลที่ไม่สมบูรณ์ออกก่อนส่งไปสร้าง Index
        all_data = cursor.fetchall()
        clean_data = []
        for row in all_data:
            # ตรวจสอบว่า avg_embedding ไม่ใช่ None และเป็น numpy array จริงๆ
            if row[2] is not None and isinstance(row[2], np.ndarray):
                clean_data.append(row)
        return clean_data

    def __del__(self):
        self.conn.close()