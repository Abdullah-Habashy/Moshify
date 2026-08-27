"""WindowLayout — entry point.

No arguments opens the window; arguments run the command line
(``WindowLayout.exe restore "شغل"``), which is what the shortcuts use.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from winlayout.app import main

if __name__ == "__main__":
    sys.exit(main())
