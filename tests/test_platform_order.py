import concurrent.futures
from pathlib import Path
import tempfile
import unittest

import app


class PlatformOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="algo-platform-order-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "data"
        self.repo = app.Repository(self.path)
        self.addCleanup(lambda: self.repo.close())

    def problem(self, name, platform="AcWing", **extra):
        return self.repo.create_problem(dict(platform=platform, name=name, number=name,
            url="https://example.com/" + name, language="cpp", code="int main() {}", **extra))

    def order(self, key="acwing"):
        state = self.repo.state()
        self.assertIn("platform_problem_orders", state)
        return state["platform_problem_orders"][key]

    def reorder(self, ids, key="acwing"):
        return self.repo.reorder_platform_problems(key, dict(version=self.order(key)["version"], problem_ids=ids))

    def test_reorder_is_independent_and_persists_across_restart(self):
        a, b = self.problem("a"), self.problem("b")
        other = self.problem("other", "AtCoder")
        before = [dict(row) for row in self.repo.db.execute("SELECT * FROM problems ORDER BY id")]
        original = self.order("atcoder")
        result = self.reorder([b["id"], a["id"]])
        self.assertEqual(result["platform"], "acwing")
        self.assertEqual(result["problem_ids"], [b["id"], a["id"]])
        self.assertEqual(before, [dict(row) for row in self.repo.db.execute("SELECT * FROM problems ORDER BY id")])
        self.assertEqual(self.order("atcoder"), original)
        self.repo.close()
        self.repo = app.Repository(self.path)
        self.assertEqual(self.order(), dict(version=result["platform_order_version"], problem_ids=[b["id"], a["id"]]))

    def test_membership_changes_increment_version_and_edits_preserve_order(self):
        a, b = self.problem("a"), self.problem("b")
        self.reorder([b["id"], a["id"]])
        previous = self.order()
        a = self.repo.update_problem(a["id"], dict(version=a["version"], name="edited"))
        self.assertEqual(self.order(), previous)
        c = self.problem("c")
        self.assertEqual(self.order()["problem_ids"], [b["id"], a["id"], c["id"]])
        self.assertGreater(self.order()["version"], previous["version"])
        previous = self.order()
        self.repo.update_problem(a["id"], dict(version=a["version"], platform="AtCoder"))
        self.assertEqual(self.order()["problem_ids"], [b["id"], c["id"]])
        self.assertGreater(self.order()["version"], previous["version"])
        self.assertEqual(self.order("atcoder")["problem_ids"], [a["id"]])
        self.repo.delete_problem(b["id"], dict(version=b["version"], confirmed=True))
        self.assertEqual(self.order()["problem_ids"], [c["id"]])

    def test_invalid_sets_and_stale_versions_do_not_write(self):
        a, b = self.problem("a"), self.problem("b")
        other = self.problem("other", "AtCoder")
        saved = self.order()
        for ids in ([a["id"], a["id"]], [a["id"]], [a["id"], other["id"]], [a["id"], 2], None):
            with self.subTest(ids=ids), self.assertRaises(app.AppError):
                self.repo.reorder_platform_problems("acwing", dict(version=saved["version"], problem_ids=ids))
            self.assertEqual(self.order(), saved)
        self.reorder([b["id"], a["id"]])
        with self.assertRaises(app.AppError) as raised:
            self.repo.reorder_platform_problems("acwing", saved)
        self.assertEqual(raised.exception.code, "version_conflict")

    def test_existing_schema_10_initializes_from_updated_time_once(self):
        a, b = self.problem("a"), self.problem("b")
        with self.repo.db:
            self.repo.db.execute("DELETE FROM settings WHERE key GLOB 'platform_problem_order:*'")
            self.repo.db.execute("UPDATE problems SET updated_at='2020-01-01' WHERE id=?", (a["id"],))
            self.repo.db.execute("UPDATE problems SET updated_at='2021-01-01' WHERE id=?", (b["id"],))
        self.repo.close()
        self.repo = app.Repository(self.path)
        self.assertEqual(self.order()["problem_ids"], [b["id"], a["id"]])
        self.assertEqual(self.repo.db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0], "10")

    def test_aliases_custom_platforms_import_and_backup_restore(self):
        a = self.problem("a", "洛谷")
        self.assertEqual(self.order("luogu")["problem_ids"], [a["id"]])
        custom = self.problem("custom", "My OJ")
        self.assertEqual(self.order("my oj")["problem_ids"], [custom["id"]])
        imported = self.repo.import_problems(dict(problems=[dict(platform="luogu", name="b", url="https://example.com/b", language="cpp", code="")]))
        self.assertEqual(self.order("luogu")["problem_ids"], [a["id"], *imported["problem_ids"]])
        expected = self.order("luogu")
        backup = self.repo.create_backup()
        self.reorder(list(reversed(expected["problem_ids"])), "luogu")
        self.repo.restore_backup(backup["name"], confirmed=True)
        self.assertEqual(self.order("luogu")["problem_ids"], expected["problem_ids"])

    def test_contest_cascade_removes_platform_members(self):
        contest = self.repo.create_contest(dict(platform="acwing", title="contest", url="https://example.com/contest"))
        a = self.problem("a", contest_id=contest["id"])
        previous = self.order()
        contest = self.repo.get_contest(contest["id"])
        self.repo.delete_contest(contest["id"], dict(version=contest["version"], confirmed=True, keep_problems=False))
        self.assertEqual(self.order()["problem_ids"], [])
        self.assertGreater(self.order()["version"], previous["version"])

    def test_restore_invalidates_pre_restore_clients_even_with_same_members(self):
        a, b = self.problem("a"), self.problem("b")
        backup = self.repo.create_backup()
        stale = self.order()
        self.repo.restore_backup(backup["name"], confirmed=True)
        with self.assertRaises(app.AppError) as raised:
            self.repo.reorder_platform_problems("acwing", stale)
        self.assertEqual(raised.exception.code, "version_conflict")
        self.assertGreater(self.order()["version"], stale["version"])

    def test_first_batch_import_appends_in_input_order(self):
        imported = self.repo.import_problems(dict(problems=[dict(platform="AcWing", name=str(i),
            url="https://example.com/" + str(i), language="cpp", code="") for i in range(20)]))
        self.assertEqual(self.order()["problem_ids"], imported["problem_ids"])

    def test_custom_unicode_key_matches_browser_lowercase(self):
        custom = self.problem("unicode", "Straße OJ")
        self.assertEqual(self.order("straße oj")["problem_ids"], [custom["id"]])

    def test_expanded_unicode_keys_accept_maximum_length_platform_names(self):
        for length in (51, 100):
            with self.subTest(length=length):
                name = "İ" * length
                key = name.lower()
                a = self.problem("expanded-a-" + str(length), name)
                b = self.problem("expanded-b-" + str(length), name)
                self.assertEqual(len(key), length * 2)
                saved = self.order(key)
                result = self.repo.reorder_platform_problems(key, dict(
                    version=saved["version"], problem_ids=[b["id"], a["id"]]))
                self.assertEqual(result["platform"], key)
                self.assertEqual(self.order(key)["problem_ids"], [b["id"], a["id"]])
        with self.assertRaises(app.AppError):
            self.problem("name-too-long", "İ" * 101)
        with self.assertRaises(app.AppError):
            self.repo.reorder_platform_problems("i" * 201, dict(version=1, problem_ids=[]))

    def test_empty_platform_rejects_boolean_version(self):
        with self.assertRaises(app.AppError):
            self.repo.reorder_platform_problems("poj", dict(version=True, problem_ids=[]))

    def test_concurrent_reorder_only_one_writer_succeeds(self):
        a, b = self.problem("a"), self.problem("b")
        saved = self.order()
        def save(ids):
            try:
                return self.repo.reorder_platform_problems("acwing", dict(version=saved["version"], problem_ids=ids))
            except app.AppError as error:
                return error.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, ([a["id"], b["id"]], [b["id"], a["id"]])))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertIn("version_conflict", results)
