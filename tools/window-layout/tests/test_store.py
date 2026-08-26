import tempfile
import unittest
from pathlib import Path

from winlayout.model import Layout, MonitorInfo, Rect, WindowInfo, assign_ids
from winlayout.store import LayoutStore


def sample(name="شغل الصبح"):
    windows = assign_ids([
        WindowInfo(title="a.py - Code", cls="C1", exe_name="Code.exe",
                   rect=Rect(0, 0, 900, 700)),
        WindowInfo(title="Gmail", cls="C2", exe_name="chrome.exe",
                   rect=Rect(900, 0, 1900, 700), state="maximized",
                   normal_rect=Rect(910, 10, 1890, 690)),
    ])
    monitors = [MonitorInfo(device=r"\\.\DISPLAY1", rect=Rect(0, 0, 1920, 1080),
                            work=Rect(0, 0, 1920, 1040), primary=True)]
    return Layout(name=name, windows=windows, monitors=monitors)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LayoutStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_keeps_every_field(self):
        self.store.save(sample())
        loaded = self.store.get("شغل الصبح")
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded.windows), 2)
        self.assertEqual(loaded.windows[0].title, "a.py - Code")
        self.assertEqual(loaded.windows[1].state, "maximized")
        self.assertEqual(loaded.windows[1].normal_rect, Rect(910, 10, 1890, 690))
        self.assertTrue(loaded.monitors[0].primary)

    def test_arabic_names_survive_the_filename(self):
        self.store.save(sample("توزيع المونتاج"))
        self.assertIn("توزيع المونتاج", self.store.names())

    def test_rename_moves_the_file(self):
        self.store.save(sample())
        self.store.rename("شغل الصبح", "شغل بالليل")
        self.assertFalse(self.store.exists("شغل الصبح"))
        self.assertEqual(self.store.get("شغل بالليل").name, "شغل بالليل")

    def test_delete(self):
        self.store.save(sample())
        self.assertTrue(self.store.delete("شغل الصبح"))
        self.assertFalse(self.store.delete("شغل الصبح"))

    def test_corrupt_file_is_skipped_not_fatal(self):
        self.store.save(sample())
        (Path(self.tmp.name) / "broken.json").write_text("{ nope", encoding="utf-8")
        self.assertEqual(len(self.store.all()), 1)

    def test_ids_are_unique_per_layout(self):
        ids = [w.id for w in sample().windows]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()


class TestArabicCounting(unittest.TestCase):
    def test_counts_agree_with_the_noun(self):
        from winlayout import arabic
        self.assertEqual(arabic.windows(0), "مافيش نوافذ")
        self.assertEqual(arabic.windows(1), "نافذة واحدة")
        self.assertEqual(arabic.windows(2), "نافذتين")
        self.assertEqual(arabic.windows(3), "3 نوافذ")
        self.assertEqual(arabic.windows(11), "11 نافذة")
        self.assertEqual(arabic.monitors(2), "شاشتين")
