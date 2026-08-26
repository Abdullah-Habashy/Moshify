import unittest

from winlayout.backend.fake_backend import FakeBackend
from winlayout.engine import (Engine, STATUS_FAILED, STATUS_LAUNCHED,
                              STATUS_MISSING, STATUS_MOVED)
from winlayout.model import Rect


class TestCapture(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.engine = Engine(self.backend)

    def test_capture_takes_every_window_by_default(self):
        layout = self.engine.capture("شغل")
        self.assertEqual(len(layout.windows), 3)
        self.assertEqual(len(layout.monitors), 2)
        self.assertTrue(all(w.id for w in layout.windows))

    def test_capture_can_keep_a_subset(self):
        live = self.backend.windows()
        layout = self.engine.capture("شغل", keep=[live[0].hwnd])
        self.assertEqual([w.title for w in layout.windows], [live[0].title])

    def test_capture_drops_runtime_handles(self):
        layout = self.engine.capture("شغل")
        self.assertNotIn("hwnd", layout.to_dict()["windows"][0])


class TestRestore(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.engine = Engine(self.backend)
        self.layout = self.engine.capture("شغل")

    def test_moved_windows_go_back_to_the_saved_rect(self):
        moved = self.backend.windows()[0]
        moved.rect = Rect(10, 10, 400, 300)
        report = self.engine.restore(self.layout)
        self.assertEqual(report.count(STATUS_MOVED), 3)
        self.assertTrue(report.ok)
        self.assertEqual(self.backend.windows()[0].rect,
                         self.layout.windows[0].rect)

    def test_closed_window_is_relaunched_then_placed(self):
        self.backend.close("Telegram")
        report = self.engine.restore(self.layout)
        self.assertEqual(self.backend.launched, ["Telegram.exe"])
        self.assertEqual(report.count(STATUS_LAUNCHED), 1)
        self.assertEqual(report.count(STATUS_MOVED), 2)
        placed = [w for w in self.backend.windows() if w.title == "Telegram"][0]
        self.assertEqual(placed.rect, Rect(2560, 100, 3200, 900))

    def test_no_launch_reports_the_window_as_missing(self):
        self.backend.close("Telegram")
        self.layout.launch_missing = False
        report = self.engine.restore(self.layout)
        self.assertEqual(self.backend.launched, [])
        self.assertEqual(report.count(STATUS_MISSING), 1)
        self.assertFalse(report.ok)

    def test_failure_is_reported_not_raised(self):
        self.backend.apply = lambda *a, **k: "ويندوز رفض"
        report = self.engine.restore(self.layout)
        self.assertEqual(report.count(STATUS_FAILED), 3)
        self.assertIn("فشلت", report.summary())

    def test_progress_messages_are_emitted(self):
        seen = []
        self.engine.restore(self.layout, progress=seen.append)
        self.assertTrue(seen)

    def test_unplugged_monitor_pulls_windows_back_on_screen(self):
        self.backend._monitors = self.backend._monitors[:1]
        for win in self.backend.windows():
            win.monitor = r"\\.\DISPLAY1"
        report = self.engine.restore(self.layout)
        self.assertTrue(report.warnings)
        for win in self.backend.windows():
            self.assertLess(win.rect.left, 2560)

    def test_report_follows_the_saved_order(self):
        report = self.engine.restore(self.layout)
        self.assertEqual([r.id for r in report.results],
                         [w.id for w in self.layout.windows])


if __name__ == "__main__":
    unittest.main()
