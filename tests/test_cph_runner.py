"""CPH-compatible C++ runner tests and persisted test-case coverage."""

import shutil
import secrets
import shutil
import os
from pathlib import Path
import time
import unittest

import app as app_module


PROJECT = Path(__file__).resolve().parents[1]
USER_GXX = Path(
    r"D:\x86_64-8.1.0-release-posix-seh-rt_v6-rev0\mingw64\bin\g++.exe"
)


def available_compiler():
    if USER_GXX.is_file():
        return USER_GXX
    discovered = shutil.which("g++")
    return Path(discovered) if discovered else None


class CphRunnerTests(unittest.TestCase):
    def test_judge_uses_cph_crlf_and_line_trim_rules(self):
        runner = app_module.CppTestRunner(Path("g++"), "gnu++14")
        self.assertTrue(
            runner.outputs_match("1 2\r\n3\r\n", "1 2\n  3  ")
        )
        self.assertFalse(runner.outputs_match("1\n2\n", "1\n2\n3\n"))
        self.assertFalse(runner.outputs_match("1 2\n", "1  2\n"))

    def test_repository_persists_cph_test_cases_in_the_database(self):
        tmp = PROJECT / ".test-tmp" / f"cph-store-{secrets.token_hex(6)}"
        tmp.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, tmp, True)
        repo = app_module.Repository(tmp / "data")
        self.addCleanup(lambda: repo.close() if repo is not None else None)
        problem = repo.create_problem(
            {
                "platform": "Codeforces",
                "number": "A",
                "name": "CPH 用例",
                "url": "https://codeforces.com/contest/1/problem/A",
                "language": "cpp",
                "code": "int main() { return 0; }\n",
                "contest_id": None,
                "algorithm_id": None,
            }
        )
        tests = repo.replace_problem_tests(
            problem["id"],
            {
                "tests": [
                    {"input": "1 2\n", "output": "3\n"},
                    {"input": "3 4\n", "output": "7\n"},
                ]
            },
        )
        self.assertEqual(len(tests), 2)
        schema = repo.db.execute(
            "SELECT value FROM settings WHERE key='schema_version'"
        ).fetchone()[0]
        self.assertEqual(schema, "8")
        self.assertEqual(
            repo.db.execute(
                "SELECT COUNT(*) FROM problem_tests WHERE problem_id=?",
                (problem["id"],),
            ).fetchone()[0],
            2,
        )

        repo.close()
        repo = None
        reopened = app_module.Repository(tmp / "data")
        self.addCleanup(reopened.close)
        self.assertEqual(
            reopened.get_problem(problem["id"])["tests"],
            tests,
        )

        reopened.delete_problem(
            problem["id"],
            {"version": problem["version"], "confirmed": True},
        )
        self.assertEqual(
            reopened.db.execute(
                "SELECT COUNT(*) FROM problem_tests WHERE problem_id=?",
                (problem["id"],),
            ).fetchone()[0],
            0,
        )

    def test_compiler_config_defaults_to_the_vscode_gcc_and_gnu14(self):
        config = app_module._normalized_user_config(
            {"format": 1, "data_dir": ""}
        )
        compiler_path, standard = app_module.resolve_cpp_compiler(config)
        if USER_GXX.is_file():
            self.assertEqual(compiler_path, USER_GXX)
        self.assertEqual(standard, "gnu++14")

    def test_configured_missing_compiler_does_not_silently_fallback(self):
        missing = PROJECT / ".test-tmp" / "missing-gpp" / "g++.exe"
        config = app_module._normalized_user_config(
            {
                "format": 1,
                "data_dir": "",
                "compiler": {
                    "cpp_path": str(missing),
                    "cpp_standard": "gnu++14",
                },
            }
        )
        compiler_path, standard = app_module.resolve_cpp_compiler(config)
        self.assertIsNone(compiler_path)
        self.assertEqual(standard, "gnu++14")

    @unittest.skipUnless(available_compiler(), "g++ is required")
    def test_runner_supports_int128_multiset_and_unordered_map(self):
        runner = app_module.CppTestRunner(
            available_compiler(),
            "gnu++14",
            temp_root=PROJECT / ".test-tmp",
        )
        code = r"""
#include <bits/stdc++.h>
using namespace std;

string toString(__int128 value) {
    if (value == 0) return "0";
    string result;
    while (value > 0) {
        result.push_back(char('0' + value % 10));
        value /= 10;
    }
    reverse(result.begin(), result.end());
    return result;
}

int main() {
    __int128 value = 1;
    for (int i = 0; i < 100; ++i) value *= 2;
    multiset<int> values{3, 1, 2};
    unordered_map<string, int> counts;
    counts["答案"] = 20;
    cout << toString(value) << '\n';
    cout << *values.begin() << ' ' << counts["答案"] << '\n';
}
"""
        result = runner.run(
            code,
            [{
                "input": "",
                "output": "1267650600228229401496703205376\n1 20\n",
            }],
            time_limit_ms=3000,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["compile"]["status"], "success")
        self.assertEqual(result["cases"][0]["status"], "passed")

    @unittest.skipUnless(available_compiler(), "g++ is required")
    def test_runner_reports_compile_error_runtime_error_and_timeout(self):
        runner = app_module.CppTestRunner(
            available_compiler(),
            "gnu++14",
            temp_root=PROJECT / ".test-tmp",
        )
        compile_error = runner.run(
            "int main() { this_is_not_cpp; }\n",
            [{"input": "", "output": ""}],
        )
        self.assertEqual(compile_error["compile"]["status"], "error")
        self.assertFalse(compile_error["ok"])

        runtime_error = runner.run(
            "int main() { return 1; }\n",
            [{"input": "", "output": ""}],
        )
        self.assertEqual(runtime_error["cases"][0]["status"], "runtime_error")
        self.assertFalse(runtime_error["ok"])

        if os.name == "nt":
            crash = runner.run(
                "#include <windows.h>\n"
                "int main(){RaiseException(0xC0000005,0,0,nullptr);}\n",
                [{"input": "", "output": ""}],
                time_limit_ms=3000,
            )
            self.assertEqual(crash["cases"][0]["status"], "runtime_error")
            self.assertLess(crash["cases"][0]["elapsed_ms"], 5000)

        started = time.monotonic()
        timeout = runner.run(
            "int main() { for (;;) {} }\n",
            [{"input": "", "output": ""}],
            time_limit_ms=120,
        )
        self.assertEqual(timeout["cases"][0]["status"], "time_limit")
        self.assertLess(time.monotonic() - started, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
