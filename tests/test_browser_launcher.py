"""Tests for browser settings and external-process launching."""

from pathlib import Path
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import urllib.request

import app
import run


class BrowserLauncherTests(unittest.TestCase):
    def test_windows_launchers_use_saved_config_instead_of_forced_data_dir(self):
        root = Path(__file__).resolve().parents[1]
        launcher = root / "start.bat"
        content = launcher.read_text(encoding="utf-8")
        normalized = content.casefold().replace("/", "\\")
        content.encode("ascii")
        self.assertNotIn("--data-dir", normalized)
        self.assertNotIn("algoarchive_data", normalized)
        self.assertFalse((root / "启动.bat").exists())
        self.assertFalse((root / "创建桌面快捷方式.bat").exists())

    def test_windows_launcher_supports_explicit_desktop_shortcut(self):
        root = Path(__file__).resolve().parents[1]
        content = (root / "start.bat").read_text(encoding="utf-8")
        runner = (root / "run.py").read_text(encoding="utf-8")
        shortcut_script = (
            root / "scripts" / "create-desktop-shortcut.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn('"run.py" %*', content)
        self.assertIn("--create-shortcut", runner)
        self.assertIn("create_desktop_shortcut()", runner)
        self.assertIn("0x7B97, 0x6CD5, 0x6863, 0x6848", shortcut_script)
        self.assertIn("'AlgoArchive.exe'", shortcut_script)
        self.assertIn("$shortcut.Arguments = ''", shortcut_script)
        self.assertIn("Microsoft\\Windows\\Start Menu\\Programs", shortcut_script)

    def test_runner_consumes_only_the_leading_shortcut_flag(self):
        with mock.patch(
            "run.app.create_desktop_shortcut",
            return_value={"message": "shortcuts ready"},
        ) as create:
            with mock.patch("run.app.main", return_value=7) as start:
                with mock.patch("builtins.print"):
                    result = run.main(
                        ["--create-shortcut", "--port", "18765", "--no-browser"]
                    )
        self.assertEqual(result, 7)
        create.assert_called_once_with()
        start.assert_called_once_with(["--port", "18765", "--no-browser"])

    @unittest.skipUnless(os.name == "nt", "Windows command-line passthrough")
    def test_batch_forwards_paths_ports_and_flags_to_application(self):
        root = Path(__file__).resolve().parents[1]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with tempfile.TemporaryDirectory(
            prefix="algoarchive launcher 中文 "
        ) as temp:
            temp_path = Path(temp)
            data = temp_path / "题库 & 100% 数据"
            config = temp_path / "配置 (100%).json"
            process = subprocess.Popen(
                [
                    "cmd.exe",
                    "/d",
                    "/c",
                    "start.bat",
                    "--data-dir",
                    str(data),
                    "--config-path",
                    str(config),
                    "--port",
                    str(port),
                    "--no-browser",
                ],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 15
                html = None
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/", timeout=0.5
                        ) as response:
                            html = response.read().decode("utf-8")
                        break
                    except OSError:
                        time.sleep(0.05)
                self.assertIsNotNone(
                    html,
                    process.stdout.read().decode("utf-8", errors="replace")
                    if process.poll() is not None
                    else "batch launcher did not forward --port",
                )
                self.assertTrue((data / "archive.sqlite3").is_file())
                token = re.search(
                    r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)',
                    html,
                ).group(1)
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/shutdown",
                    b"{}",
                    {
                        "Content-Type": "application/json",
                        "X-CSRF-Token": token,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5):
                    pass
                process.communicate(timeout=10)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate(timeout=5)
                elif process.stdout and not process.stdout.closed:
                    process.stdout.close()

    @unittest.skipUnless(os.name == "nt", "Windows desktop shortcut")
    @mock.patch("app.subprocess.run")
    def test_create_desktop_shortcut_uses_packaged_script(self, run):
        run.return_value = mock.Mock(returncode=0, stdout="", stderr="")

        result = app.create_desktop_shortcut()

        self.assertTrue(result["ok"])
        command = run.call_args.args[0]
        self.assertEqual(command[0], "powershell.exe")
        self.assertIn("create-desktop-shortcut.ps1", command[-2])
        self.assertIn("-IncludeStartMenu", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 20)

    def test_native_launcher_is_packaged(self):
        root = Path(__file__).resolve().parents[1]
        launcher = root / "AlgoArchive.exe"
        self.assertTrue(launcher.is_file())
        self.assertGreater(launcher.stat().st_size, 50_000)
        portable = (root / "scripts" / "build-portable.ps1").read_text(
            encoding="utf-8"
        )
        installer = (root / "installer" / "AlgoArchive.iss").read_text(
            encoding="utf-8"
        )
        self.assertIn('"AlgoArchive.exe"', portable)
        self.assertIn('"FileVersion", "ProductVersion"', portable)
        self.assertIn("请先重新生成启动器", portable)
        self.assertIn("AlgoArchive.exe", installer)

    def test_native_launcher_has_no_bundled_toolchain_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(root / "scripts" / "verify-launcher.py"),
                str(root / "AlgoArchive.exe"),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            (result.stdout + result.stderr).strip(),
        )
        build_script = (
            root / "launcher" / "build-launcher.ps1"
        ).read_text(encoding="utf-8")
        portable = (
            root / "scripts" / "build-portable.ps1"
        ).read_text(encoding="utf-8")
        for flag in ("-static", "-static-libgcc", "-static-libstdc++"):
            self.assertIn(flag, build_script)
        self.assertIn("verify-launcher.py", portable)
        self.assertIn("$launcherProbe = @(", portable)
        for workflow in ("windows.yml", "release.yml"):
            content = (
                root / ".github" / "workflows" / workflow
            ).read_text(encoding="utf-8")
            self.assertIn("verify-launcher.py", content)

    def test_installer_skips_data_page_when_selection_cannot_apply(self):
        installer = (
            Path(__file__).resolve().parents[1] / "installer" / "AlgoArchive.iss"
        ).read_text(encoding="utf-8")
        self.assertIn("function ShouldSkipPage", installer)
        self.assertIn('#define MyAppExeName "AlgoArchive.exe"', installer)
        self.assertIn("IsAdminInstallMode or FileExists(UserConfigPath())", installer)
        self.assertIn("if IsAdminInstallMode or (DataDirPage = nil)", installer)
        self.assertIn('Name: "{autodesktop}\\{#MyAppName}"', installer)
        self.assertIn("SaveStringsToUTF8FileWithoutBOM(ConfigPath", installer)
        self.assertIn("if not SaveStringsToUTF8FileWithoutBOM(ConfigPath", installer)
        self.assertIn("DataDirPage.Values[0] := DataDir;", installer)
        self.assertIn("IsAbsoluteDirectory(DataDir)", installer)
        self.assertIn('Name: "desktopicon"', installer)
        self.assertIn("Flags: unchecked", installer)
        self.assertIn("Tasks: desktopicon", installer)

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

    def test_settings_exposes_explicit_desktop_shortcut_action(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("create-desktop-shortcut", script)
        self.assertIn("/api/settings/desktop-shortcut", script)
        self.assertIn("普通启动不会创建或恢复快捷方式", script)
        self.assertIn("固定到开始屏幕需在系统中手动完成", script)
        browser_start = script.index("function settingsBrowserHTML")
        compiler_start = script.index("function settingsCompilerHTML")
        about_start = script.index("function settingsAboutHTML")
        self.assertNotIn("<h3>快捷方式</h3>", script[browser_start:compiler_start])
        self.assertGreater(script.index("<h3>快捷方式</h3>", about_start), about_start)
        self.assertIn(
            "bindShortcutSettings();",
            script[script.index("function bindAboutSettings"):],
        )

    def test_frontend_preserves_edits_and_binds_async_results(self):
        script = (
            Path(__file__).resolve().parents[1] / "web" / "app.js"
        ).read_text(encoding="utf-8")
        self.assertIn("if (!force && route === state.route) return;", script)
        self.assertIn("const activeAtStart=state.cph.active;", script)
        self.assertIn("state.cph!==runCph", script)
        self.assertIn("const index=allCases?item.ordinal-1:activeAtStart;", script)
        self.assertIn("MAX_CPH_SUITE_BYTES", script)
        persist_index = script.index("state.editor.entity={...saved.snippet};")
        refresh_index = script.index("try{await loadState();}", persist_index)
        self.assertLess(persist_index, refresh_index)

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
            self.assertIn("run.py", manifest)
        for manifest in (portable, installer):
            self.assertNotIn("启动.bat", manifest)
            self.assertNotIn("创建桌面快捷方式.bat", manifest)
        self.assertIn("web/platform-icons/acwing.png", verifier)
        self.assertIn("web/nav-icons/home.png", verifier)

    def test_release_packaging_checks_bundled_runtime_imports(self):
        root = Path(__file__).resolve().parents[1]
        portable = (root / "scripts" / "build-portable.ps1").read_text(
            encoding="utf-8"
        )
        verifier = (root / "scripts" / "verify-release.ps1").read_text(
            encoding="utf-8"
        )
        self_check = (root / "self_check.py").read_text(encoding="utf-8")

        self.assertIn("python313._pth", portable)
        self.assertIn("import app, cph_runner", portable)
        self.assertIn('$runtimePaths -contains ".."', verifier)
        self.assertIn("import app, cph_runner", self_check)

    def test_self_check_is_a_lightweight_production_smoke_check(self):
        self_check = (
            Path(__file__).resolve().parents[1] / "self_check.py"
        ).read_text(encoding="utf-8")

        self.assertIn("生产自检通过", self_check)
        self.assertNotIn("unittest.defaultTestLoader", self_check)

    @unittest.skipUnless(os.name == "nt", "Windows browser paths")
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
