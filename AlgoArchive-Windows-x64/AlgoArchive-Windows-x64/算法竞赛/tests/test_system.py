"""End-to-end regression tests; no network or third-party packages required.

Run from the project directory: python -m unittest discover -s tests -v
Each test launches an isolated server with a temporary database and code folder.
"""

import concurrent.futures
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request


PROJECT = Path(__file__).resolve().parents[1]


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="algo-test-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "中文目录 用户 数据"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.base = "http://127.0.0.1:%s" % self.port
        self.log = open(Path(self.tmp.name) / "server.log", "w+b")
        self.addCleanup(self.log.close)
        self.process = None
        self.addCleanup(self.stop_server)
        self.start_server()

    def start_server(self):
        self.process = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(PROJECT / "app.py"), "--data-dir", str(self.data),
             "--port", str(self.port), "--no-browser"],
            cwd=str(PROJECT), stdout=self.log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(self.base + "/", timeout=0.5) as response:
                    html = response.read().decode("utf-8")
                match = re.search(r'<meta\s+name=[\"\']csrf-token[\"\']\s+content=[\"\']([^\"\']+)', html)
                if match and match.group(1) != "__CSRF_TOKEN__":
                    self.token = match.group(1)
                    return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.05)
        self.log.flush()
        self.log.seek(0)
        self.fail("Server did not start:\n" + self.log.read().decode("utf-8", errors="replace"))

    def stop_server(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def request(self, method, path, payload=None, expected=200, headers=None):
        request_headers = {"Content-Type": "application/json", "X-CSRF-Token": self.token}
        request_headers.update(headers or {})
        raw = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.base + path, raw, request_headers, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.status
            result = json.loads(response.read().decode("utf-8"))
        allowed = expected if isinstance(expected, tuple) else (expected,)
        self.assertIn(status, allowed, (method, path, status, result))
        return result

    def contest(self, platform="codeforces", title="测试比赛", url=None):
        url = url or ("https://codeforces.com/contest/2000" if platform == "codeforces"
                      else "https://atcoder.jp/contests/abc100")
        return self.request("POST", "/api/contests", {
            "platform": platform, "title": title, "url": url,
        }, expected=(200, 201))["contest"]

    def problem(self, **overrides):
        payload = {"platform": "codeforces", "number": "A", "name": "中文题目 <script>",
                   "url": "https://codeforces.com/contest/2000/problem/A",
                   "language": "cpp", "code": "#include <iostream>\nint main() { std::cout << 42; }\n",
                   "contest_id": None}
        payload.update(overrides)
        return self.request("POST", "/api/problems", payload, expected=(200, 201))["problem"]

    def update(self, problem, **overrides):
        payload = {key: problem.get(key) for key in
                   ("platform", "number", "name", "url", "language", "code", "contest_id", "version")}
        payload.update(overrides)
        return self.request("PUT", "/api/problems/" + problem["id"], payload)["problem"]

    def source_files(self):
        return sorted(path for path in (self.data / "codes").glob("*") if path.is_file())

    def test_contest_and_all_problems_share_one_record_and_file(self):
        contest = self.contest()
        problem = self.problem(contest_id=contest["id"])
        state = self.request("GET", "/api/state")
        self.assertEqual(len(state["problems"]), 1)
        self.assertEqual(state["problems"][0]["id"], problem["id"])
        self.assertEqual(state["problems"][0]["contest_id"], contest["id"])
        self.assertEqual(state["contests"][0]["problem_count"], 1)
        self.assertNotIn("code", state["problems"][0])
        self.assertEqual(len(self.source_files()), 1)
        self.assertEqual((self.data / problem["code_path"]).read_text(encoding="utf-8"), problem["code"])
        changed = self.update(problem, code="int main() { return 7; }\n", name="修改后的题名")
        self.assertEqual(changed["id"], problem["id"])
        self.assertEqual(changed["code_path"], problem["code_path"])
        self.assertEqual(len(self.source_files()), 1)
        state = self.request("GET", "/api/state")
        self.assertEqual(state["problems"][0]["name"], "修改后的题名")
        self.assertEqual(self.request("GET", "/api/problems/" + problem["id"])["problem"]["code"], changed["code"])

    def test_optional_contest_associate_reassociate_and_unlink_preserve_code(self):
        problem = self.problem()
        first = self.contest()
        second = self.contest(title="另一场", url="https://codeforces.com/contest/2001")
        for contest_id in (first["id"], second["id"], None):
            problem = self.update(problem, contest_id=contest_id)
            self.assertEqual(problem["contest_id"], contest_id)
            self.assertEqual(len(self.source_files()), 1)
            self.assertTrue((self.data / problem["code_path"]).exists())
        state = self.request("GET", "/api/state")
        self.assertEqual([item["problem_count"] for item in state["contests"]], [0, 0])

    def test_codeforces_canonical_duplicate_does_not_overwrite(self):
        problem = self.problem()
        result = self.request("POST", "/api/problems", {
            **problem, "url": "http://www.codeforces.com/problemset/problem/2000/A/?locale=en#statement",
            "code": "duplicate must not overwrite",
        }, expected=409)
        self.assertEqual(result.get("existing_id"), problem["id"])
        self.assertEqual(len(self.source_files()), 1)
        self.assertEqual(self.request("GET", "/api/problems/" + problem["id"])["problem"]["code"], problem["code"])

    def test_atcoder_canonical_duplicate(self):
        problem = self.problem(platform="atcoder", number="A", name="A",
                               url="https://atcoder.jp/contests/abc100/tasks/abc100_a", language="python", code="print(42)\n")
        result = self.request("POST", "/api/problems", {
            **problem, "url": "https://atcoder.jp/contests/abc100/tasks/abc100_a/?lang=ja#task-statement",
        }, expected=409)
        self.assertEqual(result.get("existing_id"), problem["id"])
        self.assertEqual(len(self.source_files()), 1)

    def test_platform_association_and_url_validation(self):
        contest = self.contest(platform="atcoder")
        valid = {"platform": "codeforces", "number": "A", "name": "", "url": "https://codeforces.com/contest/2000/problem/A",
                 "language": "cpp", "code": "int main() {}", "contest_id": contest["id"]}
        self.request("POST", "/api/problems", valid, expected=(400, 422))
        for bad in ("javascript:alert(1)", "https://evil.example/contest/2000/problem/A", "https://codeforces.com.evil.example/contest/2000/problem/A"):
            self.request("POST", "/api/problems", {**valid, "contest_id": None, "url": bad}, expected=(400, 422))
        self.assertEqual(self.request("GET", "/api/state")["problems"], [])
        self.assertEqual(self.source_files(), [])

    def test_language_change_replaces_extension_without_copy(self):
        problem = self.problem()
        old_path = self.data / problem["code_path"]
        updated = self.update(problem, language="python", code="print('你好')\n")
        self.assertEqual(updated["id"], problem["id"])
        self.assertTrue(updated["code_path"].endswith(".py"))
        self.assertFalse(old_path.exists())
        self.assertEqual(len(self.source_files()), 1)
        self.assertEqual((self.data / updated["code_path"]).read_text(encoding="utf-8"), "print('你好')\n")

    def test_contest_title_edit_is_reflected_in_shared_problem(self):
        contest = self.contest()
        problem = self.problem(contest_id=contest["id"])
        current = self.request("GET", "/api/state")["contests"][0]
        self.request("PUT", "/api/contests/" + contest["id"], {
            "platform": current["platform"], "title": "重命名后的比赛", "url": current["url"], "version": current["version"],
        })
        state = self.request("GET", "/api/state")
        self.assertEqual(state["problems"][0]["contest_title"], "重命名后的比赛")
        self.assertEqual(state["problems"][0]["id"], problem["id"])
        self.assertEqual(len(self.source_files()), 1)

    def test_duplicate_update_keeps_both_original_codes(self):
        first = self.problem(code="first code")
        second = self.problem(number="B", url="https://codeforces.com/contest/2000/problem/B", code="second code")
        result = self.request("PUT", "/api/problems/" + second["id"], {
            **second, "url": "https://codeforces.com/problemset/problem/2000/A", "code": "overwrite",
        }, expected=409)
        self.assertEqual(result.get("existing_id"), first["id"])
        self.assertEqual(self.request("GET", "/api/problems/" + first["id"])["problem"]["code"], "first code")
        self.assertEqual(self.request("GET", "/api/problems/" + second["id"])["problem"]["code"], "second code")
        self.assertEqual(len(self.source_files()), 2)

    def test_stale_problem_update_and_delete_cannot_lose_code(self):
        original = self.problem()
        changed = self.update(original, code="newer code\n")
        self.request("PUT", "/api/problems/" + original["id"], {**original, "code": "stale overwrite"}, expected=409)
        self.request("DELETE", "/api/problems/" + original["id"], {"version": original["version"], "confirmed": True}, expected=409)
        self.assertEqual(self.request("GET", "/api/problems/" + original["id"])["problem"]["code"], changed["code"])
        self.assertEqual((self.data / changed["code_path"]).read_text(encoding="utf-8"), changed["code"])

    def test_delete_contest_keep_preserves_problem_and_code(self):
        contest = self.contest()
        problem = self.problem(contest_id=contest["id"])
        contest = self.request("GET", "/api/state")["contests"][0]
        self.request("DELETE", "/api/contests/" + contest["id"], {"version": contest["version"], "keep_problems": True, "confirmed": True})
        state = self.request("GET", "/api/state")
        self.assertEqual(state["contests"], [])
        self.assertEqual(len(state["problems"]), 1)
        self.assertIsNone(state["problems"][0]["contest_id"])
        self.assertTrue((self.data / problem["code_path"]).exists())

    def test_delete_contest_with_problems_removes_only_its_code(self):
        contest = self.contest()
        linked = self.problem(contest_id=contest["id"])
        independent = self.problem(number="B", url="https://codeforces.com/contest/2000/problem/B")
        contest = self.request("GET", "/api/state")["contests"][0]
        self.request("DELETE", "/api/contests/" + contest["id"], {"version": contest["version"], "keep_problems": False, "confirmed": True})
        state = self.request("GET", "/api/state")
        self.assertEqual([item["id"] for item in state["problems"]], [independent["id"]])
        self.assertFalse((self.data / linked["code_path"]).exists())
        self.assertEqual(len(self.source_files()), 1)

    def test_delete_problem_requires_confirmation_then_removes_code(self):
        problem = self.problem()
        self.request("DELETE", "/api/problems/" + problem["id"], {"version": problem["version"]}, expected=(400, 422))
        self.assertTrue((self.data / problem["code_path"]).exists())
        self.request("DELETE", "/api/problems/" + problem["id"], {"version": problem["version"], "confirmed": True})
        self.assertEqual(self.request("GET", "/api/state")["problems"], [])
        self.assertFalse((self.data / problem["code_path"]).exists())
        self.request("GET", "/api/problems/" + problem["id"], expected=404)

    def test_persistence_after_restart_with_chinese_and_space_path(self):
        contest = self.contest()
        problem = self.problem(contest_id=contest["id"], code="// 中文注释\nint main() {}\n")
        self.stop_server()
        self.start_server()
        fetched = self.request("GET", "/api/problems/" + problem["id"])["problem"]
        self.assertEqual(fetched["code"], problem["code"])
        self.assertEqual(fetched["contest_id"], contest["id"])
        self.assertEqual(len(self.source_files()), 1)

    def test_http_csrf_origin_and_host_protection(self):
        payload = {"platform": "codeforces", "title": "Forbidden", "url": "https://codeforces.com/contest/2000"}
        self.request("POST", "/api/contests", payload, expected=403, headers={"X-CSRF-Token": "wrong"})
        self.request("POST", "/api/contests", payload, expected=403, headers={"Origin": "https://evil.example"})
        self.request("GET", "/api/state", expected=(400, 403), headers={"Host": "evil.example"})
        self.assertEqual(self.request("GET", "/api/state")["contests"], [])

    def test_repeat_launch_reuses_existing_server_even_with_different_port(self):
        problem = self.problem()
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(PROJECT / "app.py"), "--data-dir", str(self.data),
             "--port", "0", "--no-browser"],
            cwd=str(PROJECT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        self.assertIn(self.base.encode("ascii"), result.stdout)
        self.assertEqual(self.request("GET", "/api/problems/" + problem["id"])["problem"]["code"], problem["code"])
        self.assertEqual(len(self.source_files()), 1)

    def test_concurrent_duplicate_add_has_one_winner(self):
        payload = {"platform": "codeforces", "number": "A", "name": "same",
                   "url": "https://codeforces.com/contest/2000/problem/A", "language": "cpp", "code": "int main() {}", "contest_id": None}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.request("POST", "/api/problems", payload, expected=(200, 201, 409)), range(2)))
        self.assertEqual(sum("problem" in item for item in results), 1)
        self.assertEqual(sum("error" in item for item in results), 1)
        self.assertEqual(len(self.request("GET", "/api/state")["problems"]), 1)
        self.assertEqual(len(self.source_files()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
