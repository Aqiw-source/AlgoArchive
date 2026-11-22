import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import app


class ProblemStudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "data"
        self.repo = app.Repository(self.path)
        self.addCleanup(lambda: self.repo.close())
        self.a, self.b, self.c = [self.repo.create_algorithm({"name": tag})["id"]
                                  for tag in ("DP", "Graph", "Math")]

    def problem(self, name, **fields):
        return self.repo.create_problem(dict(platform="AcWing", name=name,
            url=f"https://example.com/{name}", language="cpp", code=f"// {name}", **fields))

    def edit(self, p, **fields):
        return self.repo.update_problem(p["id"], dict(version=p["version"], **fields))

    def reorder(self, tag, ids):
        self.repo.reorder_algorithm_problems(tag, dict(
            version=self.repo.get_algorithm(tag)["version"], problem_ids=ids))

    def tag_order(self, tag):
        return [p["id"] for p in sorted(
            (p for p in self.repo.state()["problems"] if tag in p["algorithm_ids"]),
            key=lambda p: p["algorithm_orders"][tag])]

    def test_study_fields_and_legacy_edits(self):
        p = self.problem("p", algorithm_ids=[self.a, self.b])
        self.assertEqual((p["study_status"], p["mistake_note"]), ("unseen", ""))
        p = self.edit(p, study_status="todo", mistake_note="漏掉边界\n检查下标")
        # An older client echoes the primary tag without knowing about the second.
        p = self.edit(p, algorithm_id=self.a, code="// changed")
        listed = self.repo.state()["problems"][0]
        for key in ("algorithm_ids", "algorithm_orders", "study_status", "mistake_note"):
            self.assertEqual(p[key], listed[key])
        self.assertEqual((p["algorithm_ids"], p["study_status"], p["mistake_note"]),
                         ([self.a, self.b], "todo", "漏掉边界\n检查下标"))
        p = self.edit(p, algorithm_id=self.c, study_status="done")
        self.assertEqual(p["algorithm_ids"], [self.c, self.b])
        p = self.edit(p, algorithm_id=None)
        self.assertEqual((p["algorithm_id"], p["algorithm_ids"]), (self.b, [self.b]))
        p = self.edit(p, algorithm_ids=[], mistake_note="")
        self.assertEqual((p["algorithm_id"], p["algorithm_ids"], p["algorithm_orders"],
                          p["mistake_note"], p["study_status"]), (None, [], {}, "", "done"))

    def test_order_is_independent_per_tag_and_global_count_is_unique(self):
        x = self.problem("x", algorithm_ids=[self.a, self.b])["id"]
        y = self.problem("y", algorithm_ids=[self.b, self.a])["id"]
        z = self.problem("z", algorithm_ids=[self.a])["id"]
        self.reorder(self.b, [y, x])
        self.reorder(self.a, [z, x, y])
        self.assertEqual((self.tag_order(self.a), self.tag_order(self.b)), ([z, x, y], [y, x]))
        p = self.repo.get_problem(x)
        self.assertEqual(p["algorithm_order"], p["algorithm_orders"][p["algorithm_id"]])
        self.edit(p, algorithm_ids=[self.b, self.a, self.c])
        self.assertEqual((self.tag_order(self.a), self.tag_order(self.b)), ([z, x, y], [y, x]))
        state = self.repo.state()
        self.assertEqual(state["stats"]["problem_count"], 3)
        self.assertEqual(len(list((self.path / "codes").glob("*"))), 3)
        self.assertEqual(self.repo.get_algorithm(self.b)["problem_count"], 2)
        self.assertEqual({a["id"]: a["problem_count"] for a in state["algorithms"]},
                         {self.a: 3, self.b: 2, self.c: 1})

    def test_delete_tag_preserves_problem_and_invalidates_old_edits(self):
        before = self.problem("x", algorithm_ids=[self.b, self.a, self.c],
                              study_status="done", mistake_note="有重复边")
        for tag, expected in ((self.a, [self.b, self.c]), (self.b, [self.c]), (self.c, [])):
            self.repo.delete_algorithm(tag, dict(confirmed=True, version=self.repo.get_algorithm(tag)["version"]))
            p = self.repo.get_problem(before["id"])
            self.assertEqual((p["algorithm_ids"], p["algorithm_id"]), (expected, next(iter(expected), None)))
            self.assertEqual((p["code"], p["study_status"], p["mistake_note"]),
                             (before["code"], "done", "有重复边"))
            with self.assertRaises(app.AppError) as stale:
                self.edit(before, study_status="unseen")
            self.assertEqual(stale.exception.code, "version_conflict")
            before = p

    def test_rejected_edits_do_not_change_tags_note_or_code(self):
        p = self.problem("p", algorithm_ids=[self.a, self.b])
        for bad in ({"study_status": "pending"}, {"study_status": []},
                    {"algorithm_ids": self.b}, {"algorithm_ids": [self.a, self.a]},
                    {"algorithm_ids": [self.a, "missing"]}, {"mistake_note": "x" * 10001}):
            with self.subTest(bad=next(iter(bad))), self.assertRaises(app.AppError):
                self.edit(p, code="// rejected", **bad)
            self.assertEqual(p, self.repo.get_problem(p["id"]))

    def test_deleting_problems_cleans_all_memberships(self):
        contest = self.repo.create_contest(dict(platform="AcWing", title="Test", url="example.com/test"))
        linked = self.problem("linked", algorithm_ids=[self.a, self.b], contest_id=contest["id"])
        other = self.problem("other", algorithm_ids=[self.b, self.a])
        self.repo.delete_contest(contest["id"], dict(
            version=self.repo.get_contest(contest["id"])["version"], confirmed=True, keep_problems=False))
        for tag in (self.a, self.b):
            self.assertEqual(self.tag_order(tag), [other["id"]])
        self.assertFalse((self.path / linked["code_path"]).exists())
        self.repo.delete_problem(other["id"], dict(version=other["version"], confirmed=True))
        self.assertEqual(self.repo.db.execute("SELECT COUNT(*) FROM problem_algorithms").fetchone()[0], 0)
        self.assertEqual(self.repo.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_backup_restore_preserves_study_and_each_order(self):
        x = self.problem("x", algorithm_ids=[self.a, self.b], study_status="todo", mistake_note="栈空")
        y = self.problem("y", algorithm_ids=[self.b, self.a])
        self.reorder(self.b, [y["id"], x["id"]])
        before = self.repo.state()["problems"]
        backup = self.repo.create_backup()
        self.edit(x, study_status="done", mistake_note="", algorithm_ids=[self.c])
        self.repo.restore_backup(backup["name"], confirmed=True)
        self.assertEqual(self.repo.state()["problems"], before)
        self.assertEqual(self.repo.get_problem(x["id"])["code"], x["code"])

    def test_schema_ten_upgrade_preserves_old_order_code_and_creates_safety_copy(self):
        x = self.problem("x", algorithm_id=self.a)
        y = self.problem("y", algorithm_id=self.a)
        self.reorder(self.a, [y["id"], x["id"]])
        self.repo.close()
        with closing(sqlite3.connect(self.path / "archive.sqlite3")) as db:
            db.execute("DROP TABLE problem_algorithms")
            for column in ("study_status", "mistake_note"):
                db.execute(f"ALTER TABLE problems DROP COLUMN {column}")
            db.execute("UPDATE settings SET value='10' WHERE key='schema_version'")
            db.commit()
        self.repo = app.Repository(self.path)
        self.assertEqual(self.tag_order(self.a), [y["id"], x["id"]])
        self.assertEqual(self.repo.get_problem(x["id"])["code"], x["code"])
        self.assertEqual([(p["study_status"], p["mistake_note"], p["version"])
                          for p in self.repo.state()["problems"]], [("unseen", "", 1)] * 2)
        backup, = self.path.parent.glob("backups/before-schema-upgrade-*/archive.sqlite3")
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0], "10")
        self.repo.close()
        self.repo = app.Repository(self.path)
        self.assertEqual(self.tag_order(self.a), [y["id"], x["id"]])
        self.assertEqual(len(list(backup.parent.parent.glob("before-schema-upgrade-*"))), 1)


if __name__ == "__main__":
    unittest.main()
