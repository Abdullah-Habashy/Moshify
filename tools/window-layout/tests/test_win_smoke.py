"""Real-Windows checks for the ctypes layer.

Skipped everywhere else. These are the tests that prove the structures and
function prototypes in win_backend are right -- nothing else can.
"""
import sys
import tempfile
import unittest
from pathlib import Path

from winlayout.model import Rect, STATE_MAXIMIZED, STATE_MINIMIZED, STATE_NORMAL

TITLE = "WindowLayout CI target"


@unittest.skipUnless(sys.platform == "win32", "يشتغل على ويندوز بس")
class TestWindowsBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from winlayout.backend.win_backend import WindowsBackend
        cls.backend = WindowsBackend()

    def test_monitors_are_sane(self):
        monitors = self.backend.monitors()
        self.assertTrue(monitors, "مالقيناش أي شاشة")
        self.assertTrue(any(m.primary for m in monitors), "مافيش شاشة أساسية")
        for mon in monitors:
            self.assertTrue(mon.device)
            self.assertGreater(mon.rect.width, 0)
            self.assertGreater(mon.rect.height, 0)
            self.assertGreaterEqual(mon.dpi, 72)
            self.assertLessEqual(mon.work.width, mon.rect.width)

    def test_primary_monitor_starts_at_the_origin(self):
        primary = [m for m in self.backend.monitors() if m.primary][0]
        self.assertEqual((primary.rect.left, primary.rect.top), (0, 0))

    def test_workspace_offset_matches_the_primary_work_area(self):
        primary = [m for m in self.backend.monitors() if m.primary][0]
        self.assertEqual(self.backend._offset(),
                         (primary.work.left - primary.rect.left,
                          primary.work.top - primary.rect.top))

    def test_workspace_conversion_round_trips(self):
        rect = Rect(100, 200, 900, 800)
        self.assertEqual(self.backend._from_workspace(
            self.backend._to_workspace(rect)), rect)

    def test_enumeration_returns_usable_windows(self):
        windows = self.backend.windows()
        for win in windows:
            self.assertIsInstance(win.hwnd, int)
            self.assertGreater(win.hwnd, 0)
            self.assertTrue(win.title)
            self.assertIn(win.state, (STATE_NORMAL, STATE_MAXIMIZED, STATE_MINIMIZED))
            self.assertGreater(win.rect.width, 0)
            self.assertGreater(win.rect.height, 0)
            if win.exe:
                self.assertTrue(win.exe_name)
        self.assertEqual(len({w.hwnd for w in windows}), len(windows), "hwnd متكرر")

    def test_capture_saves_and_loads(self):
        from winlayout.engine import Engine
        from winlayout.store import LayoutStore
        with tempfile.TemporaryDirectory() as tmp:
            store = LayoutStore(Path(tmp))
            layout = Engine(self.backend).capture("ci")
            store.save(layout)
            loaded = store.get("ci")
            self.assertEqual(len(loaded.windows), len(layout.windows))
            self.assertEqual(len(loaded.monitors), len(layout.monitors))


