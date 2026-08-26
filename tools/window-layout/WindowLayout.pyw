"""Double-click entry point: opens the WindowLayout UI in the default browser.

Uses the .pyw extension so Windows runs it with pythonw.exe (no console).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from winlayout.ui.server import serve

if __name__ == "__main__":
    serve(open_browser=True)
