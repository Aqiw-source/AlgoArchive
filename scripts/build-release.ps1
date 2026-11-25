param(
    [string]$Version,
    [string]$OutputRoot
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$appSource = [System.IO.File]::ReadAllText((Join-Path $projectRoot "app.py"))
if ($appSource -notmatch '(?m)^APP_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"\s*$') {
    throw "无法从 app.py 读取 APP_VERSION"
}
$sourceVersion = $Matches[1]
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = $sourceVersion
} elseif ($Version -ne $sourceVersion) {
    throw "发行版本 '$Version' 与 app.py 版本 '$sourceVersion' 不一致"
}
$portableArguments = @{ Version = $Version }
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
    $portableArguments.OutputRoot = $OutputRoot
} else {
    $OutputRoot = Join-Path $projectRoot "dist"
}
$portable = & (Join-Path $PSScriptRoot "build-portable.ps1") @portableArguments
& (Join-Path $PSScriptRoot "verify-release.ps1") -ArchivePath $portable

$compilerCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }

if (-not $compilerCandidates) {
    Write-Warning "未找到 Inno Setup 6 的 ISCC.exe；便携 ZIP 已生成，安装包未编译。"
    exit 0
}

$compiler = $compilerCandidates | Select-Object -First 1
$packageRoot = Join-Path $OutputRoot "AlgoArchive-$Version-Windows-x64"
$packageDefine = "/DMyAppPackageRoot=$packageRoot"
$outputDefine = "/O$OutputRoot"
& $compiler "/DMyAppVersion=$Version" $packageDefine $outputDefine `
    (Join-Path $projectRoot "installer\AlgoArchive.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup 编译失败，退出码: $LASTEXITCODE"
}
$installer = Join-Path $OutputRoot "AlgoArchive-$Version-Windows-x64-Setup.exe"
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw "安装程序编译完成后未找到: $installer"
}
$installerVersionInfo = (Get-Item -LiteralPath $installer).VersionInfo
foreach ($property in @("FileVersion", "ProductVersion")) {
    $actualVersion = ([string]$installerVersionInfo.$property).Trim()
    if ($actualVersion -ne $Version) {
        throw "安装程序 $property 是 '$actualVersion'，与发行版本 '$Version' 不一致"
    }
}
$installerHash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
"$installerHash  $([System.IO.Path]::GetFileName($installer))" |
    Set-Content -LiteralPath "$installer.sha256" -Encoding ascii
Write-Output $installer
