"""Entry point used by the desktop shortcuts and by winlayout.cmd."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from winlayout.cli import main

if __name__ == "__main__":
    sys.exit(main())
