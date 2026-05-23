"""Application-level exception logging."""

from __future__ import annotations

import sys
import time
import traceback

from core.config import LOG_DIR


def install_exception_logger() -> None:
    """Write uncaught Python exceptions to logs/facelens_crash.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "facelens_crash.log"

    def _hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open(log_path, "a", encoding="utf-8") as file:
                file.write("\n" + "=" * 80 + "\n")
                file.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                file.write(text)
        finally:
            print(text)
            sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
