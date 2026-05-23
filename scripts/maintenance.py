"""FaceLens database maintenance helper.

Run from project root:
    python scripts/maintenance.py --summary
    python scripts/maintenance.py --prune-events
    python scripts/maintenance.py --optimize
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import RECOGNITION_EVENTS_RETENTION_DAYS  # noqa: E402
from core.database import Database  # noqa: E402


def print_summary(db: Database) -> None:
    summary = db.get_database_summary()
    print("FaceLens database summary")
    print(f"- active customers: {summary['active_customers']}")
    print(f"- active embeddings: {summary['active_embeddings']}")
    print(f"- recognition events: {summary['recognition_events']}")
    print(f"- database size: {summary['database_size_mb']:.2f} MB")
    if summary.get("scale_warning"):
        print("- note: embedding count is high; keep backups and run maintenance regularly")


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain a FaceLens SQLite database.")
    parser.add_argument("--summary", action="store_true", help="Print database summary")
    parser.add_argument("--prune-events", action="store_true", help="Delete old recognition events")
    parser.add_argument("--retention-days", type=int, default=RECOGNITION_EVENTS_RETENTION_DAYS)
    parser.add_argument("--optimize", action="store_true", help="Run WAL checkpoint, ANALYZE and VACUUM")
    args = parser.parse_args()

    if not (args.summary or args.prune_events or args.optimize):
        args.summary = True

    db = Database()
    try:
        if args.summary:
            print_summary(db)
        if args.prune_events:
            removed = db.prune_recognition_events(args.retention_days)
            print(f"Removed old recognition events: {removed}")
        if args.optimize:
            db.optimize_database()
            print("Database optimized.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
