import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from winlayout.backend.fake_backend import FakeBackend
from winlayout.engine import Engine
from winlayout.store import LayoutStore
from winlayout.ui import server as ui_server


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        state = ui_server.UIState()
        state.store = LayoutStore(Path(cls.tmp.name))
        state._engine = Engine(FakeBackend())
        cls.state = state
        cls.server, _state, cls.url = ui_server.create_server(0, state)
        cls.base = cls.url.split("/?")[0]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def call(self, path, payload=None, token=None, params=""):
        token = self.state.token if token is None else token
        url = f"{self.base}/api/{path}?t={token}{params}"
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            url, data=data, method="POST" if payload is not None else "GET",
            headers={"Content-Type": "application/json"} if data else {})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_token_is_required(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.call("layouts", token="wrong")
        self.assertEqual(ctx.exception.code, 403)

    def test_index_page_carries_the_token(self):
        with urllib.request.urlopen(f"{self.base}/?t={self.state.token}", timeout=10) as r:
            html = r.read().decode("utf-8")
        self.assertIn(self.state.token, html)
        self.assertNotIn("{{TOKEN}}", html)
        self.assertIn('dir="rtl"', html)

    def test_static_assets_are_served(self):
        for name in ("app.js", "style.css"):
            with urllib.request.urlopen(f"{self.base}/static/{name}?t={self.state.token}",
                                        timeout=10) as r:
                self.assertEqual(r.status, 200)
                self.assertTrue(r.read())

    def test_server_source_is_not_downloadable(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"{self.base}/static/server.py?t={self.state.token}",
                                   timeout=10)
        self.assertEqual(ctx.exception.code, 404)

    def test_snapshot_lists_live_windows(self):
        data = self.call("snapshot")
        self.assertEqual(len(data["windows"]), 3)
        self.assertEqual(len(data["monitors"]), 2)
        self.assertIn("hwnd", data["windows"][0])

    def test_capture_restore_shortcut_flow(self):
        windows = self.call("snapshot")["windows"]
        picked = [w["hwnd"] for w in windows[:2]]
        saved = self.call("capture", {"name": "شغل", "hwnds": picked})
        self.assertEqual(saved["layout"]["windows"], 2)
        self.assertEqual(len(saved["layout"]["items"]), 2)
        self.assertEqual(len(saved["layout"]["bounds"]), 4)

        listing = self.call("layouts")
        self.assertEqual([l["name"] for l in listing["layouts"]], ["شغل"])

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.call("capture", {"name": "شغل", "hwnds": picked})
        self.assertEqual(ctx.exception.code, 409)

        job = self.call("restore", {"name": "شغل"})["job"]
        for _ in range(60):
            state = self.call("job", params=f"&id={job}")
            if state["done"]:
                break
        self.assertTrue(state["done"])
        self.assertIsNone(state["error"])
        self.assertEqual(len(state["report"]["results"]), 2)
        self.assertTrue(state["report"]["ok"])

        renamed = self.call("rename", {"name": "شغل", "new_name": "شغل الصبح"})
        self.assertEqual(renamed["layout"]["name"], "شغل الصبح")
        self.assertTrue(self.call("delete", {"name": "شغل الصبح"})["ok"])

    def test_goodbye_arms_shutdown_and_the_next_request_disarms_it(self):
        self.assertTrue(self.call("bye", {})["ok"])
        self.assertIsNotNone(self.state.goodbye)
        self.call("ping")
        self.assertIsNone(self.state.goodbye)

    def test_restoring_an_unknown_layout_is_a_clean_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.call("restore", {"name": "مش موجود"})
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
