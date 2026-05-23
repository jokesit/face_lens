# FaceLens Windows Build and Installer Guide

## Recommended distribution types

FaceLens now supports two distribution modes:

1. **Installer mode — recommended for real pharmacy use**
   - Installs to `C:\Program Files\FaceLens`
   - Creates a Desktop shortcut and Start Menu shortcut
   - Stores writable data in `C:\ProgramData\FaceLens`
   - Best for non-technical pharmacy staff

2. **Portable ZIP mode — useful for testing**
   - User extracts a folder and opens `FaceLens.exe`
   - Runtime data stays beside the EXE
   - Good for quick testing, but less professional than installer mode

## Build the EXE bundle

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\build_windows.ps1
```

The output is:

```text
dist\FaceLens\FaceLens.exe
```

## Build the professional Windows installer

FaceLens uses Inno Setup for the Windows installer. After installing Inno Setup
on the build machine, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\build_installer_windows.ps1
```

The installer is created at:

```text
release\FaceLens_0.16_Setup.exe
```

The installer will:

```text
Install app files to:  C:\Program Files\FaceLens
Store shop data in:   C:\ProgramData\FaceLens
Create Desktop icon:  FaceLens
Create Start Menu:    FaceLens
```

## Why data is not stored in Program Files

Windows normally protects `C:\Program Files`. Normal users may not be able to
write databases, logs, backups, or downloaded AI model weights there.

For installed releases, FaceLens stores runtime data in:

```text
C:\ProgramData\FaceLens
```

Important folders:

```text
C:\ProgramData\FaceLens\data       # SQLite database and settings
C:\ProgramData\FaceLens\backups    # database backups
C:\ProgramData\FaceLens\logs       # support logs
C:\ProgramData\FaceLens\temp_files # temporary files / matplotlib cache
C:\ProgramData\FaceLens\.deepface  # DeepFace model weights
```

## Build debug-console version

Use this if the release EXE opens and immediately closes:

```powershell
.\scripts\build_windows.ps1 -Debug
.\scripts\run_frozen_debug.ps1
```

## Smoke test frozen app

```powershell
.\dist\FaceLens\FaceLens.exe --version
.\dist\FaceLens\FaceLens.exe --health-check
```

## Create portable ZIP

Installer mode is recommended, but a clean portable ZIP can still be created:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\create_release_zip.ps1
```

Output:

```text
release\FaceLens_0.16_Portable_PharmacyStandalone.zip
```

## Logs to ask from the pharmacy

Installed mode:

```text
C:\ProgramData\FaceLens\logs
```

Portable ZIP mode:

```text
FaceLens\logs
```

Important files:

```text
facelens_runtime.log
facelens_startup.log
facelens_crash.log
```

## Release safety rules

- Do not ship a real `facelens.db` with customer data.
- Do not ship development logs or backups.
- Prefer installer mode for pharmacies.
- Keep portable ZIP only for quick testing or support.
- Test on a clean Windows machine before sending to a real pharmacy.
