"""Exercise durable file-operation recovery at real failure boundaries."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
import app  # noqa: E402


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="algo-recovery-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "本地 数据"
        self.repo = app.Repository(self.data)
        self.addCleanup(lambda: self.repo.close())

    def payload(self):
        return {"platform": "codeforces", "number": "A", "name": "故障恢复",
                "url": "https://codeforces.com/contest/2000/problem/A", "language": "cpp",
                "code": "// 恢复后仍在\nint main() { return 0; }\n", "contest_id": None}

    def fail_committed_flush(self):
        original = self.repo._flush_pending

        def fail_only_with_pending_rows():
            count = self.repo.db.execute("SELECT COUNT(*) FROM pending_files").fetchone()[0]
            if count:
                raise OSError("Injected disk failure after metadata commit")
            return original()

        return mock.patch.object(self.repo, "_flush_pending", side_effect=fail_only_with_pending_rows)

    def reopen(self):
        self.repo.close()
        self.repo = app.Repository(self.data)

    def assert_clean_journal(self):
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM pending_files").fetchone()[0], 0)

    def test_create_recovers_committed_code_after_write_failure(self):
        payload = self.payload()
        with self.fail_committed_flush(), self.assertRaises(OSError):
            self.repo.create_problem(payload)
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM problems").fetchone()[0], 1)
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM pending_files").fetchone()[0], 1)
        self.assertEqual(list((self.data / "codes").glob("*.cpp")), [])
        self.reopen()
        saved = self.repo.state()["problems"][0]
        self.assertEqual(self.repo.get_problem(saved["id"])["code"], payload["code"])
        self.assert_clean_journal()

    def test_language_change_recovers_new_file_and_removes_old_file(self):
        original = self.repo.create_problem(self.payload())
        old_path = self.data / original["code_path"]
        with self.fail_committed_flush(), self.assertRaises(OSError):
            self.repo.update_problem(original["id"], {**original, "language": "python", "code": "print('恢复')\n"})
        self.assertTrue(old_path.exists())
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM pending_files").fetchone()[0], 2)
        self.reopen()
        saved = self.repo.get_problem(original["id"])
        self.assertEqual(saved["language"], "python")
        self.assertEqual(saved["code"], "print('恢复')\n")
        self.assertFalse(old_path.exists())
        self.assertEqual(len(list((self.data / "codes").glob("*"))), 1)
        self.assert_clean_journal()

    def test_delete_recovers_pending_file_removal(self):
        original = self.repo.create_problem(self.payload())
        source = self.data / original["code_path"]
        with self.fail_committed_flush(), self.assertRaises(OSError):
            self.repo.delete_problem(original["id"], {"version": original["version"], "confirmed": True})
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM problems").fetchone()[0], 0)
        self.assertTrue(source.exists())
        self.reopen()
        self.assertFalse(source.exists())
        self.assertEqual(self.repo.state()["problems"], [])
        self.assert_clean_journal()

    def test_replay_is_idempotent_after_atomic_file_replace(self):
        replace = app.os.replace

        def replace_then_fail(source, target):
            replace(source, target)
            raise OSError("Injected failure after atomic replace, before journal acknowledgement")

        with mock.patch.object(app.os, "replace", side_effect=replace_then_fail):
            with self.assertRaises(app.AppError) as error:
                self.repo.create_problem(self.payload())
        self.assertEqual(error.exception.code, "storage_pending")
        self.assertEqual(len(list((self.data / "codes").glob("*.cpp"))), 1)
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM pending_files").fetchone()[0], 1)
        self.reopen()
        saved = self.repo.state()["problems"][0]
        self.assertEqual(self.repo.get_problem(saved["id"])["code"], self.payload()["code"])
        self.assert_clean_journal()
        self.reopen()
        self.assertEqual(self.repo.get_problem(saved["id"])["code"], self.payload()["code"])
        self.assertEqual(len(list((self.data / "codes").glob("*"))), 1)

    def test_missing_code_reports_error_and_preserves_metadata(self):
        saved = self.repo.create_problem(self.payload())
        (self.data / saved["code_path"]).unlink()
        with self.assertRaises(app.AppError) as error:
            self.repo.get_problem(saved["id"])
        self.assertEqual(error.exception.code, "code_unavailable")
        self.assertEqual(len(self.repo.state()["problems"]), 1)

    def test_crlf_source_bytes_are_preserved(self):
        source = "// Windows 换行\r\nint main() {\r\n  return 0;\r\n}\r\n"
        saved = self.repo.create_problem({**self.payload(), "code": source})
        self.assertEqual(saved["code"], source)
        self.assertEqual((self.data / saved["code_path"]).read_bytes(), source.encode("utf-8"))
        self.reopen()
        self.assertEqual(self.repo.get_problem(saved["id"])["code"], source)

    def test_invalid_json_field_types_return_validation_errors(self):
        for key, invalid in (("platform", []), ("language", {}), ("contest_id", 0), ("contest_id", [])):
            with self.subTest(key=key, invalid=invalid):
                with self.assertRaises(app.AppError) as error:
                    self.repo.create_problem({**self.payload(), key: invalid})
                self.assertEqual(error.exception.status, 400)
        self.assertEqual(self.repo.state()["problems"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
