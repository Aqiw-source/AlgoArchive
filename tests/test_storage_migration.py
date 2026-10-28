"""Data-directory migration and schema upgrade tests."""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import zipfile

import app as app_module
from app import Repository, default_data_dir, migrate_legacy_data


def make_v1_data(root):
    root = Path(root)
    codes = root / "codes"
    codes.mkdir(parents=True)
    code_path = "codes/11111111111111111111111111111111.cpp"
    (root / code_path).write_bytes(b"int main() { return 0; }\n")
    database = root / "archive.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.executescript(
            """
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO settings VALUES ('schema_version', '1');
            CREATE TABLE contests (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                title TEXT NOT NULL, url TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE problems (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                number TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL, normalized_url TEXT NOT NULL,
                language TEXT NOT NULL,
                contest_id TEXT REFERENCES contests(id) ON DELETE SET NULL,
                code_path TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE pending_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                path TEXT NOT NULL,
                content BLOB
            );
            INSERT INTO contests VALUES (
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'codeforces', '保留比赛',
                'https://codeforces.com/contest/2000',
                '2026-10-27T00:00:00.000Z', '2026-10-27T00:00:00.000Z', 1
            );
            """
        )
        db.execute(
            """
            INSERT INTO problems VALUES (
                '11111111111111111111111111111111', 'codeforces', 'A', '保留题目',
                'https://codeforces.com/contest/2000/problem/A',
                'https://codeforces.com/contest/2000/problem/A',
                'cpp', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', ?,
                '2026-10-27T00:00:00.000Z', '2026-10-27T00:00:00.000Z', 1
            )
            """,
            (code_path,),
        )
        db.commit()
    return root


def make_v3_data(root):
    root = make_v1_data(root)
    database = root / "archive.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.executescript(
            """
            UPDATE settings SET value='3' WHERE key='schema_version';
            ALTER TABLE problems RENAME TO problems_v1;
            CREATE TABLE problems (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL CHECK(platform IN ('codeforces','atcoder')),
                number TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL, normalized_url TEXT NOT NULL,
                language TEXT NOT NULL CHECK(language IN ('cpp','python','java','other')),
                contest_id TEXT REFERENCES contests(id) ON DELETE SET NULL,
                algorithm_id TEXT REFERENCES algorithms(id) ON DELETE SET NULL,
                code_path TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                UNIQUE(platform, normalized_url)
            );
            INSERT INTO problems
                (id,platform,number,name,url,normalized_url,language,contest_id,
                 algorithm_id,code_path,created_at,updated_at,version)
            SELECT id,platform,number,name,url,url,language,contest_id,
                   NULL,code_path,created_at,updated_at,version
            FROM problems_v1;
            DROP TABLE problems_v1;
            """
        )
        db.commit()
    return root


def make_v4_data(root):
    root = make_v1_data(root)
    database = root / "archive.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.executescript(
            """
            UPDATE settings SET value='4' WHERE key='schema_version';
            ALTER TABLE contests RENAME TO contests_v1;
            CREATE TABLE contests (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL CHECK(platform IN ('codeforces','atcoder')),
                title TEXT NOT NULL, url TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO contests
                (id,platform,title,url,created_at,updated_at,version)
            SELECT id,platform,title,url,created_at,updated_at,version
            FROM contests_v1;
            DROP TABLE contests_v1;

            ALTER TABLE problems RENAME TO problems_v1;
            CREATE TABLE problems (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                number TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL, normalized_url TEXT NOT NULL,
                language TEXT NOT NULL CHECK(language IN ('cpp','python','java','other')),
                contest_id TEXT REFERENCES contests(id) ON DELETE SET NULL,
                algorithm_id TEXT REFERENCES algorithms(id) ON DELETE SET NULL,
                code_path TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                UNIQUE(platform, normalized_url)
            );
            INSERT INTO problems
                (id,platform,number,name,url,normalized_url,language,contest_id,
                 algorithm_id,code_path,created_at,updated_at,version)
            SELECT id,platform,number,name,url,url,language,contest_id,
                   NULL,code_path,created_at,updated_at,version
            FROM problems_v1;
            DROP TABLE problems_v1;
            """
        )
        db.commit()
    return root


