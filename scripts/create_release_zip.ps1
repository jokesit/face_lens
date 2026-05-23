param(
    [string]$Version = "0.16",
    [switch]$SkipBuild,
    [switch]$IncludeLogs
)

# Create a clean ZIP package for pharmacy pilot distribution.
# Run from the project root inside the virtual environment:
#   .\scripts\create_release_zip.ps1

$ErrorActionPreference = "Stop"

function Write-Step($message) {
    Write-Host "`n==> $message" -ForegroundColor Cyan
}

function Remove-IfExists($path) {
    if (Test-Path $path) {
        Remove-Item -Recurse -Force $path -ErrorAction Stop
    }
}

$projectRoot = (Get-Location).Path
$releaseRoot = Join-Path $projectRoot "release"
$sourceDist = Join-Path $projectRoot "dist\FaceLens"
$stagingRoot = Join-Path $releaseRoot "FaceLens_$Version"
$stagingApp = Join-Path $stagingRoot "FaceLens"
$zipPath = Join-Path $releaseRoot "FaceLens_$Version`_Portable_PharmacyStandalone.zip"

Write-Step "Preparing release folder"
New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
Remove-IfExists $stagingRoot
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }

if (-not $SkipBuild) {
    Write-Step "Building FaceLens before release packaging"
    & .\scripts\build_windows.ps1
    if ($LASTEXITCODE -ne 0) {
        throw "build_windows.ps1 failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path (Join-Path $sourceDist "FaceLens.exe"))) {
    throw "dist\FaceLens\FaceLens.exe not found. Build the app before creating a release ZIP."
}

Write-Step "Copying app bundle"
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null
Copy-Item -Recurse -Force $sourceDist $stagingApp

Write-Step "Removing runtime data that should not be shipped"
# Do not ship logs. They may contain machine paths or support history.
if (-not $IncludeLogs) {
    Remove-IfExists (Join-Path $stagingApp "logs")
}

# Do not ship local customer databases/backups from development machines.
Remove-IfExists (Join-Path $stagingApp "backups")
Remove-IfExists (Join-Path $stagingApp "temp_files")

$dataDir = Join-Path $stagingApp "data"
if (Test-Path $dataDir) {
    Get-ChildItem $dataDir -File -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match "facelens\.db|\.db-wal$|\.db-shm$|settings\.json"
    } | Remove-Item -Force -ErrorAction SilentlyContinue
}

# Recreate expected writable folders as empty folders so users can understand the structure.
New-Item -ItemType Directory -Force -Path (Join-Path $stagingApp "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stagingApp "backups") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stagingApp "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stagingApp "temp_files") | Out-Null

Write-Step "Adding Thai documentation"
$docsOut = Join-Path $stagingRoot "docs"
New-Item -ItemType Directory -Force -Path $docsOut | Out-Null
Copy-Item -Force README_TH.md $stagingRoot
Copy-Item -Force RELEASE_NOTES.md $stagingRoot
Copy-Item -Force docs\*.md $docsOut

Write-Step "Checking release package for accidental customer data"
$forbidden = Get-ChildItem $stagingRoot -Recurse -File | Where-Object {
    $_.Name -match "facelens\.db|\.db-wal$|\.db-shm$"
}
if ($forbidden) {
    $forbidden | Select-Object FullName | Format-Table -AutoSize
    throw "Release package contains a database file. Remove it before distribution."
}

Write-Step "Creating ZIP"
Compress-Archive -Path (Join-Path $stagingRoot "*") -DestinationPath $zipPath -Force

Write-Host "`nPortable release ZIP created successfully." -ForegroundColor Green
Write-Host "ZIP: $zipPath" -ForegroundColor Green
Write-Host "Portable ZIP created. For the most professional store install, prefer scripts\build_installer_windows.ps1 and send the Setup.exe installer." -ForegroundColor Yellow
