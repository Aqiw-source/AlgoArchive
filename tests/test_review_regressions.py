"""Local reliability regressions from the 2.2.0 review."""

import base64
import concurrent.futures
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import app
import cph_runner
from tests.test_cph_runner import available_compiler


class ReviewStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = app.Repository(self.root / "source")
        self.addCleanup(self.repo.close)
        self.payload = dict(platform="Codeforces", name="Demo", url="example.com/1",
                            language="cpp", code="int main() {}",
                            tests=[dict(input="1", output="1")])

    def test_create_and_update_commit_code_and_tests_together(self):
        problem = self.repo.create_problem(self.payload)
        self.assertEqual(problem["tests"][0]["input"], "1")
        saved = self.repo.update_problem(problem["id"], dict(
            version=problem["version"], code="// v2", tests=[dict(input="2", output="2")]))
        self.assertEqual(saved["version"], problem["version"] + 1)
        self.assertEqual(saved["code"], "// v2")
        self.assertEqual(saved["tests"][0]["input"], "2")

    def test_invalid_tests_reject_entire_new_or_existing_save(self):
        with self.assertRaises(app.AppError):
            self.repo.create_problem(dict(self.payload, tests="invalid"))
        self.assertEqual(self.repo.state()["problems"], [])
        self.assertEqual(list((self.repo.data_dir / "codes").iterdir()), [])
        problem = self.repo.create_problem(self.payload)
        with self.assertRaises(app.AppError):
            self.repo.update_problem(problem["id"], dict(version=1, code="// rejected", tests=[None]))
        self.assertEqual(self.repo.get_problem(problem["id"]), problem)

    def test_stale_save_cannot_mix_code_and_cases(self):
        original = self.repo.create_problem(self.payload)
        current = self.repo.update_problem(original["id"], dict(
            version=1, code="// editor B", tests=[dict(input="B", output="B")]))
        for save in (self.repo.update_problem, self.repo.replace_problem_tests):
            with self.assertRaises(app.AppError) as error:
                save(original["id"], dict(version=1, code="// editor A",
                                         tests=[dict(input="A", output="A")]))
            self.assertEqual(error.exception.code, "version_conflict")
        self.assertEqual(self.repo.get_problem(original["id"]), current)

    def test_separate_test_save_requires_and_advances_version(self):
        problem = self.repo.create_problem(self.payload)
        with self.assertRaises(app.AppError):
            self.repo.replace_problem_tests(problem["id"], dict(tests=[]))
        self.repo.replace_problem_tests(problem["id"], dict(version=1, tests=[]))
        saved = self.repo.get_problem(problem["id"])
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["tests"], [])
        self.assertEqual(saved["code"], problem["code"])

    def test_pending_file_recovery_keeps_saved_cases_with_saved_code(self):
        problem = self.repo.create_problem(self.payload)
        with mock.patch("app.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(app.AppError):
                self.repo.update_problem(problem["id"], dict(
                    version=1, code="// recovered", tests=[dict(input="3", output="3")]))
        saved = self.repo.get_problem(problem["id"])
        self.assertEqual(saved["code"], "// recovered")
        self.assertEqual(saved["tests"][0]["input"], "3")
        self.assertEqual(saved["version"], 2)

    def test_duplicate_click_and_retry_do_not_create_an_extra_problem(self):
        self.repo.create_problem(self.payload)
        with self.assertRaises(app.AppError):
            self.repo.create_problem(self.payload)
        self.assertEqual(len(self.repo.state()["problems"]), 1)

    def test_migration_rejects_queued_and_post_switch_writes(self):
        problem = self.repo.create_problem(self.payload)
        entered = threading.Event()
        finished = threading.Event()
        outcomes = []
        extract = self.repo._safe_extract_backup

        def write():
            entered.set()
            try:
                self.repo.update_problem(problem["id"], dict(version=1, code="// too late"))
                outcomes.append("saved")
            except app.AppError as error:
                outcomes.append(error.code)
            finally:
                finished.set()

        worker = threading.Thread(target=write)

        def during_copy(archive, destination):
            worker.start()
            self.assertTrue(entered.wait(2))
            self.assertFalse(finished.wait(0.05))
            return extract(archive, destination)

        with mock.patch.object(self.repo, "_safe_extract_backup", side_effect=during_copy):
            self.repo.relocate_to(self.root / "target")
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcomes, ["storage_maintenance"])
        with self.assertRaises(app.AppError):
            self.repo.create_problem(dict(self.payload, url="example.com/2"))
        target = app.Repository(self.root / "target")
        try:
            self.assertEqual(target.get_problem(problem["id"])["code"], problem["code"])
        finally:
            target.close()

    def test_migration_commit_failure_reopens_source_for_writes(self):
        problem = self.repo.create_problem(self.payload)
        with self.assertRaises(OSError):
            self.repo.relocate_to(self.root / "target",
                                  commit=mock.Mock(side_effect=OSError("config write failed")))
        saved = self.repo.update_problem(problem["id"], dict(version=1, code="// still usable"))
        self.assertEqual(saved["code"], "// still usable")

    def test_backup_capacity_contract_and_round_trip(self):
        problem = self.repo.create_problem(self.payload)
        algorithm = self.repo.create_algorithm(dict(name="Demo", category="", description="", links=[]))
        self.repo.create_snippet(algorithm["id"], dict(title="Demo", language="cpp", code="// demo"))
        image = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"demo").decode("ascii")
        self.repo.update_profile(dict(name="Demo", avatar="data:image/png;base64," + image))
        with mock.patch.object(app, "MAX_BACKUP_MEMBERS", 4):
            with self.assertRaises(app.AppError):
                self.repo.create_backup()
        self.assertEqual(self.repo.list_backups(), [])
        with mock.patch.object(app, "MAX_BACKUP_MEMBERS", 5):
            backup = self.repo.create_backup()
            with zipfile.ZipFile(backup["path"]) as archive:
                self.assertEqual(len(archive.infolist()), 5)
            self.repo.restore_backup(backup["name"], confirmed=True)
        self.assertEqual(self.repo.get_problem(problem["id"])["code"], problem["code"])

    def test_backup_size_budget_is_shared_with_restore(self):
        self.repo.create_problem(self.payload)
        with mock.patch.object(app, "MAX_BACKUP_EXPANDED_BYTES", 1):
            with self.assertRaises(app.AppError):
                self.repo.create_backup()
        with mock.patch.object(app, "MAX_BACKUP_UPLOAD_BYTES", 1):
            with self.assertRaises(app.AppError):
                self.repo.create_backup()
        self.assertEqual(self.repo.list_backups(), [])

    def test_platform_stats_use_canonical_identity(self):
        for i, platform in enumerate(("Codeforces", "ATCODER", "aCwInG", "LUOGU", "NowCoder")):
            self.repo.create_problem(dict(self.payload, platform=platform, url=f"example.com/{i}"))
        stats = self.repo.state()["stats"]
        for key in ("codeforces", "atcoder", "acwing", "luogu", "niuke"):
            self.assertEqual(stats[key + "_count"], 1)

    def test_large_backup_over_old_member_limit_can_restore(self):
        seed = self.repo.create_problem(self.payload)
        columns = [row[1] for row in self.repo.db.execute("PRAGMA table_info(problems)")]
        original = dict(self.repo.db.execute("SELECT * FROM problems").fetchone())
        rows = []
        for index in range(9998):
            identifier = f"{index:032x}"
            values = {**original, "id": identifier, "url": f"https://example.com/bulk/{index}",
                      "normalized_url": f"https://example.com/bulk/{index}",
                      "code_path": f"codes/{identifier}.cpp"}
            (self.repo.data_dir / values["code_path"]).write_text("// demo", encoding="utf-8")
            rows.append(tuple(values[key] for key in columns))
        with self.repo.db:
            self.repo.db.executemany(
                "INSERT INTO problems (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")", rows)
        backup = self.repo.create_backup()
        with zipfile.ZipFile(backup["path"]) as archive:
            self.assertEqual(len(archive.infolist()), 10001)
        self.repo.restore_backup(backup["name"], confirmed=True)
        self.assertEqual(len(self.repo.state()["problems"]), 9999)
        self.assertEqual(self.repo.get_problem(seed["id"])["code"], seed["code"])


class ReviewRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runner = cph_runner.CppTestRunner(None)

    def execute(self, source, **kwargs):
        return self.runner._execute([sys.executable, "-c", source], self.root, **kwargs)

    def test_large_unread_input_is_covered_by_deadline(self):
        result = self.execute("import time; time.sleep(0.8)",
                              stdin_data=b"x" * 1024 * 1024, timeout_seconds=0.05)
        self.assertTrue(result["timed_out"])
        self.assertLess(result["elapsed_ms"], 700)

    def test_output_boundary_and_truncation_are_explicit(self):
        with mock.patch.object(cph_runner, "MAX_CAPTURE_BYTES", 256):
            exact = self.execute('import sys; sys.stdout.write("x" * 256)')
            over = self.execute('import sys; sys.stdout.write("x" * 256 + "!")')
            stderr = self.execute('import sys; sys.stderr.write("x" * 257)')
        self.assertFalse(exact["output_limited"])
        self.assertTrue(over["output_limited"])
        self.assertTrue(over["stdout_truncated"])
        self.assertEqual(len(over["stdout"]), 256)
        self.assertTrue(stderr["stderr_truncated"])

    def test_stop_while_input_is_unread_cleans_up(self):
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(self.execute, "import time; time.sleep(2)",
                                 stdin_data=b"x" * 1024 * 1024, timeout_seconds=3)
            threading.Event().wait(0.1)
            self.runner.stop()
            self.assertTrue(future.result(timeout=3)["cancelled"])
        self.assertIsNone(self.runner._active_process)

    def test_slow_input_reader_and_early_exit_finish(self):
        result = self.execute('import sys, time; time.sleep(0.05); print(len(sys.stdin.buffer.read()))',
                              stdin_data=b"x" * 1024 * 1024, timeout_seconds=2)
        self.assertEqual(result["stdout"].strip(), "1048576")
        self.assertFalse(result["timed_out"])
        result = self.execute('pass', stdin_data=b"x" * 1024 * 1024, timeout_seconds=2)
        self.assertEqual(result["return_code"], 0)

    def test_descendants_and_inherited_pipes_close_after_parent_exit(self):
        child = 'import time; time.sleep(1.5); open("child-survived", "w").close()'
        result = self.execute('import subprocess, sys; subprocess.Popen([sys.executable, "-c", ' + repr(child) + '])',
                              timeout_seconds=2)
        self.assertLess(result["elapsed_ms"], 1000)
        threading.Event().wait(1.6)
        self.assertFalse((self.root / "child-survived").exists())

    @unittest.skipUnless(available_compiler(), "g++ is required")
    def test_real_compiler_output_limit_never_passes_truncated_output(self):
        runner = cph_runner.CppTestRunner(available_compiler(), temp_root=self.root)
        code = '#include <iostream>\n#include <string>\nint main(){int n;std::cin>>n; std::cout<<std::string(1048576, char(120)); if(n)std::cout<<char(33);}'
        result = runner.run(code, [dict(input="0", output="x" * 1048576),
                                   dict(input="1", output="x" * 1048576)])
        self.assertEqual([case["status"] for case in result["cases"]], ["passed", "output_limit"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["cases"][1]["stdout_truncated"])
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
