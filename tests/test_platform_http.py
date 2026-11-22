import io
import json
import logging
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

import app


class PlatformHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="algo-platform-http-")
        self.addCleanup(self.tmp.cleanup)
        repo = app.Repository(Path(self.tmp.name) / "data")
        self.server = app.LocalServer(("127.0.0.1", 0), repo,
            config_path=Path(self.tmp.name) / "config.json", config={})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = "http://127.0.0.1:%s" % self.server.server_port
        self.logs = io.StringIO()
        self.handler = logging.StreamHandler(self.logs)
        self.server.logger.addHandler(self.handler)
        self.addCleanup(lambda: self.server.logger.removeHandler(self.handler))

    def stop(self):
        self.server.shutdown()
        self.thread.join(3)
        self.server.server_close()
        self.server.repo.close()

    def request(self, path, method="GET", payload=None):
        request = urllib.request.Request(self.base + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json", "X-CSRF-Token": self.server.csrf_token}, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_independent_preference_read_and_platform_rest_contract(self):
        status, _, raw = self.request("/api/settings/sidebar-art")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {"sidebar_art": {"image": "celebration", "hidden": False}})
        status, _, raw = self.request("/api/platforms/acwing/problems/order", "PUT", {"version": 1, "problem_ids": []})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {"platform": "acwing", "platform_order_version": 2, "problem_ids": []})
        self.assertEqual(self.request("/api/platforms/acwing/problems/order", "PUT", {"version": 1, "problem_ids": []})[0], 409)

    def test_only_versioned_static_assets_are_cacheable(self):
        for path, expected in (("/app.js?v=local-test", "public, max-age=31536000, immutable"),
                ("/app.js", "no-store"), ("/?v=local-test", "no-store"),
                ("/index.html?v=local-test", "no-store"), ("/api/state?v=local-test", "no-store"),
                ("/missing.png?v=x", "no-store")):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[1]["Cache-Control"], expected)

    def test_import_preview_never_replays_pending_source_writes(self):
        repo = self.server.repo
        source = "codes/" + "a" * 32 + ".cpp"
        with repo.lock, repo.db:
            repo.db.execute("INSERT INTO pending_files(action,path,content) VALUES ('write',?,?)", (source, b"later"))
        status, _, raw = self.request("/api/problems/import/preview", "POST", {"problems": [
            {"platform": "HDU", "number": "1", "url": "https://oj.example/p1"}]})
        self.assertEqual((status, json.loads(raw)["code"]), (503, "storage_pending"))
        self.assertFalse((repo.data_dir / source).exists())
        self.assertEqual(repo.db.execute("SELECT COUNT(*) FROM pending_files").fetchone()[0], 1)

    def test_only_artwork_success_is_quiet(self):
        self.assertEqual(self.request("/api/settings/sidebar-art", "PUT", {"image": "debug", "hidden": False})[0], 200)
        self.assertNotIn("PUT /api/settings/sidebar-art", self.logs.getvalue())
        self.assertEqual(self.request("/api/settings/sidebar-art", "PUT", {"image": "invalid", "hidden": False})[0], 400)
        self.assertIn("PUT /api/settings/sidebar-art", self.logs.getvalue())
        self.logs.seek(0)
        self.logs.truncate()
        self.assertEqual(self.request("/api/profile", "PUT", {"name": "Local"})[0], 200)
        self.assertIn("PUT /api/profile", self.logs.getvalue())

    def test_artwork_write_exception_remains_diagnostic(self):
        with mock.patch.object(self.server.repo, "update_sidebar_art", side_effect=OSError("isolated write failure")):
            status, _, raw = self.request("/api/settings/sidebar-art", "PUT", {"image": "debug", "hidden": False})
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(raw)["code"], "internal_error")
        self.assertIn("isolated write failure", self.logs.getvalue())
        self.assertIn('PUT /api/settings/sidebar-art HTTP/1.1" 500', self.logs.getvalue())
