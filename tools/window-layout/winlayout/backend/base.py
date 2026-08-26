"""The small surface the engine needs from an operating system."""
from __future__ import annotations

from typing import Optional, Protocol

from ..model import MonitorInfo, Rect, WindowInfo


class Backend(Protocol):
    name: str

    def monitors(self) -> list[MonitorInfo]:
        """Displays in virtual-screen coordinates, primary first."""

    def windows(self, with_cmdlines: bool = True) -> list[WindowInfo]:
        """Visible top level windows, front-most first (``z`` = 0 is on top).

        ``with_cmdlines`` is only worth paying for at capture time.
        """

    def apply(self, win: WindowInfo, rect: Rect, state: str, topmost: bool) -> Optional[str]:
        """Move/resize one window. Returns an error message, or None on success."""

    def focus(self, win: WindowInfo) -> None:
        """Bring a window to the foreground (best effort)."""

    def raise_window(self, win: WindowInfo) -> None:
        """Put a window on top of the z-order without activating it."""

    def launch(self, spec: WindowInfo) -> Optional[str]:
        """Start the app that owns ``spec``. Returns an error message or None."""

    def is_alive(self, win: WindowInfo) -> bool:
        """Whether a previously returned window still exists."""


def get_backend(name: Optional[str] = None) -> Backend:
    import os
    import sys

    name = name or os.environ.get("WINLAYOUT_BACKEND")
    if name == "fake" or (name is None and os.environ.get("WINLAYOUT_FAKE")):
        from .fake_backend import FakeBackend
        return FakeBackend()
    if name == "win" or sys.platform == "win32":
        from .win_backend import WindowsBackend
        return WindowsBackend()
    raise RuntimeError(
        "البرنامج ده بيشتغل على ويندوز بس. "
        "للتجربة على نظام تاني شغّل بـ WINLAYOUT_FAKE=1."
    )
