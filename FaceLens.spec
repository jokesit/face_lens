# -*- mode: python ; coding: utf-8 -*-

"""PyInstaller spec for FaceLens.

Professional packaging notes:
- Default build is ONEDIR, not onefile. TensorFlow/DeepFace/PySide6 are large
  native stacks; onedir is more reliable, faster to start, and easier to debug.
- Runtime data is stored beside FaceLens.exe: data/, backups/, logs/,
  temp_files/, .deepface/.
- Do not ship a real customer database in public releases.
"""

from __future__ import annotations

import importlib.util
import os
import site
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None
project_root = Path.cwd()
assets_dir = project_root / "assets"
debug_build = os.environ.get("FACELENS_BUILD_DEBUG", "0") == "1"
app_name = "FaceLensDebug" if debug_build else "FaceLens"

binaries = []
datas = []
hiddenimports = []


def _add_existing_file_as_binary(file_path: Path, target_dir: str) -> None:
    if file_path.exists() and file_path.is_file():
        binaries.append((str(file_path), target_dir))


def _add_existing_dir_as_data(dir_path: Path, target_dir: str) -> None:
    if dir_path.exists() and dir_path.is_dir():
        datas.append((str(dir_path), target_dir))


# Application assets only. Runtime customer data is intentionally external.
if assets_dir.exists():
    datas.append((str(assets_dir), "assets"))

# Native/data-heavy packages. Be explicit because DeepFace/TensorFlow/MediaPipe
# use dynamic imports and data files that PyInstaller may not discover reliably.
for package_name in ("mediapipe", "deepface", "retinaface"):
    try:
        hiddenimports += collect_submodules(package_name)
        datas += collect_data_files(package_name)
    except Exception:
        pass

# MediaPipe imports matplotlib.drawing utilities at import time. FaceLens does
# not use matplotlib for charts, but the frozen app still needs enough of it
# available or it crashes before the UI starts with:
# "ModuleNotFoundError: No module named 'matplotlib'".
try:
    hiddenimports += collect_submodules("matplotlib")
    datas += collect_data_files("matplotlib")
except Exception:
    pass

# DeepFace imports pandas at module import time. FaceLens does not use pandas
# directly, but excluding it makes the frozen app crash before startup with:
# "ModuleNotFoundError: No module named 'pandas'". Keep pandas and its data
# files in the bundle.
try:
    hiddenimports += collect_submodules("pandas")
    datas += collect_data_files("pandas")
    binaries += collect_dynamic_libs("pandas")
except Exception:
    pass

# Requests may warn or fail if neither charset_normalizer nor chardet is
# collected. Bundle charset_normalizer explicitly because requests depends on
# it in the current venv.
for package_name in ("requests", "urllib3", "idna", "certifi", "charset_normalizer", "chardet"):
    try:
        hiddenimports += collect_submodules(package_name)
        datas += collect_data_files(package_name)
        binaries += collect_dynamic_libs(package_name)
    except Exception:
        pass

for package_name in ("tensorflow", "keras"):
    try:
        hiddenimports += collect_submodules(package_name)
        datas += collect_data_files(package_name)
        binaries += collect_dynamic_libs(package_name)
    except Exception:
        pass

# FAISS needs special handling on Windows. The faiss-cpu wheel ships compiled
# .pyd/.dll files and sometimes dependent DLLs in sibling folders such as
# faiss_cpu.libs. If these are not collected, the frozen app fails with:
# "ImportError: DLL load failed while importing _swigfaiss".
try:
    hiddenimports += collect_submodules("faiss")
    datas += collect_data_files("faiss")
    binaries += collect_dynamic_libs("faiss")

    faiss_spec = importlib.util.find_spec("faiss")
    if faiss_spec and faiss_spec.submodule_search_locations:
        faiss_root = Path(list(faiss_spec.submodule_search_locations)[0]).resolve()
        for pattern in ("*.pyd", "*.dll"):
            for native_file in faiss_root.rglob(pattern):
                relative_parent = native_file.parent.relative_to(faiss_root.parent)
                _add_existing_file_as_binary(native_file, str(relative_parent))

    for site_dir in site.getsitepackages():
        site_path = Path(site_dir)
        for libs_name in ("faiss_cpu.libs", "faiss.libs", "faiss_cpu", "faiss_gpu.libs"):
            libs_dir = site_path / libs_name
            if libs_dir.exists():
                # Keep the folder name in the frozen app so dependent DLL lookup
                # works the same way as it does in the virtual environment.
                for native_file in libs_dir.rglob("*.dll"):
                    relative_parent = native_file.parent.relative_to(site_path)
                    _add_existing_file_as_binary(native_file, str(relative_parent))
except Exception:
    pass

# Common dynamically imported modules used by the current FaceLens stack.
hiddenimports += [
    "cv2",
    "faiss",
    "faiss.loader",
    "faiss.swigfaiss",
    "faiss.swigfaiss_avx2",
    "faiss.swigfaiss_avx512",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "numpy",
    "matplotlib",
    "matplotlib.pyplot",
    "matplotlib.backends.backend_agg",
    "matplotlib._path",
    "pandas",
    "pandas._libs",
    "pandas._libs.tslibs",

    "requests",
    "requests.compat",
    "requests.models",
    "requests.sessions",
    "urllib3",
    "idna",
    "certifi",
    "charset_normalizer.api",
    "charset_normalizer.legacy",
    "charset_normalizer.models",
    "charset_normalizer.utils",
    "charset_normalizer.version",
    "charset_normalizer.cd",
    "charset_normalizer",
    "charset_normalizer.md",
    "charset_normalizer.md__mypyc",
    "chardet",
    "sqlite3",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "deepface.DeepFace",
    "deepface.models.facial_recognition.ArcFace",
    "deepface.modules.modeling",
    "deepface.modules.representation",
]

# Bundle DeepFace weights if they already exist on the build machine. This makes
# offline pharmacy installs work more reliably. If absent, warmup_models.py
# should download them before packaging.
deepface_weights = Path.home() / ".deepface" / "weights"
if deepface_weights.exists():
    datas.append((str(deepface_weights), ".deepface/weights"))

excludes = [
    "notebook",
    "IPython",
    "pytest",
    "jupyter",
]

icon_path = assets_dir / "logo.ico"
runtime_hooks = [str(project_root / "runtime_hooks" / "facelens_runtime_hook.py")]

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=runtime_hooks,
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=debug_build,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=app_name,
)
