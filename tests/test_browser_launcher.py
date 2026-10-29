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
