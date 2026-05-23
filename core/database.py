# file: core/database.py

from __future__ import annotations

import io
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from core.config import DB_PATH


class Database:
    """Small SQLite wrapper for FaceLens.

    Batch 1 keeps the existing `customers` table compatible, but makes the
    connection safer for desktop use: WAL mode, busy timeout, explicit close,
    robust numpy serialization, and lightweight migrations for timestamps.
    """

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

        sqlite3.register_adapter(np.ndarray, self.adapt_array)
        sqlite3.register_converter("array", self.convert_array)

        self.conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
            timeout=10,
        )
        self.conn.row_factory = sqlite3.Row
        self._configure_connection()
        self.create_tables()

    @staticmethod
    def adapt_array(arr: np.ndarray) -> sqlite3.Binary:
        out = io.BytesIO()
        np.save(out, np.asarray(arr, dtype=np.float32))
        return sqlite3.Binary(out.getvalue())

    @staticmethod
    def convert_array(blob: bytes) -> np.ndarray | None:
        try:
            out = io.BytesIO(blob)
            return np.load(out, allow_pickle=False).astype(np.float32)
        except Exception:
            return None

    def _configure_connection(self) -> None:
        with self._lock:
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")
            self.conn.execute("PRAGMA busy_timeout = 5000")

    def create_tables(self) -> None:
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    avg_embedding array,
                    image_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._add_column_if_missing("customers", "created_at", "TEXT")
            self._add_column_if_missing("customers", "updated_at", "TEXT")
            now = self._utc_now()
            self.conn.execute(
                "UPDATE customers SET created_at = COALESCE(created_at, ?), updated_at = COALESCE(updated_at, ?)",
                (now, now),
            )
            self.conn.commit()

    def _add_column_if_missing(self, table: str, column: str, definition: str) -> None:
        existing_columns = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing_columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def get_customer_by_name(self, name: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT id, name, avg_embedding, image_count, created_at, updated_at FROM customers WHERE name = ?",
                (name.strip(),),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def add_or_update_customer(self, name: str, new_embeddings: list[np.ndarray]) -> None:
        clean_name = name.strip()
        valid_embeddings = [np.asarray(emb, dtype=np.float32) for emb in new_embeddings if emb is not None]
        if not clean_name or not valid_embeddings:
            return

        new_avg_embedding = np.mean(valid_embeddings, axis=0).astype(np.float32)
        norm = np.linalg.norm(new_avg_embedding)
        if norm == 0:
            return
        new_avg_embedding = new_avg_embedding / norm
        num_new_images = len(valid_embeddings)
        now = self._utc_now()

        with self._lock:
            existing = self.get_customer_by_name(clean_name)
            if existing:
                old_avg = existing["avg_embedding"]
                old_count = int(existing["image_count"] or 0)
                if old_avg is None or old_count <= 0:
                    updated_avg = new_avg_embedding
                    total_images = num_new_images
                else:
                    total_images = old_count + num_new_images
                    updated_avg = ((old_avg * old_count) + (new_avg_embedding * num_new_images)) / total_images
                    updated_norm = np.linalg.norm(updated_avg)
                    if updated_norm == 0:
                        return
                    updated_avg = (updated_avg / updated_norm).astype(np.float32)

                self.conn.execute(
                    "UPDATE customers SET avg_embedding = ?, image_count = ?, updated_at = ? WHERE id = ?",
                    (updated_avg, total_images, now, existing["id"]),
                )
            else:
                self.conn.execute(
                    "INSERT INTO customers (name, avg_embedding, image_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (clean_name, new_avg_embedding, num_new_images, now, now),
                )
            self.conn.commit()

    def get_all_data_for_faiss(self) -> list[tuple[int, str, np.ndarray]]:
        with self._lock:
            rows = self.conn.execute("SELECT id, name, avg_embedding FROM customers ORDER BY id").fetchall()
        return [
            (row["id"], row["name"], row["avg_embedding"])
            for row in rows
            if isinstance(row["avg_embedding"], np.ndarray)
        ]

    def close(self) -> None:
        conn = getattr(self, "conn", None)
        if conn is not None:
            with self._lock:
                conn.close()
                self.conn = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
