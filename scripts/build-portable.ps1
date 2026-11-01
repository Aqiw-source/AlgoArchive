param(
    [string]$Version = "2.2.5",
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
    "cph_runner.py",
    "run.py",
    "AlgoArchive.exe",
    "start.bat",
    "自检.bat",
    "self_check.py",
    "README.md",
    "使用说明.txt",
    "CHANGELOG.md",
    "TEST_REPORT.md",
    "LOCAL_FIXES.md",
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
$launcherVersionInfo = (Get-Item -LiteralPath (Join-Path $projectRoot "AlgoArchive.exe")).VersionInfo
foreach ($property in @("FileVersion", "ProductVersion")) {
    $actualVersion = ([string]$launcherVersionInfo.$property).Trim()
    if ($actualVersion -ne $Version) {
        throw "AlgoArchive.exe 的 $property 是 '$actualVersion'，与发布版本 '$Version' 不一致；请先重新生成启动器。"
    }
}
$launcherVerifier = Join-Path $projectRoot "scripts\verify-launcher.py"
if (-not (Test-Path -LiteralPath $launcherVerifier -PathType Leaf)) {
    throw "缺少启动器依赖检查脚本: $launcherVerifier"
}
$python = (Get-Command python.exe -ErrorAction Stop).Source
$launcherProbe = @(
    & $python `
        -X utf8 `
        $launcherVerifier `
        (Join-Path $projectRoot "AlgoArchive.exe") 2>&1
)
if ($LASTEXITCODE -ne 0) {
    throw (
        "原生启动器依赖检查失败；请重新生成静态链接启动器。" +
        (($launcherProbe -join "`n").Trim())
    )
}
foreach ($name in @("runtime", "web", "licenses")) {
    $path = Join-Path $projectRoot $name
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "缺少发布目录: $path"
    }
}
$runtimePth = Join-Path $projectRoot "runtime\python313._pth"
if (-not (Test-Path -LiteralPath $runtimePth -PathType Leaf)) {
    throw "缺少内置 Python 路径文件: $runtimePth"
}
$runtimePthLines = @(Get-Content -LiteralPath $runtimePth)
if (-not ($runtimePthLines | Where-Object { $_.Trim() -eq ".." })) {
    $runtimePthLines += ".."
    [System.IO.File]::WriteAllLines(
        $runtimePth,
        $runtimePthLines,
        (New-Object System.Text.ASCIIEncoding)
    )
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
foreach ($name in @("runtime", "web", "licenses")) {
    $source = Join-Path $projectRoot $name
    if (Test-Path -LiteralPath $source -PathType Container) {
        Copy-Item -LiteralPath $source -Destination $staging -Recurse
    }
}

$utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
Get-ChildItem -LiteralPath $staging -Recurse -File |
    Where-Object { $_.Extension -in @(".bat", ".ps1") } |
    ForEach-Object {
        $text = $utf8.GetString([System.IO.File]::ReadAllBytes($_.FullName))
        $text = $text -replace "`r`n", "`n"
        $text = $text -replace "`n", "`r`n"
        [System.IO.File]::WriteAllText($_.FullName, $text, $utf8NoBom)
    }

$bundledPython = Join-Path $staging "runtime\python.exe"
$runtimeProbe = @(
    & $bundledPython -X utf8 -c "import app, cph_runner; print(app.APP_VERSION)" 2>&1
)
$runtimeProbeText = ($runtimeProbe -join "`n").Trim()
if ($LASTEXITCODE -ne 0 -or $runtimeProbeText -ne $Version) {
    throw "内置 Python 无法导入应用模块或版本不一致: $runtimeProbeText"
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
