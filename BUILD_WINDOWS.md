# FaceLens Windows Build Guide

## Recommended build type

Use **onedir** packaging first. FaceLens depends on TensorFlow, DeepFace,
MediaPipe, OpenCV, FAISS, and PySide6. These packages are large and contain many
native DLL/data files, so onedir is more reliable than onefile for the first
public pharmacy release.

The output will be:

```text
dist/FaceLens/FaceLens.exe
```

Send the whole `dist/FaceLens` folder to a test machine, not only the EXE.

## Build release

```powershell
.\scripts\build_windows.ps1
```

## Build debug-console version

Use this when the release EXE opens and immediately closes:

```powershell
.\scripts\build_windows.ps1 -Debug
.\scripts\run_frozen_debug.ps1
```

The debug build shows a console window and also writes logs beside the EXE.

## Logs to ask from the pharmacy

After running the EXE, ask the user to send this folder:

```text
dist/FaceLens/logs
```

Important files:

```text
facelens_runtime.log
facelens_startup.log
facelens_crash.log
```

## Smoke test frozen app

```powershell
.\dist\FaceLens\FaceLens.exe --version
.\dist\FaceLens\FaceLens.exe --health-check
```

## Important notes

- Do not ship a real `data/facelens.db` with customer data.
- The runtime database is created beside the EXE in `data/facelens.db`.
- Backups are stored in `backups/` beside the EXE.
- DeepFace weights are stored in `.deepface/weights/` beside the EXE.
- For the first few releases, prefer zip distribution of the full onedir folder.
