"""Console entry point (winlayout-cli.exe).

Same code as WindowLayout, but always the command line: a windowed exe hands
control straight back to the shell without an exit code, which makes it
useless in a script or for troubleshooting.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from winlayout.cli import main

if __name__ == "__main__":
    sys.exit(main())