def make_v5_data(root):
    root = make_v1_data(root)
    second_path = "codes/22222222222222222222222222222222.cpp"
    (root / second_path).write_bytes(b"int main() { return 1; }\n")
    database = root / "archive.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.executescript(
            """
            UPDATE settings SET value='5' WHERE key='schema_version';
            CREATE TABLE algorithms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO algorithms VALUES (
                'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', '顺序测试', '',
                '', '2026-10-27T00:00:00.000Z',
                '2026-10-27T02:00:00.000Z', 1
            );
            ALTER TABLE problems ADD COLUMN algorithm_id TEXT
                REFERENCES algorithms(id) ON DELETE SET NULL;
            UPDATE problems
            SET algorithm_id='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
            WHERE id='11111111111111111111111111111111';
            """
        )
        db.execute(
            """
            INSERT INTO problems
                (id,platform,number,name,url,normalized_url,language,
                 contest_id,algorithm_id,code_path,created_at,updated_at,version)
            VALUES (
                '22222222222222222222222222222222', 'codeforces', 'B', '后创建的题目',
                'https://codeforces.com/contest/2000/problem/B',
                'https://codeforces.com/contest/2000/problem/B',
                'cpp', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', ?,
                '2026-10-27T01:00:00.000Z', '2026-10-27T01:00:00.000Z', 1
            )
            """,
            (second_path,),
        )
        db.commit()
    return root


def make_v6_data(root):
    root = make_v5_data(root)
    database = root / "archive.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.executescript(
            """
            ALTER TABLE problems ADD COLUMN algorithm_order
                INTEGER NOT NULL DEFAULT 0;
            UPDATE problems SET algorithm_order=0
                WHERE id='22222222222222222222222222222222';
            UPDATE problems SET algorithm_order=1
                WHERE id='11111111111111111111111111111111';
            UPDATE settings SET value='6' WHERE key='schema_version';
            """
        )
        db.commit()
    return root


class StorageMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="algo-storage-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_default_data_dir_is_outside_localappdata(self):
        profile = self.root / "User"
        local = profile / "AppData" / "Local"
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
            with mock.patch.object(Path, "home", return_value=profile):
                self.assertEqual(
                    default_data_dir(),
                    profile / "AlgoArchive" / "data",
                )

    def test_saved_config_path_wins_over_default_but_not_explicit_cli(self):
        config_path = self.root / "config" / "config.json"
        configured = self.root / "custom" / "data"
        explicit = self.root / "explicit" / "data"
        app_module.save_user_config(
            {"format": 1, "data_dir": str(configured)},
            config_path,
        )

        self.assertEqual(
            app_module.resolve_data_dir(None, config_path),
            configured.resolve(),
        )
        self.assertEqual(
            app_module.resolve_data_dir(str(explicit), config_path),
            explicit.resolve(),
        )

    def test_residual_target_directory_is_safe_to_migrate(self):
        legacy = make_v1_data(self.root / "legacy")
        target = self.root / "target"
        target.mkdir()
        (target / "runtime.lock").write_text("stale", encoding="ascii")

        app_module.prepare_user_data_dir(target, [legacy])

        self.assertTrue((target / "archive.sqlite3").is_file())
        self.assertFalse((target / "runtime.lock").exists())
        self.assertFalse(legacy.exists())

    def test_incomplete_target_is_not_overwritten(self):
        legacy = make_v1_data(self.root / "legacy")
        target = self.root / "target"
        target.mkdir()
        (target / "notes.txt").write_text("keep", encoding="utf-8")

        with self.assertRaises(app_module.AppError) as error:
            app_module.prepare_user_data_dir(target, [legacy])

        self.assertEqual(error.exception.code, "data_incomplete")
        self.assertTrue((target / "notes.txt").is_file())
        self.assertTrue((legacy / "archive.sqlite3").is_file())

    def test_two_valid_legacy_directories_require_explicit_choice(self):
        first = make_v1_data(self.root / "first")
        second = make_v1_data(self.root / "second")
        target = self.root / "target"

        with self.assertRaises(app_module.AppError) as error:
            app_module.prepare_user_data_dir(target, [first, second])

        self.assertEqual(error.exception.code, "data_conflict")
        self.assertFalse(target.exists())

    def test_incompatible_database_is_rejected_before_schema_writes(self):
        data = self.root / "future-data"
        data.mkdir()
        with closing(sqlite3.connect(data / "archive.sqlite3")) as db:
            db.executescript(
                """
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO settings VALUES ('schema_version', '99');
                """
            )
            db.commit()

        with self.assertRaises(app_module.AppError) as error:
            Repository(data)

        self.assertEqual(error.exception.code, "database_incompatible")
        with closing(sqlite3.connect(data / "archive.sqlite3")) as db:
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertEqual(tables, {"settings"})

    def test_repository_relocation_preserves_database_and_code(self):
        source = self.root / "source-data"
        target = self.root / "new-data"
        repo = Repository(source)
        try:
            problem = repo.create_problem(
                {
                    "platform": "codeforces",
                    "number": "A",
                    "name": "迁移保留",
                    "url": "https://codeforces.com/contest/1/problem/A",
                    "language": "cpp",
                    "code": "int main() { return 0; }\n",
                    "contest_id": None,
                }
            )
            result = repo.relocate_to(target)
        finally:
            repo.close()

        self.assertEqual(result["new_data_dir"], str(target))
        moved = Repository(target)
        try:
            state = moved.state()
            self.assertEqual(len(state["problems"]), 1)
            self.assertEqual(
                moved.get_problem(problem["id"])["code"],
                "int main() { return 0; }\n",
            )
        finally:
            moved.close()

    def test_backup_import_rejects_path_traversal(self):
        repo = Repository(self.root / "data")
        try:
            archive = self.root / "malicious.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("../outside.txt", "unsafe")
                zipped.writestr("manifest.json", '{"format":1}')
            with self.assertRaises(app_module.AppError) as error:
                repo.import_backup_file(archive, archive.name)
            self.assertEqual(error.exception.code, "backup_invalid")
            self.assertFalse((self.root / "outside.txt").exists())
        finally:
            repo.close()

    def test_successful_migration_copies_database_and_codes_then_moves_legacy(self):
        legacy = make_v1_data(self.root / "app" / "data")
        target = self.root / "Local" / "AlgoArchive" / "data"

        backup = migrate_legacy_data(legacy, target)

        self.assertTrue((target / "archive.sqlite3").is_file())
        self.assertTrue((target / "codes" / "11111111111111111111111111111111.cpp").is_file())
        self.assertFalse(legacy.exists())
        self.assertIsNotNone(backup)
        self.assertTrue((backup / "archive.sqlite3").is_file())

    def test_copy_failure_keeps_legacy_and_does_not_publish_partial_target(self):
        legacy = make_v1_data(self.root / "app" / "data")
        target = self.root / "Local" / "AlgoArchive" / "data"

        with mock.patch("app.shutil.copytree", side_effect=OSError("copy failed")):
            with self.assertRaises(OSError):
                migrate_legacy_data(legacy, target)

        self.assertTrue((legacy / "archive.sqlite3").is_file())
        self.assertFalse(target.exists())

    def test_existing_target_is_not_overwritten(self):
        legacy = make_v1_data(self.root / "app" / "data")
        target = make_v1_data(self.root / "Local" / "AlgoArchive" / "data")
        before = (target / "archive.sqlite3").read_bytes()

        result = migrate_legacy_data(legacy, target)

        self.assertIsNone(result)
        self.assertEqual((target / "archive.sqlite3").read_bytes(), before)
        self.assertTrue((legacy / "archive.sqlite3").is_file())

    def test_v1_database_upgrade_preserves_contest_problem_and_code(self):
        data = make_v1_data(self.root / "upgrade")

        repo = Repository(data)
        self.addCleanup(repo.close)

        version = repo.db.execute(
            "SELECT value FROM settings WHERE key='schema_version'"
        ).fetchone()[0]
        self.assertEqual(version, "7")
        self.assertEqual(repo.state()["contests"][0]["title"], "保留比赛")
        self.assertEqual(repo.state()["problems"][0]["name"], "保留题目")
        self.assertEqual(
            repo.get_problem("11111111111111111111111111111111")["code"],
            "int main() { return 0; }\n",
        )
        tables = {
            row[0]
            for row in repo.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertTrue({"algorithms", "algorithm_snippets", "algorithm_links"} <= tables)
        problem_columns = {
            row[1] for row in repo.db.execute("PRAGMA table_info(problems)")
        }
        self.assertIn("algorithm_id", problem_columns)
        self.assertIn("algorithm_order", problem_columns)
        self.assertIn("global_order", problem_columns)
        table_sql = repo.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='problems'"
        ).fetchone()[0]
        self.assertNotIn("CHECK(platform IN", table_sql)

    def test_v3_database_upgrade_allows_custom_problem_platform(self):
        data = make_v3_data(self.root / "upgrade-v3")

        repo = Repository(data)
        self.addCleanup(repo.close)

        version = repo.db.execute(
            "SELECT value FROM settings WHERE key='schema_version'"
        ).fetchone()[0]
        self.assertEqual(version, "7")
        problem = repo.create_problem({
            "platform": "洛谷",
            "number": "P3374",
            "name": "树状数组 1",
            "url": "https://www.luogu.com.cn/problem/P3374",
            "language": "cpp",
            "code": "int main() { return 0; }\n",
            "contest_id": None,
            "algorithm_id": None,
        })
        self.assertEqual(problem["platform"], "洛谷")
        self.assertEqual(problem["url"], "https://www.luogu.com.cn/problem/P3374")
        self.assertEqual(
            {item["name"] for item in repo.state()["problems"]},
            {"保留题目", "树状数组 1"},
        )

    def test_v4_database_upgrade_allows_custom_contests(self):
        data = make_v4_data(self.root / "upgrade-v4")

        repo = Repository(data)
        self.addCleanup(repo.close)

        version = repo.db.execute(
            "SELECT value FROM settings WHERE key='schema_version'"
        ).fetchone()[0]
        self.assertEqual(version, "7")
        contest_sql = repo.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='contests'"
        ).fetchone()[0]
        self.assertNotIn("CHECK(platform IN", contest_sql)
        self.assertEqual(repo.state()["contests"][0]["title"], "保留比赛")
        self.assertEqual(repo.state()["problems"][0]["name"], "保留题目")

        contest = repo.create_contest({
            "platform": "洛谷",
            "title": "洛谷公开赛",
            "url": "https://www.luogu.com.cn/contest/123",
        })
        problem = repo.create_problem({
            "platform": "洛谷",
            "number": "P1000",
            "name": "测试题",
            "url": "https://www.luogu.com.cn/problem/P1000",
            "language": "cpp",
            "code": "int main() { return 0; }\n",
            "contest_id": contest["id"],
            "algorithm_id": None,
        })
        self.assertEqual(contest["platform"], "洛谷")
        self.assertEqual(problem["contest_id"], contest["id"])
        self.assertEqual(
            repo.get_contest(contest["id"])["problem_count"],
            1,
        )

    def test_v5_database_upgrade_initializes_algorithm_problem_order(self):
        data = make_v5_data(self.root / "upgrade-v5")

        repo = Repository(data)
        self.addCleanup(repo.close)

        version = repo.db.execute(
            "SELECT value FROM settings WHERE key='schema_version'"
        ).fetchone()[0]
        self.assertEqual(version, "7")
        problems = sorted(
            repo.state()["problems"],
            key=lambda item: item["algorithm_order"],
        )
        self.assertEqual(
            [item["id"] for item in problems],
            [
                "22222222222222222222222222222222",
                "11111111111111111111111111111111",
            ],
        )
        self.assertEqual(
            [item["algorithm_order"] for item in problems],
            [0, 1],
        )
        self.assertEqual(
            [item["global_order"] for item in problems],
            [0, 1],
        )

    def test_v6_database_upgrade_initializes_global_problem_order(self):
        data = make_v6_data(self.root / "upgrade-v6")

        repo = Repository(data)
        self.addCleanup(repo.close)

        version = repo.db.execute(
            "SELECT value FROM settings WHERE key='schema_version'"
        ).fetchone()[0]
        self.assertEqual(version, "7")
        problems = sorted(
            repo.state()["problems"],
            key=lambda item: item["global_order"],
        )
        self.assertEqual(
            [item["id"] for item in problems],
            [
                "22222222222222222222222222222222",
                "11111111111111111111111111111111",
            ],
        )
        self.assertEqual(
            [item["global_order"] for item in problems],
            [0, 1],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
