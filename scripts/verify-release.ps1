param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem
$fullPath = [System.IO.Path]::GetFullPath($ArchivePath)
if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
    throw "发布包不存在: $fullPath"
}

$archive = [System.IO.Compression.ZipFile]::OpenRead($fullPath)
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
        "SHA256SUMS.txt"
        "build-info.json"
        "LICENSE"
        "DISCLAIMER.md"
    )
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
        if ($extension -in $lfExtensions -and $text.Contains("`r")) {
            throw "Release source must use LF: $($entry.FullName)"
        }
        if ($extension -in @(".bat", ".ps1") -and $text -match "(?<!`r)`n|`r(?!`n)") {
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
} finally {
    $archive.Dispose()
}
Write-Output "发布包检查通过: $fullPath"
