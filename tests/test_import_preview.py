from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

import app


class ImportPreviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = app.Repository(Path(tmp.name) / "data")
        self.addCleanup(self.repo.close)
        self.base = dict(platform="luogu", number="P1", name="Original",
                         url="https://oj.example/problems/1", language="python", code="print(1)")
        self.old = self.repo.create_problem(dict(self.base, tests=[dict(input="a", output="b")]))

    def preview(self, *items):
        self.assertTrue(hasattr(self.repo, "preview_problem_import"), "read-only preview interface missing")
        return self.repo.preview_problem_import(dict(problems=list(items)))

    def commit(self, items, preview, actions):
        return self.repo.import_problems(dict(problems=items, preview_token=preview["preview_token"], decisions=actions))

    def test_preview_preserves_database_files_and_disabled_default(self):
        rows = [dict(self.base, url="https://OJ.example:443/problems/1", platform="POJ", number="X")]
        database = self.repo.data_dir / "archive.sqlite3"
        before = database.read_bytes()
        preview = self.preview(*rows)
        self.assertEqual(preview["rows"][0]["default_action"], "skip")
        self.assertEqual(preview["rows"][0]["matches"][0]["id"], self.old["id"])
        self.assertEqual(database.read_bytes(), before)
        self.assertFalse(self.repo.backup_directory().exists())
        result = self.commit(rows, preview, ["skip"])
        self.assertEqual((result["count"], result["skipped"]), (0, 1))
        self.assertEqual(self.repo.get_problem(self.old["id"])["version"], 1)

    def test_explicit_number_match_preserves_blank_source_tests_and_study_data(self):
        alg = self.repo.create_algorithm(dict(name="DP"))
        self.repo.update_problem(self.old["id"], dict(version=1, algorithm_ids=[alg["id"]],
                                  study_status="todo", mistake_note="off by one"))
        rows = [dict(platform="洛谷", number="P1", name="New title", url="https://oj.example/updated",
                     code=" \n", tests=[], language="cpp")]
        preview = self.preview(*rows)
        self.assertEqual(preview["rows"][0]["status"], "existing")
        result = self.commit(rows, preview, ["update"])
        self.assertEqual(result["updated"], 1)
        p = self.repo.get_problem(self.old["id"])
        self.assertEqual((p["name"], p["code"], p["language"], p["tests"][0]["output"]),
                         ("New title", "print(1)", "python", "b"))
        self.assertEqual((p["algorithm_ids"], p["study_status"], p["mistake_note"]), ([alg["id"]], "todo", "off by one"))

    def test_source_replacement_creates_recoverable_backup(self):
        rows = [dict(self.base, code="int main(){}", language="cpp", tests=[dict(input="c", output="d")])]
        result = self.commit(rows, self.preview(*rows), ["update"])
        with zipfile.ZipFile(self.repo.backup_directory() / result["backup"]) as z:
            self.assertEqual(z.read(self.old["code_path"]), b"print(1)")
        p = self.repo.get_problem(self.old["id"])
        self.assertEqual((p["code"], p["tests"][0]["input"]), ("int main(){}", "c"))
        self.assertFalse((self.repo.data_dir / self.old["code_path"]).exists())

    def test_metadata_only_keeps_different_source_and_cases_even_when_locked(self):
        self.repo.set_code_lock("problem", self.old["id"], dict(version=1, code_locked=True))
        rows = [dict(self.base, name="metadata only", code="new source", language="cpp",
                     tests=[dict(input="replacement", output="replacement")], code_locked=False)]
        preview = self.preview(*rows)
        self.assertIn("update_metadata", preview["rows"][0]["actions"])
        self.assertNotIn("update", preview["rows"][0]["actions"])
        result = self.commit(rows, preview, ["update_metadata"])
        self.assertEqual(result["updated"], 1)
        p = self.repo.get_problem(self.old["id"])
        self.assertEqual((p["name"], p["language"], p["code"], p["tests"][0]["output"], p["code_locked"]),
                         ("metadata only", "python", "print(1)", "b", True))

    def test_intervening_edit_rejects_entire_batch_including_new_row(self):
        rows = [dict(self.base, number="P9", url="https://oj.example/9"), dict(self.base, name="Stale")]
        preview = self.preview(*rows)
        self.repo.update_problem(self.old["id"], dict(version=1, code="print(2)"))
        with self.assertRaises(app.AppError) as ctx:
            self.commit(rows, preview, ["create", "update"])
        self.assertEqual(ctx.exception.code, "import_preview_changed")
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM problems").fetchone()[0], 1)
        self.assertEqual(self.repo.get_problem(self.old["id"])["code"], "print(2)")

    def test_collision_using_retained_number_and_incoming_platform_is_blocked(self):
        self.repo.create_problem(dict(self.base, platform="POJ", url="https://oj.example/elsewhere"))
        # URL identifies one row. Keeping its omitted number would collide with the other.
        rows = [dict(url=self.base["url"], platform="POJ", name="moved")]
        row = self.preview(*rows)["rows"][0]
        self.assertEqual((row["status"], row["actions"]), ("conflict", ["skip"]))

    def test_distinct_hash_routed_problems_and_empty_numbers_do_not_merge(self):
        rows = [dict(self.base, number="", url="https://oj.example/#/problem/2"),
                dict(self.base, number="", url="https://oj.example/#/problem/3")]
        preview = self.preview(*rows)
        self.assertEqual([r["default_action"] for r in preview["rows"]], ["create", "create"])

    def test_conflicting_keys_batch_duplicate_and_ambiguous_reference(self):
        second = dict(self.base, number="P2", url="https://oj.example/2")
        self.repo.create_problem(second)
        new = dict(self.base, number="P9", url="https://oj.example/9")
        rows = [new, dict(new, url="https://oj.example/b"), dict(self.base, url=second["url"])]
        preview = self.preview(*rows)
        self.assertEqual([r["status"] for r in preview["rows"]], ["new", "batch_duplicate", "conflict"])
        self.assertEqual(len(preview["rows"][2]["matches"]), 2)
        with self.assertRaises(app.AppError):
            self.commit(rows, preview, ["create", "update", "skip"])
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM problems").fetchone()[0], 2)

    def test_locked_source_and_replayed_or_altered_token_cannot_overwrite(self):
        self.repo.set_code_lock("problem", self.old["id"], dict(version=1, code_locked=True))
        rows = [dict(self.base, code="different", code_locked=False)]
        preview = self.preview(*rows)
        self.assertNotIn("update", preview["rows"][0]["actions"])
        with self.assertRaises(app.AppError):
            self.commit(rows, preview, ["update"])
        changed = [dict(self.base, name="Altered")]
        with self.assertRaises(app.AppError):
            self.commit(changed, preview, ["update"])
        preview = self.preview(*changed)
        self.commit(changed, preview, ["update"])
        with self.assertRaises(app.AppError):
            self.commit(changed, preview, ["update"])
        current = self.repo.get_problem(self.old["id"])
        self.assertTrue(current["code_locked"])
        self.assertEqual(current["code"], "print(1)")

    def test_transaction_failure_rolls_back_all_rows_and_source_journal(self):
        rows = [dict(self.base, number="A9", url="https://oj.example/a9"),
                dict(self.base, number="B9", url="https://oj.example/b9")]
        preview = self.preview(*rows)
        self.repo.db.execute("""CREATE TEMP TRIGGER fail_second BEFORE INSERT ON problems
                               WHEN NEW.number='B9' BEGIN SELECT RAISE(ABORT,'forced rollback'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.commit(rows, preview, ["create", "create"])
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM problems").fetchone()[0], 1)
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM pending_files").fetchone()[0], 0)
        self.assertEqual(len(list((self.repo.data_dir / "codes").iterdir())), 1)
