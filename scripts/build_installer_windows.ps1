param(
    [string]$InnoSetupCompiler = ""
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Find-Iscc {
    param([string]$ProvidedPath)

    if ($ProvidedPath -and (Test-Path $ProvidedPath)) {
        return $ProvidedPath
    }

    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        "C:\Program Files\Inno Setup 5\ISCC.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    throw "ISCC.exe was not found. Please install Inno Setup 6 or pass -InnoSetupCompiler with the full path to ISCC.exe."
}

function Assert-Exists {
    param(
        [string]$Path,
        [string]$Message
    )

    if (-not (Test-Path $Path)) {
        throw $Message
    }
}

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Step "Checking required files"

$DistDir = Join-Path $ProjectRoot "dist\FaceLens"
$ExePath = Join-Path $DistDir "FaceLens.exe"
$InstallerSpecPath = Join-Path $ProjectRoot "installer\FaceLens_Installer.iss"
$IconPath = Join-Path $ProjectRoot "assets\logo.ico"

Assert-Exists $DistDir "dist\FaceLens was not found. Run .\scripts\build_windows.ps1 first."
Assert-Exists $ExePath "dist\FaceLens\FaceLens.exe was not found. Run .\scripts\build_windows.ps1 first."
Assert-Exists $InstallerSpecPath "installer\FaceLens_Installer.iss was not found."
Assert-Exists $IconPath "assets\logo.ico was not found. The installer and desktop shortcut require this icon file."

$ReleaseDir = Join-Path $ProjectRoot "release"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

Write-Step "Locating Inno Setup compiler"

$IsccPath = Find-Iscc -ProvidedPath $InnoSetupCompiler
Write-Host "ISCC.exe: $IsccPath" -ForegroundColor Green

Write-Step "Building installer"

& $IsccPath $InstallerSpecPath
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup build failed with exit code $LASTEXITCODE."
}

Write-Step "Checking installer output"

$ExpectedInstaller = Join-Path $ReleaseDir "FaceLens_0.16_Setup.exe"
if (-not (Test-Path $ExpectedInstaller)) {
    $latestInstaller = Get-ChildItem $ReleaseDir -Filter "*Setup*.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($latestInstaller) {
        Write-Host "Installer created: $($latestInstaller.FullName)" -ForegroundColor Green
    } else {
        throw "Installer build completed but no setup EXE was found in the release folder."
    }
} else {
    Write-Host "Installer created: $ExpectedInstaller" -ForegroundColor Green
}

Write-Host ""
Write-Host "Build installer finished successfully." -ForegroundColor Green
Write-Host "Recommended test:" -ForegroundColor Yellow
Write-Host "1. Uninstall the previous FaceLens version first, or install over it." -ForegroundColor Yellow
Write-Host "2. Run release\FaceLens_0.16_Setup.exe" -ForegroundColor Yellow
Write-Host "3. Confirm app is installed to C:\Program Files\FaceLens" -ForegroundColor Yellow
Write-Host "4. Confirm C:\Program Files\FaceLens\FaceLens.ico exists" -ForegroundColor Yellow
Write-Host "5. Confirm Desktop shortcut uses the FaceLens icon" -ForegroundColor Yellow
Write-Host "6. Confirm runtime data is stored in C:\ProgramData\FaceLens" -ForegroundColor Yellow
