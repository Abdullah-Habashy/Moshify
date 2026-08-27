"""Data model shared by the capture engine, the store and the UI.

Nothing here touches the Windows API, so it can be imported (and tested)
on any platform.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

SCHEMA_VERSION = 1

STATE_NORMAL = "normal"
STATE_MAXIMIZED = "maximized"
STATE_MINIMIZED = "minimized"
STATES = (STATE_NORMAL, STATE_MAXIMIZED, STATE_MINIMIZED)


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def cx(self) -> int:
        return (self.left + self.right) // 2

    @property
    def cy(self) -> int:
        return (self.top + self.bottom) // 2

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    def as_list(self) -> list[int]:
        return [self.left, self.top, self.right, self.bottom]

    def moved_to(self, left: int, top: int) -> "Rect":
        return Rect(left, top, left + self.width, top + self.height)

    def resized(self, width: int, height: int) -> "Rect":
        return Rect(self.left, self.top, self.left + width, self.top + height)

    def offset(self, dx: int, dy: int) -> "Rect":
        return Rect(self.left + dx, self.top + dy, self.right + dx, self.bottom + dy)

    @staticmethod
    def from_any(value: Any) -> "Rect":
        if isinstance(value, Rect):
            return value
        if isinstance(value, dict):
            return Rect(int(value["left"]), int(value["top"]),
                        int(value["right"]), int(value["bottom"]))
        left, top, right, bottom = (int(v) for v in value)
        return Rect(left, top, right, bottom)

    @staticmethod
    def from_size(left: int, top: int, width: int, height: int) -> "Rect":
        return Rect(left, top, left + width, top + height)


@dataclass
class MonitorInfo:
    """One physical display, in virtual-screen coordinates."""

    device: str
    rect: Rect
    work: Rect
    primary: bool = False
    dpi: int = 96
    index: int = 0

    def to_dict(self) -> dict:
        return {
            "device": self.device,
            "rect": self.rect.as_list(),
            "work": self.work.as_list(),
            "primary": self.primary,
            "dpi": self.dpi,
            "index": self.index,
        }

    @staticmethod
    def from_dict(data: dict) -> "MonitorInfo":
        return MonitorInfo(
            device=data.get("device", ""),
            rect=Rect.from_any(data["rect"]),
            work=Rect.from_any(data.get("work", data["rect"])),
            primary=bool(data.get("primary", False)),
            dpi=int(data.get("dpi", 96)),
            index=int(data.get("index", 0)),
        )


@dataclass
class WindowInfo:
    """A top level window.

    The same shape is used for a window read off the live desktop and for a
    window stored inside a layout; ``hwnd``/``pid`` are only meaningful for
    the live case and are never written to disk.
    """

    title: str = ""
    cls: str = ""
    exe: Optional[str] = None
    exe_name: Optional[str] = None
    aumid: Optional[str] = None
    cmdline: Optional[str] = None
    rect: Rect = field(default_factory=lambda: Rect(0, 0, 0, 0))
    normal_rect: Optional[Rect] = None
    state: str = STATE_NORMAL
    topmost: bool = False
    monitor: Optional[str] = None
    z: int = 0
    focused: bool = False
    # saved-only fields
    id: str = ""
    launch: bool = True
    match_title: bool = True
    # live-only fields
    hwnd: int = 0
    pid: int = 0

    @property
    def placement_rect(self) -> Rect:
        """Restored (un-maximized) geometry, which is what we replay."""
        return self.normal_rect or self.rect

    @property
    def app(self) -> str:
        return self.exe_name or self.cls or "?"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "cls": self.cls,
            "exe": self.exe,
            "exe_name": self.exe_name,
            "aumid": self.aumid,
            "cmdline": self.cmdline,
            "rect": self.rect.as_list(),
            "normal_rect": (self.normal_rect or self.rect).as_list(),
            "state": self.state,
            "topmost": self.topmost,
            "monitor": self.monitor,
            "z": self.z,
            "focused": self.focused,
            "launch": self.launch,
            "match_title": self.match_title,
        }

    @staticmethod
    def from_dict(data: dict) -> "WindowInfo":
        rect = Rect.from_any(data.get("rect", [0, 0, 0, 0]))
        normal = data.get("normal_rect")
        state = data.get("state", STATE_NORMAL)
        return WindowInfo(
            id=data.get("id", ""),
            title=data.get("title", ""),
            cls=data.get("cls", ""),
            exe=data.get("exe"),
            exe_name=data.get("exe_name"),
            aumid=data.get("aumid"),
            cmdline=data.get("cmdline"),
            rect=rect,
            normal_rect=Rect.from_any(normal) if normal else rect,
            state=state if state in STATES else STATE_NORMAL,
            topmost=bool(data.get("topmost", False)),
            monitor=data.get("monitor"),
            z=int(data.get("z", 0)),
            focused=bool(data.get("focused", False)),
            launch=bool(data.get("launch", True)),
            match_title=bool(data.get("match_title", True)),
        )

    def describe(self) -> str:
        title = self.title.strip() or "(بدون عنوان)"
        return f"{self.app} — {title}"


@dataclass
class Layout:
    name: str
    windows: list[WindowInfo] = field(default_factory=list)
    monitors: list[MonitorInfo] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    launch_missing: bool = True
    launch_timeout: float = 30.0
    restore_focus: bool = True
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "launch_missing": self.launch_missing,
            "launch_timeout": self.launch_timeout,
            "restore_focus": self.restore_focus,
            "monitors": [m.to_dict() for m in self.monitors],
            "windows": [w.to_dict() for w in self.windows],
        }

    @staticmethod
    def from_dict(data: dict) -> "Layout":
        return Layout(
            name=data.get("name", ""),
            windows=[WindowInfo.from_dict(w) for w in data.get("windows", [])],
            monitors=[MonitorInfo.from_dict(m) for m in data.get("monitors", [])],
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            launch_missing=bool(data.get("launch_missing", True)),
            launch_timeout=float(data.get("launch_timeout", 30.0)),
            restore_focus=bool(data.get("restore_focus", True)),
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )


_SLUG_STRIP = re.compile(r"[^\w؀-ۿ -]+", re.UNICODE)
_SLUG_SPACE = re.compile(r"[\s-]+", re.UNICODE)


def slugify(text: str, fallback: str = "layout") -> str:
    """File-system safe name that still keeps Arabic letters readable."""
    text = unicodedata.normalize("NFKC", text or "").strip()
    text = _SLUG_STRIP.sub("", text)
    text = _SLUG_SPACE.sub("-", text).strip("-")
    text = text[:60]
    return text or fallback


def assign_ids(windows: Iterable[WindowInfo]) -> list[WindowInfo]:
    """Give every window a stable id, unique inside its layout."""
    used: set[str] = set()
    out: list[WindowInfo] = []
    for win in windows:
        base = slugify(f"{win.app}-{win.cls}", fallback="win").lower() or "win"
        candidate, n = base, 1
        while candidate in used:
            n += 1
            candidate = f"{base}-{n}"
        used.add(candidate)
        win.id = candidate
        out.append(win)
    return out
