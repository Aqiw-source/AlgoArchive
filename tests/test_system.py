"""End-to-end regression tests; no network or third-party packages required.

Run from the project directory: python -m unittest discover -s tests -v
Each test launches an isolated server with a temporary database and code folder.
"""

import base64
import concurrent.futures
import json
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request


PROJECT = Path(__file__).resolve().parents[1]
VSCODE_GXX = Path(
    r"D:\x86_64-8.1.0-release-posix-seh-rt_v6-rev0\mingw64\bin\g++.exe"
)


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="algo-test-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "中文目录 用户 数据"
        self.config_path = Path(self.tmp.name) / "config" / "config.json"
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
             "--config-path", str(self.config_path),
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
                    self.index_html = html
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
        platform_key = platform.casefold()
        default_url = {
            "codeforces": "https://codeforces.com/contest/2000",
            "atcoder": "https://atcoder.jp/contests/abc100",
        }.get(platform_key, "比赛链接稍后补充")
        url = url or default_url
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

    def algorithm(self, **overrides):
        payload = {
            "name": "树状数组",
            "category": "数据结构",
            "description": "支持单点修改与区间查询。",
            "links": [
                {"title": "OI Wiki", "url": "https://oi-wiki.org/ds/fenwick/"},
                {"title": "参考文章", "url": "https://example.com/fenwick"},
            ],
        }
        payload.update(overrides)
        return self.request(
            "POST", "/api/algorithms", payload, expected=(200, 201)
        )["algorithm"]

    def snippet(self, algorithm_id, **overrides):
        payload = {
            "title": "单点修改版",
            "language": "cpp",
            "code": "#include <bits/stdc++.h>\nint bit[100];\n",
        }
        payload.update(overrides)
        return self.request(
            "POST",
            f"/api/algorithms/{algorithm_id}/snippets",
            payload,
            expected=(200, 201),
        )["snippet"]

    def update(self, problem, **overrides):
        payload = {key: problem.get(key) for key in
                   ("platform", "number", "name", "url", "language", "code", "contest_id", "algorithm_id", "version")}
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

    @unittest.skipUnless(
        VSCODE_GXX.is_file() or shutil.which("g++"),
        "g++ is required",
    )
    def test_cph_test_cases_save_run_and_survive_restart(self):
        problem = self.problem(
            number="CPH",
            name="A+B",
            url="https://example.com/problems/a-plus-b",
            code=(
                "#include <bits/stdc++.h>\n"
                "using namespace std;\n"
                "int main(){int a,b;cin>>a>>b;cout<<a+b<<'\\n';}\n"
            ),
        )
        tests = [
            {"input": "1 2\n", "output": "3\n"},
            {"input": "-4 9\n", "output": "5\n"},
        ]
        saved = self.request(
            "PUT",
            f"/api/problems/{problem['id']}/tests",
            {"tests": tests},
        )["tests"]
        self.assertEqual(
            [{"input": item["input"], "output": item["output"]} for item in saved],
            tests,
        )
        result = self.request(
            "POST",
            f"/api/problems/{problem['id']}/run",
            {
                "run_id": "system-test-cph-run",
                "code": problem["code"],
                "tests": tests,
                "time_limit_ms": 3000,
            },
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(
            [item["status"] for item in result["cases"]],
            ["passed", "passed"],
        )

        self.stop_server()
        self.start_server()
        loaded = self.request(
            "GET",
            f"/api/problems/{problem['id']}",
        )["problem"]
        self.assertEqual(
            [
                {"input": item["input"], "output": item["output"]}
                for item in loaded["tests"]
            ],
            tests,
        )

    @unittest.skipUnless(
        VSCODE_GXX.is_file() or shutil.which("g++"),
        "g++ is required",
    )
    def test_cph_run_can_be_stopped(self):
        problem = self.problem(
            number="STOP",
            name="无限循环",
            url="https://example.com/problems/infinite-loop",
            code="int main(){for(;;){}}\n",
        )
        run_id = "system-stop-cph-run"
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self.request,
                "POST",
                f"/api/problems/{problem['id']}/run",
                {
                    "run_id": run_id,
                    "code": problem["code"],
                    "tests": [{"input": "", "output": ""}],
                    "time_limit_ms": 5000,
                },
            )
            deadline = time.monotonic() + 4
            stopped = False
            while time.monotonic() < deadline:
                stop = self.request(
                    "POST",
                    f"/api/problems/{problem['id']}/run/stop",
                    {"run_id": run_id},
                )
                if stop["ok"]:
                    stopped = True
                    break
                time.sleep(0.1)
            self.assertTrue(stopped, "run did not become stoppable")
            result = future.result(timeout=8)
        self.assertTrue(result["cancelled"], result)
        if result["cases"]:
            self.assertEqual(result["cases"][0]["status"], "cancelled")

    @unittest.skipUnless(
        VSCODE_GXX.is_file() or shutil.which("g++"),
        "g++ is required",
    )
    def test_standalone_compiler_runs_without_creating_a_problem(self):
        before = self.request("GET", "/api/state")
        result = self.request(
            "POST",
            "/api/compiler/run",
            {
                "run_id": "standalone-compiler-run",
                "code": (
                    "#include <bits/stdc++.h>\n"
                    "using namespace std;\n"
                    "int main(){int a,b;cin>>a>>b;cout<<a+b<<'\\n';}\n"
                ),
                "tests": [
                    {"input": "2 5\n", "output": "7\n"},
                    {"input": "-3 8\n", "output": "5\n"},
                ],
                "time_limit_ms": 3000,
            },
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(
            [case["status"] for case in result["cases"]],
            ["passed", "passed"],
        )
        after = self.request("GET", "/api/state")
        self.assertEqual(after["problems"], before["problems"])
        self.assertEqual(self.source_files(), [])
        stopped = self.request(
            "POST",
            "/api/compiler/run/stop",
            {"run_id": "standalone-stop-missing"},
        )
        self.assertFalse(stopped["ok"])

    def test_custom_contest_platform_and_link_can_be_created_and_updated(self):
        contest = self.contest(
            platform="洛谷",
            title="洛谷公开赛",
            url="比赛链接稍后补充",
        )
        self.assertEqual(contest["platform"], "洛谷")
        self.assertEqual(contest["url"], "比赛链接稍后补充")

        updated = self.request("PUT", "/api/contests/" + contest["id"], {
            "platform": "牛客",
            "title": "牛客练习赛",
            "url": "https://ac.nowcoder.com/acm/contest/12345",
            "version": contest["version"],
        })["contest"]
        self.assertEqual(updated["platform"], "牛客")
        self.assertEqual(updated["url"], "https://ac.nowcoder.com/acm/contest/12345")

    def test_custom_contest_can_contain_same_platform_problem(self):
        contest = self.contest(
            platform="牛客",
            title="牛客周赛",
            url="https://ac.nowcoder.com/acm/contest/67890",
        )
        problem = self.problem(
            platform="牛客",
            number="A",
            name="第一题",
            url="https://ac.nowcoder.com/acm/contest/67890/A",
            contest_id=contest["id"],
        )
        self.assertEqual(problem["contest_id"], contest["id"])
        self.assertEqual(problem["contest_title"], "牛客周赛")
        state = self.request("GET", "/api/state")
        self.assertEqual(state["contests"][0]["problem_count"], 1)

    def test_known_contest_platform_is_normalized_without_restricting_link(self):
        contest = self.contest(
            platform="AtCoder",
            url="https://www.luogu.com.cn/contest/123",
        )
        self.assertEqual(contest["platform"], "atcoder")
        self.assertEqual(contest["url"], "https://www.luogu.com.cn/contest/123")

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

    def test_exact_link_duplicate_does_not_overwrite(self):
        problem = self.problem()
        result = self.request("POST", "/api/problems", {
            **problem, "url": problem["url"],
            "code": "duplicate must not overwrite",
        }, expected=409)
        self.assertEqual(result.get("existing_id"), problem["id"])
        self.assertEqual(len(self.source_files()), 1)
        self.assertEqual(self.request("GET", "/api/problems/" + problem["id"])["problem"]["code"], problem["code"])

    def test_known_platform_name_is_normalized_without_restricting_link(self):
        problem = self.problem(
            platform="AtCoder",
            url="https://www.luogu.com.cn/problem/P3374",
        )
        self.assertEqual(problem["platform"], "atcoder")
        self.assertEqual(
            problem["url"], "https://www.luogu.com.cn/problem/P3374"
        )

    def test_custom_platform_and_non_url_text_are_saved_verbatim(self):
        problem = self.problem(
            platform="本地题库",
            url="题面稍后补充",
        )
        self.assertEqual(problem["platform"], "本地题库")
        self.assertEqual(problem["url"], "题面稍后补充")
        self.assertEqual(len(self.source_files()), 1)

    def test_contest_platform_must_match_problem(self):
        contest = self.contest(platform="atcoder")
        valid = {"platform": "codeforces", "number": "A", "name": "", "url": "https://codeforces.com/contest/2000/problem/A",
                 "language": "cpp", "code": "int main() {}", "contest_id": contest["id"]}
        self.request("POST", "/api/problems", valid, expected=(400, 422))
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
            **second, "url": first["url"], "code": "overwrite",
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

    def test_index_injects_local_user_name(self):
        match = re.search(
            r'<meta\s+name=[\"\']user-name[\"\']\s+content=[\"\']([^\"\']*)',
            self.index_html,
        )
        self.assertIsNotNone(match)
        self.assertNotEqual(match.group(1), "__USER_NAME__")
        self.assertTrue(match.group(1).strip())

    def test_index_exposes_github_repository_and_author(self):
        self.assertIn(
            'href="https://github.com/Aqiw-source/AlgoArchive"',
            self.index_html,
        )
        self.assertIn('rel="noopener noreferrer"', self.index_html)
        self.assertIn("作者 Aqiw", self.index_html)

    def test_index_exposes_luogu_workspace(self):
        self.assertIn('href="#platform/luogu"', self.index_html)
        self.assertIn(">洛谷</a>", self.index_html)

    def test_index_exposes_niuke_workspace(self):
        self.assertIn('href="#platform/niuke"', self.index_html)
        self.assertIn(">牛客</a>", self.index_html)

    def test_index_exposes_code_compiler_below_all_problems(self):
        problems_position = self.index_html.index('data-nav="problems"')
        compiler_position = self.index_html.index('data-nav="compiler"')
        self.assertGreater(compiler_position, problems_position)
        self.assertIn("代码试跑", self.index_html)

    def test_code_playground_has_missing_compiler_setup_prompt(self):
        script = (PROJECT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("compiler-missing-banner", script)
        self.assertIn("data-open-compiler-settings", script)
        self.assertIn("未找到 C++ 编译器", script)
        self.assertIn("选择 g++ 编译器", script)
        self.assertIn("完整 MinGW", script)

    def test_profile_name_and_avatar_persist_after_restart(self):
        avatar = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        avatar_bytes = base64.b64decode(avatar.split(",", 1)[1])
        saved = self.request("PUT", "/api/profile", {
            "name": "本地用户",
            "avatar": avatar,
        })["profile"]
        self.assertEqual(saved["name"], "本地用户")
        self.assertRegex(saved["avatar"], r"^/api/profile/avatar\?v=\d+$")
        avatar_file = self.data / "avatar" / "avatar.png"
        self.assertEqual(avatar_file.read_bytes(), avatar_bytes)
        with urllib.request.urlopen(self.base + saved["avatar"], timeout=5) as response:
            self.assertEqual(response.headers.get_content_type(), "image/png")
            self.assertEqual(response.read(), avatar_bytes)
        state_profile = self.request("GET", "/api/state")["profile"]
        self.assertEqual(state_profile["name"], "本地用户")
        self.assertRegex(state_profile["avatar"], r"^/api/profile/avatar\?v=\d+$")

        renamed = self.request("PUT", "/api/profile", {"name": "改名用户"})["profile"]
        self.assertEqual(renamed["avatar"], saved["avatar"])
        self.assertTrue(avatar_file.is_file())

        self.stop_server()
        self.start_server()
        state_profile = self.request("GET", "/api/state")["profile"]
        self.assertEqual(state_profile["name"], "改名用户")
        self.assertRegex(state_profile["avatar"], r"^/api/profile/avatar\?v=\d+$")

        reset = self.request("PUT", "/api/profile", {
            "name": "改名用户",
            "avatar": "",
        })["profile"]
        self.assertEqual(reset["avatar"], "")
        self.assertEqual(list((self.data / "avatar").glob("avatar.*")), [])

    def test_profile_rejects_empty_name_and_invalid_avatar(self):
        self.request("PUT", "/api/profile", {
            "name": "",
            "avatar": "",
        }, expected=400)
        self.request("PUT", "/api/profile", {
            "name": "Aqiw",
            "avatar": "data:text/plain;base64,SGVsbG8=",
        }, expected=400)

    def test_legacy_data_url_avatar_migrates_to_file(self):
        avatar = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        self.stop_server()
        database = sqlite3.connect(self.data / "archive.sqlite3")
        try:
            database.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES ('profile_name','旧用户')"
            )
            database.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES ('profile_avatar',?)",
                (avatar,),
            )
            database.commit()
        finally:
            database.close()
        self.start_server()
        profile = self.request("GET", "/api/state")["profile"]
        self.assertEqual(profile["name"], "旧用户")
        self.assertRegex(profile["avatar"], r"^/api/profile/avatar\?v=\d+$")
        self.assertTrue((self.data / "avatar" / "avatar.png").is_file())
        database = sqlite3.connect(self.data / "archive.sqlite3")
        try:
            legacy = database.execute(
                "SELECT value FROM settings WHERE key='profile_avatar'"
            ).fetchone()
        finally:
            database.close()
        self.assertIsNone(legacy)

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

    def test_algorithm_supports_multiple_links_and_snippets(self):
        algorithm = self.algorithm()
        first = self.snippet(
            algorithm["id"],
            title="单点修改版",
            language="cpp",
            code="int bit[100];\n",
        )
        second = self.snippet(
            algorithm["id"],
            title="二维版本",
            language="python",
            code="bit = []\n",
        )

        detail = self.request("GET", "/api/algorithms/" + algorithm["id"])["algorithm"]
        self.assertEqual(len(detail["links"]), 2)
        self.assertEqual(
            {item["id"] for item in detail["snippets"]},
            {first["id"], second["id"]},
        )
        self.assertNotIn("code", detail["snippets"][0])
        self.assertEqual(
            self.request("GET", "/api/algorithm-snippets/" + first["id"])["snippet"]["code"],
            "int bit[100];\n",
        )
        self.assertEqual(len(self.source_files()), 2)

        state = self.request("GET", "/api/state")
        self.assertEqual(state["stats"]["algorithm_count"], 1)
        self.assertEqual(state["stats"]["snippet_count"], 2)
        self.assertEqual(len(state["algorithms"][0]["snippets"]), 2)
        self.assertNotIn("code", state["algorithms"][0]["snippets"][0])

    def test_algorithm_links_are_deduplicated_after_normalization(self):
        algorithm = self.algorithm(
            links=[
                {"title": "OI Wiki", "url": "https://oi-wiki.org/ds/fenwick/"},
                {"title": "区间说明", "url": "https://oi-wiki.org/ds/fenwick/#range"},
            ]
        )
        detail = self.request("GET", "/api/algorithms/" + algorithm["id"])["algorithm"]
        self.assertEqual(len(detail["links"]), 1)
        self.assertEqual(detail["links"][0]["title"], "OI Wiki")

    def test_algorithm_can_contain_problems_without_duplicating_code(self):
        algorithm = self.algorithm()
        problem = self.problem(algorithm_id=algorithm["id"])
        self.assertEqual(problem["algorithm_id"], algorithm["id"])
        self.assertEqual(problem["algorithm_name"], algorithm["name"])

        detail = self.request("GET", "/api/algorithms/" + algorithm["id"])["algorithm"]
        self.assertEqual(detail["problem_count"], 1)
        state = self.request("GET", "/api/state")
        self.assertEqual(state["algorithms"][0]["problem_count"], 1)
        self.assertEqual(state["problems"][0]["algorithm_name"], algorithm["name"])

        contest = self.contest()
        updated = self.update(
            problem,
            contest_id=contest["id"],
            algorithm_id=algorithm["id"],
        )
        self.assertEqual(updated["contest_id"], contest["id"])
        self.assertEqual(updated["algorithm_id"], algorithm["id"])

        self.request(
            "DELETE",
            "/api/algorithms/" + algorithm["id"],
            {"version": algorithm["version"], "confirmed": True},
        )
        kept = self.request("GET", "/api/problems/" + problem["id"])["problem"]
        self.assertIsNone(kept["algorithm_id"])
        self.assertEqual(kept["contest_id"], contest["id"])
        self.assertEqual(kept["code"], problem["code"])

    def test_algorithm_problem_order_can_be_changed(self):
        algorithm = self.algorithm()
        first = self.problem(
            number="A",
            name="第一题",
            url="https://example.com/order/a",
            algorithm_id=algorithm["id"],
        )
        second = self.problem(
            number="B",
            name="第二题",
            url="https://example.com/order/b",
            algorithm_id=algorithm["id"],
        )
        third = self.problem(
            number="C",
            name="第三题",
            url="https://example.com/order/c",
            algorithm_id=algorithm["id"],
        )
        ordered = sorted(
            self.request("GET", "/api/state")["problems"],
            key=lambda item: item["algorithm_order"],
        )
        self.assertEqual(
            [item["id"] for item in ordered],
            [first["id"], second["id"], third["id"]],
        )

        current = self.request("GET", "/api/state")["algorithms"][0]
        result = self.request(
            "PUT",
            f"/api/algorithms/{algorithm['id']}/problems/order",
            {
                "version": current["version"],
                "problem_ids": [third["id"], first["id"], second["id"]],
            },
        )
        self.assertEqual(result["algorithm"]["id"], algorithm["id"])
        ordered = sorted(
            self.request("GET", "/api/state")["problems"],
            key=lambda item: item["algorithm_order"],
        )
        self.assertEqual(
            [item["id"] for item in ordered],
            [third["id"], first["id"], second["id"]],
        )
        self.assertEqual(
            [item["algorithm_order"] for item in ordered],
            [0, 1, 2],
        )

        invalid = self.request(
            "PUT",
            f"/api/algorithms/{algorithm['id']}/problems/order",
            {
                "version": result["algorithm"]["version"],
                "problem_ids": [third["id"], first["id"]],
            },
            expected=409,
        )
        self.assertEqual(invalid["code"], "problem_set_changed")
        ordered = sorted(
            self.request("GET", "/api/state")["problems"],
            key=lambda item: item["algorithm_order"],
        )
        self.assertEqual(
            [item["id"] for item in ordered],
            [third["id"], first["id"], second["id"]],
        )

    def test_all_problem_order_can_be_changed_and_reversed(self):
        first = self.problem(
            number="A",
            url="https://example.com/global-order/a",
        )
        second = self.problem(
            number="B",
            url="https://example.com/global-order/b",
        )
        third = self.problem(
            number="C",
            url="https://example.com/global-order/c",
        )
        state = self.request("GET", "/api/state")
        version = state["problem_order_version"]
        ordered = sorted(state["problems"], key=lambda item: item["global_order"])
        self.assertEqual(
            [item["id"] for item in ordered],
            [first["id"], second["id"], third["id"]],
        )

        result = self.request(
            "PUT",
            "/api/problems/order",
            {
                "version": version,
                "problem_ids": [third["id"], second["id"], first["id"]],
            },
        )
        self.assertEqual(result["problem_order_version"], version + 1)
        ordered = sorted(
            self.request("GET", "/api/state")["problems"],
            key=lambda item: item["global_order"],
        )
        self.assertEqual(
            [item["id"] for item in ordered],
            [third["id"], second["id"], first["id"]],
        )
        self.assertEqual(
            [item["global_order"] for item in ordered],
            [0, 1, 2],
        )

        stale = self.request(
            "PUT",
            "/api/problems/order",
            {
                "version": version,
                "problem_ids": [first["id"], second["id"], third["id"]],
            },
            expected=409,
        )
        self.assertEqual(stale["code"], "version_conflict")

    def test_problem_import_supports_code_and_existing_relations(self):
        contest = self.contest(
            platform="洛谷",
            title="导入测试比赛",
            url="https://www.luogu.com.cn/contest/import",
        )
        algorithm = self.algorithm(name="树状数组（导入）")
        payload = {
            "problems": [
                {
                    "contest": contest["title"],
                    "algorithm": algorithm["name"],
                    "number": "P1001",
                    "name": "导入的第一题",
                    "url": "https://www.luogu.com.cn/problem/P1001",
                    "language": "python",
                    "code": "print('imported')\n",
                },
                {
                    "platform": "AcWing",
                    "algorithm_id": algorithm["id"],
                    "number": "101",
                    "name": "导入的第二题",
                    "url": "https://www.acwing.com/problem/content/101/",
                    "language": "cpp",
                    "code": "int main() { return 0; }\n",
                },
            ]
        }
        result = self.request("POST", "/api/problems/import", payload, expected=201)
        self.assertEqual(result["count"], 2)
        imported = [
            self.request("GET", "/api/problems/" + identifier)["problem"]
            for identifier in result["problem_ids"]
        ]
        self.assertEqual(imported[0]["platform"], "洛谷")
        self.assertEqual(imported[0]["contest_id"], contest["id"])
        self.assertEqual(imported[0]["algorithm_id"], algorithm["id"])
        self.assertEqual(imported[0]["code"], "print('imported')\n")
        self.assertEqual(imported[1]["platform"], "AcWing")
        self.assertEqual(imported[1]["algorithm_id"], algorithm["id"])
        self.assertEqual(len(self.source_files()), 2)

        before = self.source_files()
        duplicate = {
            "problems": [
                {
                    "platform": "自定义",
                    "number": "X",
                    "name": "不会写入",
                    "url": "https://example.com/import/new",
                    "code": "int main() {}\n",
                },
                {
                    "platform": "洛谷",
                    "number": "P1001",
                    "name": "重复题目",
                    "url": "https://www.luogu.com.cn/problem/P1001",
                    "code": "duplicate\n",
                },
            ]
        }
        self.request("POST", "/api/problems/import", duplicate, expected=409)
        self.assertEqual(self.source_files(), before)

    def test_stale_algorithm_and_snippet_updates_are_rejected(self):
        algorithm = self.algorithm()
        snippet = self.snippet(algorithm["id"])
        current = self.request("GET", "/api/algorithms/" + algorithm["id"])["algorithm"]
        updated = self.request("PUT", "/api/algorithms/" + algorithm["id"], {
            "name": "树状数组（新版）",
            "category": current["category"],
            "description": current["description"],
            "links": current["links"],
            "version": current["version"],
        })["algorithm"]
        self.request("PUT", "/api/algorithms/" + algorithm["id"], {
            "name": "过期覆盖",
            "category": current["category"],
            "description": current["description"],
            "links": current["links"],
            "version": current["version"],
        }, expected=409)
        self.assertEqual(
            self.request("GET", "/api/algorithms/" + algorithm["id"])["algorithm"]["name"],
            updated["name"],
        )

        changed = self.request("PUT", "/api/algorithm-snippets/" + snippet["id"], {
            "title": snippet["title"],
            "language": "python",
            "code": "print(42)\n",
            "version": snippet["version"],
        })["snippet"]
        self.request("PUT", "/api/algorithm-snippets/" + snippet["id"], {
            "title": snippet["title"],
            "language": "cpp",
            "code": "stale",
            "version": snippet["version"],
        }, expected=409)
        self.assertEqual(
            self.request("GET", "/api/algorithm-snippets/" + snippet["id"])["snippet"]["code"],
            changed["code"],
        )

    def test_delete_snippet_and_algorithm_manage_only_expected_files(self):
        algorithm = self.algorithm()
        first = self.snippet(algorithm["id"], code="first\n")
        second = self.snippet(
            algorithm["id"],
            title="第二份",
            language="python",
            code="second\n",
        )
        self.request(
            "DELETE",
            "/api/algorithm-snippets/" + first["id"],
            {"version": first["version"], "confirmed": True},
        )
        self.assertFalse((self.data / first["code_path"]).exists())
        self.assertTrue((self.data / second["code_path"]).exists())

        current = self.request("GET", "/api/algorithms/" + algorithm["id"])["algorithm"]
        self.request(
            "DELETE",
            "/api/algorithms/" + algorithm["id"],
            {"version": current["version"], "confirmed": True},
        )
        self.assertEqual(self.request("GET", "/api/state")["algorithms"], [])
        self.assertFalse((self.data / second["code_path"]).exists())
        self.assertEqual(self.source_files(), [])

    def test_algorithm_validation_rejects_unsafe_link_and_bad_language(self):
        self.request("POST", "/api/algorithms", {
            "name": "不安全链接",
            "category": "",
            "description": "",
            "links": [{"title": "bad", "url": "javascript:alert(1)"}],
        }, expected=400)
        algorithm = self.algorithm()
        self.request("POST", f"/api/algorithms/{algorithm['id']}/snippets", {
            "title": "坏语言",
            "language": "rust",
            "code": "fn main() {}",
        }, expected=400)

    def test_algorithm_persists_after_restart(self):
        algorithm = self.algorithm()
        snippet = self.snippet(algorithm["id"], code="// 中文持久化\nint bit[10];\n")
        self.stop_server()
        self.start_server()

        detail = self.request("GET", "/api/algorithms/" + algorithm["id"])["algorithm"]
        self.assertEqual(detail["name"], "树状数组")
        self.assertEqual(len(detail["links"]), 2)
        self.assertEqual(len(detail["snippets"]), 1)
        saved = self.request("GET", "/api/algorithm-snippets/" + snippet["id"])["snippet"]
        self.assertEqual(saved["code"], "// 中文持久化\nint bit[10];\n")

    def test_browser_settings_persist_across_restart(self):
        initial = self.request("GET", "/api/settings")["settings"]
        self.assertEqual(initial["browser"]["mode"], "default")
        updated = self.request("PUT", "/api/settings/browser", {
            "mode": "edge",
            "window_mode": "app",
            "custom_path": "",
        })["browser"]
        self.assertEqual(updated["mode"], "edge")
        self.assertEqual(updated["window_mode"], "app")

        self.stop_server()
        self.start_server()
        saved = self.request("GET", "/api/settings")["settings"]
        self.assertEqual(saved["browser"]["mode"], "edge")
        self.assertEqual(saved["browser"]["window_mode"], "app")

    @unittest.skipUnless(
        VSCODE_GXX.is_file() or shutil.which("g++"),
        "g++ is required",
    )
    def test_compiler_settings_and_cph_attribution_are_reported(self):
        settings = self.request("GET", "/api/settings")["settings"]
        self.assertEqual(settings["compiler"]["standard"], "gnu++14")
        self.assertTrue(settings["compiler"]["available"])
        self.assertEqual(settings["cph"]["author"], "Divyanshu Agrawal")
        self.assertEqual(settings["cph"]["license"], "GPL-3.0-or-later")

        diagnostic = self.request(
            "POST",
            "/api/settings/compiler/test",
            {
                "cpp_path": str(
                    VSCODE_GXX if VSCODE_GXX.is_file() else Path(shutil.which("g++"))
                ),
                "standard": "gnu++14",
            },
        )["diagnostic"]
        self.assertTrue(diagnostic["ok"], diagnostic)
        self.assertEqual(
            diagnostic["checks"],
            {"__int128": True, "multiset": True, "unordered_map": True},
        )

        updated = self.request(
            "PUT",
            "/api/settings/compiler",
            {
                "cpp_path": diagnostic["compiler"],
                "standard": "gnu++14",
            },
        )["compiler"]
        self.assertEqual(updated["standard"], "gnu++14")
        self.assertTrue(updated["available"])

    def test_backup_and_restore_round_trip(self):
        contest = self.contest()
        problem = self.problem(contest_id=contest["id"])
        source = (self.data / problem["code_path"]).read_text(encoding="utf-8")

        backup = self.request(
            "POST",
            "/api/backups/create",
            {},
            expected=201,
        )["backup"]
        self.assertTrue(Path(backup["path"]).is_file())
        self.request(
            "DELETE",
            "/api/problems/" + problem["id"],
            {"version": problem["version"], "confirmed": True},
        )
        self.assertEqual(self.request("GET", "/api/state")["problems"], [])

        restored = self.request("POST", "/api/backups/restore", {
            "name": backup["name"],
            "confirmed": True,
        })
        self.assertTrue(restored["ok"])
        state = self.request("GET", "/api/state")
        self.assertEqual(len(state["problems"]), 1)
        self.assertEqual(state["problems"][0]["id"], problem["id"])
        self.assertEqual(
            (self.data / problem["code_path"]).read_text(encoding="utf-8"),
            source,
        )

    def test_data_directory_change_migrates_and_updates_saved_config(self):
        problem = self.problem()
        target = Path(self.tmp.name) / "迁移后的数据"
        result = self.request("POST", "/api/data-directory", {
            "data_dir": str(target),
        })
        self.assertTrue(result["restart_required"])
        self.assertEqual(result["new_data_dir"], str(target.resolve()))
        self.process.wait(timeout=8)

        self.assertTrue((target / "archive.sqlite3").is_file())
        moved = sqlite3.connect(target / "archive.sqlite3")
        try:
            count = moved.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
        finally:
            moved.close()
        self.assertEqual(count, 1)
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["data_dir"], str(target.resolve()))
        self.assertTrue((target / problem["code_path"]).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
