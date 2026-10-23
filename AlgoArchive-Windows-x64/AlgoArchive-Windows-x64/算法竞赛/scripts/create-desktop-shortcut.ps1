param(
    [string]$ShortcutPath
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$targetPath = Join-Path $projectRoot '启动.bat'
$iconPath = Join-Path $projectRoot '算法竞赛.ico'

foreach ($requiredPath in @($targetPath, $iconPath, (Join-Path $projectRoot 'runtime\python.exe'))) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "缺少必要文件: $requiredPath"
    }
}

if ([string]::IsNullOrWhiteSpace($ShortcutPath)) {
    $desktopPath = [Environment]::GetFolderPath('Desktop')
    if ([string]::IsNullOrWhiteSpace($desktopPath)) {
        throw '无法定位当前用户的桌面目录'
    }
    $ShortcutPath = Join-Path $desktopPath '算法竞赛.lnk'
}

$shortcutDirectory = Split-Path -Parent $ShortcutPath
if (-not [string]::IsNullOrWhiteSpace($shortcutDirectory) -and -not (Test-Path -LiteralPath $shortcutDirectory)) {
    throw "快捷方式目录不存在: $shortcutDirectory"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = 'AlgoArchive 算法竞赛管理工具'
$shortcut.WindowStyle = 1
$shortcut.Save()

if (-not (Test-Path -LiteralPath $ShortcutPath)) {
    throw '快捷方式写入后未找到目标文件'
}

Write-Host "快捷方式已创建: $ShortcutPath"
