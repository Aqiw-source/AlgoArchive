from pathlib import Path
import tempfile
import threading
import unittest

import app


class SidebarArtTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="algo-art-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        self.repo = app.Repository(self.data)
        self.addCleanup(lambda: self.repo.close())

    def preference(self):
        return self.repo.state().get("sidebar_art")

    def test_default_is_visible_celebration_without_writing_settings(self):
        before = list(self.repo.db.execute("SELECT * FROM settings ORDER BY key"))
        self.assertEqual(self.preference(), {"image": "celebration", "hidden": False})
        self.assertEqual(list(self.repo.db.execute("SELECT * FROM settings ORDER BY key")), before)

    def test_all_three_images_and_hidden_state_survive_restart(self):
        for image in ("debug", "thinking", "celebration"):
            for hidden in (False, True):
                expected = {"image": image, "hidden": hidden}
                self.repo.update_sidebar_art(expected)
                self.repo.close()
                self.repo = app.Repository(self.data)
                self.assertEqual(self.preference(), expected)

    def test_invalid_preferences_do_not_change_saved_choice(self):
        expected = {"image": "thinking", "hidden": True}
        self.repo.update_sidebar_art(expected)
        for payload in ({"image": "../private.png", "hidden": False},
                        {"image": "https://example.com/image.png", "hidden": False},
                        {"image": "debug", "hidden": "false"},
                        {"image": "debug"}, {"hidden": False}):
            with self.subTest(payload=payload):
                with self.assertRaises(app.AppError):
                    self.repo.update_sidebar_art(payload)
                self.assertEqual(self.preference(), expected)

    def test_backup_restores_preference_and_default_can_be_restored(self):
        expected = {"image": "debug", "hidden": True}
        self.repo.update_sidebar_art(expected)
        backup = self.repo.create_backup()
        self.repo.update_sidebar_art({"image": "thinking", "hidden": False})
        self.repo.restore_backup(backup["name"], confirmed=True)
        self.assertEqual(self.preference(), expected)
        self.repo.update_sidebar_art({"image": "celebration", "hidden": False})
        self.assertEqual(self.preference(), {"image": "celebration", "hidden": False})

    def test_artwork_write_respects_migration_barrier(self):
        self.repo.maintenance = True
        with self.assertRaises(app.AppError) as error:
            self.repo.update_sidebar_art({"image": "debug", "hidden": False})
        self.assertEqual(error.exception.code, "storage_maintenance")
        self.repo.maintenance = False
        self.assertEqual(self.preference(), {"image": "celebration", "hidden": False})

    def test_artwork_reads_wait_for_in_flight_settings_transaction(self):
        started, finished = threading.Event(), threading.Event()
        result = []

        def read():
            started.set()
            result.append(self.repo.get_sidebar_art())
            finished.set()

        reader = threading.Thread(target=read)
        try:
            with self.repo.lock:
                reader.start()
                self.assertTrue(started.wait(2))
                self.assertFalse(finished.wait(0.1), "reader bypassed the settings transaction lock")
        finally:
            reader.join(2)
        self.assertFalse(reader.is_alive())
        self.assertEqual(result, [{"image": "celebration", "hidden": False}])
