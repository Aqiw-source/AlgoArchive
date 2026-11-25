"""Exercise the release verifier against valid and invalid ZIP text payloads."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
REQUIRED = (
    "app.py", "cph_runner.py", "run.py", "AlgoArchive.exe",
    "start.bat", "自检.bat", "self_check.py", "web/index.html", "web/app.js",
    "web/style.css", "web/codex-theme.css", "web/mobile.css",
    "web/manual.html", "web/manual.css", "web/workspace-updates.css", "web/sidebar-art.png", "web/sidebar-art-blended.webp",
    "web/sidebar-art-debug.png", "web/sidebar-art-thinking.png",
    "web/sidebar-art-debug-blended.webp", "web/sidebar-art-thinking-blended.webp",
    "web/nav-icons/home.png", "web/nav-icons/SOURCES.md",
    "web/platform-icons/codeforces.png", "web/platform-icons/atcoder.png",
    "web/platform-icons/acwing.png", "web/platform-icons/luogu.png",
    "web/platform-icons/niuke.png", "web/platform-icons/lanqiao.png",
    "web/platform-icons/hdu.png", "web/platform-icons/matiji.png",
    "web/platform-icons/leetcode.png", "web/platform-icons/poj.png",
    "web/platform-icons/SOURCES.md", "runtime/python313._pth", "runtime/python.exe",
    "README.md", "使用说明.txt", "CHANGELOG.md", "TEST_REPORT.md",
    "docs/history/TEST_REPORT-through-2.4.0.md", "THIRD_PARTY.txt",
    "SHA256SUMS.txt", "build-info.json", "LICENSE", "DISCLAIMER.md",
    "ACM-ICPC-Windows.ico", "scripts/create-desktop-shortcut.ps1",
)


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows release verifier")
class ReleaseLineEndingTests(unittest.TestCase):
    def verify(self, changes=None):
        files = {name: b"fixture\n" for name in REQUIRED}
        files.update({p.relative_to(PROJECT).as_posix(): b"fixture\n" for p in (PROJECT / "web").rglob("*") if p.is_file()})
        files.update({
            "app.py": b'APP_VERSION = "2.5.0"\n',
            "build-info.json": b'{"version":"2.5.0"}\n',
            "AlgoArchive.exe": (PROJECT / "AlgoArchive.exe").read_bytes(),
            "ACM-ICPC-Windows.ico": (PROJECT / "ACM-ICPC-Windows.ico").read_bytes(),
        })
        files.update({
            "runtime/python313._pth": b"python313.zip\n.\n..\n",
            "start.bat": b"@echo off\r\nexit /b 0\r\n",
            "自检.bat": b"@echo off\r\nexit /b 0\r\n",
            "scripts/create-desktop-shortcut.ps1": b"Write-Output 'ok'\r\n",
        })
        for name, content in (changes or {}).items():
            if content is None:
                files.pop(name, None)
            else:
                files[name] = content
        with tempfile.TemporaryDirectory(prefix="algo-release-eol-") as folder:
            archive = Path(folder) / "release.zip"
            with zipfile.ZipFile(archive, "w") as output:
                for name, content in files.items():
                    output.writestr(name, content)
            return subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 str(PROJECT / "scripts/verify-release.ps1"), "-ArchivePath", str(archive)],
                capture_output=True, encoding="utf-8", errors="replace", timeout=30,
            )

    def test_accepts_lf_source_and_crlf_windows_scripts(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_missing_historical_test_report(self):
        result = self.verify({"docs/history/TEST_REPORT-through-2.4.0.md": None})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "docs/history/TEST_REPORT-through-2.4.0.md",
            result.stdout + result.stderr,
        )

    def test_rejects_missing_handbook_script(self):
        result = self.verify({"web/manual.js": None})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("web/manual.js", result.stdout + result.stderr)

    def test_rejects_crlf_and_mixed_source_line_endings(self):
        for name in ("app.py", "web/app.js", "web/style.css", "web/index.html",
                     "web/extra.cjs", "web/extra.mjs"):
            with self.subTest(file=name):
                result = self.verify({name: b"first\nsecond\r\n"})
                self.assertNotEqual(result.returncode, 0, name)
                self.assertIn("must use LF", result.stdout + result.stderr)

    def test_rejects_lf_or_lone_cr_in_windows_scripts(self):
        for name, content in (("start.bat", b"@echo off\n"),
                              ("scripts/create-desktop-shortcut.ps1", b"Write-Output 'ok'\r")):
            with self.subTest(file=name):
                result = self.verify({name: content})
                self.assertNotEqual(result.returncode, 0, name)
                self.assertIn("must use CRLF", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
