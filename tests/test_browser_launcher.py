"""Tests for browser settings and external-process launching."""

from pathlib import Path
import unittest
from unittest import mock

import app


class BrowserLauncherTests(unittest.TestCase):
    def test_windows_launchers_use_saved_config_instead_of_forced_data_dir(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("启动.bat", "start.bat"):
            content = (root / name).read_text(encoding="utf-8")
            normalized = content.casefold().replace("/", "\\")
            self.assertNotIn("--data-dir", normalized)
            self.assertNotIn("algoarchive_data", normalized)

    def test_windows_launchers_refresh_desktop_shortcut(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("启动.bat", "start.bat"):
            content = (root / name).read_text(encoding="utf-8")
            self.assertIn("create-desktop-shortcut.ps1", content)
            self.assertIn("-ShortcutName", content)

    def test_installer_skips_data_page_when_selection_cannot_apply(self):
        installer = (
            Path(__file__).resolve().parents[1] / "installer" / "AlgoArchive.iss"
        ).read_text(encoding="utf-8")
        self.assertIn("function ShouldSkipPage", installer)
        self.assertIn("IsAdminInstallMode or FileExists(UserConfigPath())", installer)
        self.assertIn("if IsAdminInstallMode or (DataDirPage = nil)", installer)
        self.assertIn('Name: "{autodesktop}\\{#MyAppName}"', installer)
        self.assertIn("SaveStringsToUTF8FileWithoutBOM(ConfigPath", installer)
        self.assertNotIn("desktopicon", installer)

    def test_readme_warns_against_source_code_archive(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Source code (zip)", readme)

    def test_cph_attribution_and_license_are_bundled(self):
        root = Path(__file__).resolve().parents[1]
        notices = (root / "THIRD_PARTY.txt").read_text(encoding="utf-8")
        license_file = root / "licenses" / "CPH-GPL-3.0.txt"
        readme = (root / "README.md").read_text(encoding="utf-8")
        self.assertIn("Divyanshu Agrawal", notices)
        self.assertIn("https://github.com/agrawal-d/cph", notices)
        self.assertIn("GPL-3.0-or-later", notices)
        self.assertTrue(license_file.is_file())
        self.assertGreater(license_file.stat().st_size, 30_000)
        self.assertIn(f"AlgoArchive-{app.APP_VERSION}-Windows-x64-Setup.exe", readme)
        self.assertIn(f"AlgoArchive-{app.APP_VERSION}-Windows-x64.zip", readme)

    def test_problem_table_exposes_copy_link_action(self):
        app_js = (
            Path(__file__).resolve().parents[1] / "web" / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("data-copy-problem-link", app_js)
        self.assertIn("copyProblemLink", app_js)
        self.assertIn("navigator.clipboard.writeText", app_js)

    def test_problem_table_uses_display_order_numbering(self):
        app_js = (
            Path(__file__).resolve().parents[1] / "web" / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("序号与题目", app_js)
        self.assertIn("items.map((p,index)", app_js)
        self.assertIn('class="problem-order"', app_js)
        self.assertIn("title.insertBefore(handle,order)", app_js)
        self.assertNotIn("原题编号", app_js)
        self.assertNotIn("<span>题目编号", app_js)
        self.assertNotIn('name="number"', app_js)

    def test_web_favicon_uses_single_bundled_icon(self):
        root = Path(__file__).resolve().parents[1]
        index = (root / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('href="/app.ico?', index)
        self.assertTrue((root / "web" / "app.ico").is_file())
        for legacy in ("app-acm.ico", "app-final.ico", "app-provided.ico"):
            self.assertNotIn(legacy, index)
            self.assertFalse((root / "web" / legacy).exists())

    def test_home_nav_uses_bundled_house_icon(self):
        root = Path(__file__).resolve().parents[1]
        web = root / "web"
        index = (web / "index.html").read_text(encoding="utf-8")
        style = (web / "codex-theme.css").read_text(encoding="utf-8")

        self.assertIn("/nav-icons/home.png", index)
        self.assertNotIn('<span class="nav-icon">⌂</span>', index)
        self.assertTrue((web / "nav-icons" / "home.png").is_file())
        self.assertTrue((web / "nav-icons" / "SOURCES.md").is_file())
        self.assertIn(".home-nav-icon", style)

    def test_platform_site_icons_are_bundled_locally(self):
        root = Path(__file__).resolve().parents[1]
        web = root / "web"
        index = (web / "index.html").read_text(encoding="utf-8")
        app_js = (web / "app.js").read_text(encoding="utf-8")
        style = (web / "codex-theme.css").read_text(encoding="utf-8")
        sources = (web / "platform-icons" / "SOURCES.md").read_text(
            encoding="utf-8"
        )

        for key in ("codeforces", "atcoder", "acwing", "luogu", "niuke"):
            icon = web / "platform-icons" / f"{key}.png"
            self.assertTrue(icon.is_file())
            self.assertGreater(icon.stat().st_size, 300)
            self.assertIn(f"{key}.png", index + app_js)
        self.assertIn("acwing: 'AcWing'", app_js)
        self.assertIn("https://codeforces.com/favicon.ico", sources)
        self.assertIn("https://img.atcoder.jp/assets/favicon.png", sources)
        self.assertNotIn("https://codeforces.com/favicon.ico", index + app_js)
        self.assertIn(".contest-relation.contest-codeforces", style)
        self.assertIn("background: #fff3df", style)
        self.assertIn("width: 108px;", style)
        self.assertIn("width: 136px;", style)
        self.assertIn("canonicalPlatformValue", app_js)
        self.assertIn(
            'class="relation-badge algorithm-relation is-empty"',
            app_js,
        )
        self.assertIn(".contest-cell .algorithm-relation {", style)
        self.assertIn("justify-content: center;", style)

    def test_problem_table_has_mobile_column_markers(self):
        root = Path(__file__).resolve().parents[1]
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        style = (root / "web" / "mobile.css").read_text(encoding="utf-8")

        self.assertIn("problem-table", app_js)
        self.assertIn("problem-col-secondary", app_js)
        self.assertIn("problem-col-platform", app_js)
        self.assertIn(
            ".problem-table .problem-col-secondary {\n    display: none;",
            style,
        )
        self.assertIn(
            ".problem-table .problem-col-platform {\n    display: none;",
            style,
        )

    def test_code_editor_uses_vscode_selection_and_scrollbars(self):
        root = Path(__file__).resolve().parents[1]
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        style = (root / "web" / "codex-theme.css").read_text(encoding="utf-8")

        self.assertIn("updateSelectionBands", app_js)
        self.assertIn("code-selection-block", app_js)
        self.assertIn(".code-selection-block", style)
        self.assertIn("background: rgba(0, 120, 215, .24)", style)
        self.assertIn("::-webkit-scrollbar-button", style)

    def test_release_manifests_include_self_check(self):
        root = Path(__file__).resolve().parents[1]
        portable = (root / "scripts" / "build-portable.ps1").read_text(
            encoding="utf-8"
        )
        verifier = (root / "scripts" / "verify-release.ps1").read_text(
            encoding="utf-8"
        )
        installer = (root / "installer" / "AlgoArchive.iss").read_text(
            encoding="utf-8"
        )

        for manifest in (portable, verifier, installer):
            self.assertIn("自检.bat", manifest)
            self.assertIn("self_check.py", manifest)
        self.assertIn("web/platform-icons/acwing.png", verifier)
        self.assertIn("web/nav-icons/home.png", verifier)

    def test_self_check_is_a_lightweight_production_smoke_check(self):
        self_check = (
            Path(__file__).resolve().parents[1] / "self_check.py"
        ).read_text(encoding="utf-8")

        self.assertIn("生产自检通过", self_check)
        self.assertNotIn("unittest.defaultTestLoader", self_check)

    def test_chrome_candidates_include_standard_program_files_path(self):
        candidates = app.chrome_candidates()
        self.assertIn(
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            candidates,
        )

    def test_default_browser_mode_uses_system_default(self):
        with mock.patch("app.webbrowser.open", return_value=True) as default:
            result = app.launch_browser(
                "http://127.0.0.1:8765",
                {"mode": "default", "window_mode": "tab"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["browser"], "system")
        default.assert_called_once_with("http://127.0.0.1:8765")

    def test_explicit_chrome_mode_uses_parameter_array(self):
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        with mock.patch("app.find_browser_executable", return_value=chrome):
            with mock.patch("app.subprocess.Popen") as popen:
                result = app.launch_browser(
                    "http://127.0.0.1:8765",
                    {"mode": "chrome", "window_mode": "tab"},
                )

        self.assertTrue(result["ok"])
        popen.assert_called_once()
        self.assertEqual(
            popen.call_args.args[0],
            [str(chrome), "http://127.0.0.1:8765"],
        )

    def test_chromium_app_window_mode_uses_app_argument(self):
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        with mock.patch("app.find_browser_executable", return_value=chrome):
            with mock.patch("app.subprocess.Popen") as popen:
                result = app.launch_browser(
                    "http://127.0.0.1:8765",
                    {"mode": "chrome", "window_mode": "app"},
                )

        self.assertTrue(result["ok"])
        self.assertEqual(
            popen.call_args.args[0],
            [str(chrome), "--app=http://127.0.0.1:8765"],
        )

    def test_failed_explicit_browser_falls_back_and_reports_reason(self):
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        with mock.patch("app.find_browser_executable", return_value=chrome):
            with mock.patch("app.subprocess.Popen", side_effect=OSError("blocked")):
                with mock.patch("app.webbrowser.open", return_value=True) as fallback:
                    result = app.launch_browser(
                        "http://127.0.0.1:8765",
                        {"mode": "chrome", "window_mode": "tab"},
                    )

        fallback.assert_called_once_with("http://127.0.0.1:8765")
        self.assertTrue(result["ok"])
        self.assertTrue(result["fallback"])
        self.assertIn("系统默认浏览器", result["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
