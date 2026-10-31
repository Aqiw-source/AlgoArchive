param(
    [string]$Version = "2.2.1"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$portable = & (Join-Path $PSScriptRoot "build-portable.ps1") -Version $Version
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
& $compiler (Join-Path $projectRoot "installer\AlgoArchive.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup 编译失败，退出码: $LASTEXITCODE"
}
$installer = Join-Path $projectRoot "dist\AlgoArchive-$Version-Windows-x64-Setup.exe"
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw "安装程序编译完成后未找到: $installer"
}
$installerHash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
"$installerHash  $([System.IO.Path]::GetFileName($installer))" |
    Set-Content -LiteralPath "$installer.sha256" -Encoding ascii
Write-Output $installer
