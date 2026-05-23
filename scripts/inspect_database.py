"""Print a small FaceLens database summary.

Run from project root:
    python scripts/inspect_database.py
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import Database  # noqa: E402


def main() -> None:
    db = Database()
    try:
        customers = db.conn.execute(
            "SELECT COUNT(*) AS count FROM customers WHERE deleted_at IS NULL"
        ).fetchone()["count"]
        embeddings = db.get_active_embedding_count()
        events = db.conn.execute("SELECT COUNT(*) AS count FROM recognition_events").fetchone()["count"]
        print("FaceLens database summary")
        print(f"- active customers: {customers}")
        print(f"- active embeddings: {embeddings}")
        print(f"- recognition events: {events}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
