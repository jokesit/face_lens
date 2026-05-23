"""Small JSON settings store for operator preferences.

This keeps shop-friendly settings such as the selected performance mode without
needing to edit environment variables or Python code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import DATA_DIR
from core.confidence_profiles import CONFIDENCE_PROFILES, DEFAULT_CONFIDENCE_PROFILE_KEY
from core.performance_profiles import DEFAULT_PROFILE_KEY, PERFORMANCE_PROFILES

SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "performance_profile": DEFAULT_PROFILE_KEY,
    "controls_collapsed": False,
    "confidence_profile": DEFAULT_CONFIDENCE_PROFILE_KEY,
}


class AppSettings:
    def __init__(self, path: str | Path = SETTINGS_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.values = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_SETTINGS)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return dict(DEFAULT_SETTINGS)
        except Exception:
            return dict(DEFAULT_SETTINGS)
        values = dict(DEFAULT_SETTINGS)
        values.update(raw)
        if values.get("performance_profile") not in PERFORMANCE_PROFILES:
            values["performance_profile"] = DEFAULT_PROFILE_KEY
        if values.get("confidence_profile") not in CONFIDENCE_PROFILES:
            values["confidence_profile"] = DEFAULT_CONFIDENCE_PROFILE_KEY
        return values

    def save(self) -> None:
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self.values, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    def get_performance_profile_key(self) -> str:
        key = str(self.values.get("performance_profile") or DEFAULT_PROFILE_KEY)
        return key if key in PERFORMANCE_PROFILES else DEFAULT_PROFILE_KEY

    def set_performance_profile_key(self, key: str) -> None:
        if key not in PERFORMANCE_PROFILES:
            raise ValueError(f"Unknown performance profile: {key}")
        self.values["performance_profile"] = key
        self.save()


    def get_controls_collapsed(self) -> bool:
        return bool(self.values.get("controls_collapsed", False))

    def set_controls_collapsed(self, collapsed: bool) -> None:
        self.values["controls_collapsed"] = bool(collapsed)
        self.save()


    def get_confidence_profile_key(self) -> str:
        key = str(self.values.get("confidence_profile") or DEFAULT_CONFIDENCE_PROFILE_KEY)
        return key if key in CONFIDENCE_PROFILES else DEFAULT_CONFIDENCE_PROFILE_KEY

    def set_confidence_profile_key(self, key: str) -> None:
        if key not in CONFIDENCE_PROFILES:
            raise ValueError(f"Unknown confidence profile: {key}")
        self.values["confidence_profile"] = key
        self.save()
