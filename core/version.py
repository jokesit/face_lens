"""FaceLens release metadata.

Keep the public version in one small module so the GUI, CLI health check,
release script, installer script, and documentation can stay aligned.
"""

from __future__ import annotations

APP_NAME = "FaceLens"
APP_VERSION = "0.16"
APP_RELEASE_STAGE = "Pharmacy Standalone Installer Pilot"


def version_text() -> str:
    return f"{APP_NAME} {APP_VERSION}"
