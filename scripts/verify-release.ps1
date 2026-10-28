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
        "启动.bat",
        "web/index.html",
        "web/app.js",
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
        "(^|/)backups/",
        "(^|/)\.qa-data/",
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
