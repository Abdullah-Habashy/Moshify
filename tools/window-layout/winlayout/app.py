"""Single entry point for the packaged app.

``WindowLayout.exe`` with no arguments opens the window; with arguments it
behaves as the command line, which is what the desktop shortcuts use.
"""
from __future__ import annotations

import sys


def prepare_console() -> None:
    """Make Arabic output survive the console the app was started from.

    A windowed .exe has no console of its own, and it lands in one of three
    situations: started from an open CMD (borrow that console), started with
    its output piped somewhere (a stream exists already, but with the legacy
    code page), or double-clicked (no stream at all -- print then no-ops).
    Only the first needs AttachConsole; all of them need UTF-8.
    """
    if sys.platform == "win32" and sys.stdout is None and getattr(sys, "frozen", False):
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # None, or a stream that cannot be reconfigured


def main() -> int:
    if len(sys.argv) > 1:
        prepare_console()
        from .cli import main as cli_main
        return cli_main()
    from .ui.desktop import run
    return run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
