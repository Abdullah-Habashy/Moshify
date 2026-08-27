"""Open the UI as a real desktop window instead of a browser tab.

Every Windows 10/11 machine ships Edge, and Chromium's ``--app=`` mode gives
a plain window with no tabs, no address bar and our own icon -- a native
looking window without adding a GUI toolkit (and without Tk, which cannot
shape Arabic).

The server's lifetime deliberately does *not* hang on that browser process:
Chromium frequently relaunches itself, and the launcher we started can exit
within a second while the window it opened stays up. The page's own heartbeat
is the authority; the process exit and the goodbye beacon only let us stop
sooner.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional

from .. import diag
from ..store import home_dir
from .server import (IDLE_TIMEOUT, claim_instance, create_server,
                     release_instance, _existing_instance)

WINDOW_SIZE = "1240,900"
STARTUP_GRACE = 60.0   # give a cold browser time to open and start pinging
ORPHAN_GRACE = 45.0    # window process gone and the page has stopped pinging
BYE_GRACE = 4.0        # the page said goodbye; a reload would have pinged by now

BROWSER_CANDIDATES = (
    r"Microsoft\Edge\Application\msedge.exe",
    r"Google\Chrome\Application\chrome.exe",
    r"BraveSoftware\Brave-Browser\Application\brave.exe",
    r"Chromium\Application\chrome.exe",
)


def find_browser() -> Optional[str]:
    roots = [os.environ.get(name) for name in
             ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
    for root in roots:
        if not root:
            continue
        for relative in BROWSER_CANDIDATES:
            candidate = Path(root) / relative
            if candidate.exists():
                return str(candidate)
    return None


def open_window(browser: str, url: str) -> Optional[subprocess.Popen]:
    """Launch the app window. The returned process is a hint, not a leash."""
    profile = home_dir() / "window-profile"
    profile.mkdir(parents=True, exist_ok=True)
    command = [
        browser,
        f"--app={url}",
        f"--user-data-dir={profile}",
        f"--window-size={WINDOW_SIZE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-extensions",
        "--disable-sync",
    ]
    try:
        return subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        diag.log_exception("could not start the browser window")
        return None


def wait_until_ready(url: str, token: str, timeout: float = 8.0) -> bool:
    """Do not open a window onto a server that is not answering yet."""
    port = url.split("//", 1)[1].split("/", 1)[0]
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    f"http://{port}/api/ping?t={token}", timeout=1.5) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def should_stop(now: float, started_at: float, last_seen: float,
                goodbye: Optional[float], jobs_busy: bool, process_alive: bool,
                idle_timeout: float = IDLE_TIMEOUT) -> bool:
    """Whether to stop serving. Pure, so the decision is testable."""
    if jobs_busy:
        return False  # never cut a restore short
    if goodbye is not None and now - goodbye >= BYE_GRACE:
        return True   # the page closed for good; a reload clears goodbye
    if now - started_at < STARTUP_GRACE:
        return False
    if not process_alive and now - last_seen >= ORPHAN_GRACE:
        return True
    return now - last_seen >= idle_timeout


def run(port: int = 0) -> int:
    try:
        return _run(port)
    except Exception:
        diag.log_exception("startup failed")
        diag.alert("WindowLayout",
                   "البرنامج مقدرش يشتغل.\n\nالتفاصيل في:\n" + str(diag.log_path()))
        return 1


def _run(port: int) -> int:
    diag.log(f"start: python={sys.version.split()[0]} "
             f"frozen={bool(getattr(sys, 'frozen', False))}")
    running = _existing_instance()
    browser = find_browser() if sys.platform == "win32" else None
    diag.log(f"browser={browser or 'none'} already-running={bool(running)}")

    if running:
        if not (browser and open_window(browser, running)):
            webbrowser.open(running)
        return 0

    server, state, url = create_server(port)
    claim_instance(server, state)
    threading.Thread(target=server.serve_forever, daemon=True, name="ui-server").start()
    try:
        if not wait_until_ready(url, state.token):
            diag.log("the server never answered its own ping")
            diag.alert("WindowLayout",
                       "السيرفر المحلي مردّش.\n\nالتفاصيل في:\n" + str(diag.log_path()))
            return 1
        diag.log(f"serving on port {server.server_address[1]}")

        process = open_window(browser, url) if browser else None
        if process is None:
            diag.log("no app window available; using the default browser")
            webbrowser.open(url)

        started = time.time()
        while True:
            time.sleep(1)
            alive = process is not None and process.poll() is None
            if should_stop(time.time(), started, state.last_seen, state.goodbye,
                           state.jobs.busy(), alive):
                break
        diag.log("window closed; shutting down")
        server.shutdown()
        return 0
    except KeyboardInterrupt:  # pragma: no cover
        server.shutdown()
        return 130
    finally:
        release_instance(server)
