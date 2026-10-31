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
        "LOCAL_FIXES.md",
        "启动.bat",
        "自检.bat",
        "self_check.py",
        "web/index.html",
        "web/app.js",
        "web/style.css",
        "web/codex-theme.css",
        "web/mobile.css",
        "web/nav-icons/home.png",
        "web/nav-icons/SOURCES.md",
        "web/platform-icons/codeforces.png",
        "web/platform-icons/atcoder.png",
        "web/platform-icons/acwing.png",
        "web/platform-icons/luogu.png",
        "web/platform-icons/niuke.png",
        "web/platform-icons/SOURCES.md",
        "runtime/python.exe",
        "README.md",
        "使用说明.txt",
        "SHA256SUMS.txt"
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
} finally {
    $archive.Dispose()
}
Write-Output "发布包检查通过: $fullPath"
