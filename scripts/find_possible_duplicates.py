"""Find possible duplicate customer records in a FaceLens database.

Usage:
    python scripts\find_possible_duplicates.py
    python scripts\find_possible_duplicates.py --threshold 0.65

This script uses each customer's current average embedding. It is designed as a
safe maintenance aid for standalone pharmacy databases. It does not change data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import ENROLLMENT_DUPLICATE_WARNING_DISTANCE  # noqa: E402
from core.database import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Find likely duplicate FaceLens customers.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=ENROLLMENT_DUPLICATE_WARNING_DISTANCE,
        help="Maximum average-embedding distance to report.",
    )
    args = parser.parse_args()

    db = Database()
    try:
        duplicates = db.find_possible_duplicate_customers(args.threshold)
    finally:
        db.close()

    if not duplicates:
        print(f"No likely duplicates found at threshold <= {args.threshold:.3f}.")
        return 0

    print(f"Possible duplicate customers at threshold <= {args.threshold:.3f}:")
    for item in duplicates:
        print(
            f"- {item['left_name']} (ID {item['left_id']}) <-> "
            f"{item['right_name']} (ID {item['right_id']}) | "
            f"distance={item['distance']:.4f} | "
            f"embeddings={item['left_image_count']}/{item['right_image_count']}"
        )
    print("\nReview manually before deleting or merging any customer record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
