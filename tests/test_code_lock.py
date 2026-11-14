import tempfile
import unittest
from pathlib import Path

import app


class CodeLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = app.Repository(Path(self.tmp.name) / "data")
        self.addCleanup(lambda: self.repo.close())
        self.problem_payload = dict(platform="HDU", name="Demo", url="hdu.example/1",
                                    language="cpp", code="int main() {}")

    def test_problem_lock_blocks_code_and_language_but_allows_metadata_and_tests(self):
        problem = self.repo.create_problem(self.problem_payload)
        self.assertFalse(problem["code_locked"])
        locked = self.repo.set_code_lock("problem", problem["id"],
                                         dict(version=1, code_locked=True))
        self.assertTrue(locked["code_locked"])
        for payload in (dict(code="// changed"), dict(language="python"),
                        dict(code="// bypass", code_locked=False)):
            with self.assertRaises(app.AppError) as error:
                self.repo.update_problem(problem["id"], dict(version=locked["version"], **payload))
            self.assertEqual(error.exception.code, "code_locked")
        saved = self.repo.update_problem(problem["id"],
                                         dict(version=locked["version"], name="Renamed"))
        self.repo.replace_problem_tests(problem["id"],
                                        dict(version=saved["version"], tests=[dict(input="1", output="2")]))
        final = self.repo.get_problem(problem["id"])
        self.assertEqual(final["code"], problem["code"])
        self.assertTrue(final["code_locked"])
        self.assertEqual(final["tests"][0]["output"], "2")

    def test_lock_is_independent_persistent_and_requires_current_version(self):
        first = self.repo.create_problem(self.problem_payload)
        second = self.repo.create_problem(dict(self.problem_payload, url="hdu.example/2"))
        locked = self.repo.set_code_lock("problem", first["id"], dict(version=1, code_locked=True))
        self.assertFalse(self.repo.get_problem(second["id"])["code_locked"])
        with self.assertRaises(app.AppError) as error:
            self.repo.set_code_lock("problem", first["id"], dict(version=1, code_locked=False))
        self.assertEqual(error.exception.code, "version_conflict")
        self.repo.close()
        self.repo = app.Repository(Path(self.tmp.name) / "data")
        self.assertTrue(self.repo.get_problem(first["id"])["code_locked"])
        unlocked = self.repo.set_code_lock("problem", first["id"],
                                           dict(version=locked["version"], code_locked=False))
        saved = self.repo.update_problem(first["id"], dict(version=unlocked["version"], code="// edited"))
        self.assertEqual(saved["code"], "// edited")

    def test_lock_toggle_is_idempotent_and_rejects_non_boolean_values(self):
        problem = self.repo.create_problem(self.problem_payload)
        for value in ("true", 1, None, [], {}):
            with self.assertRaises(app.AppError):
                self.repo.set_code_lock("problem", problem["id"], dict(version=1, code_locked=value))
        unchanged = self.repo.set_code_lock("problem", problem["id"], dict(version=1, code_locked=False))
        self.assertEqual(unchanged["version"], 1)

    def test_snippet_lock_blocks_editing_and_cleans_up_after_delete(self):
        algorithm = self.repo.create_algorithm(dict(name="Demo", category="", description=""))
        snippet = self.repo.create_snippet(algorithm["id"], dict(title="Main", language="cpp", code="// main"))
        self.assertFalse(snippet["code_locked"])
        locked = self.repo.set_code_lock("snippet", snippet["id"], dict(version=1, code_locked=True))
        with self.assertRaises(app.AppError) as error:
            self.repo.update_snippet(snippet["id"], dict(version=locked["version"], code="// changed"))
        self.assertEqual(error.exception.code, "code_locked")
        saved = self.repo.update_snippet(snippet["id"], dict(version=locked["version"], title="Renamed"))
        self.assertTrue(saved["code_locked"])
        self.repo.delete_snippet(snippet["id"], dict(version=saved["version"], confirmed=True))
        self.assertEqual(self.repo.db.execute(
            "SELECT COUNT(*) FROM settings WHERE key=?", ("code_lock:snippet:" + snippet["id"],)).fetchone()[0], 0)

    def test_new_locked_code_can_be_saved_and_problem_delete_removes_lock(self):
        problem = self.repo.create_problem(dict(self.problem_payload, code_locked=True))
        self.assertTrue(problem["code_locked"])
        self.repo.delete_problem(problem["id"], dict(version=1, confirmed=True))
        self.assertEqual(self.repo.db.execute(
            "SELECT COUNT(*) FROM settings WHERE key=?", ("code_lock:problem:" + problem["id"],)).fetchone()[0], 0)

    def test_lock_survives_full_backup_restore(self):
        problem = self.repo.create_problem(dict(self.problem_payload, code_locked=True))
        backup = self.repo.create_backup()
        self.repo.set_code_lock("problem", problem["id"], dict(version=1, code_locked=False))
        self.repo.restore_backup(backup["name"], confirmed=True)
        self.assertTrue(self.repo.get_problem(problem["id"])["code_locked"])

    def test_new_platform_aliases_share_contest_identity(self):
        for alias, canonical in (("lanqiao", "蓝桥杯"), ("hduoj", "HDU"), ("MATIJI", "码蹄集")):
            contest = self.repo.create_contest(dict(platform=alias, title=alias, url=alias + ".example"))
            problem = self.repo.create_problem(dict(self.problem_payload, platform=canonical,
                                                    url=alias + ".example/1", contest_id=contest["id"]))
            self.assertEqual(contest["platform"], canonical)
            self.assertEqual(problem["platform"], canonical)
