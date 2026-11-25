$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath ".").Path
$readme = Get-Content -LiteralPath (Join-Path $root "README.md") -Raw -Encoding utf8
$app = Get-Content -LiteralPath (Join-Path $root "app.py") -Raw -Encoding utf8
if ($app -notmatch 'APP_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"') { throw "Cannot read application version." }
$version = $Matches[1]
foreach ($asset in @("AlgoArchive-$version-Windows-x64-Setup.exe", "AlgoArchive-$version-Windows-x64.zip")) {
    if (-not $readme.Contains($asset)) { throw "README does not advertise the current release asset: $asset" }
}
foreach ($path in @("LICENSE", "DISCLAIMER.md", "THIRD_PARTY.txt", "TEST_REPORT.md")) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $path) -PathType Leaf)) { throw "Required notice or test record is missing: $path" }
    if (-not $readme.Contains($path)) { throw "README does not link the required notice or test record: $path" }
}

$references = [regex]::Matches($readme, '\]\(([^)]+)\)') | ForEach-Object { $_.Groups[1].Value }
foreach ($reference in $references) {
    if ($reference -match '^(?:[A-Za-z][A-Za-z0-9+.-]*:|#|//)') { continue }
    $relative = ($reference -split '[?#]', 2)[0].Replace('/', [IO.Path]::DirectorySeparatorChar)
    $target = [IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $target -PathType Leaf)) {
        throw "README reference does not resolve inside the repository: $reference"
    }
}
Write-Host "Documentation references, release names, and notices are valid for $version."
