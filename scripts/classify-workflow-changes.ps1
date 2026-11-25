param(
    [string]$BaseRevision,
    [string]$HeadRevision = $env:GITHUB_SHA
)

$ErrorActionPreference = "Stop"
# Without a known baseline, run everything (new branch or force push).
$files = @()
if ($BaseRevision -and $BaseRevision -notmatch '^0+$' -and $HeadRevision) {
    git cat-file -e "${BaseRevision}^{commit}" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $files = @(git -c core.quotepath=false diff --no-renames --name-only $BaseRevision $HeadRevision --)
        if ($LASTEXITCODE -ne 0) { throw "Unable to list changed files." }
    }
}
$docs = '^(README\.md|CHANGELOG\.md|TEST_REPORT\.md|使用说明\.txt|docs/screenshots/[^/]+\.(png|svg|webp|jpg)|\.github/release-notes/[^/]+\.md)$'
$docsOnly = $files.Count -gt 0 -and @($files -cnotmatch $docs).Count -eq 0
$fullLayout = $files.Count -eq 0 -or @($files -match '^(web/|demo/|tests/test_view_layout\.cjs$|scripts/(build-demo\.cjs|.*workflow.*|run_browser_tests\.ps1)$|\.github/workflows/)').Count -gt 0
Write-Host "Changed files: $($files.Count); docs only: $docsOnly; full layout: $fullLayout"
if ($env:GITHUB_OUTPUT) {
    "docs_only=$($docsOnly.ToString().ToLowerInvariant())", "full_layout=$($fullLayout.ToString().ToLowerInvariant())" |
        Out-File -LiteralPath $env:GITHUB_OUTPUT -Encoding utf8 -Append
}
exit 0
