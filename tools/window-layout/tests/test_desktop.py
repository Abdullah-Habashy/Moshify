"""The shutdown decision — the part that left a window open onto nothing."""
import unittest

from winlayout.ui.desktop import (BYE_GRACE, ORPHAN_GRACE, STARTUP_GRACE,
                                  should_stop)

NOW = 10_000.0


def stop(**kwargs):
    args = dict(now=NOW, started_at=NOW - 300, last_seen=NOW, goodbye=None,
                jobs_busy=False, process_alive=True, idle_timeout=900.0)
    args.update(kwargs)
    return should_stop(**args)


class TestShouldStop(unittest.TestCase):
    def test_a_live_page_keeps_serving(self):
        self.assertFalse(stop())

    def test_a_dead_launcher_does_not_kill_a_live_page(self):
        """Chromium relaunches itself: the process we started can exit while
        its window stays open. That bug showed as ERR_CONNECTION_REFUSED."""
        self.assertFalse(stop(process_alive=False, last_seen=NOW - 5))

    def test_dead_process_and_a_silent_page_stops(self):
        self.assertTrue(stop(process_alive=False,
                             last_seen=NOW - ORPHAN_GRACE - 1))

    def test_goodbye_stops_after_its_grace(self):
        self.assertTrue(stop(goodbye=NOW - BYE_GRACE - 1))

    def test_goodbye_is_not_instant(self):
        self.assertFalse(stop(goodbye=NOW - 1))

    def test_a_reload_retracts_the_goodbye(self):
        # The server clears goodbye on the next request, so it arrives as None.
        self.assertFalse(stop(goodbye=None, last_seen=NOW))

    def test_startup_grace_survives_a_slow_browser(self):
        self.assertFalse(stop(started_at=NOW - 5, process_alive=False,
                              last_seen=NOW - 30))

    def test_goodbye_beats_the_startup_grace(self):
        self.assertTrue(stop(started_at=NOW - 5, goodbye=NOW - BYE_GRACE - 1))

    def test_a_running_restore_is_never_cut_short(self):
        self.assertFalse(stop(jobs_busy=True, goodbye=NOW - 600,
                              process_alive=False, last_seen=NOW - 3600))

    def test_idle_timeout_still_applies(self):
        self.assertTrue(stop(last_seen=NOW - 901))

    def test_grace_periods_are_ordered_sensibly(self):
        self.assertLess(BYE_GRACE, ORPHAN_GRACE)
        self.assertLess(ORPHAN_GRACE, STARTUP_GRACE)


if __name__ == "__main__":
    unittest.main()
