$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath ".").Path.TrimEnd([IO.Path]::DirectorySeparatorChar)
$webRoot = Join-Path $root "web"
$readme = Get-Content -LiteralPath (Join-Path $root "README.md") -Raw -Encoding utf8
$app = Get-Content -LiteralPath (Join-Path $root "app.py") -Raw -Encoding utf8
if ($app -notmatch 'APP_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"') { throw "Cannot read application version." }
$version = $Matches[1]
foreach ($asset in @("AlgoArchive-$version-Windows-x64-Setup.exe", "AlgoArchive-$version-Windows-x64.zip")) {
    if (-not $readme.Contains($asset)) { throw "README does not advertise the current release asset: $asset" }
}
foreach ($path in @("LICENSE", "DISCLAIMER.md", "THIRD_PARTY.txt", "TEST_REPORT.md")) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $path) -PathType Leaf)) { throw "Required notice or current test record is missing: $path" }
    if (-not $readme.Contains($path)) { throw "README does not link the required notice or test record: $path" }
}

$readmeReferences = [regex]::Matches($readme, '!??\[[^\]]*\]\(([^)]+)\)') | ForEach-Object { $_.Groups[1].Value }
foreach ($reference in $readmeReferences) {
    if ($reference -match '^(?:[A-Za-z][A-Za-z0-9+.-]*:|#|//)') { continue }
    $relative = [Uri]::UnescapeDataString((($reference -split '[?#]', 2)[0]).Replace('/', [IO.Path]::DirectorySeparatorChar))
    $target = [IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $target.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $target -PathType Leaf)) {
        throw "README reference does not resolve inside the repository: $reference"
    }
}

function Resolve-WebReference([string]$SourceFile, [string]$Reference) {
    $value = [Uri]::UnescapeDataString($Reference.Trim())
    if ($value -match '^(?:[A-Za-z][A-Za-z0-9+.-]*:|//)') { return $null }
    $parts = $value -split '#', 2
    $pathPart = ($parts[0] -split '\?', 2)[0]
    if ([string]::IsNullOrEmpty($pathPart)) { return @{Path=$SourceFile; Fragment=if($parts.Count -gt 1){$parts[1]}else{''}} }
    $directoryReference = $pathPart -eq '.' -or $pathPart.EndsWith('/')
    if ($pathPart.StartsWith('/')) {
        $pathPart = $pathPart.TrimStart('/')
        if ($pathPart.StartsWith('AlgoArchive/')) { $pathPart = $pathPart.Substring('AlgoArchive/'.Length) }
        $candidate = Join-Path $webRoot ($pathPart.Replace('/', [IO.Path]::DirectorySeparatorChar))
    } else {
        $candidate = Join-Path (Split-Path -Parent $SourceFile) ($pathPart.Replace('/', [IO.Path]::DirectorySeparatorChar))
    }
    $resolved = [IO.Path]::GetFullPath($candidate)
    $webPrefix = $webRoot + [IO.Path]::DirectorySeparatorChar
    if ($resolved -ne $webRoot -and -not $resolved.StartsWith($webPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Web page reference escapes web/: $SourceFile -> $Reference"
    }
    if ($directoryReference) { $resolved = Join-Path $resolved 'index.html' }
    return @{Path=$resolved; Fragment=if($parts.Count -gt 1){$parts[1]}else{''}}
}

$htmlFiles = @(Get-ChildItem -LiteralPath $webRoot -Recurse -File -Filter '*.html')
foreach ($htmlFile in $htmlFiles) {
    $html = Get-Content -LiteralPath $htmlFile.FullName -Raw -Encoding utf8
    foreach ($match in [regex]::Matches($html, '(?:href|src)="([^"]+)"')) {
        $reference = $match.Groups[1].Value
        $resolved = Resolve-WebReference $htmlFile.FullName $reference
        if ($null -eq $resolved) { continue }
        if (-not (Test-Path -LiteralPath $resolved.Path -PathType Leaf)) { throw "Web resource does not exist: $($htmlFile.FullName) -> $reference" }
        if ($resolved.Fragment -and [IO.Path]::GetExtension($resolved.Path) -eq '.html') {
            $linkedHtml = Get-Content -LiteralPath $resolved.Path -Raw -Encoding utf8
            $fragment = [System.Net.WebUtility]::HtmlDecode(($resolved.Fragment -split '\?', 2)[0])
            $hasId = $linkedHtml.Contains(('id="{0}"' -f $fragment)) -or $linkedHtml.Contains(("id='{0}'" -f $fragment))
            $hasName = $linkedHtml.Contains(('name="{0}"' -f $fragment)) -or $linkedHtml.Contains(("name='{0}'" -f $fragment))
            $appRoute = $resolved.Path -eq (Join-Path $webRoot 'index.html') -and $fragment -match '^(?:home|algorithms|contests|problems|compiler|platform/(?:codeforces|atcoder|acwing|luogu|niuke)|settings/(?:about|compiler))$'
            if (-not ($hasId -or $hasName -or $appRoute)) { throw "HTML fragment does not exist: $($htmlFile.FullName) -> $reference" }
        }
    }
}

$appJs = Get-Content -LiteralPath (Join-Path $webRoot 'app.js') -Raw -Encoding utf8
if ($appJs -notmatch 'function\s+parseSettingsHash' -or
    $appJs -notmatch "const settingsTabs=new Set" -or
    $appJs -notmatch "'about'" -or $appJs -notmatch "'compiler'" -or
    $appJs -notmatch "params\.get\('focus'\)==='shortcuts'") {
    throw "Application is missing the allow-listed settings routes or shortcut focus handling."
}
$manualEntryFiles = @('manual.html', 'shortcuts.html', 'guide\backup.html', 'guide\test.html')
foreach ($name in $manualEntryFiles) {
    $source = Get-Content -LiteralPath (Join-Path $webRoot $name) -Raw -Encoding utf8
    if ($source -notmatch 'data-settings-link') { throw "Settings help link is missing from web/$name" }
}
if ($appJs -notmatch 'data-settings-link') { throw "Application does not handle settings-navigation links." }
if ($readme -notmatch 'compiler|g\+\+|编译器' -or $readme -notmatch '快捷方式|shortcut') { throw "README must explain compiler setup and desktop shortcuts." }

Write-Host "Documentation links, HTML assets/fragments, release names, notices, and settings routes are valid for $version ($($htmlFiles.Count) HTML pages)."
