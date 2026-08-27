"""Open the UI as a real desktop window instead of a browser tab.

Every Windows 10/11 machine ships Edge, and Chromium's ``--app=`` mode gives
a plain window with no tabs, no address bar and our own icon -- a native
looking window without adding a GUI toolkit (and without Tk, which cannot
shape Arabic). Pointing it at a private ``--user-data-dir`` guarantees a
dedicated browser process, so when the user closes the window that process
exits and we can shut the server down with it.

If no Chromium browser is found we fall back to the default browser.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

from ..store import home_dir
from .server import (IDLE_TIMEOUT, claim_instance, create_server,
                     release_instance, _existing_instance)

WINDOW_SIZE = "1240,900"

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
    """Launch the app window. Returns the process to wait on, if we got one."""
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
        return None


def run(port: int = 0) -> int:
    running = _existing_instance()
    browser = find_browser() if sys.platform == "win32" else None

    if running:
        # Another copy already serves the layouts; just show a window on it.
        if not (browser and open_window(browser, running)):
            webbrowser.open(running)
        return 0

    server, state, url = create_server(port)
    claim_instance(server, state)
    threading.Thread(target=server.serve_forever, daemon=True,
                     name="ui-server").start()
    try:
        process = open_window(browser, url) if browser else None
        if process is None:
            # No Chromium around: open the default browser and stay up until
            # the page stops pinging.
            webbrowser.open(url)
            while state.jobs.busy() or time.time() - state.last_seen <= IDLE_TIMEOUT:
                time.sleep(1)
            server.shutdown()
            return 0

        process.wait()  # blocks until the user closes the window
        deadline = time.time() + 120
        while state.jobs.busy() and time.time() < deadline:
            time.sleep(0.5)  # never cut a restore short
        server.shutdown()
        return 0
    except KeyboardInterrupt:  # pragma: no cover
        server.shutdown()
        return 130
    finally:
        release_instance(server)
