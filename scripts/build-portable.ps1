param(
    [string]$Version = "2.0.1",
    [string]$OutputRoot
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $projectRoot "dist"
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$packageName = "AlgoArchive-$Version-Windows-x64"
$staging = Join-Path $OutputRoot $packageName
$archivePath = Join-Path $OutputRoot "$packageName.zip"

$requiredFiles = @(
    "app.py",
    "启动.bat",
    "start.bat",
    "创建桌面快捷方式.bat",
    "README.md",
    "使用说明.txt",
    "CHANGELOG.md",
    "TEST_REPORT.md",
    "THIRD_PARTY.txt",
    "LICENSE-PENDING.md",
    "ACM-ICPC-Windows.ico"
)
foreach ($name in $requiredFiles) {
    $path = Join-Path $projectRoot $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "缺少发布文件: $path"
    }
}
foreach ($name in @("runtime", "web")) {
    $path = Join-Path $projectRoot $name
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "缺少发布目录: $path"
    }
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}
New-Item -ItemType Directory -Path $staging | Out-Null

foreach ($name in $requiredFiles) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $name) -Destination $staging
}
foreach ($name in @("runtime", "web")) {
    $source = Join-Path $projectRoot $name
    if (Test-Path -LiteralPath $source -PathType Container) {
        Copy-Item -LiteralPath $source -Destination $staging -Recurse
    }
}
$screenshots = Join-Path $projectRoot "docs\screenshots"
if (Test-Path -LiteralPath $screenshots -PathType Container) {
    New-Item -ItemType Directory -Path (Join-Path $staging "docs") | Out-Null
    Copy-Item -LiteralPath $screenshots -Destination (Join-Path $staging "docs") -Recurse
}
$shortcutScript = Join-Path $projectRoot "scripts\create-desktop-shortcut.ps1"
if (-not (Test-Path -LiteralPath $shortcutScript -PathType Leaf)) {
    throw "缺少发布文件: $shortcutScript"
}
New-Item -ItemType Directory -Path (Join-Path $staging "scripts") | Out-Null
Copy-Item -LiteralPath $shortcutScript -Destination (Join-Path $staging "scripts")

Get-ChildItem -LiteralPath $staging -Recurse -Force -Directory |
    Where-Object { $_.Name -in @("__pycache__", ".qa-data", ".test-tmp", "backups") } |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $staging -Recurse -Force -File |
    Where-Object { $_.Name -in @("archive.sqlite3", "runtime.lock") -or $_.Extension -eq ".lnk" } |
    Remove-Item -Force

$hashLines = Get-ChildItem -LiteralPath $staging -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relative = [System.IO.Path]::GetRelativePath($staging, $_.FullName).Replace("\", "/")
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
$hashLines | Set-Content -LiteralPath (Join-Path $staging "SHA256SUMS.txt") -Encoding utf8

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $archivePath -CompressionLevel Optimal
$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
"$archiveHash  $([System.IO.Path]::GetFileName($archivePath))" |
    Set-Content -LiteralPath "$archivePath.sha256" -Encoding ascii

Write-Output $archivePath
