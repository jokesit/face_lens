param(
    [switch]$Debug,
    [switch]$SkipHealthCheck,
    [switch]$SkipSmokeTest
)

# Build FaceLens for Windows with PyInstaller.
# Run from the project root inside your virtual environment:
#   .\scripts\build_windows.ps1
# Debug-console build:
#   .\scripts\build_windows.ps1 -Debug

$ErrorActionPreference = "Stop"

function Write-Step($message) {
    Write-Host "`n==> $message" -ForegroundColor Cyan
}

Write-Step "Checking Python imports"
python -c "import cv2, mediapipe, faiss, deepface, PySide6, matplotlib, pandas, charset_normalizer; print('imports ok')"

Write-Step "Running syntax check"
python -m compileall -f main.py add_customer_dialog.py customer_management_dialog.py health_check_dialog.py core scripts

if (-not $SkipHealthCheck) {
    Write-Step "Running source health check"
    python scripts\health_check.py
}

Write-Step "Warming up DeepFace model before packaging"
python scripts\warmup_models.py

if ($Debug) {
    $env:FACELENS_BUILD_DEBUG = "1"
    $buildName = "FaceLensDebug"
    Write-Step "Building debug-console onedir app"
} else {
    Remove-Item Env:\FACELENS_BUILD_DEBUG -ErrorAction SilentlyContinue
    $buildName = "FaceLens"
    Write-Step "Building release onedir app"
}

# Prevent stale locked executables from producing misleading builds.
Get-Process FaceLens, FaceLensDebug -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

pyinstaller --clean --noconfirm FaceLens.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$exePath = Join-Path "dist" (Join-Path $buildName "$buildName.exe")
if (-not (Test-Path $exePath)) {
    throw "Build finished but EXE was not found: $exePath"
}

# Remove stale logs before smoke tests so old errors cannot make a fresh build
# look broken or, worse, make a failed launch look successful.
$logsDir = Join-Path "dist" (Join-Path $buildName "logs")
if (Test-Path $logsDir) {
    Remove-Item -Recurse -Force $logsDir -ErrorAction SilentlyContinue
}

if (-not $SkipSmokeTest) {
    Write-Step "Running frozen smoke test"
    & $exePath --version
    if ($LASTEXITCODE -ne 0) { throw "Frozen app --version failed with exit code $LASTEXITCODE" }

    & $exePath --health-check
    if ($LASTEXITCODE -ne 0) { throw "Frozen app --health-check failed with exit code $LASTEXITCODE" }

    $runtimeLog = Join-Path "dist" (Join-Path $buildName "logs\facelens_runtime.log")
    if (Test-Path $runtimeLog) {
        $tail = Get-Content $runtimeLog -Tail 200 -ErrorAction SilentlyContinue
        if ($tail -match "Traceback|ModuleNotFoundError|ImportError|DLL load failed") {
            Write-Host "`nFrozen smoke test wrote an error to $runtimeLog" -ForegroundColor Red
            $tail | Select-String -Pattern "Traceback|ModuleNotFoundError|ImportError|DLL load failed" -Context 2,4
            throw "Frozen smoke test failed. Check $runtimeLog"
        }
    }
}

Write-Host "`nBuild finished successfully." -ForegroundColor Green
Write-Host "Output folder: dist\$buildName" -ForegroundColor Green
Write-Host "Executable: $exePath" -ForegroundColor Green
Write-Host "Runtime logs after launch: dist\$buildName\logs" -ForegroundColor Yellow
