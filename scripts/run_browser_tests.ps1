$ErrorActionPreference = "Stop"
$tests = @(
    "test_editor_lock",
    "test_editor_preserve",
    "test_editor_performance",
    "test_home_performance",
    "test_problem_navigation",
    "test_problem_recovery_drafts",
    "test_card_colors",
    "test_platform_art",
    "test_local_upgrade",
    "test_background_sync",
    "test_modal_scroll",
    "test_view_layout",
    "test_image_preview",
    "test_study_ui"
)
foreach ($test in $tests) {
    Write-Host "Running browser regression: $test"
    node "tests/$test.cjs"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
node --test tests/test_demo.cjs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
node --test tests/test_saved_problem_counts.cjs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
