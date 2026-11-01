param(
    [string]$ShortcutPath,
    [string]$ShortcutName = 'AlgoArchive.lnk'
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$targetPath = Join-Path $projectRoot 'start.bat'
$iconPath = Join-Path $projectRoot 'ACM-ICPC-Windows.ico'

foreach ($requiredPath in @($targetPath, $iconPath, (Join-Path $projectRoot 'runtime\python.exe'))) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required file is missing: $requiredPath"
    }
}

if ([string]::IsNullOrWhiteSpace($ShortcutPath)) {
    $desktopPath = [Environment]::GetFolderPath('Desktop')
    if ([string]::IsNullOrWhiteSpace($desktopPath)) {
        throw 'Unable to locate the current user desktop folder.'
    }
    if ([string]::IsNullOrWhiteSpace($ShortcutName)) {
        throw 'Shortcut name cannot be empty.'
    }
    $ShortcutPath = Join-Path $desktopPath $ShortcutName
}

$shortcutDirectory = Split-Path -Parent $ShortcutPath
if (-not [string]::IsNullOrWhiteSpace($shortcutDirectory) -and -not (Test-Path -LiteralPath $shortcutDirectory)) {
    throw "Shortcut directory does not exist: $shortcutDirectory"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = 'AlgoArchive local contest archive'
$shortcut.WindowStyle = 1
$shortcut.Save()

if (-not (Test-Path -LiteralPath $ShortcutPath)) {
    throw 'Shortcut file was not created.'
}

Write-Output "Shortcut created: $ShortcutPath"
