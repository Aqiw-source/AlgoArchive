param(
    [string]$Version = "2.2.5",
    [string]$Compiler,
    [string]$ResourceCompiler,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
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

    $objdump = Join-Path (Split-Path -Parent $Compiler) "objdump.exe"
    if (-not (Test-Path -LiteralPath $objdump -PathType Leaf)) {
        $objdump = (Get-Command objdump.exe -ErrorAction Stop).Source
    }
    $importDump = & $objdump -p $OutputPath
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect launcher imports with objdump"
    }
    $imports = @(
        [regex]::Matches(
            ($importDump -join "`n"),
            "DLL Name:\s*([^\r\n]+)"
        ) | ForEach-Object {
            $_.Groups[1].Value.Trim().ToLowerInvariant()
        }
    )
    $forbiddenImports = @(
        $imports | Where-Object {
            $_ -match "^libgcc_s_" -or
            $_ -match "^libstdc\+\+-" -or
            $_ -match "^libwinpthread-"
        }
    )
    if ($forbiddenImports.Count -gt 0) {
        throw (
            "Launcher still depends on unbundled MinGW runtime DLLs: " +
            ($forbiddenImports -join ", ")
        )
    }
} finally {
    if (Test-Path -LiteralPath $buildRoot) {
        Remove-Item -LiteralPath $buildRoot -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) {
    throw "Launcher output was not created: $OutputPath"
}
Get-Item -LiteralPath $OutputPath |
    Select-Object FullName, Length, @{Name="ProductVersion";Expression={$_.VersionInfo.ProductVersion}}
