"""An in-memory desktop, so the engine and the UI can be exercised anywhere.

Enabled with WINLAYOUT_FAKE=1. It is a development aid, never used on a real
machine.
"""
from __future__ import annotations

import itertools
from typing import Optional

from ..model import MonitorInfo, Rect, STATE_NORMAL, WindowInfo

_ids = itertools.count(1000)


def _demo_windows() -> list[WindowInfo]:
    return [
        WindowInfo(title="dashboard.ejs - Visual Studio Code", cls="Chrome_WidgetWin_1",
                   exe=r"C:\Program Files\Microsoft VS Code\Code.exe", exe_name="Code.exe",
                   rect=Rect(0, 0, 1280, 1040), normal_rect=Rect(0, 0, 1280, 1040),
                   monitor=r"\\.\DISPLAY1", hwnd=next(_ids), pid=101),
        WindowInfo(title="طفرة — لوحة الدعم - Google Chrome", cls="Chrome_WidgetWin_1",
                   exe=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                   exe_name="chrome.exe", cmdline=r'"C:\Program Files\Google\Chrome\Application\chrome.exe"',
                   rect=Rect(1280, 0, 2560, 1040), normal_rect=Rect(1280, 0, 2560, 1040),
                   monitor=r"\\.\DISPLAY1", hwnd=next(_ids), pid=102),
        WindowInfo(title="Telegram", cls="Qt5152QWindowIcon",
                   exe=r"C:\Users\me\AppData\Roaming\Telegram Desktop\Telegram.exe",
                   exe_name="Telegram.exe",
                   rect=Rect(2560, 100, 3200, 900), normal_rect=Rect(2560, 100, 3200, 900),
                   monitor=r"\\.\DISPLAY2", hwnd=next(_ids), pid=103),
    ]


class FakeBackend:
    name = "fake"

    def __init__(self) -> None:
        self._monitors = [
            MonitorInfo(device=r"\\.\DISPLAY1", rect=Rect(0, 0, 2560, 1440),
                        work=Rect(0, 0, 2560, 1400), primary=True, dpi=96, index=0),
            MonitorInfo(device=r"\\.\DISPLAY2", rect=Rect(2560, 0, 4480, 1080),
                        work=Rect(2560, 0, 4480, 1040), primary=False, dpi=96, index=1),
        ]
        self._windows = _demo_windows()
        self.applied: list[tuple[str, Rect, str]] = []
        self.launched: list[str] = []
        # test hooks: what a launch does
        self.launch_errors: dict[str, str] = {}   # exe name -> error message
        self.launch_titles: dict[str, list[str]] = {}  # exe name -> titles to hand out
        self.launch_opens_nothing: set[str] = set()

    def monitors(self) -> list[MonitorInfo]:
        return list(self._monitors)

    def windows(self, with_cmdlines: bool = True) -> list[WindowInfo]:
        for index, win in enumerate(self._windows):
            win.z = index
        return list(self._windows)

    def apply(self, win: WindowInfo, rect: Rect, state: str, topmost: bool) -> Optional[str]:
        win.rect = rect
        win.normal_rect = rect
        win.state = state
        win.topmost = topmost
        self.applied.append((win.title, rect, state))
        return None

    def focus(self, win: WindowInfo) -> None:
        for other in self._windows:
            other.focused = other is win

    def raise_window(self, win: WindowInfo) -> None:
        if win in self._windows:
            self._windows.remove(win)
            self._windows.insert(0, win)

    def launch(self, spec: WindowInfo) -> Optional[str]:
        key = spec.exe_name or spec.aumid or spec.cls
        if key in self.launch_errors:
            return self.launch_errors[key]
        self.launched.append(key)
        if key in self.launch_opens_nothing:
            return None
        titles = self.launch_titles.get(key)
        title = titles.pop(0) if titles else spec.title
        clone = WindowInfo(
            title=title, cls=spec.cls, exe=spec.exe, exe_name=spec.exe_name,
            aumid=spec.aumid, rect=Rect(50, 50, 850, 650),
            normal_rect=Rect(50, 50, 850, 650), state=STATE_NORMAL,
            monitor=self._monitors[0].device, hwnd=next(_ids), pid=next(_ids),
        )
        self._windows.append(clone)
        return None

    def is_alive(self, win: WindowInfo) -> bool:
        return any(w.hwnd == win.hwnd for w in self._windows)

    # test helpers
    def close_all(self) -> None:
        self._windows = []

    def close(self, title_part: str) -> None:
        self._windows = [w for w in self._windows if title_part not in w.title]
