import copy
from pathlib import Path
import tempfile
import unittest

import app


class CardColorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="algo-colors-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        self.repo = app.Repository(self.data)
        self.addCleanup(lambda: self.repo.close())

    def create(self, kind, index, **extra):
        if kind == "contest":
            return self.repo.create_contest(dict(
                platform="HDU", title=f"Contest {index}", url=f"https://example.com/{index}", **extra
            ))
        return self.repo.create_algorithm(dict(name=f"Algorithm {index}", **extra))

    def color_map(self):
        state = self.repo.state()
        return {item["id"]: item["card_color"]
                for key in ("algorithms", "contests") for item in state[key]}

    def reopen(self):
        self.repo.close()
        self.repo = app.Repository(self.data)

    @staticmethod
    def without_colors(state):
        result = copy.deepcopy(state)
        for key in ("algorithms", "contests"):
            for item in result[key]:
                item.pop("card_color", None)
        return result

    def test_new_algorithms_and_contests_cycle_six_colors_independently(self):
        expected = ["blue", "cyan", "green", "amber", "rose", "violet", "blue", "cyan"]
        for kind in ("algorithm", "contest"):
            records = [self.create(kind, i) for i in range(8)]
            self.assertEqual([item.get("card_color") for item in records], expected)

    def test_colors_survive_rename_reordering_and_restart(self):
        algorithms = [self.create("algorithm", i) for i in range(6)]
        contests = [self.create("contest", i) for i in range(6)]
        original = self.color_map()
        self.repo.update_algorithm(algorithms[0]["id"], dict(version=1, name="Renamed search", category="DFS"))
        self.repo.update_contest(contests[0]["id"], dict(version=1, title="Renamed contest"))
        self.repo.reorder_algorithms(dict(version=1, ordered_ids=[a["id"] for a in reversed(algorithms)]))
        self.repo.reorder_contests(dict(version=1, ordered_ids=[c["id"] for c in reversed(contests)]))
        self.reopen()
        self.assertEqual(self.color_map(), original)
        for a in algorithms:
            self.assertEqual(self.repo.get_algorithm(a["id"]).get("card_color"), original[a["id"]])
        for c in contests:
            self.assertEqual(self.repo.get_contest(c["id"]).get("card_color"), original[c["id"]])

    def test_deletion_and_rejected_creation_do_not_rewind_or_advance_the_cycle(self):
        for kind in ("algorithm", "contest"):
            with self.subTest(kind=kind):
                first = self.create(kind, 0)
                second = self.create(kind, 1)
                if kind == "algorithm":
                    with self.assertRaises(app.AppError):
                        self.repo.create_algorithm(dict(name=""))
                    self.repo.delete_algorithm(second["id"], dict(version=1, confirmed=True))
                else:
                    with self.assertRaises(app.AppError):
                        self.repo.create_contest(dict(platform="HDU", title="", url="https://example.com"))
                    self.repo.delete_contest(second["id"], dict(version=1, confirmed=True, keep_problems=True))
                self.assertEqual(self.create(kind, 2).get("card_color"), "green")
                self.assertEqual(self.color_map()[first["id"]], "blue")
                self.assertEqual(self.repo.db.execute(
                    "SELECT COUNT(*) FROM settings WHERE key=?", (f"card_color:{kind}:{second['id']}",)
                ).fetchone()[0], 0)

    def test_backup_restores_colors_and_next_color(self):
        for kind in ("algorithm", "contest"):
            for i in range(3):
                self.create(kind, i)
        original = self.color_map()
        backup = self.repo.create_backup()
        for kind in ("algorithm", "contest"):
            self.create(kind, 3)
            self.create(kind, 4)
        self.repo.restore_backup(backup["name"], confirmed=True)
        self.assertEqual(self.color_map(), original)
        for kind in ("algorithm", "contest"):
            self.assertEqual(self.create(kind, 5).get("card_color"), "amber")

    def test_old_data_backfill_preserves_records_order_and_code(self):
        algorithms = [self.create("algorithm", i) for i in range(7)]
        contests = [self.create("contest", i) for i in range(7)]
        problem = self.repo.create_problem(dict(
            platform="HDU", name="Preserved source", url="https://example.com/problem",
            language="cpp", code="// preserve this source\nint main(){}\n",
            algorithm_id=algorithms[0]["id"], contest_id=contests[0]["id"]
        ))
        for kind, records in (("algorithm", algorithms), ("contest", contests)):
            reorder = self.repo.reorder_algorithms if kind == "algorithm" else self.repo.reorder_contests
            reorder(dict(version=1, ordered_ids=[item["id"] for item in reversed(records)]))
        with self.repo.db:
            self.repo.db.execute("DELETE FROM settings WHERE key GLOB 'card_color:*' OR key GLOB 'card_color_next:*'")
        before = self.without_colors(self.repo.state())
        backup = self.repo.create_backup()
        self.reopen()
        self.assertEqual(self.without_colors(self.repo.state()), before)
        expected = ["blue", "cyan", "green", "amber", "rose", "violet", "blue"]
        for collection in ("algorithms", "contests"):
            self.assertEqual([item.get("card_color") for item in self.repo.state()[collection]], expected)
        self.assertEqual((self.data / problem["code_path"]).read_text(encoding="utf-8"), problem["code"])
        original = self.color_map()
        self.reopen()
        self.assertEqual(self.color_map(), original)
        self.repo.restore_backup(backup["name"], confirmed=True)
        self.assertEqual(self.color_map(), original)
        self.assertEqual(self.without_colors(self.repo.state()), before)
        self.assertEqual(self.create("algorithm", 9).get("card_color"), "cyan")

    def test_clients_cannot_replace_assigned_color(self):
        for kind in ("algorithm", "contest"):
            record = self.create(kind, 0, card_color="violet")
            self.assertEqual(record.get("card_color"), "blue")
            update = self.repo.update_algorithm if kind == "algorithm" else self.repo.update_contest
            updated = update(record["id"], dict(version=record["version"], card_color="rose"))
            self.assertEqual(updated.get("card_color"), "blue")


if __name__ == "__main__":
    unittest.main()
