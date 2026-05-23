param(
    [string]$ExePath = "dist\FaceLensDebug\FaceLensDebug.exe"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $ExePath)) {
    throw "Debug EXE not found: $ExePath. Build it first with .\scripts\build_windows.ps1 -Debug"
}

Write-Host "Starting FaceLens debug EXE..." -ForegroundColor Cyan
Write-Host "If it closes, check the logs folder beside the EXE." -ForegroundColor Yellow
& $ExePath
