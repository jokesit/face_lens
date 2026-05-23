r"""Command-line health check for FaceLens.

Usage:
    python scripts\health_check.py
    python scripts\health_check.py --camera
    python scripts\health_check.py --camera-index 1 --camera
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import CAMERA_INDEX
from core.health_check import run_health_checks


def main() -> int:
    parser = argparse.ArgumentParser(description="FaceLens health check")
    parser.add_argument("--camera", action="store_true", help="เปิดกล้องเพื่อตรวจจริง ควรปิดโปรแกรมหลักก่อน")
    parser.add_argument("--camera-index", type=int, default=CAMERA_INDEX, help="หมายเลขกล้องที่ต้องการตรวจ")
    args = parser.parse_args()

    report = run_health_checks(camera_index=args.camera_index, include_camera=args.camera)
    print(report.to_plain_text())
    return 1 if report.has_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
