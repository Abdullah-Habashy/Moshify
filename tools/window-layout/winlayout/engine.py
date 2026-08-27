"""Capture and restore, on top of whatever backend is in use."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from . import arabic, geometry, matching
from .model import (Layout, MonitorInfo, Rect, STATE_MINIMIZED, STATE_NORMAL,
                    WindowInfo, assign_ids)

Progress = Callable[[str], None]

LAUNCH_STAGGER = 1.2     # seconds between two windows of the same app
POLL_INTERVAL = 0.5      # how often to look for windows that just opened
MIN_LAUNCH_WAIT = 3.0    # never give an app less than this to show a window

STATUS_MOVED = "moved"
STATUS_LAUNCHED = "launched"
STATUS_MISSING = "missing"
STATUS_FAILED = "failed"

STATUS_LABEL = {
    STATUS_MOVED: "اتظبطت",
    STATUS_LAUNCHED: "اتفتحت واتظبطت",
    STATUS_MISSING: "مش موجودة",
    STATUS_FAILED: "فشلت",
}


@dataclass
class WindowResult:
    id: str
    app: str
    title: str
    status: str
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "app": self.app, "title": self.title,
            "status": self.status, "label": STATUS_LABEL.get(self.status, self.status),
            "message": self.message,
        }


@dataclass
class RestoreReport:
    layout: str
    results: list[WindowResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0

    def count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)

    @property
    def ok(self) -> bool:
        return not any(r.status in (STATUS_FAILED, STATUS_MISSING) for r in self.results)

    def summary(self) -> str:
        moved = self.count(STATUS_MOVED) + self.count(STATUS_LAUNCHED)
        parts = [f"{arabic.windows(moved)} اتظبطت"]
        if self.count(STATUS_LAUNCHED):
            parts.append(f"منهم {arabic.windows(self.count(STATUS_LAUNCHED))} اتفتحت من جديد")
        if self.count(STATUS_MISSING):
            parts.append(f"{arabic.windows(self.count(STATUS_MISSING))} مش لاقيينها")
        if self.count(STATUS_FAILED):
            parts.append(f"{arabic.windows(self.count(STATUS_FAILED))} فشلت")
        return "، ".join(parts)

    def to_dict(self) -> dict:
        return {
            "layout": self.layout,
            "seconds": round(self.seconds, 1),
            "summary": self.summary(),
            "ok": self.ok,
            "warnings": self.warnings,
            "results": [r.to_dict() for r in self.results],
        }


class Engine:
    def __init__(self, backend=None):
        if backend is None:
            from .backend import get_backend
            backend = get_backend()
        self.backend = backend

    # -- capture --------------------------------------------------------------
    def snapshot(self) -> tuple[list[MonitorInfo], list[WindowInfo]]:
        return self.backend.monitors(), self.backend.windows()

    def capture(self, name: str, keep: Optional[Sequence[int]] = None,
                windows: Optional[Sequence[WindowInfo]] = None,
                monitors: Optional[Sequence[MonitorInfo]] = None) -> Layout:
        """Build a layout out of the windows that are open right now.

        ``keep`` is a list of hwnds; ``None`` means every capturable window.
        """
        if windows is None:
            windows = self.backend.windows()
        if monitors is None:
            monitors = self.backend.monitors()
        if keep is not None:
            wanted = {int(h) for h in keep}
            windows = [w for w in windows if w.hwnd in wanted]
        chosen = assign_ids([_freeze(w) for w in windows])
        return Layout(name=name, windows=chosen, monitors=list(monitors))

    # -- restore --------------------------------------------------------------
    def restore(self, layout: Layout, progress: Optional[Progress] = None) -> RestoreReport:
        started = time.time()
        say = progress or (lambda _message: None)
        report = RestoreReport(layout=layout.name)

        live_monitors = self.backend.monitors()
        if (geometry.signature(live_monitors) != geometry.signature(layout.monitors)
                and layout.monitors):
            report.warnings.append(
                "شكل الشاشات اتغيّر عن وقت الحفظ — النوافذ هتتظبط على أقرب توزيع ممكن")

        say("بندوّر على النوافذ المفتوحة…")
        live = self.backend.windows(with_cmdlines=False)
        matches = matching.assign(layout.windows, live)
        used = {w.hwnd for w in matches.values()}

        missing = matching.unmatched(layout.windows, matches)
        if missing and layout.launch_missing:
            self._launch_missing(layout, missing, matches, used, say, report)

        say("بنظبّط الأماكن…")
        # Bottom of the z-order first, so the stacking ends up like it was.
        for spec in sorted(layout.windows, key=lambda s: s.z, reverse=True):
            win = matches.get(spec.id)
            if win is None:
                report.results.append(WindowResult(
                    spec.id, spec.app, spec.title, STATUS_MISSING,
                    "مافيش نافذة مطابقة، ومحاولة الفتح مانجحتش"
                    if layout.launch_missing else "مافيش نافذة مطابقة"))
                continue
            report.results.append(self._place(spec, win, layout, live_monitors))

        if layout.restore_focus:
            self._restore_focus(layout, matches)

        report.seconds = time.time() - started
        # Keep the report in the layout's own order, it reads better.
        order = {spec.id: index for index, spec in enumerate(layout.windows)}
        report.results.sort(key=lambda r: order.get(r.id, 0))
        say(report.summary())
        return report

    def _place(self, spec: WindowInfo, win: WindowInfo, layout: Layout,
               live_monitors: Sequence[MonitorInfo]) -> WindowResult:
        target = spec.rect if spec.state == STATE_NORMAL else spec.placement_rect
        saved_monitor = geometry.find_monitor(layout.monitors, spec.monitor)
        rect, note = geometry.remap_rect(target, saved_monitor, layout.monitors, live_monitors)
        rect = geometry.keep_on_screen(rect, live_monitors)

        error = self.backend.apply(win, rect, spec.state, spec.topmost)
        if error:
            return WindowResult(spec.id, spec.app, spec.title, STATUS_FAILED, error)
        if spec.state != STATE_MINIMIZED:
            self.backend.raise_window(win)
        status = STATUS_LAUNCHED if getattr(win, "_launched", False) else STATUS_MOVED
        return WindowResult(spec.id, spec.app, spec.title, status, note or "")

    def _launch_missing(self, layout: Layout, missing: list[WindowInfo],
                        matches: dict[str, WindowInfo], used: set[int],
                        say: Progress, report: RestoreReport) -> None:
        """Start everything that is closed, then wait for the windows together.

        Waiting per app in turn would add up: five slow apps at twenty seconds
        each is a minute and a half of staring at a half-built desktop. Apps
        boot in parallel anyway, so start them all and collect what appears.
        """
        pending: list[WindowInfo] = []
        for _key, specs in matching.group_for_launch(missing):
            for index, spec in enumerate(specs):
                say(f"بنفتح {spec.app}…")
                error = self.backend.launch(spec)
                if error:
                    report.warnings.append(f"{spec.app}: {error}")
                    continue
                pending.append(spec)
                if index + 1 < len(specs):
                    # A second window of the same app: give the first one a
                    # moment, or the app treats both as one launch.
                    time.sleep(LAUNCH_STAGGER)
        if pending:
            self._collect_launched(pending, matches, used, layout.launch_timeout, say)

    def _collect_launched(self, pending: list[WindowInfo],
                          matches: dict[str, WindowInfo], used: set[int],
                          timeout: float, say: Progress) -> None:
        waiting = list(pending)
        deadline = time.time() + max(MIN_LAUNCH_WAIT, timeout)
        while waiting and time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            for win in self.backend.windows(with_cmdlines=False):
                if win.hwnd in used or not waiting:
                    continue
                owners = [spec for spec in waiting if same_app(spec, win)]
                if not owners:
                    continue
                # Two windows of one app: give each to the spec whose title it
                # looks most like, instead of whichever opened first.
                spec = max(owners, key=lambda s: matching.title_score(s.title, win.title))
                setattr(win, "_launched", True)
                matches[spec.id] = win
                used.add(win.hwnd)
                waiting.remove(spec)
        for spec in waiting:
            say(f"{spec.app} ماردّش خلال {int(timeout)} ثانية")

    def _restore_focus(self, layout: Layout, matches: dict[str, WindowInfo]) -> None:
        for spec in layout.windows:
            if spec.focused and spec.state != STATE_MINIMIZED:
                win = matches.get(spec.id)
                if win is not None:
                    self.backend.focus(win)
                return


def same_app(spec: WindowInfo, win: WindowInfo) -> bool:
    """Whether a window that just appeared belongs to the app we started."""
    if spec.aumid and win.aumid:
        return spec.aumid == win.aumid
    return matching.same_exe(spec.exe_name, win.exe_name)


def _freeze(win: WindowInfo) -> WindowInfo:
    """Copy a live window into a storable spec (dropping hwnd/pid)."""
    return WindowInfo(
        title=win.title, cls=win.cls, exe=win.exe, exe_name=win.exe_name,
        aumid=win.aumid, cmdline=win.cmdline,
        rect=win.rect, normal_rect=win.normal_rect or win.rect,
        state=win.state, topmost=win.topmost, monitor=win.monitor,
        z=win.z, focused=win.focused, launch=True, match_title=True,
    )


def layout_bounds(layout: Layout) -> Rect:
    """Bounding box of every monitor in a layout (for the UI preview)."""
    rects = [m.rect for m in layout.monitors] or [w.rect for w in layout.windows]
    if not rects:
        return Rect(0, 0, 1920, 1080)
    return Rect(min(r.left for r in rects), min(r.top for r in rects),
                max(r.right for r in rects), max(r.bottom for r in rects))
