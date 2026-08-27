"""Where a desktop shortcut lands, and what it is called."""
import tempfile
import unittest
from pathlib import Path

from winlayout import shortcuts
from winlayout.shortcuts import (Command, _create_cmd, desktop_by_guessing,
                                 safe_filename, shortcut_command)


class TestDesktopLocation(unittest.TestCase):
    """OneDrive moves the desktop and leaves the old folder behind, empty.
    Guessing %USERPROFILE%\\Desktop first drops the shortcut somewhere the
    user never sees."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_onedrive_wins_over_a_leftover_desktop_folder(self):
        (self.profile / "Desktop").mkdir()
        onedrive = self.profile / "OneDrive" / "Desktop"
        onedrive.mkdir(parents=True)
        self.assertEqual(desktop_by_guessing(self.profile), onedrive)

    def test_plain_desktop_when_there_is_no_onedrive(self):
        desktop = self.profile / "Desktop"
        desktop.mkdir()
        self.assertEqual(desktop_by_guessing(self.profile), desktop)

    def test_arabic_desktop_folder_name(self):
        desktop = self.profile / "سطح المكتب"
        desktop.mkdir()
        self.assertEqual(desktop_by_guessing(self.profile), desktop)

    def test_falls_back_to_the_profile_root(self):
        self.assertEqual(desktop_by_guessing(self.profile), self.profile)

    def test_the_shell_is_asked_before_any_guessing(self):
        calls = []
        original = (shortcuts.desktop_from_known_folder,
                    shortcuts.desktop_from_registry)
        shortcuts.desktop_from_known_folder = lambda: (calls.append("shell")
                                                       or self.profile)
        shortcuts.desktop_from_registry = lambda: calls.append("registry")
        try:
            self.assertEqual(shortcuts.desktop_dir(), self.profile)
        finally:
            (shortcuts.desktop_from_known_folder,
             shortcuts.desktop_from_registry) = original
        self.assertEqual(calls, ["shell"])


class TestNaming(unittest.TestCase):
    def test_spaces_survive_so_the_name_reads_normally(self):
        self.assertEqual(safe_filename("شغل الصبح"), "شغل الصبح")

    def test_characters_windows_refuses_are_dropped(self):
        self.assertEqual(safe_filename('a<b>c:d"e/f\\g|h?i*j'), "abcdefghij")

    def test_a_trailing_dot_would_break_the_file(self):
        self.assertFalse(safe_filename("layout...").endswith("."))

    def test_a_name_of_only_symbols_still_produces_something(self):
        self.assertTrue(safe_filename("///"))


class TestCmdFallback(unittest.TestCase):
    def test_the_batch_file_switches_to_utf8_and_carries_no_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = Command(r"C:\a\WindowLayout.exe", 'restore "شغل الصبح"',
                              "", r"C:\a")
            path = _create_cmd("شغل الصبح", Path(tmp), command)
            raw = path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "BOM بيتنفّذ كأمر")
        text = raw.decode("utf-8")
        self.assertIn("chcp 65001", text)
        self.assertIn('restore "شغل الصبح"', text)
        self.assertTrue(path.name.endswith(".cmd"))


class TestCommand(unittest.TestCase):
    def test_frozen_app_points_at_itself(self):
        cmd = shortcut_command("شغل", frozen=True,
                               executable=r"C:\a\WindowLayout.exe", root=Path(r"C:\a"))
        self.assertEqual(cmd.arguments, 'restore "شغل"')


if __name__ == "__main__":
    unittest.main()
