# file: core/database.py (Final Version with Search)

import sqlite3, numpy as np, io, os

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
        try: return np.load(out)
        except: return None

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

    def get_customer_by_name(self, name):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, avg_embedding, image_count FROM customers WHERE name = ?", (name,))
        result = cursor.fetchone()
        if result:
            return {"id": result[0], "name": result[1], "avg_embedding": result[2], "image_count": result[3]}
        return None

    def add_or_update_customer(self, name, new_embeddings):
        valid_embeddings = [emb for emb in new_embeddings if emb is not None]
        if not valid_embeddings: return

        cursor = self.conn.cursor()
        existing_customer = self.get_customer_by_name(name)
        new_avg_embedding = np.mean(valid_embeddings, axis=0)
        num_new_images = len(valid_embeddings)

        if existing_customer:
            old_avg_embedding = existing_customer['avg_embedding']
            old_image_count = existing_customer['image_count']
            if old_avg_embedding is None: old_avg_embedding, old_image_count = np.zeros_like(new_avg_embedding), 0
            
            total_images = old_image_count + num_new_images
            updated_avg_embedding = ((old_avg_embedding * old_image_count) + (new_avg_embedding * num_new_images)) / total_images
            updated_avg_embedding /= np.linalg.norm(updated_avg_embedding)
            cursor.execute("UPDATE customers SET avg_embedding = ?, image_count = ? WHERE id = ?", (updated_avg_embedding, total_images, existing_customer['id']))
        else:
            new_avg_embedding /= np.linalg.norm(new_avg_embedding)
            cursor.execute("INSERT INTO customers (name, avg_embedding, image_count) VALUES (?, ?, ?)", (name, new_avg_embedding, num_new_images))
        self.conn.commit()

    def get_all_data_for_faiss(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, avg_embedding FROM customers")
        clean_data = [row for row in cursor.fetchall() if row[2] is not None and isinstance(row[2], np.ndarray)]
        return clean_data

    def __del__(self):
        self.conn.close()