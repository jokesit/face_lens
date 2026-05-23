param(
    [string]$Target = "",
    [string]$ShortcutPath = ""
)

# Optional helper for portable ZIP users. The installer creates this shortcut
# automatically, but this script is useful if someone uses the portable build.

$ErrorActionPreference = "Stop"

if (-not $Target) {
    $Target = Join-Path (Get-Location).Path "dist\FaceLens\FaceLens.exe"
}
if (-not (Test-Path $Target)) {
    throw "ไม่พบ FaceLens.exe ที่: $Target"
}

if (-not $ShortcutPath) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $desktop "FaceLens.lnk"
}

$targetPath = (Resolve-Path $Target).Path
$workingDir = Split-Path $targetPath -Parent
$iconPath = Join-Path $workingDir "assets\logo.ico"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $workingDir
if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
}
$shortcut.Description = "FaceLens - ระบบช่วยจำชื่อลูกค้าสำหรับร้านยา"
$shortcut.Save()

Write-Host "Desktop shortcut created: $ShortcutPath" -ForegroundColor Green
