from __future__ import annotations

import os
import zipfile
from datetime import datetime
from pathlib import Path


EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "venv",
    ".venv",
    "env",
    "build",
    "dist",
    "release",
    "handoff",
    "data",
    "backups",
    "logs",
    "temp_files",
    ".deepface",
    ".idea",
    ".vscode",
    "node_modules",
}

EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".env",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-wal",
    ".db-shm",
    ".h5",
    ".onnx",
    ".exe",
    ".msi",
    ".zip",
    ".7z",
    ".rar",
    ".log",
}


def should_include(path: Path, project_dir: Path, output_dir: Path) -> bool:
    try:
        relative = path.relative_to(project_dir)
    except ValueError:
        return False

    if path.resolve().is_relative_to(output_dir.resolve()):
        return False

    parts = set(relative.parts)
    if parts & EXCLUDE_DIRS:
        return False

    name = path.name.lower()
    if any(name.endswith(suffix) for suffix in EXCLUDE_SUFFIXES):
        return False

    return True


def create_project_handoff(project_dir: str = ".", output_dir: str = "handoff", project_name: str = "facelens_handoff") -> Path:
    project_path = Path(project_dir).resolve()
    output_path = (project_path / output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = output_path / f"{project_name}_{timestamp}.zip"

    print(f"กำลังรวบรวมไฟล์เพื่อสร้าง: {zip_path.name} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(project_path):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if should_include(root_path / d, project_path, output_path)]
            for filename in files:
                file_path = root_path / filename
                if not should_include(file_path, project_path, output_path):
                    continue
                zipf.write(file_path, file_path.relative_to(project_path))

    print(f"✅ บีบอัดไฟล์เสร็จสิ้น: {zip_path}")
    return zip_path


if __name__ == "__main__":
    create_project_handoff(project_name="facelens_handoff")
