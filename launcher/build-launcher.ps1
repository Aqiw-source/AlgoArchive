param(
    [string]$Version,
    [string]$Compiler,
    [string]$ResourceCompiler,
    [string]$OutputPath
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
    throw "启动器版本 '$Version' 与 app.py 版本 '$sourceVersion' 不一致"
}
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $projectRoot "AlgoArchive.exe"
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

if (-not $Compiler) {
    $Compiler = (Get-Command g++.exe -ErrorAction Stop).Source
}
if (-not $ResourceCompiler) {
    $ResourceCompiler = (Get-Command windres.exe -ErrorAction Stop).Source
}

$versionParts = $Version.Split(".")
if ($versionParts.Count -ne 3) {
    throw "Version must use major.minor.patch format: $Version"
}
foreach ($part in $versionParts) {
    if ($part -notmatch "^\d+$") {
        throw "Version contains a non-numeric component: $Version"
    }
}
$numericVersion = ($versionParts -join ",") + ",0"

$buildRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "algoarchive-launcher-" + [Guid]::NewGuid().ToString("N")
)
New-Item -ItemType Directory -Path $buildRoot | Out-Null
try {
    Copy-Item -LiteralPath (Join-Path $projectRoot "launcher\AlgoArchive.cpp") -Destination $buildRoot
    Copy-Item -LiteralPath (Join-Path $projectRoot "ACM-ICPC-Windows.ico") -Destination (Join-Path $buildRoot "app.ico")

    $resourceText = Get-Content -LiteralPath (Join-Path $projectRoot "launcher\AlgoArchive.rc.in") -Raw
    $resourceText = $resourceText.Replace("__FILE_VERSION__", $numericVersion)
    $resourceText = $resourceText.Replace("__PRODUCT_VERSION__", $numericVersion)
    $resourceText = $resourceText.Replace("__VERSION__", $Version)
    $resourcePath = Join-Path $buildRoot "AlgoArchive.rc"
    [System.IO.File]::WriteAllText(
        $resourcePath,
        $resourceText,
        (New-Object System.Text.UTF8Encoding($false))
    )

    $resourceObject = Join-Path $buildRoot "AlgoArchive.res.o"
    & $ResourceCompiler $resourcePath -O coff -o $resourceObject
    if ($LASTEXITCODE -ne 0) {
        throw "Resource compilation failed with exit code $LASTEXITCODE"
    }

    $outputDirectory = Split-Path -Parent $OutputPath
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    & $Compiler `
        -std=c++17 `
        -Os `
        -s `
        -static `
        -static-libgcc `
        -static-libstdc++ `
        -municode `
        -mwindows `
        (Join-Path $buildRoot "AlgoArchive.cpp") `
        $resourceObject `
        -lshell32 `
        -luser32 `
        -o $OutputPath
    if ($LASTEXITCODE -ne 0) {
        throw "Launcher compilation failed with exit code $LASTEXITCODE"
    }
} finally {
    if (Test-Path -LiteralPath $buildRoot) {
        Remove-Item -LiteralPath $buildRoot -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) {
    throw "Launcher output was not created: $OutputPath"
}
$launcherVerifier = Join-Path $projectRoot "scripts\verify-launcher.py"
$iconPath = Join-Path $projectRoot "ACM-ICPC-Windows.ico"
$sourcePath = Join-Path $projectRoot "launcher\AlgoArchive.cpp"
$python = (Get-Command python.exe -ErrorAction Stop).Source
$verification = @(
    & $python -X utf8 $launcherVerifier $OutputPath `
        --version $Version --icon $iconPath --source $sourcePath --smoke-arguments 2>&1
)
if ($LASTEXITCODE -ne 0) {
    throw "启动器版本、图标、DLL 或参数转发检查失败:`n$(($verification -join "`n").Trim())"
}
$versionInfo = (Get-Item -LiteralPath $OutputPath).VersionInfo
foreach ($property in @("FileVersion", "ProductVersion")) {
    if (([string]$versionInfo.$property).Trim() -ne $Version) {
        throw "启动器 $property 与应用版本不一致: $($versionInfo.$property)"
    }
}
Get-Item -LiteralPath $OutputPath |
    Select-Object FullName, Length, @{Name="FileVersion";Expression={$_.VersionInfo.FileVersion}},
        @{Name="ProductVersion";Expression={$_.VersionInfo.ProductVersion}}
