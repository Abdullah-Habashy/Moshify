"""Pure geometry helpers: monitor lookup, clamping and layout remapping.

Used when the screen setup at restore time differs from the setup that was
captured (a monitor unplugged, a different resolution, a laptop docked).
"""
from __future__ import annotations

from typing import Optional, Sequence

from .model import MonitorInfo, Rect

MIN_VISIBLE = 80  # px of a window that must stay reachable on screen


def intersect_area(a: Rect, b: Rect) -> int:
    left = max(a.left, b.left)
    top = max(a.top, b.top)
    right = min(a.right, b.right)
    bottom = min(a.bottom, b.bottom)
    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)


def monitor_for_rect(rect: Rect, monitors: Sequence[MonitorInfo]) -> Optional[MonitorInfo]:
    """The monitor holding most of ``rect`` (falling back to the nearest one)."""
    if not monitors:
        return None
    best, best_area = None, 0
    for mon in monitors:
        area = intersect_area(rect, mon.rect)
        if area > best_area:
            best, best_area = mon, area
    if best is not None:
        return best
    # No overlap at all: pick the monitor whose centre is closest.
    return min(
        monitors,
        key=lambda m: (m.rect.cx - rect.cx) ** 2 + (m.rect.cy - rect.cy) ** 2,
    )


def primary_monitor(monitors: Sequence[MonitorInfo]) -> Optional[MonitorInfo]:
    for mon in monitors:
        if mon.primary:
            return mon
    return monitors[0] if monitors else None


def find_monitor(monitors: Sequence[MonitorInfo], device: Optional[str],
                 index: Optional[int] = None) -> Optional[MonitorInfo]:
    """Look a saved monitor up in a live monitor list: device name, then index."""
    if device:
        for mon in monitors:
            if mon.device == device:
                return mon
    if index is not None:
        for mon in monitors:
            if mon.index == index:
                return mon
    return None


def signature(monitors: Sequence[MonitorInfo]) -> str:
    """Compact description of a screen setup, for change detection."""
    parts = [
        f"{m.device}:{m.rect.left},{m.rect.top},{m.rect.width}x{m.rect.height}"
        for m in sorted(monitors, key=lambda m: (m.rect.left, m.rect.top))
    ]
    return "|".join(parts)


def clamp_to_monitor(rect: Rect, mon: MonitorInfo) -> Rect:
    """Shrink/move ``rect`` so it fits inside a monitor's work area."""
    work = mon.work
    width = min(rect.width, work.width)
    height = min(rect.height, work.height)
    left = min(max(rect.left, work.left), work.right - width)
    top = min(max(rect.top, work.top), work.bottom - height)
    return Rect.from_size(left, top, width, height)


def keep_on_screen(rect: Rect, monitors: Sequence[MonitorInfo]) -> Rect:
    """Nudge a window back until a usable part of it is visible somewhere."""
    if not monitors:
        return rect
    for mon in monitors:
        if intersect_area(rect, mon.work) >= MIN_VISIBLE * MIN_VISIBLE:
            return rect
    mon = monitor_for_rect(rect, monitors) or primary_monitor(monitors)
    return clamp_to_monitor(rect, mon) if mon else rect


def scale_within(rect: Rect, src: MonitorInfo, dst: MonitorInfo) -> Rect:
    """Map a rect from one monitor to another, keeping relative position/size."""
    if src.rect.width <= 0 or src.rect.height <= 0:
        return rect
    fx = dst.work.width / src.work.width if src.work.width else 1.0
    fy = dst.work.height / src.work.height if src.work.height else 1.0
    left = dst.work.left + round((rect.left - src.work.left) * fx)
    top = dst.work.top + round((rect.top - src.work.top) * fy)
    width = max(120, round(rect.width * fx))
    height = max(60, round(rect.height * fy))
    return clamp_to_monitor(Rect.from_size(left, top, width, height), dst)


def remap_rect(rect: Rect, saved_monitor: Optional[MonitorInfo],
               saved_monitors: Sequence[MonitorInfo],
               live_monitors: Sequence[MonitorInfo]) -> tuple[Rect, Optional[str]]:
    """Translate a saved rect into the current screen setup.

    Returns the rect plus an optional Arabic note describing any adjustment.
    """
    if not live_monitors:
        return rect, None

    src = saved_monitor or monitor_for_rect(rect, saved_monitors)
    if src is None:
        return keep_on_screen(rect, live_monitors), None

    exact = find_monitor(live_monitors, src.device)
    if exact is not None and exact.rect == src.rect and exact.work == src.work:
        return rect, None  # same screen, same geometry: replay as captured

    target = exact or find_monitor(live_monitors, None, src.index)
    if target is None:
        target = primary_monitor(live_monitors)
        note = f"الشاشة {src.device or src.index} مش موجودة — اتنقلت للشاشة الأساسية"
    else:
        note = f"مقاس الشاشة {target.device or target.index} اتغيّر — الأبعاد اتظبطت"
    if target is None:
        return keep_on_screen(rect, live_monitors), None
    return scale_within(rect, src, target), note
