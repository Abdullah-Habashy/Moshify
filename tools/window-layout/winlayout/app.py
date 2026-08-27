"""Single entry point for the packaged app.

``WindowLayout.exe`` with no arguments opens the window; with arguments it
behaves as the command line, which is what the desktop shortcuts use.
"""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from .cli import main as cli_main  # sets the console up itself
        return cli_main()
    from .ui.desktop import run
    return run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
