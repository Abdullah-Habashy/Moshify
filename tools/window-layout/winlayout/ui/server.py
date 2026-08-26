"""A tiny local web UI.

Rendering Arabic correctly is the reason this is a web page and not a Tk
window: Tk does not shape Arabic glyphs on Windows, every browser does. The
server binds to 127.0.0.1 only, and every request must carry a token that is
generated at start-up, so nothing else on the machine can drive it.
"""
from __future__ import annotations

import json
import mimetypes
import os
import secrets
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from .. import __version__
from ..engine import Engine, layout_bounds
from ..model import Layout
from ..store import LayoutStore, home_dir

STATIC_DIR = Path(__file__).resolve().parent
IDLE_TIMEOUT = 15 * 60  # shut down after the browser tab has been gone a while


class Jobs:
    """Restores run in a thread so the page can show live progress."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, engine: Engine, layout: Layout) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {"done": False, "messages": [], "report": None,
                                  "error": None, "started": time.time()}

        def say(message: str) -> None:
            with self._lock:
                self._jobs[job_id]["messages"].append(message)

        def run() -> None:
            try:
                report = engine.restore(layout, progress=say)
                payload = report.to_dict()
            except Exception as exc:  # pragma: no cover - defensive
                with self._lock:
                    self._jobs[job_id]["error"] = str(exc)
                    self._jobs[job_id]["done"] = True
                return
            with self._lock:
                self._jobs[job_id]["report"] = payload
                self._jobs[job_id]["done"] = True

        threading.Thread(target=run, daemon=True, name=f"restore-{job_id}").start()
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def busy(self) -> bool:
        with self._lock:
            return any(not job["done"] for job in self._jobs.values())


class UIState:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(24)
        self.store = LayoutStore()
        self.jobs = Jobs()
        self.last_seen = time.time()
        self._engine: Optional[Engine] = None
        self._engine_error: Optional[str] = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = Engine()
        return self._engine

    def engine_or_error(self) -> tuple[Optional[Engine], Optional[str]]:
        try:
            return self.engine, None
        except RuntimeError as exc:
            return None, str(exc)


def layout_summary(layout: Layout) -> dict:
    bounds = layout_bounds(layout)
    return {
        "name": layout.name,
        "windows": len(layout.windows),
        "monitors": [m.to_dict() for m in layout.monitors],
        "updated_at": layout.updated_at,
        "launch_missing": layout.launch_missing,
        "bounds": bounds.as_list(),
        "items": [
            {
                "id": w.id, "app": w.app, "title": w.title, "state": w.state,
                "rect": (w.rect if w.state != "minimized" else w.placement_rect).as_list(),
                "monitor": w.monitor, "launch": w.launch,
                "exe": w.exe, "z": w.z,
            }
            for w in layout.windows
        ],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = f"WindowLayout/{__version__}"
    state: UIState

    # -- plumbing -------------------------------------------------------------
    def log_message(self, fmt, *args):  # noqa: A003 - silence console spam
        pass

    def _authorized(self, query: dict) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        token = self.headers.get("X-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(token, self.state.token)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):  # pragma: no cover
            pass

    def _json(self, payload: Any, status: int = 200) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, OSError):
            return {}

    # -- routes ---------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path

        if path in ("/", "/index.html"):
            if not self._authorized(query):
                return self._error("مسموح بالفتح من داخل البرنامج بس", 403)
            html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
            html = html.replace("{{TOKEN}}", self.state.token)
            html = html.replace("{{VERSION}}", __version__)
            self.state.last_seen = time.time()
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

        if path.startswith("/static/"):
            name = os.path.basename(path)
            target = STATIC_DIR / name
            if not target.exists() or name in ("server.py", "index.html"):
                return self._error("مش موجود", 404)
            kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
            if kind.startswith(("text/", "application/javascript")):
                kind += "; charset=utf-8"
            return self._send(200, target.read_bytes(), kind)

        if not path.startswith("/api/"):
            return self._error("مش موجود", 404)
        if not self._authorized(query):
            return self._error("توكن غلط", 403)
        self.state.last_seen = time.time()

        if path == "/api/ping":
            return self._json({"ok": True, "version": __version__})

        if path == "/api/layouts":
            return self._json({
                "layouts": [layout_summary(l) for l in self.state.store.all()],
                "home": str(home_dir()),
            })

        if path == "/api/snapshot":
            engine, error = self.state.engine_or_error()
            if engine is None:
                return self._error(error or "الباك إند مش شغال", 500)
            monitors, windows = engine.snapshot()
            return self._json({
                "monitors": [m.to_dict() for m in monitors],
                "windows": [
                    {"hwnd": w.hwnd, "app": w.app, "title": w.title,
                     "rect": w.rect.as_list(), "state": w.state,
                     "monitor": w.monitor, "exe": w.exe, "focused": w.focused}
                    for w in windows
                ],
            })

        if path == "/api/job":
            job = self.state.jobs.get((query.get("id") or [""])[0])
            if job is None:
                return self._error("المهمة مش موجودة", 404)
            return self._json(job)

        return self._error("مش موجود", 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._authorized(query):
            return self._error("توكن غلط", 403)
        self.state.last_seen = time.time()
        body = self._body()
        path = parsed.path
        store = self.state.store

        if path == "/api/capture":
            name = (body.get("name") or "").strip()
            if not name:
                return self._error("اكتب اسم للتوزيع")
            if store.exists(name) and not body.get("force"):
                return self._error(f"فيه توزيع اسمه «{name}» بالفعل", 409)
            engine, error = self.state.engine_or_error()
            if engine is None:
                return self._error(error or "الباك إند مش شغال", 500)
            hwnds = body.get("hwnds")
            layout = engine.capture(name, keep=hwnds)
            if not layout.windows:
                return self._error("مااخترتش أي نافذة")
            layout.launch_missing = bool(body.get("launch_missing", True))
            store.save(layout)
            return self._json({"layout": layout_summary(layout)})

        if path == "/api/restore":
            layout = store.get((body.get("name") or "").strip())
            if layout is None:
                return self._error("التوزيع مش موجود", 404)
            engine, error = self.state.engine_or_error()
            if engine is None:
                return self._error(error or "الباك إند مش شغال", 500)
            return self._json({"job": self.state.jobs.start(engine, layout)})

        if path == "/api/delete":
            if store.delete((body.get("name") or "").strip()):
                return self._json({"ok": True})
            return self._error("التوزيع مش موجود", 404)

        if path == "/api/rename":
            new_name = (body.get("new_name") or "").strip()
            if not new_name:
                return self._error("اكتب الاسم الجديد")
            if store.exists(new_name):
                return self._error(f"فيه توزيع اسمه «{new_name}» بالفعل", 409)
            layout = store.rename((body.get("name") or "").strip(), new_name)
            if layout is None:
                return self._error("التوزيع مش موجود", 404)
            return self._json({"layout": layout_summary(layout)})

        if path == "/api/options":
            layout = store.get((body.get("name") or "").strip())
            if layout is None:
                return self._error("التوزيع مش موجود", 404)
            if "launch_missing" in body:
                layout.launch_missing = bool(body["launch_missing"])
            if "restore_focus" in body:
                layout.restore_focus = bool(body["restore_focus"])
            store.save(layout)
            return self._json({"layout": layout_summary(layout)})

        if path == "/api/shortcut":
            name = (body.get("name") or "").strip()
            if not store.exists(name):
                return self._error("التوزيع مش موجود", 404)
            try:
                from ..shortcuts import create_shortcut
                path_created = create_shortcut(name)
            except Exception as exc:
                return self._error(f"مانفعش نعمل الاختصار: {exc}", 500)
            return self._json({"path": str(path_created)})

        return self._error("مش موجود", 404)


def _instance_file() -> Path:
    return home_dir() / "ui.json"


def _existing_instance() -> Optional[str]:
    """URL of an instance that is already running, if any."""
    try:
        data = json.loads(_instance_file().read_text(encoding="utf-8"))
        url = f"http://127.0.0.1:{int(data['port'])}/?t={data['token']}"
    except (OSError, ValueError, KeyError):
        return None
    try:
        import urllib.request
        with urllib.request.urlopen(
                f"http://127.0.0.1:{int(data['port'])}/api/ping?t={data['token']}",
                timeout=1.5) as response:
            if response.status == 200:
                return url
    except Exception:
        return None
    return None


def create_server(port: int = 0, state: Optional[UIState] = None):
    """Bound but not yet serving. Split out so tests can drive it."""
    state = state or UIState()
    handler = type("BoundHandler", (Handler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={state.token}"
    return server, state, url


def serve(open_browser: bool = True, port: int = 0) -> None:
    running = _existing_instance()
    if running:
        if open_browser:
            webbrowser.open(running)
        print(f"البرنامج شغال بالفعل: {running}")
        return

    server, state, url = create_server(port)
    actual_port = server.server_address[1]

    home_dir().mkdir(parents=True, exist_ok=True)
    _instance_file().write_text(
        json.dumps({"port": actual_port, "token": state.token, "pid": os.getpid()}),
        encoding="utf-8")

    def watchdog() -> None:
        while True:
            time.sleep(20)
            if state.jobs.busy():
                continue
            if time.time() - state.last_seen > IDLE_TIMEOUT:
                server.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True, name="idle-watchdog").start()
    print(f"WindowLayout شغال على {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.server_close()
        try:
            _instance_file().unlink()
        except OSError:
            pass
