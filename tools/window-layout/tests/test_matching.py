import unittest

from winlayout import matching
from winlayout.model import Rect, WindowInfo


def win(**kwargs):
    kwargs.setdefault("rect", Rect(0, 0, 800, 600))
    return WindowInfo(**kwargs)


class TestTitles(unittest.TestCase):
    def test_unread_counter_is_ignored(self):
        self.assertEqual(matching.normalize_title("(3) WhatsApp"), "whatsapp")

    def test_unsaved_marker_is_ignored(self):
        self.assertEqual(matching.normalize_title("● app.js - Code"),
                         matching.normalize_title("app.js - Code"))

    def test_identical_titles_score_highest(self):
        self.assertEqual(matching.title_score("a - Code", "a - Code"), 40)

    def test_same_app_different_document_still_scores(self):
        score = matching.title_score("index.html - Code", "style.css - Code")
        self.assertTrue(0 < score < 40)


class TestScore(unittest.TestCase):
    def test_different_executables_never_match(self):
        a = win(exe_name="chrome.exe", cls="Chrome_WidgetWin_1", title="x")
        b = win(exe_name="Code.exe", cls="Chrome_WidgetWin_1", title="x")
        self.assertIsNone(matching.score(a, b))

    def test_same_app_and_title_beats_same_app_alone(self):
        saved = win(exe_name="Code.exe", cls="C1", title="a.py - Code")
        same = win(exe_name="Code.exe", cls="C1", title="a.py - Code")
        other = win(exe_name="Code.exe", cls="C1", title="b.py - Code")
        self.assertGreater(matching.score(saved, same), matching.score(saved, other))

    def test_class_only_match_without_exe_is_rejected(self):
        saved = win(cls="C1", title="x", exe_name=None)
        live = win(cls="C2", title="x", exe_name=None)
        self.assertIsNone(matching.score(saved, live))


class TestAssign(unittest.TestCase):
    def test_one_live_window_is_used_once(self):
        saved = [
            win(id="a", exe_name="chrome.exe", cls="C", title="طفرة - Chrome"),
            win(id="b", exe_name="chrome.exe", cls="C", title="Gmail - Chrome"),
        ]
        live = [win(hwnd=1, exe_name="chrome.exe", cls="C", title="Gmail - Chrome")]
        result = matching.assign(saved, live)
        self.assertEqual(list(result), ["b"])
        self.assertEqual([s.id for s in matching.unmatched(saved, result)], ["a"])

    def test_each_saved_window_gets_its_own_live_window(self):
        saved = [
            win(id="a", exe_name="chrome.exe", cls="C", title="طفرة - Chrome"),
            win(id="b", exe_name="chrome.exe", cls="C", title="Gmail - Chrome"),
        ]
        live = [
            win(hwnd=1, exe_name="chrome.exe", cls="C", title="Gmail - Chrome"),
            win(hwnd=2, exe_name="chrome.exe", cls="C", title="طفرة - Chrome"),
        ]
        result = matching.assign(saved, live)
        self.assertEqual(result["a"].hwnd, 2)
        self.assertEqual(result["b"].hwnd, 1)

    def test_unrelated_window_is_not_matched(self):
        saved = [win(id="a", exe_name="Code.exe", cls="C1", title="a.py")]
        live = [win(hwnd=9, exe_name="notepad.exe", cls="Notepad", title="ملف")]
        self.assertEqual(matching.assign(saved, live), {})

    def test_launch_groups_are_per_application(self):
        specs = [
            win(id="a", exe="C:/chrome.exe", exe_name="chrome.exe"),
            win(id="b", exe="C:/chrome.exe", exe_name="chrome.exe"),
            win(id="c", exe="C:/Code.exe", exe_name="Code.exe", launch=False),
        ]
        groups = matching.group_for_launch(specs)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0][1]), 2)


if __name__ == "__main__":
    unittest.main()
