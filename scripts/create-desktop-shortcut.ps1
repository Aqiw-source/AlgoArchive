param(
    [string]$ShortcutPath,
    [string]$ShortcutName,
    [switch]$IncludeStartMenu
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$targetPath = Join-Path $projectRoot 'AlgoArchive.exe'
$defaultShortcutName = (
    -join (0x7B97, 0x6CD5, 0x6863, 0x6848 | ForEach-Object { [char]$_ })
) + '.lnk'

foreach ($requiredPath in @($targetPath, (Join-Path $projectRoot 'runtime\python.exe'))) {
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
        $ShortcutName = $defaultShortcutName
    }
    $ShortcutPath = Join-Path $desktopPath $ShortcutName
}

function Save-LauncherShortcut {
    param([string]$Path)

    $shortcutDirectory = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($shortcutDirectory) -and -not (Test-Path -LiteralPath $shortcutDirectory)) {
        throw "Shortcut directory does not exist: $shortcutDirectory"
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $targetPath
    $shortcut.Arguments = ''
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.IconLocation = "$targetPath,0"
    $shortcut.Description = 'AlgoArchive local contest archive'
    $shortcut.WindowStyle = 1
    $shortcut.Save()

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Shortcut file was not created: $Path"
    }
    Write-Output "Shortcut created: $Path"
}

Save-LauncherShortcut -Path $ShortcutPath

if ($IncludeStartMenu) {
    if ([string]::IsNullOrWhiteSpace($ShortcutName)) {
        $ShortcutName = $defaultShortcutName
    }
    $programsPath = Join-Path (
        [Environment]::GetFolderPath('ApplicationData')
    ) 'Microsoft\Windows\Start Menu\Programs'
    if (-not (Test-Path -LiteralPath $programsPath -PathType Container)) {
        New-Item -ItemType Directory -Path $programsPath | Out-Null
    }
    Save-LauncherShortcut -Path (Join-Path $programsPath $ShortcutName)
}
