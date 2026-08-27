"""Single entry point for the packaged app.

``WindowLayout.exe`` with no arguments opens the window; with arguments it
behaves as the command line, which is what the desktop shortcuts use.
"""
from __future__ import annotations

import sys


def attach_console() -> None:
    """A windowed .exe has no stdout. When it was started from an open CMD,
    borrow that console so command line output is actually visible."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        if not kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
            return
        kernel32.SetConsoleOutputCP(65001)
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    except Exception:
        pass


def main() -> int:
    if len(sys.argv) > 1:
        attach_console()
        from .cli import main as cli_main
        return cli_main()
    from .ui.desktop import run
    return run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
