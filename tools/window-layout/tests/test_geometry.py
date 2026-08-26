import unittest

from winlayout import geometry
from winlayout.model import MonitorInfo, Rect

LEFT = MonitorInfo(device=r"\\.\DISPLAY1", rect=Rect(0, 0, 1920, 1080),
                   work=Rect(0, 0, 1920, 1040), primary=True, index=0)
RIGHT = MonitorInfo(device=r"\\.\DISPLAY2", rect=Rect(1920, 0, 3840, 1080),
                    work=Rect(1920, 0, 3840, 1040), index=1)


class TestLookup(unittest.TestCase):
    def test_picks_the_monitor_holding_most_of_the_window(self):
        rect = Rect(1800, 100, 2200, 500)  # straddles the seam, mostly right
        self.assertIs(geometry.monitor_for_rect(rect, [LEFT, RIGHT]), RIGHT)

    def test_offscreen_window_falls_back_to_nearest(self):
        rect = Rect(5000, 100, 5400, 500)
        self.assertIs(geometry.monitor_for_rect(rect, [LEFT, RIGHT]), RIGHT)

    def test_signature_changes_with_the_setup(self):
        self.assertNotEqual(geometry.signature([LEFT, RIGHT]), geometry.signature([LEFT]))
        self.assertEqual(geometry.signature([LEFT, RIGHT]), geometry.signature([RIGHT, LEFT]))


class TestClamping(unittest.TestCase):
    def test_window_bigger_than_the_screen_is_shrunk(self):
        result = geometry.clamp_to_monitor(Rect(-200, -200, 4000, 4000), LEFT)
        self.assertEqual(result, Rect(0, 0, 1920, 1040))

    def test_offscreen_window_is_pulled_back(self):
        result = geometry.keep_on_screen(Rect(6000, 6000, 6800, 6600), [LEFT])
        self.assertGreaterEqual(geometry.intersect_area(result, LEFT.work), 1)

    def test_visible_window_is_left_alone(self):
        rect = Rect(100, 100, 900, 700)
        self.assertEqual(geometry.keep_on_screen(rect, [LEFT, RIGHT]), rect)


class TestRemap(unittest.TestCase):
    def test_same_setup_replays_exactly(self):
        rect = Rect(1920, 40, 2920, 840)
        out, note = geometry.remap_rect(rect, RIGHT, [LEFT, RIGHT], [LEFT, RIGHT])
        self.assertEqual(out, rect)
        self.assertIsNone(note)

    def test_missing_monitor_moves_the_window_to_the_primary(self):
        rect = Rect(1920, 40, 2920, 840)
        out, note = geometry.remap_rect(rect, RIGHT, [LEFT, RIGHT], [LEFT])
        self.assertIsNotNone(note)
        self.assertGreater(geometry.intersect_area(out, LEFT.work), 0)

    def test_resized_monitor_scales_proportionally(self):
        smaller = MonitorInfo(device=r"\\.\DISPLAY2", rect=Rect(1920, 0, 3200, 720),
                              work=Rect(1920, 0, 3200, 680), index=1)
        rect = Rect(1920, 0, 2880, 1040)  # left half of the old right screen
        out, note = geometry.remap_rect(rect, RIGHT, [LEFT, RIGHT], [LEFT, smaller])
        self.assertIsNotNone(note)
        self.assertLessEqual(out.right, smaller.work.right)
        self.assertLessEqual(out.bottom, smaller.work.bottom)
        self.assertAlmostEqual(out.width / smaller.work.width, 0.5, places=1)


if __name__ == "__main__":
    unittest.main()
