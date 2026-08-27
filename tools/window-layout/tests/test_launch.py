"""Restoring a layout whose apps are closed."""
import tempfile
import unittest
from pathlib import Path

from winlayout import applaunch, engine
from winlayout.backend.fake_backend import FakeBackend
from winlayout.engine import (Engine, STATUS_LAUNCHED, STATUS_MISSING,
                              STATUS_MOVED)
from winlayout.model import Rect, WindowInfo


class TestLaunchOnRestore(unittest.TestCase):
    def setUp(self):
        # Keep the waits out of the test suite's wall clock.
        self._saved = (engine.LAUNCH_STAGGER, engine.POLL_INTERVAL,
                       engine.MIN_LAUNCH_WAIT)
        engine.LAUNCH_STAGGER = 0.0
        engine.POLL_INTERVAL = 0.01
        engine.MIN_LAUNCH_WAIT = 0.3
        self.backend = FakeBackend()
        self.engine = Engine(self.backend)
        self.layout = self.engine.capture("شغل")

    def tearDown(self):
        (engine.LAUNCH_STAGGER, engine.POLL_INTERVAL,
         engine.MIN_LAUNCH_WAIT) = self._saved

    def test_a_closed_app_is_opened_and_placed(self):
        self.backend.close("Telegram")
        report = self.engine.restore(self.layout)
        self.assertEqual(self.backend.launched, ["Telegram.exe"])
        self.assertEqual(report.count(STATUS_LAUNCHED), 1)
        placed = [w for w in self.backend.windows() if w.title == "Telegram"][0]
        self.assertEqual(placed.rect, Rect(2560, 100, 3200, 900))

    def test_everything_closed_comes_back(self):
        self.backend.close_all()
        report = self.engine.restore(self.layout)
        self.assertEqual(sorted(self.backend.launched),
                         ["Code.exe", "Telegram.exe", "chrome.exe"])
        self.assertEqual(report.count(STATUS_LAUNCHED), 3)
        self.assertTrue(report.ok)
        for spec in self.layout.windows:
            live = [w for w in self.backend.windows() if w.title == spec.title][0]
            self.assertEqual(live.rect, spec.rect)

    def test_two_windows_of_one_app_are_matched_by_title(self):
        second = WindowInfo(
            title="Gmail - Google Chrome", cls="Chrome_WidgetWin_1",
            exe=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            exe_name="chrome.exe", rect=Rect(0, 1040, 1280, 1400),
            normal_rect=Rect(0, 1040, 1280, 1400), monitor=r"\\.\DISPLAY1",
            hwnd=9001, pid=9001)
        self.backend._windows.append(second)
        layout = self.engine.capture("شغل")
        self.backend.close("Chrome")

        # The app opens its windows back in the other order.
        self.backend.launch_titles["chrome.exe"] = [
            "Gmail - Google Chrome", "طفرة — لوحة الدعم - Google Chrome"]
        self.engine.restore(layout)

        for spec in layout.windows:
            if spec.exe_name != "chrome.exe":
                continue
            live = [w for w in self.backend.windows() if w.title == spec.title]
            self.assertEqual(len(live), 1, spec.title)
            self.assertEqual(live[0].rect, spec.rect,
                             f"«{spec.title}» راحت مكان غلط")

    def test_a_launch_that_fails_is_reported_not_swallowed(self):
        self.backend.close("Telegram")
        self.backend.launch_errors["Telegram.exe"] = "الملف مش موجود"
        report = self.engine.restore(self.layout)
        self.assertEqual(report.count(STATUS_MISSING), 1)
        self.assertTrue(any("Telegram" in w for w in report.warnings))
        self.assertFalse(report.ok)

    def test_an_app_that_never_shows_a_window_times_out_cleanly(self):
        self.backend.close("Telegram")
        self.backend.launch_opens_nothing.add("Telegram.exe")
        self.layout.launch_timeout = 0.2  # the real default is 30 seconds
        messages = []
        report = self.engine.restore(self.layout, progress=messages.append)
        self.assertEqual(report.count(STATUS_MISSING), 1)
        self.assertTrue(any("ماردّش" in m for m in messages))
        # The windows that were open still get placed.
        self.assertEqual(report.count(STATUS_MOVED), 2)

    def test_launching_is_skipped_when_the_layout_says_so(self):
        self.backend.close_all()
        self.layout.launch_missing = False
        report = self.engine.restore(self.layout)
        self.assertEqual(self.backend.launched, [])
        self.assertEqual(report.count(STATUS_MISSING), 3)


class TestFindingAMovedApp(unittest.TestCase):
    """Discord, Slack and Teams move to a new folder on every update."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path

    def test_an_existing_path_is_used_as_is(self):
        exe = self.make("Discord/app-1.0.9040/Discord.exe")
        self.assertEqual(applaunch.resolve(str(exe)), exe)

    def test_the_newest_versioned_folder_wins(self):
        old = self.root / "Discord" / "app-1.0.9040" / "Discord.exe"
        self.make("Discord/app-1.0.9041/Discord.exe")
        newest = self.make("Discord/app-1.0.10000/Discord.exe")
        self.assertEqual(applaunch.resolve(str(old)), newest)

    def test_version_order_is_numeric_not_alphabetical(self):
        self.assertGreater(applaunch.version_key("app-1.0.10000"),
                           applaunch.version_key("app-1.0.9999"))

    def test_a_start_menu_shortcut_is_the_last_resort(self):
        gone = self.root / "Old" / "Notion.exe"
        shortcut = self.make("StartMenu/Programs/Notion.lnk")
        self.assertEqual(
            applaunch.resolve(str(gone), [self.root / "StartMenu"]), shortcut)

    def test_shortcut_names_ignore_spaces_and_dashes(self):
        gone = self.root / "Old" / "VisualStudioCode.exe"
        shortcut = self.make("StartMenu/Visual Studio Code.lnk")
        self.assertEqual(
            applaunch.resolve(str(gone), [self.root / "StartMenu"]), shortcut)

    def test_an_unrelated_shortcut_is_not_used(self):
        gone = self.root / "Old" / "Notion.exe"
        self.make("StartMenu/Notepad.lnk")
        self.assertIsNone(
            applaunch.resolve(str(gone), [self.root / "StartMenu"]))

    def test_nothing_to_go_on(self):
        self.assertIsNone(applaunch.resolve(None))
        self.assertIsNone(applaunch.resolve(str(self.root / "nope" / "gone.exe")))


if __name__ == "__main__":
    unittest.main()
