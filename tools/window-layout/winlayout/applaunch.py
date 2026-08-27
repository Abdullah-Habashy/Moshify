"""Finding an app again when its recorded path is gone.

Two things break a stored executable path: apps that live in a versioned
folder and move on every update (Discord, Slack, Teams), and apps the user
reinstalled somewhere else. Pure path logic, so it is testable off Windows.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional, Sequence

_DIGITS = re.compile(r"(\d+)")
_VERSION_SUFFIX = re.compile(r"^(.*?)[-_. ]*[\d][\d.]*$")


def version_key(name: str) -> tuple:
    """Sort 'app-1.0.10' above 'app-1.0.9', which a plain string sort gets wrong."""
    return tuple((1, int(part), "") if part.isdigit() else (0, 0, part.lower())
                 for part in _DIGITS.split(name) if part)


def folder_prefix(name: str) -> str:
    """'app-1.0.9040' -> 'app'. Left alone when there is no version suffix."""
    match = _VERSION_SUFFIX.match(name)
    return match.group(1) if match and match.group(1) else name


def versioned_siblings(exe: Path) -> list[Path]:
    """Same executable under a newer sibling of its versioned folder."""
    parent = exe.parent
    grandparent = parent.parent
    if not grandparent.is_dir():
        return []
    prefix = folder_prefix(parent.name).lower()
    if not prefix:
        return []
    found = []
    try:
        for directory in grandparent.iterdir():
            if not directory.is_dir() or directory == parent:
                continue
            if not directory.name.lower().startswith(prefix):
                continue
            candidate = directory / exe.name
            if candidate.exists():
                found.append(candidate)
    except OSError:
        return []
    return sorted(found, key=lambda path: version_key(path.parent.name), reverse=True)


def _shortcut_matches(shortcut_stem: str, exe_stem: str) -> bool:
    left = re.sub(r"[\s_-]+", "", shortcut_stem).lower()
    right = re.sub(r"[\s_-]+", "", exe_stem).lower()
    return left == right


def start_menu_shortcut(exe_name: str, roots: Iterable[Path]) -> Optional[Path]:
    """A .lnk named after the app -- the Start menu entry the user would click."""
    exe_stem = Path(exe_name).stem
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        try:
            for shortcut in root.rglob("*.lnk"):
                if _shortcut_matches(shortcut.stem, exe_stem):
                    return shortcut
        except OSError:
            continue
    return None


def resolve(exe: Optional[str], start_menu_roots: Sequence[Path] = ()) -> Optional[Path]:
    """Where to actually launch from, or None when the app cannot be found."""
    if not exe:
        return None
    path = Path(exe)
    if path.exists():
        return path
    newer = versioned_siblings(path)
    if newer:
        return newer[0]
    return start_menu_shortcut(path.name, start_menu_roots)
