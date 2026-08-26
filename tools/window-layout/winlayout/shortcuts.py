"""Desktop shortcuts: the actual "one click" part of the app.

Each shortcut runs ``pythonw.exe winlayout restore <name>`` with no console
window, so it can be double clicked or pinned to the taskbar.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .model import slugify


def pythonw() -> str:
    """The windowed interpreter next to the current one, if there is one."""
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    if candidate.exists():
        return str(candidate)
    return str(exe)


def package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def desktop_dir() -> Path:
    profile = os.environ.get("USERPROFILE") or str(Path.home())
    for name in ("Desktop", "سطح المكتب"):
        candidate = Path(profile) / name
        if candidate.is_dir():
            return candidate
    return Path(profile)


def _default_icon() -> str:
    system_root = os.environ.get("SystemRoot") or "C:\\Windows"
    return os.path.join(system_root, "System32", "imageres.dll") + ",110"


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def create_shortcut(layout_name: str, directory: Optional[Path] = None) -> Path:
    """Write ``<layout>.lnk`` on the desktop. Falls back to a .cmd file when
    PowerShell is unavailable."""
    directory = Path(directory) if directory else desktop_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{slugify(layout_name)}.lnk"
    root = package_root()
    arguments = f'"{root / "winlayout-cli.py"}" restore "{layout_name}"'

    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut({path});"
        "$s.TargetPath = {exe};"
        "$s.Arguments = {args};"
        "$s.WorkingDirectory = {cwd};"
        "$s.IconLocation = {icon};"
        "$s.Description = {desc};"
        "$s.Save()"
    ).format(
        path=_ps_quote(target),
        exe=_ps_quote(pythonw()),
        args=_ps_quote(arguments),
        cwd=_ps_quote(root),
        icon=_ps_quote(_default_icon()),
        desc=_ps_quote(f"WindowLayout — {layout_name}"),
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0 and target.exists():
            return target
    except (OSError, subprocess.SubprocessError):
        pass
    return _create_cmd(layout_name, directory)


def _create_cmd(layout_name: str, directory: Path) -> Path:
    target = directory / f"{slugify(layout_name)}.cmd"
    root = package_root()
    target.write_text(
        "@echo off\r\n"
        f'start "" "{pythonw()}" "{root / "winlayout-cli.py"}" restore "{layout_name}"\r\n',
        encoding="utf-8-sig",
    )
    return target
