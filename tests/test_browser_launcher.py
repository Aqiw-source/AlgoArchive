"""Tests for opening AlgoArchive in Google Chrome."""

from pathlib import Path
import unittest
from unittest import mock

import app


class BrowserLauncherTests(unittest.TestCase):
    def test_chrome_candidates_include_standard_program_files_path(self):
        candidates = app.chrome_candidates()
        self.assertIn(
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            candidates,
        )

    def test_open_browser_prefers_installed_chrome(self):
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        with mock.patch("app.find_chrome_executable", return_value=chrome):
            with mock.patch("app.subprocess.Popen") as popen:
                with mock.patch("app.webbrowser.open") as fallback:
                    self.assertTrue(app.open_browser("http://127.0.0.1:8765"))

        popen.assert_called_once()
        self.assertEqual(
            popen.call_args.args[0],
            [str(chrome), "http://127.0.0.1:8765"],
        )
        fallback.assert_not_called()

    def test_open_browser_falls_back_when_chrome_is_missing(self):
        with mock.patch("app.find_chrome_executable", return_value=None):
            with mock.patch("app.webbrowser.open", return_value=False) as fallback:
                self.assertFalse(app.open_browser("http://127.0.0.1:8765"))

        fallback.assert_called_once_with("http://127.0.0.1:8765")

    def test_open_browser_falls_back_when_chrome_cannot_start(self):
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        with mock.patch("app.find_chrome_executable", return_value=chrome):
            with mock.patch("app.subprocess.Popen", side_effect=OSError("blocked")):
                with mock.patch("app.webbrowser.open", return_value=False) as fallback:
                    self.assertFalse(app.open_browser("http://127.0.0.1:8765"))

        fallback.assert_called_once_with("http://127.0.0.1:8765")


if __name__ == "__main__":
    unittest.main(verbosity=2)
