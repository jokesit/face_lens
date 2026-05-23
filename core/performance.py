"""Small performance helpers for camera/recognition throttling."""

from __future__ import annotations

from core.recognition_types import FaceBox


def box_iou(a: FaceBox, b: FaceBox) -> float:
    """Return intersection-over-union for two face boxes."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b

    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh

    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)

    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    intersection = iw * ih
    if intersection <= 0:
        return 0.0

    union = (aw * ah) + (bw * bh) - intersection
    if union <= 0:
        return 0.0
    return float(intersection / union)