@unittest.skipUnless(sys.platform == "win32", "يشتغل على ويندوز بس")
class TestMovesARealWindow(unittest.TestCase):
    """Create a window, move it, and read the position back."""

    @classmethod
    def setUpClass(cls):
        from winlayout.backend.win_backend import WindowsBackend
        cls.backend = WindowsBackend()  # DPI awareness first, then the window
        try:
            import tkinter
            cls.root = tkinter.Tk()
        except Exception as exc:  # no desktop on this runner
            raise unittest.SkipTest(f"مافيش سطح مكتب: {exc}")
        cls.root.title(TITLE)
        cls.root.geometry("500x400+120+120")
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "root", None) is not None:
            cls.root.destroy()

    def find(self):
        self.root.update()
        for win in self.backend.windows(with_cmdlines=False):
            if win.title == TITLE:
                return win
        return None

    def test_the_window_is_visible_to_the_enumerator(self):
        win = self.find()
        if win is None:
            self.skipTest("النافذة مش ظاهرة للجلسة دي")
        self.assertEqual(win.state, STATE_NORMAL)
        self.assertTrue(win.exe_name.lower().startswith("python"))

    def test_move_and_resize_lands_where_asked(self):
        win = self.find()
        if win is None:
            self.skipTest("النافذة مش ظاهرة للجلسة دي")
        target = Rect(220, 160, 940, 700)
        self.assertIsNone(self.backend.apply(win, target, STATE_NORMAL, False))
        moved = self.find()
        for name, got, want in (("left", moved.rect.left, target.left),
                                ("top", moved.rect.top, target.top),
                                ("width", moved.rect.width, target.width),
                                ("height", moved.rect.height, target.height)):
            self.assertAlmostEqual(got, want, delta=2, msg=f"{name}: {got} != {want}")

    def test_maximize_then_restore_keeps_the_saved_geometry(self):
        win = self.find()
        if win is None:
            self.skipTest("النافذة مش ظاهرة للجلسة دي")
        target = Rect(200, 150, 900, 650)
        self.assertIsNone(self.backend.apply(win, target, STATE_MAXIMIZED, False))
        maximized = self.find()
        self.assertEqual(maximized.state, STATE_MAXIMIZED)
        # The restored size travels with it, which is what a later restore replays.
        self.assertAlmostEqual(maximized.normal_rect.width, target.width, delta=2)
        self.assertIsNone(self.backend.apply(maximized, target, STATE_NORMAL, False))
        self.assertEqual(self.find().state, STATE_NORMAL)

    def test_minimize_and_come_back(self):
        win = self.find()
        if win is None:
            self.skipTest("النافذة مش ظاهرة للجلسة دي")
        target = Rect(260, 180, 860, 620)
        self.assertIsNone(self.backend.apply(win, target, STATE_MINIMIZED, False))
        self.assertEqual(self.find().state, STATE_MINIMIZED)
        self.assertIsNone(self.backend.apply(self.find(), target, STATE_NORMAL, False))
        back = self.find()
        self.assertEqual(back.state, STATE_NORMAL)
        self.assertAlmostEqual(back.rect.left, target.left, delta=2)


@unittest.skipUnless(sys.platform == "win32", "يشتغل على ويندوز بس")
class TestShortcutsOnWindows(unittest.TestCase):
    """The ctypes/COM plumbing behind 'where is the desktop', and whether
    PowerShell really writes a shell link."""

    def test_the_shell_knows_where_the_desktop_is(self):
        from winlayout.shortcuts import desktop_from_known_folder
        found = desktop_from_known_folder()
        self.assertIsNotNone(found, "SHGetKnownFolderPath مرجعش حاجة")
        self.assertTrue(found.is_dir())

    def test_the_registry_agrees_with_the_shell(self):
        from winlayout.shortcuts import (desktop_from_known_folder,
                                         desktop_from_registry)
        shell, registry = desktop_from_known_folder(), desktop_from_registry()
        if registry is None:
            self.skipTest("مافيش قيمة في الريجستري")
        self.assertEqual(Path(str(shell)).resolve(), registry.resolve())

    def test_desktop_dir_always_answers(self):
        from winlayout.shortcuts import desktop_dir
        self.assertTrue(desktop_dir().is_dir())

    def test_a_real_shell_link_is_written(self):
        from winlayout.shortcuts import create_shortcut
        with tempfile.TemporaryDirectory() as tmp:
            path = create_shortcut("شغل الصبح", Path(tmp))
            self.assertTrue(path.exists(), "الاختصار مااتكتبش")
            if path.suffix == ".cmd":
                import shutil
                from winlayout.diag import log_path
                reason = ""
                if log_path().exists():
                    reason = "\n".join(log_path().read_text(
                        encoding="utf-8", errors="replace").splitlines()[-6:])
                if not (shutil.which("powershell.exe") or shutil.which("pwsh.exe")):
                    self.skipTest("مافيش PowerShell على الجهاز")
                self.fail("PowerShell موجود ومع ذلك مااتكتبش .lnk — "
                          f"آخر السجل:\n{reason}")
            self.assertEqual(path.name, "شغل الصبح.lnk")
            raw = path.read_bytes()
        # A .lnk starts with its 76-byte header and the shell link CLSID.
        self.assertEqual(raw[:4], b"\x4c\x00\x00\x00")
        self.assertEqual(
            raw[4:20],
            b"\x01\x14\x02\x00\x00\x00\x00\x00\xc0\x00\x00\x00\x00\x00\x00\x46")


if __name__ == "__main__":
    unittest.main()
