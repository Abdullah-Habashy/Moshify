"""A log file and a message box, because a windowed .exe has nowhere to print.

Without these, every startup failure looks identical to the user: a window
that opens onto nothing.
"""
from __future__ import annotations

import datetime
import sys
import traceback
from pathlib import Path

from .store import home_dir

MAX_BYTES = 512 * 1024
MB_ICONERROR = 0x10


def log_path() -> Path:
    return home_dir() / "log.txt"


def log(message: str) -> None:
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_BYTES:
            path.unlink()
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp}  {message}\n")
    except OSError:
        pass  # a log that cannot be written must never break the app


def log_exception(context: str) -> None:
    log(f"{context}\n{traceback.format_exc().rstrip()}")


def alert(title: str, message: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, title, MB_ICONERROR)
    except Exception:
        print(f"{title}: {message}", file=sys.stderr)
