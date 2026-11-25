param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem
$projectRoot = Split-Path -Parent $PSScriptRoot
$fullPath = [System.IO.Path]::GetFullPath($ArchivePath)
if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
    throw "发布包不存在: $fullPath"
}

$archive = [System.IO.Compression.ZipFile]::OpenRead($fullPath)
$verificationRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "algoarchive-release-check-" + [Guid]::NewGuid().ToString("N")
)
try {
    $entries = @($archive.Entries | ForEach-Object { $_.FullName.Replace("\", "/") })
    $required = @(
        "app.py",
        "cph_runner.py",
        "run.py",
        "AlgoArchive.exe",
        "start.bat",
        "自检.bat",
        "self_check.py",
        "web/index.html",
        "web/app.js",
        "web/style.css",
        "web/codex-theme.css",
        "web/mobile.css",
        "web/manual.html",
        "web/manual.css",
        "web/workspace-updates.css",
        "web/sidebar-art.png",
        "web/sidebar-art-blended.webp",
        "web/sidebar-art-debug.png",
        "web/sidebar-art-thinking.png",
        "web/sidebar-art-debug-blended.webp",
        "web/sidebar-art-thinking-blended.webp",
        "web/nav-icons/home.png",
        "web/nav-icons/SOURCES.md",
        "web/platform-icons/codeforces.png",
        "web/platform-icons/atcoder.png",
        "web/platform-icons/acwing.png",
        "web/platform-icons/luogu.png",
        "web/platform-icons/niuke.png",
        "web/platform-icons/lanqiao.png",
        "web/platform-icons/hdu.png",
        "web/platform-icons/matiji.png",
        "web/platform-icons/leetcode.png",
        "web/platform-icons/poj.png",
        "web/platform-icons/SOURCES.md",
        "runtime/python313._pth",
        "runtime/python.exe",
        "README.md",
        "使用说明.txt",
        "CHANGELOG.md",
        "TEST_REPORT.md",
        "docs/history/TEST_REPORT-through-2.4.0.md",
        "THIRD_PARTY.txt",
        "SHA256SUMS.txt",
        "build-info.json",
        "LICENSE",
        "DISCLAIMER.md",
        "ACM-ICPC-Windows.ico",
        "scripts/create-desktop-shortcut.ps1"
    )
    $required += @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'web') -Recurse -File | ForEach-Object {
        [IO.Path]::GetRelativePath($projectRoot, $_.FullName).Replace('\','/')
    })
    foreach ($name in $required) {
        if (-not ($entries -contains $name)) {
            throw "发布包缺少必要文件: $name"
        }
    }
    $forbiddenPatterns = @(
        "(^|/)archive\.sqlite3$",
        "(^|/)runtime\.lock$",
        "(^|/)data/",
        "(^|/)codes/",
        "(^|/)avatar/",
        "(^|/)config\.json$",
        "(^|/)backups/",
        "(^|/)\.qa-data/",
        "(^|/)\.qa-[^/]+/",
        "(^|/)tests/",
        "(^|/)__pycache__/",
        "\.lnk$"
    )
    foreach ($entry in $entries) {
        foreach ($pattern in $forbiddenPatterns) {
            if ($entry -match $pattern) {
                throw "发布包包含禁止内容: $entry"
            }
        }
    }
    $lfExtensions = @(".py", ".js", ".cjs", ".mjs", ".css", ".html")
    foreach ($entry in $archive.Entries) {
        $extension = [System.IO.Path]::GetExtension($entry.FullName)
        if ($extension -notin ($lfExtensions + @(".bat", ".ps1"))) {
            continue
        }
        $reader = New-Object System.IO.StreamReader(
            $entry.Open(),
            (New-Object System.Text.UTF8Encoding($false, $true))
        )
        try {
            $text = $reader.ReadToEnd()
        } finally {
            $reader.Dispose()
        }
        if ($extension -in $lfExtensions -and $text.Contains([char]13)) {
            throw "Release source must use LF: $($entry.FullName)"
        }
        if ($extension -in @(".bat", ".ps1") -and $text -match "(?<!\x0d)\x0a|\x0d(?!\x0a)") {
            throw "Windows scripts must use CRLF: $($entry.FullName)"
        }
    }
    $runtimePthEntry = $archive.GetEntry("runtime/python313._pth")
    $reader = New-Object System.IO.StreamReader(
        $runtimePthEntry.Open(),
        [System.Text.Encoding]::UTF8
    )
    try {
        $runtimePthText = $reader.ReadToEnd()
    } finally {
        $reader.Dispose()
    }
    $runtimePaths = @(
        $runtimePthText -split "\r?\n" |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    )
    if (-not ($runtimePaths -contains "..")) {
        throw "发布包未将父程序目录加入内置 Python 搜索路径"
    }

    $appEntry = $archive.GetEntry("app.py")
    $reader = New-Object System.IO.StreamReader(
        $appEntry.Open(),
        (New-Object System.Text.UTF8Encoding($false, $true))
    )
    try {
        $appText = $reader.ReadToEnd()
    } finally {
        $reader.Dispose()
    }
    if ($appText -notmatch '(?m)^APP_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"\s*$') {
        throw "发布包 app.py 中无法读取 APP_VERSION"
    }
    $appVersion = $Matches[1]

    $buildInfoEntry = $archive.GetEntry("build-info.json")
    $reader = New-Object System.IO.StreamReader(
        $buildInfoEntry.Open(),
        [System.Text.Encoding]::UTF8
    )
    try {
        $buildInfo = $reader.ReadToEnd() | ConvertFrom-Json
    } finally {
        $reader.Dispose()
    }
    if ($buildInfo.version -ne $appVersion) {
        throw "build-info.json 版本 '$($buildInfo.version)' 与 app.py '$appVersion' 不一致"
    }

    New-Item -ItemType Directory -Path $verificationRoot | Out-Null
    foreach ($name in @("AlgoArchive.exe", "ACM-ICPC-Windows.ico")) {
        $entry = $archive.GetEntry($name)
        $target = Join-Path $verificationRoot $name
        $input = $entry.Open()
        $output = [System.IO.File]::Create($target)
        try {
            $input.CopyTo($output)
        } finally {
            $output.Dispose()
            $input.Dispose()
        }
    }
    $launcherPath = Join-Path $verificationRoot "AlgoArchive.exe"
    $launcherVersionInfo = (Get-Item -LiteralPath $launcherPath).VersionInfo
    foreach ($property in @("FileVersion", "ProductVersion")) {
        $actualVersion = ([string]$launcherVersionInfo.$property).Trim()
        if ($actualVersion -ne $appVersion) {
            throw "AlgoArchive.exe 的 $property 是 '$actualVersion'，与 app.py '$appVersion' 不一致"
        }
    }
    $launcherVerifier = Join-Path $PSScriptRoot "verify-launcher.py"
    $python = (Get-Command python.exe -ErrorAction Stop).Source
    $launcherArguments = @(
        $launcherVerifier,
        $launcherPath,
        "--version", $appVersion,
        "--icon", (Join-Path $verificationRoot "ACM-ICPC-Windows.ico"),
        "--source", (Join-Path $projectRoot "launcher\AlgoArchive.cpp")
    )
    $launcherProbe = @(& $python -X utf8 @launcherArguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "启动器资源或静态依赖检查失败: $($launcherProbe -join [Environment]::NewLine)"
    }
} finally {
    $archive.Dispose()
    if (Test-Path -LiteralPath $verificationRoot) {
        Remove-Item -LiteralPath $verificationRoot -Recurse -Force
    }
}
Write-Output "发布包检查通过: $fullPath"
