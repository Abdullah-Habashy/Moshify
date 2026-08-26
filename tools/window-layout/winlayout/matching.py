"""Match saved windows against the windows that are open right now.

Titles change all the time (a document name, an unread counter), so the
scoring leans on the executable and the window class first and treats the
title as a tie-breaker.
"""
from __future__ import annotations

import os
import re
from typing import Iterable, Optional, Sequence

from .model import WindowInfo

# A live window scoring below this is never considered the same window.
MIN_SCORE = 30

_NOISE = re.compile(r"[‎‏‪-‮]")
_COUNTER = re.compile(r"^\s*[(\[]\d+[)\]]\s*")
_SEPARATORS = re.compile(r"\s*[-–—|·:]\s*")


def normalize_title(title: str) -> str:
    title = _NOISE.sub("", title or "").strip().lower()
    title = _COUNTER.sub("", title)          # "(3) WhatsApp" -> "whatsapp"
    title = title.lstrip("*● ").strip()      # unsaved-changes markers
    return re.sub(r"\s+", " ", title)


def title_tokens(title: str) -> list[str]:
    return [t for t in _SEPARATORS.split(normalize_title(title)) if t]


def same_exe(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    return os.path.basename(a).lower() == os.path.basename(b).lower()


def title_score(saved: str, live: str) -> int:
    """0..40 — how confidently two titles name the same window."""
    a, b = normalize_title(saved), normalize_title(live)
    if not a or not b:
        return 0
    if a == b:
        return 40
    if a in b or b in a:
        return 26
    ta, tb = title_tokens(saved), title_tokens(live)
    if not ta or not tb:
        return 0
    # Apps put the product name last: "file - Visual Studio Code".
    if ta[-1] and ta[-1] == tb[-1]:
        return 20
    shared = len(set(ta) & set(tb))
    if shared:
        return min(16, 8 * shared)
    return 0


def score(saved: WindowInfo, live: WindowInfo) -> Optional[int]:
    """Score a candidate, or ``None`` when the two cannot be the same window."""
    if saved.exe_name and live.exe_name and not same_exe(saved.exe_name, live.exe_name):
        return None
    if saved.aumid and live.aumid and saved.aumid != live.aumid:
        return None

    total = 0
    if same_exe(saved.exe_name, live.exe_name):
        total += 30
    if saved.cls and live.cls:
        if saved.cls == live.cls:
            total += 25
        elif not saved.exe_name or not live.exe_name:
            return None  # nothing left to identify it with
    if saved.aumid and saved.aumid == live.aumid:
        total += 20

    title = title_score(saved.title, live.title)
    if saved.match_title and title == 0 and saved.title and live.title:
        # Same app, clearly different document: still usable, but ranked low.
        total -= 6
    total += title

    if saved.monitor and saved.monitor == live.monitor:
        total += 3
    if saved.state == live.state:
        total += 2

    # Windows that already sit near the saved spot are likelier to be the one.
    dx = abs(saved.placement_rect.cx - live.placement_rect.cx)
    dy = abs(saved.placement_rect.cy - live.placement_rect.cy)
    if dx + dy < 200:
        total += 4
    elif dx + dy < 800:
        total += 2

    return total


def assign(saved: Sequence[WindowInfo], live: Sequence[WindowInfo]) -> dict[str, WindowInfo]:
    """Greedy one-to-one assignment, best pairs first.

    Greedy is the right shape here: candidate sets are tiny (a handful of
    windows per app) and a globally optimal assignment would not change the
    outcome in any realistic layout.
    """
    pairs = []
    for s_index, spec in enumerate(saved):
        for l_index, win in enumerate(live):
            value = score(spec, win)
            if value is not None and value >= MIN_SCORE:
                pairs.append((value, -abs(spec.z - win.z), s_index, l_index))
    pairs.sort(reverse=True)

    taken_saved: set[int] = set()
    taken_live: set[int] = set()
    result: dict[str, WindowInfo] = {}
    for _value, _z, s_index, l_index in pairs:
        if s_index in taken_saved or l_index in taken_live:
            continue
        taken_saved.add(s_index)
        taken_live.add(l_index)
        result[saved[s_index].id] = live[l_index]
    return result


def unmatched(saved: Sequence[WindowInfo], matches: dict[str, WindowInfo]) -> list[WindowInfo]:
    return [s for s in saved if s.id not in matches]


def group_for_launch(specs: Iterable[WindowInfo]) -> list[tuple[str, list[WindowInfo]]]:
    """Group windows that still need launching by the app that owns them."""
    groups: dict[str, list[WindowInfo]] = {}
    for spec in specs:
        if not spec.launch:
            continue
        key = (spec.aumid or spec.exe or spec.exe_name or spec.cls or "").lower()
        if not key:
            continue
        groups.setdefault(key, []).append(spec)
    return list(groups.items())
