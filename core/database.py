# file: core/database.py

from __future__ import annotations

import io
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from core.config import DB_PATH, RECOGNITION_EVENTS_RETENTION_DAYS, STANDALONE_WARN_EMBEDDINGS


class Database:
    """SQLite persistence layer for FaceLens.

    Batch 4 upgraded the storage model from one averaged embedding per customer
    to production-friendly tables. Batch 10 adds maintenance, backup restore,
    and privacy-delete helpers for standalone pharmacy deployments.
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

    def _ensure_open(self) -> None:
        if getattr(self, "conn", None) is None:
            raise RuntimeError("Database connection is already closed.")

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
            self._add_column_if_missing("customers", "deleted_at", "TEXT")
            self._add_column_if_missing("customers", "consent_status", "TEXT NOT NULL DEFAULT 'granted'")
            self._add_column_if_missing("customers", "notes", "TEXT")

            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS face_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    embedding array NOT NULL,
                    quality_score REAL,
                    source TEXT NOT NULL DEFAULT 'enrollment',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recognition_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    predicted_name TEXT,
                    distance REAL,
                    result_type TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE SET NULL
                )
                """
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_face_embeddings_customer_id ON face_embeddings(customer_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_face_embeddings_active ON face_embeddings(is_active)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_face_embeddings_active_customer ON face_embeddings(is_active, customer_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_active_name ON customers(deleted_at, consent_status, name)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_recognition_events_created_at ON recognition_events(created_at)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_recognition_events_customer_id ON recognition_events(customer_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_recognition_events_type_created ON recognition_events(result_type, created_at)")

            now = self._utc_now()
            self.conn.execute(
                """
                UPDATE customers
                SET created_at = COALESCE(created_at, ?),
                    updated_at = COALESCE(updated_at, ?),
                    consent_status = COALESCE(consent_status, 'granted')
                """,
                (now, now),
            )
            self._migrate_legacy_avg_embeddings()
            self.conn.commit()

    def _add_column_if_missing(self, table: str, column: str, definition: str) -> None:
        existing_columns = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing_columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _migrate_legacy_avg_embeddings(self) -> None:
        """Copy old customers.avg_embedding rows into face_embeddings once."""
        now = self._utc_now()
        rows = self.conn.execute(
            """
            SELECT c.id, c.avg_embedding
            FROM customers c
            WHERE c.avg_embedding IS NOT NULL
              AND c.deleted_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM face_embeddings fe WHERE fe.customer_id = c.id
              )
            """
        ).fetchall()
        for row in rows:
            embedding = row["avg_embedding"]
            if isinstance(embedding, np.ndarray):
                self.conn.execute(
                    """
                    INSERT INTO face_embeddings
                        (customer_id, embedding, quality_score, source, is_active, created_at)
                    VALUES (?, ?, NULL, 'legacy_avg_migration', 1, ?)
                    """,
                    (row["id"], self._normalize_embedding(embedding), now),
                )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _normalize_embedding(embedding: np.ndarray) -> np.ndarray:
        emb = np.asarray(embedding, dtype=np.float32)
        norm = np.linalg.norm(emb)
        if norm == 0:
            raise ValueError("Cannot normalize zero-vector embedding.")
        return (emb / norm).astype(np.float32)

    def get_customer_by_name(self, name: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT id, name, avg_embedding, image_count, created_at, updated_at,
                       deleted_at, consent_status, notes
                FROM customers
                WHERE name = ? AND deleted_at IS NULL
                """,
                (name.strip(),),
            ).fetchone()
        return dict(row) if row else None

    def get_customer_by_id(self, customer_id: int) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT id, name, avg_embedding, image_count, created_at, updated_at,
                       deleted_at, consent_status, notes
                FROM customers
                WHERE id = ? AND deleted_at IS NULL
                """,
                (customer_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_active_customers(self) -> list[dict]:
        """Return active customers with embedding/event counts for the management screen."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT
                    c.id,
                    c.name,
                    c.image_count,
                    c.created_at,
                    c.updated_at,
                    c.consent_status,
                    COALESCE(c.notes, '') AS notes,
                    COUNT(fe.id) AS active_embedding_count,
                    MAX(re.created_at) AS last_seen_at
                FROM customers c
                LEFT JOIN face_embeddings fe
                    ON fe.customer_id = c.id AND fe.is_active = 1
                LEFT JOIN recognition_events re
                    ON re.customer_id = c.id AND re.result_type = 'recognized'
                WHERE c.deleted_at IS NULL
                GROUP BY c.id
                ORDER BY LOWER(c.name)
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_database_summary(self) -> dict[str, int]:
        with self._lock:
            active_customers = self.conn.execute(
                "SELECT COUNT(*) AS count FROM customers WHERE deleted_at IS NULL"
            ).fetchone()["count"]
            active_embeddings = self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM face_embeddings fe
                JOIN customers c ON c.id = fe.customer_id
                WHERE fe.is_active = 1 AND c.deleted_at IS NULL
                """
            ).fetchone()["count"]
            events = self.conn.execute("SELECT COUNT(*) AS count FROM recognition_events").fetchone()["count"]
        return {
            "active_customers": int(active_customers),
            "active_embeddings": int(active_embeddings),
            "recognition_events": int(events),
            "database_size_mb": self.get_database_size_mb(),
            "scale_warning": int(active_embeddings) >= STANDALONE_WARN_EMBEDDINGS,
        }

    def add_or_update_customer(self, name: str, new_embeddings: list[np.ndarray]) -> None:
        clean_name = name.strip()
        valid_embeddings: list[np.ndarray] = []
        for emb in new_embeddings:
            if emb is None:
                continue
            try:
                valid_embeddings.append(self._normalize_embedding(emb))
            except ValueError:
                continue

        if not clean_name or not valid_embeddings:
            return

        now = self._utc_now()
        with self._lock:
            existing = self.get_customer_by_name(clean_name)
            if existing:
                customer_id = int(existing["id"])
            else:
                cursor = self.conn.execute(
                    """
                    INSERT INTO customers
                        (name, avg_embedding, image_count, created_at, updated_at, consent_status)
                    VALUES (?, NULL, 0, ?, ?, 'granted')
                    """,
                    (clean_name, now, now),
                )
                customer_id = int(cursor.lastrowid)

            for emb in valid_embeddings:
                self.conn.execute(
                    """
                    INSERT INTO face_embeddings
                        (customer_id, embedding, quality_score, source, is_active, created_at)
                    VALUES (?, ?, NULL, 'enrollment', 1, ?)
                    """,
                    (customer_id, emb, now),
                )

            self._refresh_customer_embedding_summary(customer_id, now)
            self.conn.commit()

    def rename_customer(self, customer_id: int, new_name: str) -> None:
        clean_name = new_name.strip()
        if not clean_name:
            raise ValueError("ชื่อลูกค้าห้ามว่าง")
        now = self._utc_now()
        with self._lock:
            self.conn.execute(
                "UPDATE customers SET name = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (clean_name, now, customer_id),
            )
            self.conn.commit()

    def update_customer_notes(self, customer_id: int, notes: str) -> None:
        now = self._utc_now()
        with self._lock:
            self.conn.execute(
                "UPDATE customers SET notes = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (notes.strip(), now, customer_id),
            )
            self.conn.commit()

    def set_customer_consent(self, customer_id: int, consent_status: str) -> None:
        if consent_status not in {"granted", "paused"}:
            raise ValueError("consent_status must be 'granted' or 'paused'")
        now = self._utc_now()
        is_active = 1 if consent_status == "granted" else 0
        with self._lock:
            self.conn.execute(
                "UPDATE customers SET consent_status = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (consent_status, now, customer_id),
            )
            self.conn.execute("UPDATE face_embeddings SET is_active = ? WHERE customer_id = ?", (is_active, customer_id))
            self._refresh_customer_embedding_summary(customer_id, now)
            self.conn.commit()

    def _refresh_customer_embedding_summary(self, customer_id: int, now: str | None = None) -> None:
        rows = self.conn.execute(
            """
            SELECT embedding
            FROM face_embeddings
            WHERE customer_id = ? AND is_active = 1
            ORDER BY id
            """,
            (customer_id,),
        ).fetchall()
        embeddings = [row["embedding"] for row in rows if isinstance(row["embedding"], np.ndarray)]
        now = now or self._utc_now()
        if not embeddings:
            self.conn.execute(
                "UPDATE customers SET avg_embedding = NULL, image_count = 0, updated_at = ? WHERE id = ?",
                (now, customer_id),
            )
            return

        avg_embedding = np.mean(np.asarray(embeddings, dtype=np.float32), axis=0)
        avg_embedding = self._normalize_embedding(avg_embedding)
        self.conn.execute(
            """
            UPDATE customers
            SET avg_embedding = ?, image_count = ?, updated_at = ?
            WHERE id = ?
            """,
            (avg_embedding, len(embeddings), now, customer_id),
        )

    def get_all_data_for_faiss(self) -> list[tuple[int, str, np.ndarray]]:
        """Return active embedding rows for FAISS."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT fe.id AS embedding_id, c.name, fe.embedding
                FROM face_embeddings fe
                JOIN customers c ON c.id = fe.customer_id
                WHERE fe.is_active = 1
                  AND c.deleted_at IS NULL
                  AND c.consent_status = 'granted'
                ORDER BY c.id, fe.id
                """
            ).fetchall()
        return [
            (int(row["embedding_id"]), row["name"], row["embedding"])
            for row in rows
            if isinstance(row["embedding"], np.ndarray)
        ]

    def get_active_embedding_count(self) -> int:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM face_embeddings fe
                JOIN customers c ON c.id = fe.customer_id
                WHERE fe.is_active = 1 AND c.deleted_at IS NULL AND c.consent_status = 'granted'
                """
            ).fetchone()
        return int(row["count"] if row else 0)

    def find_customer_id_by_name(self, name: str) -> int | None:
        if not name or name == "Unknown":
            return None
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM customers WHERE name = ? AND deleted_at IS NULL",
                (name.strip(),),
            ).fetchone()
        return int(row["id"]) if row else None

    def log_recognition_event(
        self,
        predicted_name: str | None,
        distance: float | None,
        result_type: str,
        note: str | None = None,
    ) -> None:
        now = self._utc_now()
        clean_name = predicted_name.strip() if predicted_name else None
        with self._lock:
            self._ensure_open()
            customer_id = self.find_customer_id_by_name(clean_name) if clean_name else None
            self.conn.execute(
                """
                INSERT INTO recognition_events
                    (customer_id, predicted_name, distance, result_type, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (customer_id, clean_name, distance, result_type, note, now),
            )
            self.conn.commit()

    def soft_delete_customer(self, name: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM customers WHERE name = ? AND deleted_at IS NULL",
                (name.strip(),),
            ).fetchone()
            if not row:
                return False
            return self.soft_delete_customer_by_id(int(row["id"]))

    def soft_delete_customer_by_id(self, customer_id: int) -> bool:
        """Deactivate a customer without physically deleting recognition history."""
        now = self._utc_now()
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM customers WHERE id = ? AND deleted_at IS NULL",
                (customer_id,),
            ).fetchone()
            if not row:
                return False
            self.conn.execute("UPDATE customers SET deleted_at = ?, updated_at = ? WHERE id = ?", (now, now, customer_id))
            self.conn.execute("UPDATE face_embeddings SET is_active = 0 WHERE customer_id = ?", (customer_id,))
            self.conn.commit()
            return True


    def hard_delete_customer_by_id(self, customer_id: int) -> bool:
        """Permanently remove a customer's biometric data and direct event history.

        Use this when a customer asks the shop to delete their face data. This is
        intentionally separate from soft_delete_customer_by_id(), which only hides
        a customer from recognition.
        """
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM customers WHERE id = ?",
                (customer_id,),
            ).fetchone()
            if not row:
                return False
            self.conn.execute("DELETE FROM face_embeddings WHERE customer_id = ?", (customer_id,))
            self.conn.execute("DELETE FROM recognition_events WHERE customer_id = ?", (customer_id,))
            self.conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
            self.conn.commit()
            return True

    def prune_recognition_events(self, retention_days: int = RECOGNITION_EVENTS_RETENTION_DAYS) -> int:
        """Delete old recognition events and return the number of removed rows."""
        retention_days = max(1, int(retention_days))
        with self._lock:
            cursor = self.conn.execute(
                """
                DELETE FROM recognition_events
                WHERE datetime(created_at) < datetime('now', ?)
                """,
                (f"-{retention_days} days",),
            )
            removed = int(cursor.rowcount if cursor.rowcount is not None else 0)
            self.conn.commit()
            return removed

    def optimize_database(self) -> None:
        """Checkpoint WAL, refresh SQLite statistics, and compact the DB file."""
        with self._lock:
            self.conn.commit()
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.conn.execute("ANALYZE")
            self.conn.commit()
            self.conn.execute("VACUUM")
            self.conn.commit()

    def get_database_size_mb(self) -> float:
        total_bytes = 0
        for path in (self.db_path, Path(str(self.db_path) + "-wal"), Path(str(self.db_path) + "-shm")):
            if path.exists():
                total_bytes += path.stat().st_size
        return round(total_bytes / (1024 * 1024), 2)

    def restore_from_backup(self, source: str | Path) -> Path:
        """Restore this database connection from a SQLite .db backup file."""
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"Backup file not found: {source_path}")
        with self._lock:
            self.conn.commit()
            with sqlite3.connect(str(source_path), detect_types=sqlite3.PARSE_DECLTYPES) as source_conn:
                required = {"customers", "face_embeddings", "recognition_events"}
                tables = {
                    row[0]
                    for row in source_conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                missing = required - tables
                if missing:
                    raise ValueError("ไฟล์สำรองนี้ไม่ใช่ฐานข้อมูล FaceLens ที่ถูกต้อง")
                source_conn.backup(self.conn)
            self._configure_connection()
            self.create_tables()
            self.conn.commit()
        return source_path

    def backup_to(self, destination: str | Path) -> Path:
        """Create a consistent SQLite backup, including WAL changes."""
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with sqlite3.connect(str(destination_path)) as backup_conn:
                self.conn.backup(backup_conn)
        return destination_path

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
